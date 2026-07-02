#!/usr/bin/env python3
"""Behavior tests for the trellis-mode-switcher inspector CLI."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
INSPECTOR = SKILL_DIR / "scripts" / "inspect_trellis_mode.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def inspect(repo: Path, platform: str | None = None) -> dict:
    cmd = ["python3", str(INSPECTOR), "--repo", str(repo), "--json"]
    if platform is not None:
        cmd += ["--platform", platform]
    proc = subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(proc.stdout)


class InspectTrellisModeCliTest(unittest.TestCase):
    def test_reports_only_complete_workflow_state_blocks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: inline\n")
            write(
                repo / ".trellis" / "workflow.md",
                "\n".join(
                    [
                        "# Workflow",
                        "<!-- [workflow-state:STATUS] is documentation, not a live block -->",
                        "[workflow-state:in_progress-inline]",
                        "Inline mode uses trellis-before-dev.",
                        "[/workflow-state:in_progress-inline]",
                        "```text",
                        "[workflow-state:example]",
                        "Example block in docs.",
                        "[/workflow-state:example]",
                        "```",
                    ]
                ),
            )

            report = inspect(repo)

        self.assertEqual(report["workflow_state_tags"], ["in_progress-inline"])

    def test_channel_agent_files_do_not_imply_channel_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: inline\n")
            write(
                repo / ".trellis" / "workflow.md",
                "\n".join(
                    [
                        "[workflow-state:in_progress-inline]",
                        "Inline mode uses trellis-before-dev.",
                        "[/workflow-state:in_progress-inline]",
                    ]
                ),
            )
            write(
                repo / ".trellis" / "agents" / "implement.md",
                "---\nname: implement\ndescription: worker\nprovider: codex\n---\n",
            )
            write(
                repo / ".trellis" / "agents" / "check.md",
                "---\nname: check\ndescription: worker\nprovider: codex\n---\n",
            )

            report = inspect(repo)

        self.assertEqual(report["inferred_execution_model"], "inline")
        self.assertIn(
            "Channel worker definitions exist but workflow does not mention trellis channel.",
            report["warnings"],
        )

    def test_channel_workflow_is_reported_as_channel_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(
                repo / ".trellis" / "config.yaml",
                "\n".join(
                    [
                        "channel:",
                        "  worker_guard:",
                        "    idle_timeout: 5m",
                        "    max_live_workers: 6",
                        "codex:",
                        "  dispatch_mode: inline",
                    ]
                ),
            )
            write(
                repo / ".trellis" / "workflow.md",
                "\n".join(
                    [
                        "[workflow-state:in_progress-inline]",
                        "trellis channel spawn --agent implement",
                        "[/workflow-state:in_progress-inline]",
                    ]
                ),
            )
            write(
                repo / ".trellis" / "agents" / "implement.md",
                "---\nname: implement\ndescription: channel implement worker\nprovider: codex\n---\n",
            )
            write(
                repo / ".trellis" / "agents" / "check.md",
                "---\nname: check\ndescription: channel check worker\nprovider: codex\n---\n",
            )

            report = inspect(repo)

        self.assertEqual(report["codex_dispatch_mode_effective"], "inline")
        self.assertEqual(report["inferred_execution_model"], "channel")
        self.assertTrue(report["workflow_mentions"]["trellis_channel"])
        self.assertTrue(report["channel"]["worker_guard_configured"])
        self.assertEqual(report["channel"]["agents"]["implement"]["provider"], "codex")

    def test_invalid_codex_dispatch_mode_falls_back_to_inline(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: bogus\n")
            write(
                repo / ".trellis" / "workflow.md",
                "\n".join(
                    [
                        "[workflow-state:in_progress-inline]",
                        "Inline mode uses trellis-before-dev.",
                        "[/workflow-state:in_progress-inline]",
                    ]
                ),
            )

            report = inspect(repo)

        self.assertEqual(report["codex_dispatch_mode_configured"], "bogus")
        self.assertEqual(report["codex_dispatch_mode_effective"], "inline")
        self.assertEqual(report["inferred_execution_model"], "inline")
        self.assertIn(
            "Invalid codex.dispatch_mode='bogus'; effective mode is inline.",
            report["warnings"],
        )


    def test_codex_dispatch_style_is_switchable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: sub-agent\n")
            write(
                repo / ".codex" / "agents" / "trellis-implement.toml", "name='x'\n"
            )
            write(repo / ".codex" / "agents" / "trellis-check.toml", "name='x'\n")
            write(repo / ".trellis" / "workflow.md", "codex-sub-agent\n")

            report = inspect(repo, platform="codex")

        self.assertEqual(report["triggering_platform"], "codex")
        self.assertEqual(report["axes"]["dispatch_style"]["value"], "sub-agent")
        self.assertTrue(report["axes"]["dispatch_style"]["switchable_here"])
        self.assertTrue(report["axes"]["orchestration"]["switchable_here"])

    def test_class1_platform_dispatch_style_not_switchable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: inline\n")
            write(
                repo / ".trellis" / "workflow.md",
                "[workflow-state:in_progress-inline]\nx\n[/workflow-state:in_progress-inline]\n",
            )

            report = inspect(repo, platform="claude")

        self.assertEqual(report["triggering_platform"], "claude")
        self.assertEqual(report["axes"]["dispatch_style"]["value"], "native-subagent")
        self.assertFalse(report["axes"]["dispatch_style"]["switchable_here"])
        # channel orchestration stays switchable on any platform.
        self.assertTrue(report["axes"]["orchestration"]["switchable_here"])

    def test_non_codex_platform_warns_when_dispatch_mode_set(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: sub-agent\n")
            write(
                repo / ".trellis" / "workflow.md",
                "[workflow-state:in_progress-inline]\nx\n[/workflow-state:in_progress-inline]\n",
            )

            report = inspect(repo, platform="claude")

        self.assertTrue(
            any("ignores it (Codex-only knob)" in w for w in report["warnings"]),
            report["warnings"],
        )

    def test_platform_override_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: inline\n")
            write(repo / ".trellis" / "workflow.md", "x\n")

            report = inspect(repo, platform="cursor")

        self.assertEqual(report["triggering_platform"], "cursor")
        self.assertEqual(report["platform_detection_source"], "override")
        self.assertEqual(report["axes"]["dispatch_style"]["value"], "native-subagent")

    def test_brief_output_is_compact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trellis-mode-test-") as tmp:
            repo = Path(tmp)
            write(repo / ".trellis" / "config.yaml", "codex:\n  dispatch_mode: sub-agent\n")
            write(repo / ".trellis" / "workflow.md", "codex-sub-agent\n")
            write(repo / ".codex" / "agents" / "trellis-implement.toml", "name='x'\n")
            write(repo / ".codex" / "agents" / "trellis-check.toml", "name='x'\n")

            proc = subprocess.run(
                [
                    "python3",
                    str(INSPECTOR),
                    "--repo",
                    str(repo),
                    "--platform",
                    "codex",
                    "--brief",
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("platform=codex", lines[0])
        self.assertIn("codex=sub-agent->sub-agent", lines[0])
        self.assertIn("A=sub-agent/switchable=True", lines[0])


if __name__ == "__main__":
    unittest.main()
