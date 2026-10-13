"""Offline exit-code checks for codex_thread_turn.py; no daemon or model calls."""

import os
import socket
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "codex_thread_turn.py"


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

    def test_empty_brief_is_rejected_before_connecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "brief.md"
            brief.write_text("  \n")
            result = run("thread-id", str(brief), codex_home=tmp)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("brief is empty", result.stderr)


if __name__ == "__main__":
    unittest.main()
