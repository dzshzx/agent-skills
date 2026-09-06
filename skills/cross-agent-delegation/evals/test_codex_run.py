import tempfile
import unittest
import json
import os
import subprocess
from unittest.mock import patch
from pathlib import Path

from check_codex_run import check_file, check_posture, validate


ANSWER = {"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}}
DONE = {"type": "turn.completed"}


class CodexRunTests(unittest.TestCase):
    def test_success(self):
        validate([ANSWER, DONE], 0)

    def test_failure_counterexamples(self):
        cases = [([ANSWER, DONE], 1), ([ANSWER, DONE], 124),
                 ([ANSWER, {"type": "turn.failed"}], 1),
                 ([ANSWER, {"type": "turn.failed"}, DONE], 0),
                 ([ANSWER], 0), ([DONE], 0), ([], 0),
                 ([{"type": "item.completed", "item": {"type": "agent_message", "phase": "commentary", "text": "working"}}, DONE], 0),
                 ([{"type": "error"}, ANSWER, DONE], 0),
                 ([{"type": "item.started", "item": ANSWER["item"]}, DONE], 0)]
        for events, rc in cases:
            with self.subTest(events=events, rc=rc), self.assertRaises(ValueError):
                validate(events, rc)

    def test_missing_and_malformed_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            with self.assertRaises(OSError):
                check_file(path, 0)
            path.write_text("not-json\n")
            with self.assertRaises(ValueError):
                check_file(path, 0)

    def test_final_file_is_required_and_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events"
            final = Path(tmp) / "final"
            log.write_text("\n".join(json.dumps(e) for e in [ANSWER, DONE]))
            with self.assertRaises(OSError):
                check_file(log, 0, final)
            for value in ["", "progress"]:
                final.write_text(value)
                with self.assertRaises(ValueError):
                    check_file(log, 0, final)
            final.write_text("OK\n")
            check_file(log, 0, final)
            commentary = {"type": "item.completed", "item": {
                "type": "agent_message", "phase": "commentary", "text": "working"}}
            log.write_text("\n".join(json.dumps(e) for e in [ANSWER, commentary, DONE]))
            final.write_text("working")
            with self.assertRaises(ValueError):
                check_file(log, 0, final)

    def test_actual_permission_context(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, CODEX_HOME=tmp):
            root = Path(tmp)
            log = root / "events"
            log.write_text(json.dumps({"type": "thread.started", "thread_id": "test-id"}))
            with self.assertRaises(ValueError):
                check_posture(log, "read-only")
            sessions = root / "sessions"
            sessions.mkdir()
            record = sessions / "rollout-test-id.jsonl"
            for mode, approval in [("danger-full-access", "never"), ("read-only", "on-request")]:
                record.write_text(json.dumps({"type": "turn_context", "payload": {
                    "sandbox_policy": {"type": mode}, "approval_policy": approval}}))
                with self.assertRaises(ValueError):
                    check_posture(log, "read-only")
            record.write_text(json.dumps({"type": "turn_context", "payload": {
                "sandbox_policy": {"type": "read-only"}, "approval_policy": "never"}}))
            check_posture(log, "read-only")


class CliSelectionTests(unittest.TestCase):
    script = Path(__file__).with_name("live-check.sh")

    def test_invalid_args(self):
        for args in [["--cli"], ["--cli", "invalid"], ["--wat"]]:
            result = subprocess.run(["bash", str(self.script), *args], capture_output=True)
            self.assertEqual(result.returncode, 2)

    def test_retry_exhaustion_cannot_report_success(self):
        script = self.script.read_text()
        wrapper = "  cx(){" + script.split("  cx(){", 1)[1].split("  # cerr", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "fake-codex"
            fake.write_text('#!/bin/sh\necho \'{"type":"turn.failed","error":{"message":"flagged for possible cybersecurity risk"}}\'\nexit 0\n')
            fake.chmod(0o755)
            command = 'T=1; sleep(){ :; };\n' + wrapper + '\ncx "$1" "$1/events" "$1/fake-codex"'
            result = subprocess.run(["bash", "-c", command, "check", tmp],
                                    env=dict(os.environ, BASH_ENV="/dev/null"), capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_codex_only_does_not_call_other_vendors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["claude", "codex", "kimi"]:
                path = root / name
                path.write_text('#!/bin/sh\nprintf "%s\\n" "${0##*/}" >> "$CALLS"\nexit 1\n')
                path.chmod(0o755)
            for name, body in [("sleep", "exit 0"), ("timeout", 'shift; exec "$@"')]:
                path = root / name
                path.write_text("#!/bin/sh\n" + body + "\n")
                path.chmod(0o755)
            calls = root / "calls"
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       CALLS=str(calls), LIVE_CHECK_EVIDENCE_DIR=tmp, BASH_ENV="/dev/null")
            subprocess.run(["bash", str(self.script), "--cli", "codex"], env=env,
                           capture_output=True, timeout=20)
            self.assertEqual(set(calls.read_text().splitlines()), {"codex"})


if __name__ == "__main__":
    unittest.main()
