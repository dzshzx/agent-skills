"""Exercise tool provisioning and the offline entrypoint with an isolated PATH."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CiToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binaries = self.root / "bin"
        self.binaries.mkdir()
        for name in ("sh", "dirname"):
            (self.binaries / name).symlink_to(shutil.which(name))
        self.calls = self.root / "calls.jsonl"
        self.env = {
            **os.environ,
            "PATH": str(self.binaries),
            "BASH_ENV": "/dev/null",
            "RIPGREP_CONFIG_PATH": "",
            "CALL_RECORD": str(self.calls),
            "TOOLS_DIR": str(self.binaries),
        }

    def executable(self, name, script):
        file = self.binaries / name
        file.write_text(script)
        file.chmod(0o755)

    def install_script(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        marker = "      - name: Install required system tools\n        run: |\n"
        self.assertTrue(
            marker in workflow,
            "workflow must explicitly provision required system tools",
        )
        body = []
        for line in workflow.split(marker, 1)[1].splitlines():
            if not line.startswith("          "):
                break
            body.append(line)
        return textwrap.dedent("\n".join(body))

    def package_manager(self, *, install=True):
        for binary in ("rg", "shellcheck"):
            source = shutil.which(binary)
            self.assertIsNotNone(source, f"test prerequisite missing: {binary}")
            self.env[f"SOURCE_{binary.upper()}"] = source
        self.env["INSTALL_TOOLS"] = "1" if install else "0"
        self.executable("sudo", '#!/bin/sh\nexec "$@"\n')
        self.executable(
            "apt-get",
            f"#!{sys.executable}\n"
            + textwrap.dedent("""\
                import json, os
                from pathlib import Path
                import sys
                args = sys.argv[1:]
                with open(os.environ["CALL_RECORD"], "a") as record:
                    record.write(json.dumps(args) + "\\n")
                if args == ["update"]:
                    sys.exit(0)
                if not args or args[0] != "install":
                    sys.exit(2)
                packages = [arg for arg in args[1:] if not arg.startswith("-")]
                tools = {"ripgrep": "rg", "shellcheck": "shellcheck"}
                for package in packages:
                    binary = tools[package]
                    if os.environ["INSTALL_TOOLS"] == "1":
                        (Path(os.environ["TOOLS_DIR"]) / binary).symlink_to(
                            os.environ["SOURCE_" + binary.upper()]
                        )
                """),
        )

    def run_bash(self, *args, cwd=ROOT):
        return subprocess.run(
            [shutil.which("bash"), *args],
            cwd=cwd,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_missing_rg_fails_before_running_locked_environment(self):
        self.executable(
            "uv",
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALL_RECORD"\n',
        )
        result = self.run_bash("scripts/check-offline.sh")
        self.assertEqual(result.returncode, 127, result.stdout + result.stderr)
        self.assertIn("rg", result.stderr)
        self.assertIn("ripgrep", result.stderr)
        self.assertFalse(self.calls.exists(), "uv ran before the dependency check")

    def test_ci_provisions_tools_and_the_real_routing_regression_passes(self):
        script = self.install_script()
        self.package_manager()
        self.assertIsNone(shutil.which("rg", path=self.env["PATH"]))
        self.assertIsNone(shutil.which("shellcheck", path=self.env["PATH"]))
        result = self.run_bash("-e", "-c", script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNotNone(shutil.which("rg", path=self.env["PATH"]))
        self.assertIsNotNone(shutil.which("shellcheck", path=self.env["PATH"]))
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(calls[0], ["update"])
        self.assertEqual(calls[1][0], "install")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "test_check_logs.RoutingChecks."
                "test_quoted_search_patterns_really_match_and_full_check_accepts_them",
            ],
            cwd=ROOT / "skills/codex-subagent-routing/evals",
            env=self.env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_ci_checks_tools_when_package_manager_did_not_make_them_available(self):
        script = self.install_script()
        self.package_manager(install=False)
        result = self.run_bash("-e", "-c", script)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("rg", result.stderr)


if __name__ == "__main__":
    unittest.main()
