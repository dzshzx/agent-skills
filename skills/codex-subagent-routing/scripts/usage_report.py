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


def load_threads(directories, thread=None):
    threads = {}
    indexed = []
    for directory in directories:
        for path in sorted(Path(directory).rglob("rollout-*.jsonl")):
            with path.open() as stream:
                first = json.loads(stream.readline())
            meta = first.get("payload", {}) if first.get("type") == "session_meta" else {}
            indexed.append((path, meta))
    wanted = {thread} if thread else {m.get("id") for _, m in indexed}
    while True:
        children = {m.get("id") for _, m in indexed if m.get("parent_thread_id") in wanted}
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
            group = threads.setdefault(tid, {"meta": meta, "rows": [], "files": [], "seen": {}})
            if group["meta"] != meta:
                raise ValueError(f"conflicting metadata for {tid}")
            group["files"].append(str(path))
            for row in own:
                canonical = json.dumps(row, sort_keys=True)
                key = ("ordinal", row["ordinal"]) if "ordinal" in row else ("row", canonical)
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
    rates = [r for r in prices["rates"] if
             (r["model"], r["service_tier"]) == (request["model"], request["service_tier"])]
    if len(rates) != 1:
        return None
    rate, usage = rates[0], request["usage"]
    if any(usage.get(k) is None for k in ("input_tokens", "cached_input_tokens", "output_tokens")):
        return None
    return ((usage["input_tokens"] - usage["cached_input_tokens"]) * rate["input_per_million"]
            + usage["cached_input_tokens"] * rate["cached_input_per_million"]
            + usage["output_tokens"] * rate["output_per_million"]) / 1_000_000


def summarize(tid, node, since=None, until=None, prices=None):
    meta = node["meta"]
    spawn = meta.get("source", {})
    spawn = spawn.get("subagent", {}).get("thread_spawn", {}) if isinstance(spawn, dict) else {}
    current = {"model": None, "effort": None, "service_tier": None}
    requests, seen, limits, moments = [], {}, [], []
    counts = {"turn_starts": 0, "continuation_calls": 0, "compactions": 0}
    status = "unknown"
    missing = set()
    # Current runtimes persist authoritative per-response records alongside
    # UI token_count snapshots. Match cumulative totals to avoid counting both.
    typed_snapshots, typed_turns = set(), set()
    current_turn = None
    for item in node["rows"]:
        payload = item.get("payload", {})
        if item.get("type") == "token_usage_record":
            if payload.get("thread_id") != tid:
                raise ValueError(f"foreign token usage inside own boundary of {tid}")
            if payload.get("thread_token_usage"):
                typed_snapshots.add(json.dumps(payload["thread_token_usage"], sort_keys=True))
            typed_turns.add(payload.get("turn_id"))
    for row in node["rows"]:
        p = row.get("payload", {})
        if not isinstance(p, dict):
            continue
        kind = row.get("type")
        if kind == "turn_context":
            current_turn = p.get("turn_id")
            current = {"model": p.get("model"), "effort": p.get("effort", p.get("reasoning_effort")),
                       "service_tier": p.get("service_tier")}
        raw_time = row.get("timestamp")
        if not raw_time:
            missing.add("event_timestamp")
            continue
        when = timestamp(raw_time)
        in_range = not ((since and when < since) or (until and when >= until))
        token_event = kind == "token_usage_record" or (kind == "event_msg" and p.get("type") == "token_count")
        if not in_range and not token_event:
            continue
        if in_range:
            moments.append(when)
        if kind == "event_msg" and p.get("type") in {"task_started", "turn_started"}:
            counts["turn_starts"] += 1
            status = "running"
        if kind == "event_msg" and p.get("type") in {"task_complete", "turn_completed"}:
            status = "completed"
        if kind == "event_msg" and p.get("type") in {"task_failed", "turn_failed", "turn_aborted", "error"}:
            status = "failed_or_aborted"
        if kind == "compacted" or (kind == "event_msg" and p.get("type") == "context_compacted"):
            counts["compactions"] += 1
        if kind == "response_item" and p.get("type") == "function_call":
            if p.get("name", "").split(".")[-1] in {"followup_task", "send_input", "resume_agent"}:
                counts["continuation_calls"] += 1
        if not token_event:
            continue
        if in_range and p.get("rate_limits"):
            snap = {"timestamp": raw_time, "value": p["rate_limits"]}
            if not limits or limits[-1]["value"] != snap["value"]:
                limits.append(snap)
        info = p.get("info") or {}
        typed = kind == "token_usage_record"
        if not typed and current_turn in typed_turns:
            # UI cumulative totals can change meaning after compaction. Native
            # records own accounting for the entire turn, regardless of that
            # display reset; UI-only older turns retain the legacy fallback.
            continue
        usage = p.get("usage") if typed else info.get("last_token_usage")
        if not usage:
            continue
        if all(usage.get(k) == 0 for k in ("input_tokens", "output_tokens", "cached_input_tokens")):
            # Compaction/status updates can carry a nonzero context total but
            # zero billed components; they are not another completed response.
            continue
        response = p.get("response_id") or info.get("response_id")
        cumulative = p.get("thread_token_usage") if typed else info.get("total_token_usage")
        if not typed and cumulative and json.dumps(cumulative, sort_keys=True) in typed_snapshots:
            continue
        if response:
            key = ("response", response)
        elif cumulative:
            key = ("cumulative", json.dumps(cumulative, sort_keys=True))
            missing.add("response_id: cumulative snapshot deduplication used")
        else:
            missing.add("response_identity: usage excluded")
            continue
        if key in seen:
            if seen[key] != usage:
                raise ValueError(f"conflicting response usage in {tid}")
            continue
        seen[key] = usage
        if not in_range:
            continue
        for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
            if not isinstance(usage.get(field), int) or usage[field] < 0:
                raise ValueError(f"missing or invalid {field} in {tid}")
        if usage["cached_input_tokens"] > usage["input_tokens"]:
            raise ValueError("cached input exceeds total input")
        request = {"timestamp": raw_time, "response_id": response, **current, "usage": usage}
        # Only an explicitly logged actual tier is attributed, never today's config.
        request["service_tier"] = p.get("service_tier") or info.get("service_tier") or current["service_tier"]
        for field in ("model", "effort", "service_tier"):
            if not request[field]:
                missing.add(field)
        request["cost"] = price(request, prices)
        requests.append(request)
    totals = {k: sum(r["usage"][k] for r in requests)
              for k in ("input_tokens", "cached_input_tokens", "output_tokens")}
    known = sum(r["cost"] for r in requests if r["cost"] is not None)
    return {"thread_id": tid, "parent_thread_id": meta.get("parent_thread_id") or spawn.get("parent_thread_id"),
            "role": spawn.get("agent_role") or ("unknown" if spawn else "main"), "status": status,
            "files": node["files"], "observed_responses": len(requests),
            "first_request_input": requests[0]["usage"]["input_tokens"] if requests else None,
            "peak_request_input": max((r["usage"]["input_tokens"] for r in requests), default=None),
            "totals": totals, **counts, "resume_status": "unknown unless explicit continuation call observed",
            "elapsed_seconds": (max(moments) - min(moments)).total_seconds() if moments else None,
            "first_event": min(moments).isoformat() if moments else None,
            "last_event": max(moments).isoformat() if moments else None,
            "known_cost_subtotal": known,
            "cost": known if requests and all(r["cost"] is not None for r in requests) else None,
            "missing": sorted(missing), "rate_limit_snapshots": limits, "requests": requests}


