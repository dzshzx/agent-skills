import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from check_logs import Unverifiable
import live_check


class LiveScenarioSelection(unittest.TestCase):
    def test_inheritance_scope_is_explicit_and_never_none(self):
        self.assertEqual(live_check.parse_args([]).inheritance_fork, "all")
        self.assertEqual(
            live_check.parse_args(["--inheritance-fork", "3"]).inheritance_fork, "3"
        )
        for value in ["none", "0", "-1", "unbounded"]:
            with self.subTest(value=value), self.assertRaises(SystemExit):
                live_check.parse_args(["--inheritance-fork", value])

    def run_main(self, root, args, check_effect=None):
        def git_read(command):
            return b"" if "status" in command else b"fixture refs"

        with (
            patch.object(live_check.tempfile, "mkdtemp", return_value=str(root)),
            patch.object(
                live_check, "fixture", return_value=(root / "repo", root / "remote.git")
            ),
            patch.object(live_check.subprocess, "check_output", side_effect=git_read),
            patch.object(live_check, "routing_defaults", return_value={}),
            patch.object(live_check, "run_cli", return_value=0) as run,
            patch.object(
                live_check,
                "check_run",
                side_effect=check_effect,
                return_value={"thread_id": "parent", "rollouts": []},
            ) as check,
        ):
            rc = live_check.main(args)
        return rc, run, check, json.loads((root / "results.json").read_text())

    def test_skipped_inheritance_leaves_overall_acceptance_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, run, _, results = self.run_main(
                Path(tmp),
                [
                    "--skip-inheritance",
                    "rendered schema and host policy have no common historical fork",
                ],
            )
        self.assertEqual(rc, 3)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(results["inheritance"]["result"], "SKIP")
        self.assertIn("no common historical fork", results["inheritance"]["reason"])
        self.assertEqual(results["override"]["result"], "PASS")
        self.assertEqual(results["irreversible"]["result"], "PASS")

    def test_fork_scope_is_bound_to_prompt_and_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc, _, check, results = self.run_main(
                root, ["--scenario", "inheritance", "--inheritance-fork", "3"]
            )
            self.assertIn(
                'fork_turns="3"', (root / "inheritance.input.txt").read_text()
            )
        self.assertEqual(rc, 0)
        self.assertEqual(check.call_args.kwargs["inheritance_fork"], "3")
        self.assertEqual(results["inheritance"]["inheritance_fork"], "3")

    def test_blocked_or_missing_evidence_is_unverifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _, _, results = self.run_main(
                Path(tmp),
                ["--scenario", "inheritance"],
                Unverifiable("host rejected historical fork"),
            )
        self.assertEqual(rc, 3)
        self.assertEqual(results["inheritance"]["result"], "UNVERIFIABLE")

    def test_skip_requires_selected_inheritance_and_reason(self):
        for args in [
            ["--skip-inheritance", " "],
            ["--scenario", "override", "--skip-inheritance", "unavailable"],
        ]:
            with self.subTest(args=args), self.assertRaises(SystemExit):
                live_check.parse_args(args)


if __name__ == "__main__":
    unittest.main()
