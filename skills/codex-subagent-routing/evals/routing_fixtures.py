"""Shared fixtures for the check_logs tests.

RoutingFixtures is a mixin, not a TestCase, so unittest discovery does not
collect it on its own. Test classes combine it with unittest.TestCase.
"""

import json

from check_logs import check_run


class RoutingFixtures:
    def events(self):
        return [
            {"type": "thread.started", "thread_id": "parent"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "done"},
            },
            {"type": "turn.completed"},
        ]

    def tree(self, args=None):
        history = {
            "type": "message",
            "role": "user",
            "content": [{"text": "read links"}],
        }
        return {
            "parent": {
                "meta": {},
                "spawns": {
                    "call": (
                        args or {"task_name": "child", "fork_turns": "all"},
                        {"model": "model-a", "effort": "high"},
                    )
                },
                "handles": {"call": {"task_name": "/root/child", "nickname": "N"}},
                "spawn_history": {"call": {"turns": [[history]], "gap": None}},
            },
            "child": {
                "meta": {
                    "parent_thread_id": "parent",
                    "subagent_history_start_ordinal": 2,
                    "source": {
                        "subagent": {
                            "thread_spawn": {
                                "agent_path": "/root/child",
                                "agent_nickname": "N",
                            }
                        }
                    },
                },
                "turn": {"model": "model-a", "effort": "high"},
                "spawns": {},
                "handles": {},
                "complete": True,
                "inherited_history": [history],
            },
        }

    def run_fixture(self, root, command=None):
        """Complete loader fixture, including parent history and child boundary."""

        def row(kind, payload, ordinal):
            return {"type": kind, "payload": payload, "ordinal": ordinal}

        history = {
            "type": "message",
            "role": "user",
            "content": [{"text": "read links"}],
        }
        parent = [
            row("session_meta", {"id": "parent"}, 0),
            row("event_msg", {"type": "task_started"}, 1),
            row("turn_context", {"model": "model-a", "effort": "high"}, 1),
            row("response_item", history, 2),
        ]
        if command is None:
            parent.extend(
                [
                    row(
                        "response_item",
                        {
                            "type": "function_call",
                            "name": "spawn_agent",
                            "call_id": "call",
                            "arguments": {"task_name": "child", "fork_turns": "all"},
                        },
                        3,
                    ),
                    row(
                        "response_item",
                        {
                            "type": "function_call_output",
                            "call_id": "call",
                            "output": {"agent_id": "child"},
                        },
                        4,
                    ),
                ]
            )
        child = [
            row(
                "session_meta",
                {
                    "id": "child",
                    "parent_thread_id": "parent",
                    "subagent_history_start_ordinal": 2,
                },
                0,
            ),
            row("response_item", history, 1),
            row("turn_context", {"model": "model-a", "effort": "high"}, 2),
            row(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final",
                    "content": [{"text": "child done"}],
                },
                3,
            ),
            row("event_msg", {"type": "task_complete"}, 4),
        ]
        parent[3]["timestamp"] = "2026-10-09T00:00:00Z"
        child[1]["timestamp"] = "2026-10-09T00:00:01Z"
        events = self.events()
        if command is not None:
            events.insert(
                1,
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": command},
                },
            )
        sessions = root / "sessions"
        sessions.mkdir()
        (root / "events.jsonl").write_text("\n".join(json.dumps(r) for r in events))
        (root / "final.txt").write_text("done")
        (sessions / "rollout-parent.jsonl").write_text(
            "\n".join(json.dumps(r) for r in parent)
        )
        if command is None:
            (sessions / "rollout-child.jsonl").write_text(
                "\n".join(json.dumps(r) for r in child)
            )
        return child

    def scope_fixture(self, root, fork, inherited, parent_rows=()):
        """Two parent turns: turn 1 completed, dispatch inside turn 2."""
        texts = {
            "u1": ("user", "turn one: read README", None),
            "a1": ("assistant", "turn one done", "final_answer"),
            "u2": ("user", "turn two: also check notes", None),
            "c2": ("assistant", "checking notes", "commentary"),
        }

        def message(key):
            role, text, phase = texts[key]
            item = {"type": "message", "role": role, "content": [{"text": text}]}
            return {**item, "phase": phase} if phase else item

        def rows(items):
            return [
                {"type": kind, "payload": payload, "ordinal": n}
                for n, (kind, payload) in enumerate(items)
            ]

        context = ("turn_context", {"model": "model-a", "effort": "high"})
        parent = [
            ("session_meta", {"id": "parent"}),
            ("event_msg", {"type": "task_started"}),
            context,
            ("response_item", message("u1")),
            ("response_item", message("a1")),
            ("event_msg", {"type": "task_complete"}),
            *parent_rows,
            ("event_msg", {"type": "task_started"}),
            context,
            ("response_item", message("u2")),
            ("response_item", message("c2")),
            (
                "response_item",
                {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "call",
                    "arguments": json.dumps({"task_name": "child", "fork_turns": fork}),
                },
            ),
            (
                "response_item",
                {
                    "type": "function_call_output",
                    "call_id": "call",
                    "output": json.dumps({"agent_id": "child"}),
                },
            ),
        ]
        child = [
            (
                "session_meta",
                {
                    "id": "child",
                    "parent_thread_id": "parent",
                    "subagent_history_start_ordinal": 1 + len(inherited),
                },
            ),
            *(("response_item", message(key)) for key in inherited),
            context,
            (
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final",
                    "content": [{"text": "child done"}],
                },
            ),
            ("event_msg", {"type": "task_complete"}),
        ]
        sessions = root / "sessions"
        sessions.mkdir()
        for name, items in (("parent", parent), ("child", child)):
            (sessions / f"rollout-{name}.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows(items))
            )
        (root / "events.jsonl").write_text(
            "\n".join(json.dumps(r) for r in self.events())
        )
        (root / "final.txt").write_text("done")
        return check_run(
            "inheritance",
            root / "events.jsonl",
            0,
            root / "sessions",
            0,
            root / "final.txt",
            inheritance_fork=fork,
        )
