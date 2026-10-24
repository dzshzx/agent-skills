"""check_logs tests for spawn trees, model/effort inheritance and fork scope.

Command parsing, event summary and live_check input tests stay in
test_check_logs.py; shared fixtures live in routing_fixtures.py.
"""

import json
from pathlib import Path
import tempfile
import unittest

from check_logs import Unverifiable, check_tree, check_run, read_node
from routing_fixtures import RoutingFixtures


class InheritanceChecks(RoutingFixtures, unittest.TestCase):
    def test_inherited_and_explicit(self):
        self.assertEqual(
            check_tree("inheritance", "parent", [], self.tree()), ["parent", "child"]
        )
        args = {
            "task_name": "child",
            "fork_turns": "none",
            "model": "model-b",
            "reasoning_effort": "low",
        }
        nodes = self.tree(args)
        nodes["child"]["turn"] = {"model": "model-b", "effort": "low"}
        check_tree("override", "parent", [], nodes)
        nodes["child"]["turn"]["model"] = "wrong"
        with self.assertRaises(Unverifiable):
            check_tree("override", "parent", [], nodes)

    def test_history_fork_respects_configured_resource_defaults(self):
        nodes = self.tree()
        nodes["child"]["turn"] = {"model": "configured", "effort": "medium"}
        check_tree(
            "inheritance",
            "parent",
            [],
            nodes,
            defaults={"model": "configured", "effort": "medium"},
        )
        with self.assertRaises(Unverifiable):
            check_tree("inheritance", "parent", [], nodes)

    def test_role_model_precedes_explicit_spawn_model(self):
        nodes = self.tree(
            {
                "task_name": "child",
                "fork_turns": "none",
                "model": "requested",
                "reasoning_effort": "low",
            }
        )
        nodes["child"]["turn"] = {"model": "fixed", "effort": "low"}
        nodes["child"]["meta"]["source"]["subagent"]["thread_spawn"]["agent_role"] = (
            "default"
        )
        check_tree(
            "override",
            "parent",
            [],
            nodes,
            defaults={
                "model": "global",
                "effort": "medium",
                "roles": {"default": {"model": "fixed"}},
            },
        )

    def test_missing_evidence(self):
        for change in [
            lambda n: n.pop("child"),
            lambda n: n["parent"]["handles"].clear(),
            lambda n: n["child"]["turn"].clear(),
        ]:
            nodes = self.tree()
            change(nodes)
            with self.assertRaises(Unverifiable):
                check_tree("inheritance", "parent", [], nodes)

    def test_limits_completion_and_combinations(self):
        for change in [
            lambda n: n["child"].update(complete=False),
            lambda n: n["parent"]["spawns"].update(extra=n["parent"]["spawns"]["call"]),
            lambda n: n["parent"]["spawns"]["call"][0].update(model="model-a"),
            lambda n: n["parent"]["spawns"]["call"][0].update(fork_turns="0"),
        ]:
            nodes = self.tree()
            change(nodes)
            with self.assertRaises(Unverifiable):
                check_tree("inheritance", "parent", [], nodes)

    def test_spawn_time_inheritance(self):
        rows = [
            {"type": "turn_context", "payload": {"model": "old", "effort": "low"}},
            {"type": "turn_context", "payload": {"model": "new", "effort": "high"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "c",
                    "arguments": "{}",
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows))
            self.assertEqual(
                read_node(path)["spawns"]["c"][1], {"model": "new", "effort": "high"}
            )

    def test_full_fork_history_is_not_child_execution(self):
        rows = [
            {
                "ordinal": 0,
                "type": "session_meta",
                "payload": {"id": "child", "subagent_history_start_ordinal": 4},
            },
            {"ordinal": 1, "type": "session_meta", "payload": {"id": "parent"}},
            {
                "ordinal": 2,
                "type": "turn_context",
                "payload": {"model": "old", "effort": "low"},
            },
            {
                "ordinal": 3,
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "historical",
                },
            },
            {
                "ordinal": 4,
                "type": "turn_context",
                "payload": {"model": "new", "effort": "high"},
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows))
            node = read_node(path)
            self.assertEqual(node["meta"]["id"], "child")
            self.assertEqual(node["turn"]["model"], "new")
            self.assertEqual(node["spawns"], {})

    def test_inheritance_requires_matching_parent_history_through_loader(self):
        for defect in [
            "missing boundary",
            "invalid boundary",
            "missing history",
            "missing ordinal",
            "invalid ordinal",
            "mismatched history",
            "post-spawn history",
            None,
        ]:
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                child = self.run_fixture(root)
                if defect == "missing boundary":
                    child[0]["payload"].pop("subagent_history_start_ordinal")
                    child.pop(1)
                elif defect == "invalid boundary":
                    child[0]["payload"]["subagent_history_start_ordinal"] = "2"
                elif defect == "missing history":
                    child.pop(1)
                elif defect == "missing ordinal":
                    child[1].pop("ordinal")
                elif defect == "invalid ordinal":
                    child[1]["ordinal"] = -1
                elif defect == "mismatched history":
                    child[1]["payload"]["content"][0]["text"] = "unrelated history"
                elif defect == "post-spawn history":
                    child[1]["payload"]["content"][0]["text"] = "later history"
                    parent_path = root / "sessions" / "rollout-parent.jsonl"
                    with parent_path.open("a") as parent:
                        parent.write(
                            "\n"
                            + json.dumps(
                                {
                                    "type": "response_item",
                                    "payload": child[1]["payload"],
                                }
                            )
                        )
                (root / "sessions" / "rollout-child.jsonl").write_text(
                    "\n".join(json.dumps(r) for r in child)
                )
                if defect:
                    with self.assertRaises(Unverifiable):
                        check_run(
                            "inheritance",
                            root / "events.jsonl",
                            0,
                            root / "sessions",
                            0,
                            root / "final.txt",
                        )
                else:
                    # Parent/child ordinal differences do not change copied content.
                    self.assertEqual(
                        check_run(
                            "inheritance",
                            root / "events.jsonl",
                            0,
                            root / "sessions",
                            0,
                            root / "final.txt",
                        )["thread_id"],
                        "parent",
                    )

    def test_inheritance_does_not_accept_metadata_only(self):
        nodes = self.tree()
        nodes["child"].pop("inherited_history")
        with self.assertRaises(Unverifiable):
            check_tree("inheritance", "parent", [], nodes)

    def test_bounded_fork_checks_the_requested_scope(self):
        # Numeric scope: the dispatching turn plus the N-1 turns before it.
        cases = [
            ("2", ["u1", "a1", "u2"], None),
            ("2", ["u1", "a1", "u2", "c2"], None),
            ("1", ["u2"], None),
            ("2", ["u1"], "does not cover"),
            ("2", ["u2"], "does not cover"),
            ("2", ["u1", "u2"], "does not cover"),
            ("1", ["u1"], "exceeds"),
            ("1", ["u1", "a1", "u2"], "exceeds"),
        ]
        for fork, inherited, failure in cases:
            with (
                self.subTest(fork=fork, inherited=inherited),
                tempfile.TemporaryDirectory() as tmp,
            ):
                if failure is None:
                    self.scope_fixture(Path(tmp), fork, inherited)
                else:
                    with self.assertRaisesRegex(Unverifiable, failure):
                        self.scope_fixture(Path(tmp), fork, inherited)
        # The argument binding is still checked independently of coverage.
        nodes = self.tree({"task_name": "child", "fork_turns": "2"})
        check_tree("inheritance", "parent", [], nodes, inheritance_fork="2")
        with self.assertRaises(Unverifiable):
            check_tree("inheritance", "parent", [], nodes)

    def test_full_fork_must_cover_every_turn_before_dispatch(self):
        # Assistant messages of the in-progress dispatching turn are optional.
        for inherited in (["u1", "a1", "u2"], ["u1", "a1", "u2", "c2"]):
            with (
                self.subTest(inherited=inherited),
                tempfile.TemporaryDirectory() as tmp,
            ):
                self.scope_fixture(Path(tmp), "all", inherited)
        cases = [
            (["u1"], "does not cover"),
            (["u1", "a1"], "does not cover"),
            (["a1", "u2"], "does not cover"),
            (["u2"], "does not cover"),
            (["u2", "c2"], "does not cover"),
            (["u2", "u1"], "does not match"),
            ([], "missing inherited"),
        ]
        for inherited, failure in cases:
            with (
                self.subTest(inherited=inherited),
                tempfile.TemporaryDirectory() as tmp,
            ):
                with self.assertRaisesRegex(Unverifiable, failure):
                    self.scope_fixture(Path(tmp), "all", inherited)

    def test_unprovable_parent_history_is_unverifiable(self):
        cases = [
            ("compacted", [("compacted", {"message": "summary"})]),
            ("compacted", [("event_msg", {"type": "context_compacted"})]),
            ("compacted", [("event_msg", {"type": "thread_rolled_back"})]),
            ("compacted", [("event_msg", {"type": "undo_completed"})]),
        ]
        for fork in ("all", "2"):
            for failure, parent_rows in cases:
                with (
                    self.subTest(fork=fork, rows=parent_rows),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    with self.assertRaisesRegex(Unverifiable, failure):
                        self.scope_fixture(
                            Path(tmp), fork, ["u1", "a1", "u2"], parent_rows
                        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.scope_fixture(root, "all", ["u1", "a1", "u2"])
            # Without any turn-start event the parent's turns cannot be split.
            path = root / "sessions" / "rollout-parent.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows = [
                r
                for r in rows
                if r["type"] != "event_msg" or r["payload"]["type"] != "task_started"
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows))
            with self.assertRaisesRegex(Unverifiable, "outside turn boundaries"):
                check_run(
                    "inheritance",
                    root / "events.jsonl",
                    0,
                    root / "sessions",
                    0,
                    root / "final.txt",
                )


if __name__ == "__main__":
    unittest.main()
