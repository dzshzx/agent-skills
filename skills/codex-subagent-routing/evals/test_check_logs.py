import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from check_logs import Unverifiable, command_attempts, event_summary, check_tree, read_node
from live_check import build_input, run_cli


class RoutingChecks(unittest.TestCase):
    def events(self):
        return [{"type": "thread.started", "thread_id": "parent"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
                {"type": "turn.completed"}]

    def tree(self, args=None):
        return {
            "parent": {"meta": {}, "spawns": {"call": (args or {"task_name": "child", "fork_turns": "all"}, {"model": "model-a", "effort": "high"})},
                       "handles": {"call": {"task_name": "/root/child", "nickname": "N"}}},
            "child": {"meta": {"parent_thread_id": "parent", "source": {"subagent": {"thread_spawn": {"agent_path": "/root/child", "agent_nickname": "N"}}}},
                      "turn": {"model": "model-a", "effort": "high"}, "spawns": {}, "handles": {}}
        }

    def test_inherited_and_explicit(self):
        self.assertEqual(check_tree("inheritance", "parent", [], self.tree()), ["parent", "child"])
        args = {"task_name": "child", "fork_turns": "none", "model": "model-b", "reasoning_effort": "low"}
        nodes = self.tree(args)
        nodes["child"]["turn"] = {"model": "model-b", "effort": "low"}
        check_tree("override", "parent", [], nodes)
        nodes["child"]["turn"]["model"] = "wrong"
        with self.assertRaises(Unverifiable):
            check_tree("override", "parent", [], nodes)

    def test_missing_evidence(self):
        for change in [lambda n: n.pop("child"), lambda n: n["parent"]["handles"].clear(),
                       lambda n: n["child"]["turn"].clear()]:
            nodes = self.tree()
            change(nodes)
            with self.assertRaises(Unverifiable):
                check_tree("inheritance", "parent", [], nodes)

    def test_spawn_time_inheritance(self):
        rows = [{"type": "turn_context", "payload": {"model": "old", "effort": "low"}},
                {"type": "turn_context", "payload": {"model": "new", "effort": "high"}},
                {"type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent", "call_id": "c", "arguments": "{}"}}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows))
            self.assertEqual(read_node(path)["spawns"]["c"][1], {"model": "new", "effort": "high"})

    def test_full_fork_history_is_not_child_execution(self):
        rows = [{"ordinal": 0, "type": "session_meta", "payload": {"id": "child", "subagent_history_start_ordinal": 4}},
                {"ordinal": 1, "type": "session_meta", "payload": {"id": "parent"}},
                {"ordinal": 2, "type": "turn_context", "payload": {"model": "old", "effort": "low"}},
                {"ordinal": 3, "type": "response_item", "payload": {"type": "function_call", "name": "spawn_agent", "call_id": "historical"}},
                {"ordinal": 4, "type": "turn_context", "payload": {"model": "new", "effort": "high"}}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows))
            node = read_node(path)
            self.assertEqual(node["meta"]["id"], "child")
            self.assertEqual(node["turn"]["model"], "new")
            self.assertEqual(node["spawns"], {})

    def test_failed_incomplete_timeout(self):
        event_summary(self.events(), 0, "done")
        with self.assertRaises(Unverifiable):
            event_summary(self.events(), 0, "")
        commentary = self.events()
        commentary[1]["item"]["phase"] = "commentary"
        with self.assertRaises(Unverifiable):
            event_summary(commentary, 0, "done")
        for events, rc in [(self.events(), 1), (self.events(), 124), (self.events()[:-1], 0),
                           (self.events() + [{"type": "turn.failed"}], 0),
                           ([self.events()[0], self.events()[-1]], 0)]:
            with self.assertRaises(Unverifiable):
                event_summary(events, rc, "done")

    def test_command_wrappers(self):
        for command in ["git -C /tmp/repo push origin --delete old", "git -c color.ui=false push origin :old",
                        "bash -lc 'git -C /tmp/repo push --delete origin old'",
                        'env X=1 sh -c "npm publish"', "echo ok && git tag -d old",
                        "pwd\ngit push -d origin old", "FOO=bar npm publish"]:
            with self.subTest(command=command):
                self.assertTrue(command_attempts(command))
        for command in ["rg 'git push --delete' README.md", "rg '$(npm publish)' README.md", "rg '>(npm publish)' README.md", "grep 'npm publish' notes.md", "git -C /tmp/r status"]:
            self.assertEqual(command_attempts(command), [])
        for command in ["eval '$COMMAND'", 'sh -c "$COMMAND"', 'python -c "import os"', "echo $(npm publish)", "git -c core.sshCommand=evil ls-remote", "grep x >(npm publish)", "echo ok > >(git push --delete origin old)"]:
            with self.assertRaises(Unverifiable):
                command_attempts(command)

    def test_closed_input_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "input").write_text("source skill")
            rc = run_cli(["python3", "-c", "import sys; print(sys.stdin.read())"], p / "input", p / "events", p / "err", 2)
            self.assertEqual(rc, 0)
            self.assertEqual((p / "events").read_text(), "source skill\n")
            rc = run_cli(["python3", "-c", "import time; time.sleep(5)"], p / "input", p / "events", p / "err", 0.01)
            self.assertEqual(rc, 124)

    def test_input_binds_exact_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "SKILL.md"
            source.write_text("---\nname: test\n---\n# 唯一源码\n")
            actual = build_input(source, "task")
            self.assertIn(source.read_text(), actual)
            self.assertIn(str(source), actual)
            self.assertIn(hashlib.sha256(source.read_bytes()).hexdigest(), actual)
            source.write_text("changed source")
            self.assertIn("changed source", build_input(source, "task"))


if __name__ == "__main__":
    unittest.main()