def report(threads, thread=None, since=None, until=None, prices=None):
    wanted = list(threads) if thread is None else [thread]
    if thread and thread not in threads:
        raise ValueError("requested thread not found")
    for tid in wanted:
        wanted.extend(t for t, n in threads.items() if t not in wanted and
                      (n["meta"].get("parent_thread_id") or
                       (n["meta"].get("source", {}) if isinstance(n["meta"].get("source"), dict) else {})
                       .get("subagent", {}).get("thread_spawn", {}).get("parent_thread_id")) == tid)
    result = [summarize(t, threads[t], since, until, prices) for t in wanted]
    if thread is None:
        result = [r for r in result if r["first_event"] is not None]
    subtotal = sum(r["known_cost_subtotal"] for r in result)
    moments = [timestamp(r[k]) for r in result for k in ("first_event", "last_event") if r[k]]
    return {"schema_version": 1, "scope": {"thread": thread, "since": str(since) if since else None,
                                          "until": str(until) if until else None},
            "price_input": prices, "threads": result,
            "totals": {k: sum(r["totals"][k] for r in result)
                       for k in ("input_tokens", "cached_input_tokens", "output_tokens")},
            "observed_responses": sum(r["observed_responses"] for r in result),
            "elapsed_seconds": (max(moments) - min(moments)).total_seconds() if moments else None,
            "known_cost_subtotal": subtotal,
            "cost": subtotal if result and all(r["cost"] is not None for r in result) else None,
            "limitations": ["Completed response observations are not all HTTP requests.",
                           "First input is not pure history; parent cost is not pure coordination.",
                           "Account quota snapshots do not identify per-agent quota percentages.",
                           "Historical accounting does not establish policy savings."]}


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
            for key in ("input_per_million", "cached_input_per_million", "output_per_million"):
                if not isinstance(rate.get(key), (int, float)) or rate[key] < 0:
                    parser.error(f"invalid price: {key}")
    if args.since and args.until and args.since >= args.until:
        parser.error("--since must precede --until")
    result = report(load_threads(args.sessions, args.thread), args.thread, args.since, args.until, prices)
    args.json.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{len(result['threads'])} threads; {result['observed_responses']} observed responses; "
          f"input={result['totals']['input_tokens']}, cached={result['totals']['cached_input_tokens']}, "
          f"output={result['totals']['output_tokens']}; cost={result['cost']}; JSON: {args.json}")
    for item in result["threads"]:
        print(f"  {item['thread_id']} {item['role']} {item['status']}: "
              f"{item['observed_responses']} responses, {item['totals']}; missing={item['missing']}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f"usage report: {exc}", file=sys.stderr)
        sys.exit(1)
