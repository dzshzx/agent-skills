import copy
import json
from pathlib import Path
import tempfile
import unittest

from task_skill_check import INSTRUCTION, RESULT, check, prepare
from check_logs import Unverifiable
from usage_report import load_threads, own_rows, report, timestamp


def row(kind, payload, ordinal=1):
    return {"type": kind, "payload": payload, "ordinal": ordinal,
            "timestamp": f"2026-09-12T00:00:{ordinal:02d}Z"}


class UsageTests(unittest.TestCase):
    def node(self, tier="priority"):
        usage = {"input_tokens": 100, "cached_input_tokens": 60,
                 "output_tokens": 20, "reasoning_output_tokens": 10}
        token = row("event_msg", {"type": "token_count", "response_id": "r1",
                    "info": {"last_token_usage": usage, "total_token_usage": usage}}, 2)
        return {"meta": {"id": "p"}, "files": [],
                "rows": [row("turn_context", {"model": "model-a", "effort": "high", "service_tier": tier}),
                         token, copy.deepcopy(token)]}

    def test_dedup_and_reasoning(self):
        result = report({"p": self.node()})
        self.assertEqual(result["observed_responses"], 1)
        self.assertEqual(result["totals"]["output_tokens"], 20)
        self.assertEqual(result["threads"][0]["first_request_input"], 100)

    def test_legacy_and_missing(self):
        node = self.node(None)
        for r in node["rows"][1:]:
            r["payload"].pop("response_id", None)
        result = report({"p": node})
        self.assertEqual(result["observed_responses"], 1)
        self.assertIn("service_tier", result["threads"][0]["missing"])
        self.assertIsNone(result["cost"])

    def test_tier_pricing_and_partial_total(self):
        prices = {"rates": [{"model": "model-a", "service_tier": "priority",
                  "input_per_million": 10, "cached_input_per_million": 2, "output_per_million": 20}]}
        result = report({"p": self.node()}, prices=prices)
        self.assertAlmostEqual(result["cost"], .00092)
        result = report({"p": self.node(), "q": self.node(None)}, prices=prices)
        self.assertIsNone(result["cost"])
        self.assertAlmostEqual(result["known_cost_subtotal"], .00092)

    def test_tree_and_time(self):
        parent, child = self.node(), self.node()
        child["meta"] = {"id": "c", "parent_thread_id": "p"}
        result = report({"p": parent, "c": child}, "p")
        self.assertEqual(len(result["threads"]), 2)
        self.assertEqual(result["observed_responses"], 2)
        result = report({"p": parent}, since=timestamp("2026-09-12T00:00:03Z"))
        self.assertEqual(result["observed_responses"], 0)
        repeated = self.node()
        repeated["rows"][-1]["timestamp"] = "2026-09-12T00:00:04Z"
        result = report({"p": repeated}, since=timestamp("2026-09-12T00:00:03Z"))
        self.assertEqual(result["observed_responses"], 0)

    def test_boundary_and_duplicate_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [row("session_meta", {"id": "c", "subagent_history_start_ordinal": 3}, 0),
                    *self.node()["rows"][:2], row("turn_context", {"model": "child"}, 3)]
            for name in ("rollout-a.jsonl", "rollout-copy.jsonl"):
                (root / name).write_text("".join(json.dumps(r) + "\n" for r in rows))
            threads = load_threads([root])
            self.assertEqual(len(threads["c"]["rows"]), 1)
            self.assertEqual(report(threads)["observed_responses"], 0)
            rows[1].pop("ordinal")
            with self.assertRaises(ValueError):
                own_rows(rows)

    def test_conflicting_usage(self):
        node = self.node()
        node["rows"][-1]["payload"]["info"]["last_token_usage"]["output_tokens"] = 21
        with self.assertRaises(ValueError):
            report({"p": node})

    def test_unicode_separator_and_zero_compaction_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            node = self.node()
            rows = [row("session_meta", {"id": "p"}, 0), *node["rows"][:2]]
            rows.append(row("event_msg", {"type": "agent_message", "message": "a\u2028b"}, 3))
            zero = copy.deepcopy(rows[2])
            zero["ordinal"] = 4
            zero["payload"]["info"]["last_token_usage"] = {
                "input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0, "total_tokens": 123}
            rows.append(zero)
            (Path(tmp) / "rollout-p.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
            self.assertEqual(report(load_threads([tmp]))["observed_responses"], 1)


class SkillEvidenceTests(unittest.TestCase):
    def rows(self, root):
        entry = root / ".agents/skills/routing-stamp/SKILL.md"
        script = root / ".agents/skills/routing-stamp/stamp.py"
        return [
            row("session_meta", {"id": "c", "parent_thread_id": "p"}, 0),
            row("response_item", {"type": "function_call", "name": "exec_command",
                "call_id": "read", "arguments": json.dumps({"cmd": f"cat {entry}"})}, 1),
            row("response_item", {"type": "function_call_output", "call_id": "read",
                "output": json.dumps({"exit_code": 0, "output": INSTRUCTION})}, 2),
            row("response_item", {"type": "function_call", "name": "exec_command",
                "call_id": "run", "arguments": json.dumps({"cmd": f"python3 {script}"})}, 3),
            row("response_item", {"type": "function_call_output", "call_id": "run",
                "output": json.dumps({"exit_code": 0, "output": RESULT})}, 4),
            row("response_item", {"type": "message", "role": "assistant", "phase": "final",
                "content": [{"text": RESULT}]}, 5),
            row("event_msg", {"type": "task_complete"}, 6),
        ]

    def test_explicit_natural_and_read_without_execution(self):
        root = Path("/tmp/fixture")
        rows = self.rows(root)
        for case in ("explicit", "natural"):
            self.assertEqual(check(case, rows, root)["result"], "PASS")
            with self.assertRaises(Unverifiable):
                check(case, rows[:3] + rows[5:], root)

    def test_parent_and_inherited_reads_rejected(self):
        root = Path("/tmp/fixture")
        rows = self.rows(root)
        rows[0]["payload"].pop("parent_thread_id")
        with self.assertRaises(Unverifiable):
            check("explicit", rows, root)

    def test_code_mode_result_attribution(self):
        root = Path("/tmp/fixture")
        rows = self.rows(root)
        for idx in (1, 3):
            call = rows[idx]["payload"]
            call.update(type="custom_tool_call", name="exec",
                        input="text(await tools.exec_command(" + call.pop("arguments") + "));")
            output = rows[idx + 1]["payload"]
            output.update(type="custom_tool_call_output", output=[
                {"type": "input_text", "text": "Script completed\nOutput:\n"},
                {"type": "input_text", "text": output["output"]}])
        check("natural", rows, root)
        rows[1]["payload"]["input"] = "text('I read it')"
        with self.assertRaises(Unverifiable):
            check("natural", rows, root)
        rows = self.rows(root)
        rows[0]["payload"]["subagent_history_start_ordinal"] = 3
        with self.assertRaises(Unverifiable):
            check("explicit", rows, root)

    def test_failed_read_completion_and_result(self):
        root = Path("/tmp/fixture")
        for mutate in [
            lambda r: r.pop(),
            lambda r: r[2]["payload"].update(output=json.dumps({"exit_code": 1, "output": INSTRUCTION})),
            lambda r: r[5]["payload"].update(content=[{"text": "I used the skill"}]),
        ]:
            rows = self.rows(root)
            mutate(rows)
            with self.assertRaises(Unverifiable):
                check("explicit", rows, root)

    def test_unrelated_missing_and_prepare(self):
        root = Path("/tmp/fixture")
        rows = self.rows(root)
        unrelated = [rows[0], rows[5], rows[6]]
        unrelated[1]["payload"]["content"] = [{"text": "42"}]
        check("unrelated", unrelated, root)
        rows = self.rows(root)
        rows[1]["payload"]["arguments"] = json.dumps({"cmd": f"cat {root}/absent-stamp/SKILL.md"})
        rows[2]["payload"]["output"] = json.dumps({"exit_code": 1, "output": "No such file"})
        rows[5]["payload"]["content"] = [{"text": "Required skill entry is missing."}]
        check("missing", rows[:3] + rows[5:], root)
        with tempfile.TemporaryDirectory() as tmp:
            prompts = prepare(Path(tmp) / "fixture")
            self.assertEqual(set(prompts), {"explicit", "natural", "unrelated", "missing"})
            self.assertNotIn("routing-stamp", prompts["natural"])


if __name__ == "__main__":
    unittest.main()
