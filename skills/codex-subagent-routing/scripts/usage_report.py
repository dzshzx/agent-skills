#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""On-demand accounting of observed Codex rollout responses; no model calls."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    return result


def own_rows(rows):
    meta = next((r["payload"] for r in rows if r.get("type") == "session_meta"), {})
    boundary = meta.get("subagent_history_start_ordinal", 0)
    result = []
    for row in rows:
        if row.get("type") == "session_meta":
            continue
        if boundary:
            if "ordinal" not in row:
                raise ValueError("missing ordinal for inherited-history boundary")
            if row["ordinal"] < boundary:
                continue
        result.append(row)
    return meta, result


def thread_spawn(meta):
    source = meta.get("source")
    subagent = source.get("subagent") if isinstance(source, dict) else None
    # Subagent sources are a tagged union: review/compact may be strings,
    # whereas thread_spawn carries an object with origin and role metadata.
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    return spawn if isinstance(spawn, dict) else {}


def parent_thread_id(meta):
    return meta.get("parent_thread_id") or thread_spawn(meta).get("parent_thread_id")


def load_threads(directories, thread=None):
    threads = {}
    indexed = []
    for directory in directories:
        for path in sorted(Path(directory).rglob("rollout-*.jsonl")):
            with path.open() as stream:
                head = stream.readline()
            if not head.endswith("\n"):
                # Empty, or its writer has not finished the first line yet; the
                # snapshot reader below would drop that line, so skip the file.
                reason = "empty file" if not head else "no complete line"
                print(f"usage report: skipped {path}: {reason}", file=sys.stderr)
                continue
            first = json.loads(head)
            meta = (
                first.get("payload", {}) if first.get("type") == "session_meta" else {}
            )
            indexed.append((path, meta))
    wanted = {thread} if thread else {m.get("id") for _, m in indexed}
    while True:
        children = {m.get("id") for _, m in indexed if parent_thread_id(m) in wanted}
        if children <= wanted:
            break
        wanted.update(children)
    for path, indexed_meta in indexed:
        if indexed_meta.get("id") in wanted:
            # Read snapshots, ignoring only an incomplete last line of active logs.
            content = path.read_text()
            lines = content.split("\n")
            if content and not content.endswith("\n"):
                lines = lines[:-1]
            try:
                rows = [json.loads(line) for line in lines if line.strip()]
            except ValueError as exc:
                raise ValueError(f"invalid rollout {path}: {exc}") from exc
            meta, own = own_rows(rows)
            tid = meta.get("id")
            if not tid:
                raise ValueError(f"missing thread id: {path}")
            group = threads.setdefault(
                tid, {"meta": meta, "rows": [], "files": [], "seen": {}}
            )
            if group["meta"] != meta:
                raise ValueError(f"conflicting metadata for {tid}")
            group["files"].append(str(path))
            for row in own:
                canonical = json.dumps(row, sort_keys=True)
                key = (
                    ("ordinal", row["ordinal"])
                    if "ordinal" in row
                    else ("row", canonical)
                )
                if key in group["seen"] and group["seen"][key] != canonical:
                    raise ValueError(f"conflicting event in {tid}: {key}")
                if key not in group["seen"]:
                    group["seen"][key] = canonical
                    group["rows"].append(row)
    for group in threads.values():
        group["rows"].sort(key=lambda r: (r.get("timestamp", ""), r.get("ordinal", -1)))
    return threads


def price(request, prices):
    if not prices or not request["model"] or not request["service_tier"]:
        return None
    if request["usage"].get("cache_write_input_tokens", 0):
        return None
    rates = [
        r
        for r in prices["rates"]
        if (r["model"], r["service_tier"])
        == (request["model"], request["service_tier"])
    ]
    if len(rates) != 1:
        return None
    rate, usage = rates[0], request["usage"]
    if any(
        usage.get(k) is None
        for k in ("input_tokens", "cached_input_tokens", "output_tokens")
    ):
        return None
    return (
        (usage["input_tokens"] - usage["cached_input_tokens"])
        * rate["input_per_million"]
        + usage["cached_input_tokens"] * rate["cached_input_per_million"]
        + usage["output_tokens"] * rate["output_per_million"]
    ) / 1_000_000


TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")
TURN_STARTED = {"task_started", "turn_started"}
EVENT_STATUS = {
    "task_started": "running",
    "turn_started": "running",
    "task_complete": "completed",
    "turn_completed": "completed",
    "task_failed": "failed_or_aborted",
    "turn_failed": "failed_or_aborted",
    "turn_aborted": "failed_or_aborted",
    "error": "failed_or_aborted",
}
CONTINUATION_TOOLS = {"followup_task", "send_input", "resume_agent"}


def typed_usage_index(tid, rows):
    # Current runtimes persist authoritative per-response records alongside
    # UI token_count snapshots. Match cumulative totals to avoid counting both.
    snapshots, turns = set(), set()
    for item in rows:
        if item.get("type") != "token_usage_record":
            continue
        payload = item.get("payload", {})
        if payload.get("thread_id") != tid:
            raise ValueError(f"foreign token usage inside own boundary of {tid}")
        if payload.get("thread_token_usage"):
            snapshots.add(json.dumps(payload["thread_token_usage"], sort_keys=True))
        turns.add(payload.get("turn_id"))
    return snapshots, turns


def is_token_event(kind, payload):
    return kind == "token_usage_record" or (
        kind == "event_msg" and payload.get("type") == "token_count"
    )


def validate_usage(tid, usage):
    for field in TOKEN_FIELDS:
        if not isinstance(usage.get(field), int) or usage[field] < 0:
            raise ValueError(f"missing or invalid {field} in {tid}")
    if usage["cached_input_tokens"] > usage["input_tokens"]:
        raise ValueError("cached input exceeds total input")


def event_span(moments):
    if not moments:
        return {"elapsed_seconds": None, "first_event": None, "last_event": None}
    first, last = min(moments), max(moments)
    return {
        "elapsed_seconds": (last - first).total_seconds(),
        "first_event": first.isoformat(),
        "last_event": last.isoformat(),
    }


def lineage_gaps(spawn, parent):
    """Lineage fields a subagent thread is expected to record but lacks."""
    gaps = set()
    if not spawn.get("agent_role"):
        gaps.add("agent_role")
    if not parent:
        gaps.add("parent_thread_id")
    return gaps


