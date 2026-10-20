"""Offline exit-code checks for codex_thread_turn.py; no daemon or model calls."""

import json
import os
import socket
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "codex_thread_turn.py"
FAKE_DAEMON = Path(__file__).resolve().parent / "fake_codex_daemon.py"
THREAD = "00000000-0000-7000-8000-0000000000f1"


def run(*args, codex_home):
    return subprocess.run(
        ["uv", "run", "-q", "--script", str(SCRIPT), *args],
        env=dict(os.environ, CODEX_HOME=codex_home),
        capture_output=True,
        text=True,
        timeout=120,
    )


class CodexThreadTurnTest(unittest.TestCase):
    def test_missing_daemon_points_to_exec_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "brief.md"
            brief.write_text("hello\n")
            result = run("thread-id", str(brief), codex_home=tmp)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("use exec resume", result.stderr)

    def test_stale_socket_points_to_exec_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            control = Path(tmp) / "app-server-control"
            control.mkdir()
            stale = socket.socket(socket.AF_UNIX)
            stale.bind(str(control / "app-server-control.sock"))
            stale.close()
            brief = Path(tmp) / "brief.md"
            brief.write_text("hello\n")
            result = run("thread-id", str(brief), codex_home=tmp)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("use exec resume", result.stderr)

    def test_steer_without_daemon_still_points_to_exec_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "brief.md"
            brief.write_text("hello\n")
            result = run("thread-id", str(brief), "--steer", codex_home=tmp)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("use exec resume", result.stderr)

    def test_empty_brief_is_rejected_before_connecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "brief.md"
            brief.write_text("  \n")
            result = run("thread-id", str(brief), codex_home=tmp)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("brief is empty", result.stderr)


class CodexThreadTurnDaemonTest(unittest.TestCase):
    """Against fake_codex_daemon.py: which requests are sent, ids line and exit code."""

    def daemon(self, status, turns=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        scenario = home / "scenario.json"
        scenario.write_text(
            json.dumps({"thread_id": THREAD, "status": status, "turns": list(turns)})
        )
        self.log = home / "requests.jsonl"
        proc = subprocess.Popen(
            ["uv", "run", "-q", "--script", str(FAKE_DAEMON), tmp.name, str(scenario)]
            + [str(self.log)]
        )
        self.addCleanup(proc.wait)
        self.addCleanup(proc.terminate)
        sock = home / "app-server-control" / "app-server-control.sock"
        deadline = time.monotonic() + 60
        while not sock.exists():
            self.assertIsNone(proc.poll(), "fake daemon exited")
            self.assertLess(time.monotonic(), deadline, "fake daemon did not start")
            time.sleep(0.1)
        brief = home / "brief.md"
        brief.write_text("hello\n")
        return home, brief

    def requests(self):
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        return [json.loads(line) for line in lines]

    def methods(self):
        return [r["method"] for r in self.requests() if r["method"] != "thread/read"]

    def test_idle_thread_starts_a_turn_and_waits(self):
        home, brief = self.daemon("idle")
        result = run(THREAD, str(brief), "--wait", codex_home=str(home))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "done")
        self.assertIn(
            json.dumps({"thread_id": THREAD, "turn_id": "new-turn"}), result.stderr
        )
        self.assertEqual(
            self.methods(),
            ["initialize", "thread/loaded/list", "thread/resume", "turn/start"],
        )

    def test_idle_thread_without_wait_does_not_subscribe(self):
        home, brief = self.daemon("idle")
        result = run(THREAD, str(brief), codex_home=str(home))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            self.methods(), ["initialize", "thread/loaded/list", "turn/start"]
        )

    def test_busy_thread_exits_four_before_subscribing(self):
        home, brief = self.daemon("active")
        result = run(THREAD, str(brief), "--wait", codex_home=str(home))
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertEqual(self.methods(), ["initialize", "thread/loaded/list"])

    def test_steer_targets_the_in_progress_turn(self):
        turns = [
            {"id": "old", "status": "completed"},
            {"id": "live", "status": "inProgress"},
        ]
        home, brief = self.daemon("active", turns)
        result = run(THREAD, str(brief), "--steer", "--wait", codex_home=str(home))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "done")
        self.assertIn(
            json.dumps({"thread_id": THREAD, "turn_id": "live", "steered": True}),
            result.stderr,
        )
        self.assertEqual(
            self.methods(),
            ["initialize", "thread/loaded/list", "thread/resume", "turn/steer"],
        )
        reads = [r for r in self.requests() if r["method"] == "thread/read"]
        self.assertTrue(reads[-1]["params"].get("includeTurns"))
        steer = self.requests()[-1]["params"]
        self.assertEqual(steer["expectedTurnId"], "live")
        self.assertEqual(steer["input"], [{"type": "text", "text": "hello\n"}])

    def test_steer_on_idle_thread_exits_one_without_sending(self):
        home, brief = self.daemon("idle")
        result = run(THREAD, str(brief), "--steer", codex_home=str(home))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("--steer needs a running turn", result.stderr)
        self.assertEqual(self.methods(), ["initialize", "thread/loaded/list"])

    def test_steer_without_in_progress_turn_exits_one(self):
        home, brief = self.daemon("active", [{"id": "old", "status": "completed"}])
        result = run(THREAD, str(brief), "--steer", "--wait", codex_home=str(home))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("no in-progress turn found to steer", result.stderr)
        self.assertEqual(self.methods(), ["initialize", "thread/loaded/list"])

    def test_steer_reads_the_thread_once(self):
        home, brief = self.daemon("active", [{"id": "live", "status": "inProgress"}])
        run(THREAD, str(brief), "--steer", codex_home=str(home))
        reads = [r for r in self.requests() if r["method"] == "thread/read"]
        self.assertEqual(len(reads), 1)


if __name__ == "__main__":
    unittest.main()
