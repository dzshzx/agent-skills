import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import version_plan  # noqa: E402


SCRIPT = Path(__file__).resolve().parents[1] / "version_plan.py"


class VersionPlanTest(unittest.TestCase):
    def test_canonical_json_is_stable(self):
        plan = {
            "repository": "dzshzx/example",
            "schema": 1,
            "versions": [
                {"baseline": "1.2.3", "namespace": "v", "target": "1.3.0"}
            ],
        }
        self.assertEqual(
            version_plan.canonical_json(plan),
            '{"repository":"dzshzx/example","schema":1,"versions":'
            '[{"baseline":"1.2.3","namespace":"v","target":"1.3.0"}]}',
        )

    def test_repository_urls_normalize_to_owner_repo(self):
        for remote in (
            "https://github.com/DzShZx/agent-skills.git",
            "ssh://git@github.com/dzshzx/agent-skills.git",
            "git@github.com:dzshzx/agent-skills.git",
        ):
            with self.subTest(remote=remote):
                self.assertEqual(
                    version_plan.normalize_repository(remote), "dzshzx/agent-skills"
                )

    def test_any_forward_increment_is_planned_and_target_tag_is_excluded(self):
        for target in ("1.2.4", "1.2.5", "1.3.0", "2.0.0"):
            with self.subTest(target=target):
                plan = version_plan.build_plan(
                    "dzshzx/example",
                    {"v": version_plan.Version.parse(target)},
                    {"v1.2.3", f"v{target}", "unrelated-9.9.9"},
                    {f"v{target}"},
                )
                self.assertEqual(
                    plan["versions"],
                    [{"namespace": "v", "baseline": "1.2.3", "target": target}],
                )

    def test_unknown_baseline_and_downgrade_fail_closed(self):
        with self.assertRaisesRegex(version_plan.PlanError, "baseline .* is unknown"):
            version_plan.build_plan(
                "dzshzx/example", {"v": version_plan.Version.parse("1.0.0")}, set()
            )
        with self.assertRaisesRegex(version_plan.PlanError, "downgrade is not allowed"):
            version_plan.build_plan(
                "dzshzx/example",
                {"v": version_plan.Version.parse("1.2.2")},
                {"v1.2.3"},
            )

    def test_published_tag_cannot_be_reused(self):
        with self.assertRaisesRegex(version_plan.PlanError, "already published"):
            version_plan.build_plan(
                "dzshzx/example",
                {"v": version_plan.Version.parse("1.2.3")},
                {"v1.2.2", "v1.2.3"},
            )

    def test_targets_are_complete_unique_and_namespace_sorted(self):
        targets = version_plan.parse_targets(["z/=2.0.1", "a/=1.0.1"])
        plan = version_plan.build_plan(
            "dzshzx/example", targets, {"z/2.0.0", "a/1.0.0"}
        )
        self.assertEqual([item["namespace"] for item in plan["versions"]], ["a/", "z/"])
        with self.assertRaisesRegex(version_plan.PlanError, "at least one"):
            version_plan.parse_targets([])
        with self.assertRaisesRegex(version_plan.PlanError, "duplicate"):
            version_plan.parse_targets(["v=1.0.0", "v=1.0.1"])


class VersionPlanCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo = root / "repo"
        self.remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", self.remote], check=True)
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        Path(self.repo, "fixture").write_text("fixture\n", encoding="utf-8")
        self.git("add", "fixture")
        self.git("commit", "-qm", "fixture")
        self.origin_url = "https://github.com/dzshzx/example.git"
        self.git("remote", "add", "origin", self.origin_url)
        self.git("config", f"url.{self.remote.as_uri()}.insteadOf", self.origin_url)
        self.tag("v1.2.3", "Release v1.2.3")
        self.git("push", "-q", "origin", "HEAD:refs/heads/master", "v1.2.3")

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, text=True
        )

    def tag(self, name: str, *messages: str) -> None:
        command = ["tag", "-a", name]
        for message in messages:
            command.extend(("-m", message))
        self.git(*command)

    def cli(self, command: str, target: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, SCRIPT, command, "--repository", "dzshzx/example",
             "--target", f"v={target}", *extra],
            cwd=self.repo,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_cli_plan_prints_baseline_and_target(self):
        result = self.cli("plan", "1.3.0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("v: 1.2.3 -> 1.3.0", result.stdout)

    def test_cli_verifies_patch_minor_and_major_without_extra_input(self):
        for target in ("1.2.4", "1.3.0", "2.0.0"):
            with self.subTest(target=target):
                self.tag(f"v{target}", f"Release v{target}")
                self.git("push", "-q", "origin", f"v{target}")
                result = self.cli("verify", target, "--tag-ref", f"refs/tags/v{target}")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_ignores_legacy_approval_trailers(self):
        legacy = (
            ("1.3.0", "Version-Approval: sha256:" + "a" * 64),
            ("1.4.0", "Version-Approval: approved"),
        )
        for target, trailer in legacy:
            with self.subTest(trailer=trailer):
                self.tag(f"v{target}", f"Release v{target}", trailer, trailer)
                result = self.cli("verify", target, "--tag-ref", f"refs/tags/v{target}")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_rejects_lightweight_tag_and_local_only_baseline(self):
        self.git("tag", "v1.2.4")
        result = self.cli("verify", "1.2.4", "--tag-ref", "refs/tags/v1.2.4")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("annotated", result.stderr)
        self.tag("v1.9.0", "Local only")
        planned = self.cli("plan", "1.3.0")
        self.assertIn("v: 1.2.3 -> 1.3.0", planned.stdout)

    def test_cli_rejects_reusing_a_published_tag(self):
        result = self.cli("plan", "1.2.3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already published", result.stderr)


if __name__ == "__main__":
    unittest.main()
