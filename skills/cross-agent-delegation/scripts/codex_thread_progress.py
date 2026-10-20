#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Read-only progress report for a Codex thread and the subagents it spawned, from its rollouts.

Prints, for records after --since: assistant progress messages, questions the thread asked the user
(request_user_input_async) and the user's replies, other user messages; then a subagent table,
whether the root thread has a turn in progress, and the questions still unanswered.
--since only filters those messages; it takes an ISO time, a local HH:MM (today, or yesterday if
that is still ahead), or "all"; by default it is one hour before the root thread's last record.
The tables always cover the whole thread.

Turns are tracked by the turn_id on task_started / task_complete / turn_aborted; a turn is in
progress from its task_started until one of the other two, and the thread is running while its
latest turn is (an earlier turn left open, say by a crash, does not count). Records without a
turn_id (older rollouts) count as one turn per task_started; an id-less end closes the latest
open turn.

--wait polls the root rollout every --interval seconds and returns, after printing the report,
as soon as the awaited state holds (checked at start too): "question" = the root thread has an
unanswered question; "complete" = the root thread's latest turn has ended and had not already
ended when the script started (a turn running at start, or one started after it); "any" =
either. --turn <id> (the turn_id codex_thread_turn.py prints) waits for that turn to end instead,
returning at once if it already has; it implies --wait complete and also works with --wait any.

Exit codes: 0 report printed (with --wait: the awaited turn ended, completed or aborted); 1 error,
such as no rollout for the thread; 2 usage error; 3 --wait question/any: a question awaits the
user's answer; 124 --wait timed out. Never writes under $CODEX_HOME.
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
    return next(read_records(path), None)


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
class Turn:
    started: datetime | None
    ended: datetime | None = None
    end: str | None = None  # "complete" or "aborted (<reason>)"


@dataclass
class Thread:
    path: Path
    started: datetime | None = None
    last: datetime | None = None
    turns: dict = field(default_factory=dict)  # turn id -> Turn, in start order
    events: list = field(default_factory=list)  # (ts, kind, text)
    questions: dict = field(default_factory=dict)  # call_id -> (ts, [question dict])
    answered: set = field(default_factory=set)  # call ids
    answered_titles: set = field(default_factory=set)
    seen_replies: set = field(default_factory=set)

    @property
    def latest(self):
        """(turn id, Turn) of the last task_started, or (None, None)."""
        return next(reversed(self.turns.items()), (None, None))

    @property
    def running(self):
        return self.latest[1] is not None and self.latest[1].end is None

    def start_turn(self, turn_id, ts):
        if not isinstance(turn_id, str):
            turn_id = f"#{len(self.turns) + 1}"  # no turn_id: older rollout
        self.turns.setdefault(turn_id, Turn(ts))

    def end_turn(self, turn_id, ts, end):
        if not isinstance(turn_id, str):
            open_ids = [k for k, t in self.turns.items() if t.end is None]
            turn_id = open_ids[-1] if open_ids else None
        turn = self.turns.get(turn_id)
        if turn is not None and turn.end is None:
            turn.ended, turn.end = ts, end

    def turn_state(self, turn_id=None):
        turn_id, turn = (turn_id, self.turns.get(turn_id)) if turn_id else self.latest
        if turn is None:
            return "no turn recorded"
        if turn.end is None:
            return f"turn {turn_id} running since {local(turn.started)}"
        return f"turn {turn_id} {turn.end} {local(turn.ended)}"

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
            thread.start_turn(payload.get("turn_id"), ts)
        elif kind == "event_msg" and ptype == "task_complete":
            thread.end_turn(payload.get("turn_id"), ts, "complete")
        elif kind == "event_msg" and ptype == "turn_aborted":
            reason = payload.get("reason") or "unknown"
            thread.end_turn(payload.get("turn_id"), ts, f"aborted ({reason})")
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
        # Review subagents record `subagent` as a bare string such as "review".
        subagent = source.get("subagent") if isinstance(source, dict) else None
        spawn = (
            (subagent.get("thread_spawn") or {}) if isinstance(subagent, dict) else {}
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


def report(thread_id, root, children, since, status_file, turn_id=None):
    kids = [(name, parse_thread(path)) for name, path in children]
    out = [f"== thread {thread_id}  ({root.path})"]
    window = f"since {local(since)}" if since else "all records"
    out.append(f"== messages, {window}")
    for ts, kind, text in root.events:
        if since and ts and ts < since:
            continue
        body = text.strip().replace("\n", "\n    ")
        out.append(f"[{local(ts)}] {kind}: {body}")
    out.append(f"== subagents ({len(kids)})")
    for name, kid in kids:
        out.append(
            f"  {name}\tstarted {local(kid.started)}\tlast {local(kid.last)}"
            f"\t{kid.turn_state()}"
        )
    out.append("== root")
    out.append(
        f"  turn in progress: {'yes' if root.running else 'no'}"
        f"  (latest {root.turn_state()})"
    )
    if turn_id and turn_id != root.latest[0]:
        out.append(f"  awaited: {root.turn_state(turn_id)}")
    out.append(f"  last record: {local(root.last)}")
    pending = root.unanswered()
    out.append(f"== unanswered questions ({len(pending)})")
    for _, (ts, qs) in pending.items():
        for q in qs:
            out.append(f"  [{local(ts)}] {q.get('title')}")
    if status_file:
        out += status_file_report(status_file)
    return "\n".join(out)


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
        "--turn", help="wait for this turn id to end (implies --wait complete)"
    )
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
    if args.turn:
        if args.wait == "question":
            parser.error("--turn needs --wait complete or any")
        args.wait = args.wait or "complete"

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
        print(report(args.thread_id, root, children, since, args.status_file))
        return 0

    ended_at_start = {k for k, t in root.turns.items() if t.end is not None}

    def turn_ended(thread):
        if args.turn:
            turn = thread.turns.get(args.turn)
            return turn is not None and turn.end is not None
        turn_id, turn = thread.latest
        return (
            turn is not None and turn.end is not None and turn_id not in ended_at_start
        )

    deadline = time.monotonic() + args.timeout
    while True:
        if args.wait in ("question", "any") and root.unanswered():
            code = 3
        elif args.wait in ("complete", "any") and turn_ended(root):
            code = 0
        elif time.monotonic() >= deadline:
            code = 124
        else:
            time.sleep(min(args.interval, max(0.0, deadline - time.monotonic())))
            root = parse_thread(root_path)
            continue
        break
    found, kids = locate(home, args.thread_id)
    print(
        report(
            args.thread_id,
            root,
            kids if found is not None else children,
            since,
            args.status_file,
            args.turn,
        )
    )
    if code == 124:
        print(f"--wait {args.wait}: timed out after {args.timeout:g}s", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
