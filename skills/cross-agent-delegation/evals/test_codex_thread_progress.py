"""Offline checks for codex_thread_progress.py against synthetic rollouts."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "codex_thread_progress.py"
_spec = importlib.util.spec_from_file_location("codex_thread_progress", SCRIPT)
progress = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(progress)
ROOT = "00000000-0000-7000-8000-00000000000a"
CHILD = "00000000-0000-7000-8000-00000000000b"
GRANDCHILD = "00000000-0000-7000-8000-00000000000c"
OTHER = "00000000-0000-7000-8000-00000000000d"


def rec(ts, kind, payload):
    return {"timestamp": f"2026-01-02T{ts}Z", "type": kind, "payload": payload}


def meta(thread_id, parent=None, path=None):
    source = "cli"
    if parent:
        source = {
            "subagent": {
                "thread_spawn": {"parent_thread_id": parent, "agent_path": path}
            }
        }
    return rec("10:00:00.000", "session_meta", {"id": thread_id, "source": source})


def ask(ts, call_id, *titles):
    questions = [{"title": t, "options": ["yes", "no"]} for t in titles]
    return rec(
        ts,
        "response_item",
        {
            "type": "function_call",
            "name": "request_user_input_async",
            "call_id": call_id,
            "arguments": json.dumps({"questions": questions}),
        },
    )


def reply(ts, call_id, title, answer):
    body = json.dumps(
        [
            {
                "questionItemId": json.dumps(["request_user_input_async", call_id, 0]),
                "question": title,
                "answer": answer,
            }
        ]
    )
    text = (
        f"<send_user_message_question_reply>{body}</send_user_message_question_reply>"
    )
    return rec(
        ts,
        "response_item",
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        },
    )


def say(ts, text, phase="commentary"):
    return rec(
        ts,
        "response_item",
        {
            "type": "message",
            "role": "assistant",
            "phase": phase,
            "content": [{"type": "output_text", "text": text}],
        },
    )


def event(ts, kind, **extra):
    return rec(ts, "event_msg", {"type": kind, **extra})


def write(home, thread_id, stamp, records, torn=False):
    day = Path(home) / "sessions" / "2026" / "01" / "02"
    day.mkdir(parents=True, exist_ok=True)
    path = day / f"rollout-2026-01-02T{stamp}-{thread_id}.jsonl"
    lines = [json.dumps(r) for r in records]
    text = "\n".join(lines) + "\n"
    if torn:
        text += '{"timestamp": "2026-01-02T11:59'
    path.write_text(text)
    return path


def append_later(path, *records, delay=1.5):
    """Append records (dicts as JSON lines, strings verbatim) from a thread after delay."""

    def append():
        time.sleep(delay)
        with path.open("a") as fh:
            for r in records:
                fh.write(r if isinstance(r, str) else json.dumps(r) + "\n")

    threading.Thread(target=append).start()


def run(*args, home, timeout=60):
    return subprocess.run(
        ["uv", "run", "-q", "--script", str(SCRIPT), *args],
        env=dict(os.environ, CODEX_HOME=str(home)),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def base_root():
    return [
        meta(ROOT),
        event("10:00:01.000", "task_started"),
        say("10:01:00.000", "dispatching wave 1"),
        ask("10:02:00.000", "call_1", "Merge now?"),
        reply("10:03:00.000", "call_1", "Merge now?", "yes"),
        event("10:04:00.000", "user_message", message="please also check docs"),
        {"type": "mystery_record", "payload": 42},
        ask("10:05:00.000", "call_2", "Deploy?"),
    ]


class CodexThreadProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self, root_records=None, torn=True):
        root = write(
            self.home, ROOT, "10-00-00", root_records or base_root(), torn=torn
        )
        write(
            self.home,
            CHILD,
            "10-00-30",
            [
                meta(CHILD, ROOT, "/root/worker_a"),
                event("10:00:31.000", "task_started"),
                event("10:30:00.000", "task_complete"),
            ],
        )
        write(
            self.home,
            GRANDCHILD,
            "10-01-00",
            [
                meta(GRANDCHILD, CHILD, "/root/worker_a/helper"),
                event("10:01:01.000", "task_started"),
            ],
        )
        write(
            self.home,
            OTHER,
            "10-02-00",
            [meta(OTHER, "someone-else", "/root/stranger")],
        )
        return root

    def test_report_parses_messages_questions_and_subagents(self):
        self.fixture()
        before = {p: p.stat().st_mtime_ns for p in self.home.rglob("*") if p.is_file()}
        result = run(ROOT, "--since", "all", home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("assistant/commentary: dispatching wave 1", out)
        self.assertIn("Q: Merge now?", out)
        self.assertIn("A: yes", out)
        self.assertIn("user: please also check docs", out)
        self.assertIn("== subagents (2)", out)
        self.assertIn("/root/worker_a\t", out)
        self.assertIn("/root/worker_a/helper\t", out)
        self.assertNotIn("stranger", out)
        self.assertIn("turn in progress: yes", out)
        pending = out.split("== unanswered questions (1)")[1]
        self.assertIn("Deploy?", pending)
        self.assertNotIn("Merge now?", pending)
        after = {p: p.stat().st_mtime_ns for p in self.home.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_rollout_with_unparsable_first_line_is_not_a_subagent(self):
        self.fixture()
        broken = write(
            self.home,
            "00000000-0000-7000-8000-00000000000e",
            "10-03-00",
            [event("10:03:01.000", "task_started", turn_id="x")],
        )
        broken.write_text('{"timestamp": "2026-01-02T10:03\n' + broken.read_text())
        result = run(ROOT, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("== subagents (2)", result.stdout)

    def test_review_subagent_with_string_source_is_not_a_child(self):
        self.fixture()
        write(
            self.home,
            "00000000-0000-7000-8000-00000000000f",
            "10-03-00",
            [
                rec(
                    "10:03:00.000",
                    "session_meta",
                    {"id": "review-1", "source": {"subagent": "review"}},
                )
            ],
        )
        result = run(ROOT, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("== subagents (2)", result.stdout)

    def test_since_filters_messages(self):
        self.fixture()
        result = run(ROOT, "--since", "2026-01-02T10:04:30Z", home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("dispatching wave 1", result.stdout)
        self.assertIn("Q: Deploy?", result.stdout)

    def test_status_file_tasks_and_other_shapes(self):
        self.fixture()
        tasks = self.home / "tasks.json"
        tasks.write_text(json.dumps({"tasks": [{"id": "t1", "status": "done"}]}))
        result = run(ROOT, "--status-file", str(tasks), home=self.home)
        self.assertIn("t1\tdone", result.stdout)
        tasks.write_text(json.dumps({"phase": 2, "notes": []}))
        result = run(ROOT, "--status-file", str(tasks), home=self.home)
        self.assertIn("top-level keys: phase, notes", result.stdout)

    def test_missing_thread_is_an_error(self):
        result = run(ROOT, home=self.home)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no rollout for thread", result.stderr)

    def test_wait_complete_exits_zero_on_completion_after_start(self):
        records = base_root()[:-1]
        root = self.fixture(records, torn=False)
        append_later(root, event("11:00:00.000", "task_complete"))
        result = self.wait("--wait", "complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("turn in progress: no", result.stdout)

    def test_wait_question_with_pending_question_exits_three_at_once(self):
        self.fixture()
        result = self.wait("--wait", "any")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("== unanswered questions (1)", result.stdout)

    def test_wait_question_exits_three_when_one_arrives(self):
        records = base_root()[:-1]
        root = self.fixture(records, torn=False)
        append_later(root, ask("11:00:00.000", "call_3", "Rollback?"))
        result = self.wait("--wait", "question")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn(
            "Rollback?", result.stdout.split("== unanswered questions (1)")[1]
        )

    def wait(self, *args, timeout="30"):
        return run(
            ROOT, *args, "--interval", "0.2", "--timeout", timeout, home=self.home
        )

    def turns_root(self, *records):
        return self.fixture([meta(ROOT), *records], torn=False)

    def test_running_follows_turn_ids_not_timestamps(self):
        # Turn b's task_complete carries an earlier timestamp than its task_started.
        self.turns_root(
            event("10:00:01.000", "task_started", turn_id="a"),
            event("10:01:00.000", "task_complete", turn_id="a"),
            event("10:05:00.000", "task_started", turn_id="b"),
            event("10:04:59.000", "task_complete", turn_id="b"),
        )
        result = run(ROOT, home=self.home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("turn in progress: no", result.stdout)
        self.assertIn("latest turn b", result.stdout)

    def test_aborted_turn_is_not_running(self):
        self.turns_root(
            event("10:00:01.000", "task_started", turn_id="a"),
            event("10:01:00.000", "turn_aborted", turn_id="a", reason="interrupted"),
        )
        result = run(ROOT, home=self.home)
        self.assertIn("turn in progress: no", result.stdout)
        self.assertIn("aborted (interrupted)", result.stdout)

    def test_wait_complete_returns_when_open_turn_completes_with_old_timestamp(self):
        root = self.turns_root(event("10:00:01.000", "task_started", turn_id="a"))
        append_later(root, event("10:30:00.000", "task_complete", turn_id="a"))
        result = self.wait("--wait", "complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("turn in progress: no", result.stdout)

    def test_wait_complete_ignores_turns_finished_before_start(self):
        self.turns_root(
            event("10:00:01.000", "task_started", turn_id="a"),
            event("10:01:00.000", "task_complete", turn_id="a"),
        )
        result = self.wait("--wait", "complete", "--since", "all", timeout="1")
        self.assertEqual(result.returncode, 124)

    def test_wait_complete_returns_for_new_turn_after_start(self):
        root = self.turns_root(
            event("10:00:01.000", "task_started", turn_id="a"),
            event("10:01:00.000", "task_complete", turn_id="a"),
        )
        append_later(
            root,
            event("10:02:00.000", "task_started", turn_id="b"),
            event("10:03:00.000", "task_complete", turn_id="b"),
        )
        result = self.wait("--wait", "complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("latest turn b", result.stdout)

    def test_turn_already_complete_exits_zero_at_once(self):
        self.turns_root(
            event("10:00:01.000", "task_started", turn_id="a"),
            event("10:01:00.000", "task_complete", turn_id="a"),
            event("10:02:00.000", "task_started", turn_id="b"),
        )
        result = self.wait("--turn", "a")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_turn_waits_for_that_turn_to_appear_and_finish(self):
        root = self.turns_root(
            event("10:00:01.000", "task_started", turn_id="a"),
            event("10:01:00.000", "task_complete", turn_id="a"),
        )
        self.assertEqual(self.wait("--turn", "b", timeout="1").returncode, 124)
        append_later(
            root,
            event("10:02:00.000", "task_started", turn_id="b"),
            event("10:03:00.000", "task_complete", turn_id="b"),
        )
        result = self.wait("--turn", "b")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_turn_rejects_wait_question(self):
        self.turns_root()
        result = run(ROOT, "--turn", "a", "--wait", "question", home=self.home)
        self.assertEqual(result.returncode, 2)

    def test_wait_complete_ignores_idless_turn_finished_before_start(self):
        self.fixture(base_root()[:3] + [event("10:10:00.000", "task_complete")])
        result = self.wait("--wait", "complete", timeout="1")
        self.assertEqual(result.returncode, 124)
        self.assertIn("timed out", result.stderr)

    def test_wait_reads_a_line_finished_in_a_later_poll(self):
        root = self.turns_root(event("10:00:01.000", "task_started", turn_id="a"))
        line = json.dumps(event("10:30:00.000", "task_complete", turn_id="a")) + "\n"
        with root.open("a") as fh:
            fh.write(line[:20])
        append_later(root, line[20:])
        result = self.wait("--wait", "complete")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("turn a complete", result.stdout)

    def test_read_new_applies_only_appended_complete_lines(self):
        root = self.turns_root(say("10:00:02.000", "first"))
        thread = progress.parse_thread(root, eof=False)
        self.assertEqual(thread.offset, root.stat().st_size)
        complete = json.dumps(say("10:00:03.000", "second")) + "\n"
        half = json.dumps(event("10:00:04.000", "task_started", turn_id="b"))
        with root.open("a") as fh:
            fh.write(complete + half[:20])
        progress.read_new(thread)
        self.assertEqual([e[2] for e in thread.events], ["first", "second"])
        self.assertNotIn("b", thread.turns)
        with root.open("a") as fh:
            fh.write(half[20:] + "\n")
        progress.read_new(thread)
        self.assertIn("b", thread.turns)
        self.assertEqual(thread.offset, root.stat().st_size)

    def test_unhashable_record_types_are_ignored(self):
        thread = progress.Thread(path=self.home / "unused.jsonl")
        records = [
            {"type": ["event_msg"], "payload": {"type": "task_started"}},
            {"type": "event_msg", "payload": {"type": {"a": 1}}},
            {"type": {"a": 1}, "payload": {"type": ["message"]}},
        ]
        for record in records:
            progress.apply_record(thread, record)
        self.assertEqual(thread, progress.Thread(path=self.home / "unused.jsonl"))


if __name__ == "__main__":
    unittest.main()
