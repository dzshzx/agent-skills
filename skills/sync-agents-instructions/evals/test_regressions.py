import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scope_evidence import check, git, snapshot

VALIDATOR = Path(__file__).resolve().parents[1] / "scripts/validate_config.py"
spec = importlib.util.spec_from_file_location("validate_config", VALIDATOR)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ConfigTests(unittest.TestCase):
    def test_paths_and_enums_in_both_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "exists"
            path.touch()
            data = {"workspace": {"project_globs": [temp]}, "shared_sources": [
                {"path": str(path), "role": "rules", "domain": "all", "load": "always"}],
                "agents": [{"name": "codex", "entry_file": str(path),
                            "project_instruction_file": "AGENTS.md", "always_load_mode": "native"}]}
            for mode in (False, True):
                for surface in ("..", "x/../..", ".", "x/..", "../AGENTS.md"):
                    case = copy.deepcopy(data)
                    case["agents"][0]["project_instruction_file"] = surface
                    self.assertTrue(any("must stay inside" in e for e in validator.Checker(case, mode).run()))
                for surface in ("AGENTS.md", "docs/AGENTS.md", "docs/../AGENTS.md"):
                    case = copy.deepcopy(data)
                    case["agents"][0]["project_instruction_file"] = surface
                    self.assertEqual(validator.Checker(case, mode).run(), [])
                for value in ([], {}, True, 1, "invalid"):
                    case = copy.deepcopy(data)
                    case["shared_sources"][0]["load"] = value
                    case["agents"][0]["always_load_mode"] = value
                    errors = validator.Checker(case, mode).run()
                    self.assertTrue(any("shared_sources[0].load:" in e for e in errors))
                    self.assertTrue(any("agents[codex].always_load_mode:" in e for e in errors))
                for load in validator.LOAD_MODES:
                    for always in validator.ALWAYS_LOAD_MODES:
                        case = copy.deepcopy(data)
                        case["shared_sources"][0]["load"] = load
                        case["agents"][0]["always_load_mode"] = always
                        self.assertEqual(validator.Checker(case, mode).run(), [])

    def test_cli_exit_contract_and_no_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            base = f'''[workspace]
project_globs = ["."]
[[shared_sources]]
path = {json.dumps(str(path))}
role = "rules"
domain = "all"
load = LOAD
[[agents]]
name = "codex"
entry_file = {json.dumps(str(path))}
project_instruction_file = "AGENTS.md"
always_load_mode = MODE
'''
            for flags in ([], ["--schema-only"]):
                for value, expected in [('"always"', 0), ('[]', 1), ('{}', 1), ('true', 1), ('42', 1)]:
                    mode = '"native"' if expected == 0 else value
                    path.write_text(base.replace("LOAD", value).replace("MODE", mode))
                    result = subprocess.run([sys.executable, str(VALIDATOR), *flags, str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                result = subprocess.run([sys.executable, str(VALIDATOR), *flags, str(path) + ".missing"], capture_output=True)
                self.assertEqual(result.returncode, 2)
            self.assertEqual(subprocess.run([sys.executable, str(VALIDATOR), "--bad"], capture_output=True).returncode, 2)

    def test_off_limits_env_references_must_be_set(self):
        data = {"workspace": {"project_globs": ["."], "off_limits": []},
                "shared_sources": [{"path": "rules.md", "role": "rules", "domain": "all", "load": "always"}],
                "agents": [{"name": "codex", "entry_file": "AGENTS.md",
                            "project_instruction_file": "AGENTS.md", "always_load_mode": "native"}]}
        unset = "SYNC_TEST_UNSET_VAR"
        for pattern, var in (("$SYNC_TEST_UNSET_VAR/private/**", unset), ("${SYNC_TEST_UNSET_VAR}/**", unset)):
            for environment, expected in (({}, "unset"), ({var: ""}, "empty"), ({var: "/srv/data"}, None)):
                with mock.patch.dict(os.environ, environment):
                    if not environment:
                        os.environ.pop(var, None)
                    case = copy.deepcopy(data)
                    case["workspace"]["off_limits"] = ["**/docs/agents/**", pattern]
                    errors = validator.Checker(case, False).run()
                    if expected is None:
                        self.assertEqual(errors, [])
                    else:
                        self.assertEqual(errors, [f"workspace.off_limits: {pattern!r} references {expected} environment variable ${var}"])
        with mock.patch.dict(os.environ, {"SYNC_TEST_SET_VAR": "/srv"}):
            os.environ.pop(unset, None)
            case = copy.deepcopy(data)
            case["workspace"]["off_limits"] = ["$SYNC_TEST_SET_VAR/$SYNC_TEST_UNSET_VAR/**", "${SYNC_TEST_SET_VAR/**"]
            errors = validator.Checker(case, False).run()
            self.assertEqual(len(errors), 2, errors)
            self.assertIn("unset environment variable $SYNC_TEST_UNSET_VAR", errors[0])
            self.assertIn("unterminated variable reference ${SYNC_TEST_SET_VAR/**", errors[1])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text(f'''[workspace]
project_globs = ["."]
off_limits = ["${{{unset}}}/**"]
[[shared_sources]]
path = {json.dumps(str(path))}
role = "rules"
domain = "all"
load = "always"
[[agents]]
name = "codex"
entry_file = {json.dumps(str(path))}
project_instruction_file = "AGENTS.md"
always_load_mode = "native"
''')
            for flags in ([], ["--schema-only"]):
                env = {k: v for k, v in os.environ.items() if k != unset}
                result = subprocess.run([sys.executable, str(VALIDATOR), *flags, str(path)],
                                        capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"unset environment variable ${unset}", result.stderr)
                result = subprocess.run([sys.executable, str(VALIDATOR), *flags, str(path)],
                                        capture_output=True, text=True, env={**env, unset: temp})
                self.assertEqual(result.returncode, 0, result.stderr)


class ScopeTests(unittest.TestCase):
    def test_clean_committed_and_reverted_out_of_scope_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            git(repo, "init", "-q")
            git(repo, "config", "user.name", "test")
            git(repo, "config", "user.email", "test@localhost")
            (repo / "CLAUDE.md").write_text("rules\n")
            (repo / "protected.txt").write_text("original\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "initial")
            before = snapshot(repo)
            self.assertEqual(check(repo, before, set()), [])
            (repo / "protected.txt").write_text("modified\n")
            git(repo, "commit", "-qam", "out of scope")
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            self.assertTrue(check(repo, before, set()))
            git(repo, "revert", "--no-edit", "HEAD")
            self.assertTrue(any("commit" in e for e in check(repo, before, {"CLAUDE.md"})))
            # A fresh stage baseline permits existing history, but detects inventory changes.
            before = snapshot(repo)
            (repo / "untracked").write_text("new")
            self.assertTrue(check(repo, before, set()))
            (repo / "untracked").unlink()
            (repo / "CLAUDE.md").write_text("converged\n")
            git(repo, "commit", "-qam", "allowed")
            self.assertEqual(check(repo, before, {"CLAUDE.md"}), [])
            before = snapshot(repo)
            (repo / "protected.txt").write_text("staged change\n")
            git(repo, "add", "protected.txt")
            (repo / "protected.txt").write_text("original\n")
            self.assertTrue(any("status" in e for e in check(repo, before, {"CLAUDE.md"})))


if __name__ == "__main__":
    unittest.main()
