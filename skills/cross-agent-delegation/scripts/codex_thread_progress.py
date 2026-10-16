#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Read-only progress report for a Codex thread and the subagents it spawned, from its rollouts.

Prints, for records after --since: assistant progress messages, questions the thread asked the user
(request_user_input_async) and the user's replies, other user messages; then a subagent table,
whether the root thread has a turn in progress, and the questions still unanswered.
--since takes an ISO time, a local HH:MM (today, or yesterday if that is still ahead), or "all";
by default it is one hour before the root thread's last record. The tables always cover the whole
thread.

--wait polls the rollouts every --interval seconds and returns, after printing the same report,
as soon as the awaited state holds (checked at start too): "question" = the root thread has an
unanswered question; "complete" = the root thread's last task_complete is later than its last
task_started and than the baseline, which is --since when given (so "--since <when I sent the
turn>" returns at once if it already finished) and the script's start time otherwise; "any" =
either.

Exit codes: 0 report printed (with --wait: the root turn completed); 1 error, such as no rollout
for the thread; 2 usage error; 3 --wait question/any: a question awaits the user's answer;
124 --wait timed out. Never writes under $CODEX_HOME.
"""

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys
import time

REPLY = re.compile(
    r"<send_user_message_question_reply>(.*?)</send_user_message_question_reply>", re.S
)


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def parse_ts(value):
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.astimezone()


def local(ts):
    return ts.astimezone().strftime("%m-%d %H:%M:%S") if ts else "-"


def read_records(path):
    """Yield parsed JSON objects; skip a torn last line and anything unparsable."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def first_record(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return json.loads(fh.readline())
    except (OSError, ValueError):
        return None


def texts(content):
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [
        c["text"]
        for c in content
        if isinstance(c, dict) and isinstance(c.get("text"), str)
    ]


@dataclass
class Thread:
    path: Path
    started: datetime | None = None
    last: datetime | None = None
    last_started: datetime | None = None
    last_complete: datetime | None = None
    events: list = field(default_factory=list)  # (ts, kind, text)
    questions: dict = field(default_factory=dict)  # call_id -> (ts, [question dict])
    answered: set = field(default_factory=set)  # call ids
    answered_titles: set = field(default_factory=set)
    seen_replies: set = field(default_factory=set)

    @property
    def running(self):
        return self.last_started is not None and (
            self.last_complete is None or self.last_started > self.last_complete
        )

    def unanswered(self):
        out = {}
        for call_id, (ts, qs) in self.questions.items():
            if call_id in self.answered:
                continue
            titles = {q.get("title") for q in qs if isinstance(q, dict)}
            if titles and titles <= self.answered_titles:
                continue
            out[call_id] = (ts, qs)
        return out


def add_replies(thread, ts, text):
    found = False
    for match in REPLY.finditer(text):
        found = True
        try:
            replies = json.loads(match.group(1))
        except ValueError:
            continue
        for reply in replies if isinstance(replies, list) else []:
            if not isinstance(reply, dict):
                continue
            try:
                item = json.loads(reply.get("questionItemId") or "null")
                if isinstance(item, list) and len(item) > 1:
                    thread.answered.add(item[1])
            except (TypeError, ValueError):
                pass
            thread.answered_titles.add(reply.get("question"))
            key = (
                reply.get("questionItemId"),
                reply.get("question"),
                reply.get("answer"),
            )
            if key in thread.seen_replies:
                continue
            thread.seen_replies.add(key)
            thread.events.append(
                (ts, "answer", f"Q: {reply.get('question')}\nA: {reply.get('answer')}")
            )
    return found


def parse_thread(path):
    thread = Thread(path)
    seen_user = set()
    for record in read_records(path):
        ts = parse_ts(record.get("timestamp"))
        payload = record.get("payload")
        if ts:
            thread.started = thread.started or ts
            thread.last = ts
        if not isinstance(payload, dict):
            continue
        kind, ptype = record.get("type"), payload.get("type")
        if kind == "event_msg" and ptype == "task_started":
            thread.last_started = ts
        elif kind == "event_msg" and ptype == "task_complete":
            thread.last_complete = ts
        elif kind == "event_msg" and ptype == "user_message":
            text = payload.get("message")
            if isinstance(text, str) and text not in seen_user:
                if not add_replies(thread, ts, text):
                    seen_user.add(text)
                    thread.events.append((ts, "user", text))
        elif kind == "event_msg" and ptype == "item_completed":
            item = payload.get("item") or {}
            if isinstance(item, dict) and item.get("type") == "UserMessage":
                text = "\n".join(texts(item.get("content")))
                if text and text not in seen_user and not REPLY.search(text):
                    seen_user.add(text)
                    thread.events.append((ts, "user", text))
        elif kind == "response_item" and ptype == "message":
            role = payload.get("role")
            text = "\n".join(texts(payload.get("content")))
            if role == "assistant" and text:
                phase = payload.get("phase") or "message"
                thread.events.append((ts, f"assistant/{phase}", text))
            elif role == "user" and text:
                add_replies(thread, ts, text)
        elif (
            kind == "response_item"
            and ptype == "function_call"
            and payload.get("name") == "request_user_input_async"
        ):
            try:
                args = json.loads(payload.get("arguments") or "{}")
            except ValueError:
                args = {}
            qs = args.get("questions") if isinstance(args, dict) else None
            qs = [q for q in qs if isinstance(q, dict)] if isinstance(qs, list) else []
            thread.questions[payload.get("call_id")] = (ts, qs)
            lines = []
            for q in qs:
                opts = q.get("options") or []
                lines.append(f"Q: {q.get('title')}")
                lines += [
                    f"   - {o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)}"
                    for o in opts
                ]
            thread.events.append((ts, "question", "\n".join(lines)))
    return thread


ROLLOUT_STAMP = re.compile(r"rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})")


def locate(home, thread_id):
    sessions = home / "sessions"
    hits = sorted(sessions.glob(f"**/rollout-*-{thread_id}.jsonl"))
    if not hits:
        return None, []
    root = hits[-1]
    stamp = (ROLLOUT_STAMP.search(root.name) or [None, ""])[1]
    known, children = {thread_id}, []
    candidates = sorted(
        (p for p in sessions.glob("**/rollout-*.jsonl") if p != root),
        key=lambda p: p.name,
    )
    for path in candidates:
        m = ROLLOUT_STAMP.search(path.name)
        if m and m[1] < stamp:
            continue
        meta = first_record(path)
        payload = meta.get("payload") if isinstance(meta, dict) else None
        if not isinstance(payload, dict) or meta.get("type") != "session_meta":
            continue
        source = payload.get("source")
        spawn = (
            ((source.get("subagent") or {}).get("thread_spawn") or {})
            if isinstance(source, dict)
            else {}
        )
        if isinstance(spawn, dict) and spawn.get("parent_thread_id") in known:
            known.add(payload.get("id"))
            children.append((spawn.get("agent_path") or payload.get("id"), path))
    return root, children


def parse_since(value, root):
    if value == "all":
        return None
    if value is None:
        return root.last - timedelta(hours=1) if root.last else None
    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        hour, minute = map(int, value.split(":"))
        now = datetime.now().astimezone()
        ts = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return ts - timedelta(days=1) if ts > now else ts
    ts = parse_ts(value)
    if ts is None:
        raise ValueError(f"--since: cannot parse {value!r}")
    return ts


def status_file_report(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"status file {path}: unreadable ({exc})"]
    lines = [f"== status file {path}"]
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if isinstance(tasks, list) and all(isinstance(t, dict) for t in tasks):
        counts = {}
        for t in tasks:
            counts[t.get("status")] = counts.get(t.get("status"), 0) + 1
            lines.append(f"  {t.get('id')}\t{t.get('status')}")
        lines.append("  totals: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    elif isinstance(data, dict):
        lines.append("  top-level keys: " + ", ".join(data))
    else:
        lines.append(f"  top-level type: {type(data).__name__}")
    return lines


def report(thread_id, root_path, children, since, status_file):
    root = parse_thread(root_path)
    kids = [(name, parse_thread(path)) for name, path in children]
    out = [f"== thread {thread_id}  ({root_path})"]
    window = f"since {local(since)}" if since else "all records"
    out.append(f"== messages, {window}")
    for ts, kind, text in root.events:
        if since and ts and ts < since:
            continue
        body = text.strip().replace("\n", "\n    ")
        out.append(f"[{local(ts)}] {kind}: {body}")
    out.append(f"== subagents ({len(kids)})")
    for name, kid in kids:
        if kid.running:
            state = f"running since {local(kid.last_started)}"
        elif kid.last_complete:
            state = f"task_complete {local(kid.last_complete)}"
        else:
            state = "no turn recorded"
        out.append(
            f"  {name}\tstarted {local(kid.started)}\tlast {local(kid.last)}\t{state}"
        )
    out.append("== root")
    out.append(
        f"  turn in progress: {'yes' if root.running else 'no'}"
        f"  (last task_started {local(root.last_started)},"
        f" last task_complete {local(root.last_complete)})"
    )
    out.append(f"  last record: {local(root.last)}")
    pending = root.unanswered()
    out.append(f"== unanswered questions ({len(pending)})")
    for _, (ts, qs) in pending.items():
        for q in qs:
            out.append(f"  [{local(ts)}] {q.get('title')}")
    if status_file:
        out += status_file_report(status_file)
    return root, "\n".join(out)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("thread_id")
    parser.add_argument("--since", help='ISO time, local HH:MM, or "all"')
    parser.add_argument(
        "--status-file", help="JSON file; a tasks[] of {id, status} is tabulated"
    )
    parser.add_argument("--wait", choices=["question", "complete", "any"])
    parser.add_argument(
        "--timeout",
        type=float,
        default=3600,
        help="--wait limit in seconds (default 3600)",
    )
    parser.add_argument(
        "--interval", type=float, default=30, help="--wait poll seconds (default 30)"
    )
    args = parser.parse_args()

    home = codex_home()
    root_path, children = locate(home, args.thread_id)
    if root_path is None:
        print(
            f"no rollout for thread {args.thread_id} under {home / 'sessions'}",
            file=sys.stderr,
        )
        return 1
    root = parse_thread(root_path)
    try:
        since = parse_since(args.since, root)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not args.wait:
        print(report(args.thread_id, root_path, children, since, args.status_file)[1])
        return 0

    if args.since is None:
        baseline = datetime.now().astimezone()
    else:
        baseline = since
    deadline = time.monotonic() + args.timeout
    while True:
        found, kids = locate(home, args.thread_id)
        if found is not None:
            root_path, children = found, kids
        root, text = report(
            args.thread_id, root_path, children, since, args.status_file
        )
        if args.wait in ("question", "any") and root.unanswered():
            print(text)
            return 3
        completed = root.last_complete and (
            baseline is None or root.last_complete > baseline
        )
        if args.wait in ("complete", "any") and completed and not root.running:
            print(text)
            return 0
        if time.monotonic() >= deadline:
            print(text)
            print(
                f"--wait {args.wait}: timed out after {args.timeout:g}s",
                file=sys.stderr,
            )
            return 124
        time.sleep(min(args.interval, max(0.0, deadline - time.monotonic())))


if __name__ == "__main__":
    sys.exit(main())