class ThreadScan:
    """Accumulates one thread's own rows: lifecycle events inside the window,
    and token usage deduplicated across the whole thread."""

    def __init__(self, tid, rows, since, until, prices):
        self.tid, self.since, self.until, self.prices = tid, since, until, prices
        self.typed_snapshots, self.typed_turns = typed_usage_index(tid, rows)
        self.current = {"model": None, "effort": None, "service_tier": None}
        self.current_turn = None
        self.requests, self.seen, self.limits, self.moments = [], {}, [], []
        self.counts = {"turn_starts": 0, "continuation_calls": 0, "compactions": 0}
        self.status = "unknown"
        self.missing = set()

    def in_range(self, when):
        return not (
            (self.since and when < self.since) or (self.until and when >= self.until)
        )

    def scan(self, row):
        p = row.get("payload", {})
        if not isinstance(p, dict):
            return
        kind = row.get("type")
        if kind == "turn_context":
            self.current_turn = p.get("turn_id")
            self.current = {
                "model": p.get("model"),
                "effort": p.get("effort", p.get("reasoning_effort")),
                "service_tier": p.get("service_tier"),
            }
        raw_time = row.get("timestamp")
        if not raw_time:
            self.missing.add("event_timestamp")
            return
        when = timestamp(raw_time)
        in_range = self.in_range(when)
        # Lifecycle events count only inside the window; token events outside
        # it still feed deduplication so a later in-range repeat is not new.
        if in_range:
            self.moments.append(when)
            self.note_event(kind, p)
        if is_token_event(kind, p):
            self.note_tokens(kind, p, raw_time, in_range)

    def note_event(self, kind, p):
        event = p.get("type") if kind == "event_msg" else None
        if event in TURN_STARTED:
            self.counts["turn_starts"] += 1
        self.status = EVENT_STATUS.get(event, self.status)
        if kind == "compacted" or event == "context_compacted":
            self.counts["compactions"] += 1
        if kind == "response_item" and p.get("type") == "function_call":
            if p.get("name", "").split(".")[-1] in CONTINUATION_TOOLS:
                self.counts["continuation_calls"] += 1

    def note_rate_limits(self, raw_time, value):
        if not self.limits or self.limits[-1]["value"] != value:
            self.limits.append({"timestamp": raw_time, "value": value})

    def note_tokens(self, kind, p, raw_time, in_range):
        if in_range and p.get("rate_limits"):
            self.note_rate_limits(raw_time, p["rate_limits"])
        info = p.get("info") or {}
        typed = kind == "token_usage_record"
        if not typed and self.current_turn in self.typed_turns:
            # UI cumulative totals can change meaning after compaction. Native
            # records own accounting for the entire turn, regardless of that
            # display reset; UI-only older turns retain the legacy fallback.
            return
        usage = p.get("usage") if typed else info.get("last_token_usage")
        if not usage:
            return
        if all(usage.get(k) == 0 for k in TOKEN_FIELDS):
            # Compaction/status updates can carry a nonzero context total but
            # zero billed components; they are not another completed response.
            return
        response = p.get("response_id") or info.get("response_id")
        cumulative = (
            p.get("thread_token_usage") if typed else info.get("total_token_usage")
        )
        key = self.response_key(typed, response, cumulative)
        if key is None or self.already_seen(key, usage):
            return
        if in_range:
            self.add_request(raw_time, response, usage, p, info)

    def response_key(self, typed, response, cumulative):
        """Deduplication key for a usage event, or None when it is excluded."""
        if (
            not typed
            and cumulative
            and json.dumps(cumulative, sort_keys=True) in self.typed_snapshots
        ):
            return None
        if response:
            return ("response", response)
        if cumulative:
            self.missing.add("response_id: cumulative snapshot deduplication used")
            return ("cumulative", json.dumps(cumulative, sort_keys=True))
        self.missing.add("response_identity: usage excluded")
        return None

    def already_seen(self, key, usage):
        if key in self.seen:
            if self.seen[key] != usage:
                raise ValueError(f"conflicting response usage in {self.tid}")
            return True
        self.seen[key] = usage
        return False

    def add_request(self, raw_time, response, usage, p, info):
        validate_usage(self.tid, usage)
        request = {
            "timestamp": raw_time,
            "response_id": response,
            **self.current,
            "usage": usage,
        }
        # Only an explicitly logged actual tier is attributed, never today's config.
        request["service_tier"] = (
            p.get("service_tier")
            or info.get("service_tier")
            or self.current["service_tier"]
        )
        for field in ("model", "effort", "service_tier"):
            if not request[field]:
                self.missing.add(field)
        request["cost"] = price(request, self.prices)
        self.requests.append(request)


def summarize(tid, node, since=None, until=None, prices=None):
    meta = node["meta"]
    spawn = thread_spawn(meta)
    parent = parent_thread_id(meta)
    source = meta.get("source")
    is_subagent = bool(parent) or (isinstance(source, dict) and "subagent" in source)
    scan = ThreadScan(tid, node["rows"], since, until, prices)
    if is_subagent:
        scan.missing.update(lineage_gaps(spawn, parent))
    for row in node["rows"]:
        scan.scan(row)
    requests = scan.requests
    known = sum(r["cost"] for r in requests if r["cost"] is not None)
    priced = bool(requests) and all(r["cost"] is not None for r in requests)
    return {
        "thread_id": tid,
        "parent_thread_id": parent,
        "role": spawn.get("agent_role") or ("unknown" if is_subagent else "main"),
        "status": scan.status,
        "files": node["files"],
        "observed_responses": len(requests),
        "first_request_input": requests[0]["usage"]["input_tokens"]
        if requests
        else None,
        "peak_request_input": max(
            (r["usage"]["input_tokens"] for r in requests), default=None
        ),
        "totals": {k: sum(r["usage"][k] for r in requests) for k in TOKEN_FIELDS},
        **scan.counts,
        "resume_status": "unknown unless explicit continuation call observed",
        **event_span(scan.moments),
        "known_cost_subtotal": known,
        "cost": known if priced else None,
        "missing": sorted(scan.missing),
        "rate_limit_snapshots": scan.limits,
        "requests": requests,
    }


def report(threads, thread=None, since=None, until=None, prices=None):
    wanted = list(threads) if thread is None else [thread]
    if thread and thread not in threads:
        raise ValueError("requested thread not found")
    for tid in wanted:
        wanted.extend(
            t
            for t, n in threads.items()
            if t not in wanted and parent_thread_id(n["meta"]) == tid
        )
    result = [summarize(t, threads[t], since, until, prices) for t in wanted]
    if thread is None:
        result = [r for r in result if r["first_event"] is not None]
    subtotal = sum(r["known_cost_subtotal"] for r in result)
    moments = [
        timestamp(r[k]) for r in result for k in ("first_event", "last_event") if r[k]
    ]
    return {
        "schema_version": 1,
        "scope": {
            "thread": thread,
            "since": str(since) if since else None,
            "until": str(until) if until else None,
        },
        "price_input": prices,
        "threads": result,
        "totals": {
            k: sum(r["totals"][k] for r in result)
            for k in ("input_tokens", "cached_input_tokens", "output_tokens")
        },
        "observed_responses": sum(r["observed_responses"] for r in result),
        "elapsed_seconds": (max(moments) - min(moments)).total_seconds()
        if moments
        else None,
        "known_cost_subtotal": subtotal,
        "cost": subtotal
        if result and all(r["cost"] is not None for r in result)
        else None,
        "limitations": [
            "Completed response observations are not all HTTP requests.",
            "First input is not pure history; parent cost is not pure coordination.",
            "Account quota snapshots do not identify per-agent quota percentages.",
            "Historical accounting does not establish policy savings.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", action="append", required=True)
    parser.add_argument("--thread")
    parser.add_argument("--since", type=timestamp)
    parser.add_argument("--until", type=timestamp)
    parser.add_argument("--prices", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    prices = json.loads(args.prices.read_text()) if args.prices else None
    if prices:
        for key in ("as_of", "currency", "source", "rates"):
            if not prices.get(key):
                parser.error(f"price input requires {key}")
        datetime.strptime(prices["as_of"], "%Y-%m-%d")
        for rate in prices["rates"]:
            for key in (
                "input_per_million",
                "cached_input_per_million",
                "output_per_million",
            ):
                if not isinstance(rate.get(key), (int, float)) or rate[key] < 0:
                    parser.error(f"invalid price: {key}")
    if args.since and args.until and args.since >= args.until:
        parser.error("--since must precede --until")
    result = report(
        load_threads(args.sessions, args.thread),
        args.thread,
        args.since,
        args.until,
        prices,
    )
    args.json.write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"{len(result['threads'])} threads; {result['observed_responses']} observed responses; "
        f"input={result['totals']['input_tokens']}, cached={result['totals']['cached_input_tokens']}, "
        f"output={result['totals']['output_tokens']}; cost={result['cost']}; JSON: {args.json}"
    )
    for item in result["threads"]:
        print(
            f"  {item['thread_id']} {item['role']} {item['status']}: "
            f"{item['observed_responses']} responses, {item['totals']}; missing={item['missing']}"
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"usage report: {exc}", file=sys.stderr)
        sys.exit(1)
