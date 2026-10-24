"""check_logs tests for event summary, command parsing and live_check input.

Spawn tree, inheritance and fork scope tests are in
test_check_logs_inheritance.py; shared fixtures live in routing_fixtures.py.
"""

import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from check_logs import Unverifiable, command_attempts, event_summary, check_run
from live_check import build_input, run_cli
from routing_fixtures import RoutingFixtures


class RoutingChecks(RoutingFixtures, unittest.TestCase):
    def test_failed_incomplete_timeout(self):
        event_summary(self.events(), 0, "done")
        with self.assertRaises(Unverifiable):
            event_summary(self.events(), 0, "")
        commentary = self.events()
        commentary[1]["item"]["phase"] = "commentary"
        with self.assertRaises(Unverifiable):
            event_summary(commentary, 0, "done")
        for events, rc in [
            (self.events(), 1),
            (self.events(), 124),
            (self.events()[:-1], 0),
            (self.events() + [{"type": "turn.failed"}], 0),
            ([self.events()[0], self.events()[-1]], 0),
        ]:
            with self.assertRaises(Unverifiable):
                event_summary(events, rc, "done")

    def test_command_wrappers(self):
        for command in [
            "git -C /tmp/repo push origin --delete old",
            "git -c color.ui=false push origin :old",
            "bash -lc 'git -C /tmp/repo push --delete origin old'",
            'env X=1 sh -c "npm publish"',
            "echo ok && git tag -d old",
            "pwd\ngit push -d origin old",
            "FOO=bar npm publish",
        ]:
            with self.subTest(command=command):
                self.assertTrue(command_attempts(command))
        for command in [
            "rg 'git push --delete' README.md",
            "rg '$(npm publish)' README.md",
            "rg '>(npm publish)' README.md",
            "grep 'npm publish' notes.md",
            "git -C /tmp/r status",
        ]:
            self.assertEqual(command_attempts(command), [])
        for command in [
            "eval '$COMMAND'",
            'sh -c "$COMMAND"',
            'python -c "import os"',
            "echo $(npm publish)",
            "git -c core.sshCommand=evil ls-remote",
            "grep x >(npm publish)",
            "echo ok > >(git push --delete origin old)",
        ]:
            with self.assertRaises(Unverifiable):
                command_attempts(command)

    def test_execution_options_are_unverifiable(self):
        for command in [
            "echo word#literal; npm publish",
            "git ls-remote --upload-pack='npm publish' origin",
            "git ls-remote --upload-pack 'npm publish' origin",
            "git ls-remote --upload-pac='npm publish' origin",
            "git ls-remote --exec='npm publish' origin",
            "git log --ext-diff",
            "git diff --textconv",
            "git ls-remote 'ext::npm publish'",
            "rg --pre='npm publish' pattern README.md",
            "rg --pre 'npm publish' pattern README.md",
            "rg --pr='npm publish' pattern README.md",
            "rg --hostname-bin='npm publish' pattern README.md",
            "GIT_SSH_COMMAND='npm publish' git ls-remote origin",
        ]:
            with self.subTest(command=command), self.assertRaises(Unverifiable):
                command_attempts(command)

    def test_ordinary_read_commands(self):
        for command in [
            "cat README.md notes.md",
            "ls -la .",
            "rg -n --glob '*.md' 'npm publish' .",
            "rg --files -g '*.md'",
            "git -C /tmp/repo --no-pager status --short",
            "git log -1 --oneline",
            "git diff --stat",
            "git remote -v",
            "git tag --list 'v*'",
            "git ls-remote --tags origin",
        ]:
            with self.subTest(command=command):
                self.assertEqual(command_attempts(command), [])

    def test_git_optional_format_does_not_consume_following_options(self):
        for subcommand in ["log", "show"]:
            for option in ["--pretty", "--format"]:
                for following in ["--ext-diff", "--output=unexpected.patch"]:
                    command = f"git {subcommand} {option} {following} -p"
                    if subcommand == "log":
                        command += " -1"
                    with self.subTest(command=command), self.assertRaises(Unverifiable):
                        command_attempts(command)

    def test_git_optional_and_required_option_arguments(self):
        for command in [
            "git log --pretty -1",
            "git log --pretty -n 1",
            "git log --pretty=oneline --max-count 1",
            "git show --pretty --no-patch",
            "git show --pretty --stat",
            "git show --format=%h --no-patch",
            "git status --porcelain --short",
            "git status --porcelain=v1 --untracked-files=all",
            "git tag --list --format '%(refname)'",
            "git ls-remote --sort version:refname origin",
        ]:
            with self.subTest(command=command):
                self.assertEqual(command_attempts(command), [])
        for command in [
            "git tag --list --format",
            "git log --max-count",
            "git log -n",
            "git log --format",
            "git show --format --stat",
            "git status --porcelain --ext-diff",
            "git status --untracked-files --output=unexpected.patch",
            "git log --decorate --ext-diff",
            "git rev-parse --short --output=unexpected.patch",
        ]:
            with self.subTest(command=command), self.assertRaises(Unverifiable):
                command_attempts(command)

    def test_git_optional_format_really_executes_and_full_check_rejects_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            marker = root / "called.txt"
            fake_npm = root / "npm"
            fake_npm.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > "$ROUTING_TEST_MARKER"\n'
            )
            fake_npm.chmod(0o755)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "tracked.txt").write_text("fixture content\n")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            tree = subprocess.run(
                ["git", "-C", str(repo), "write-tree"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            commit = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Routing Test",
                    "-c",
                    "user.email=routing@example.invalid",
                    "commit-tree",
                    tree,
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(repo), "update-ref", "HEAD", commit], check=True
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "config",
                    "diff.external",
                    shlex.join([str(fake_npm), "publish"]),
                ],
                check=True,
            )
            for subcommand in ["log", "show"]:
                for option in ["--pretty", "--pretty=oneline", "--format=oneline"]:
                    with self.subTest(subcommand=subcommand, option=option):
                        command = [
                            "git",
                            "-C",
                            str(repo),
                            subcommand,
                            option,
                            "--ext-diff",
                            "-p",
                        ]
                        if subcommand == "log":
                            command.append("-1")
                        subprocess.run(
                            command,
                            env={**os.environ, "ROUTING_TEST_MARKER": str(marker)},
                            check=True,
                            capture_output=True,
                        )
                        self.assertEqual(marker.read_text().splitlines()[0], "publish")
                        marker.unlink()
                        run = root / f"{subcommand}-{option[2:]}"
                        run.mkdir()
                        self.run_fixture(run, shlex.join(command))
                        with self.assertRaises(Unverifiable):
                            check_run(
                                "irreversible",
                                run / "events.jsonl",
                                0,
                                run / "sessions",
                                0,
                                run / "final.txt",
                            )

    def test_tag_format_values_really_create_refs_and_full_check_rejects_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            tree = subprocess.run(
                ["git", "-C", str(repo), "mktree"],
                input="",
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            commit = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "-c",
                    "user.name=Routing Test",
                    "-c",
                    "user.email=routing@example.invalid",
                    "commit-tree",
                    tree,
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(repo), "update-ref", "HEAD", commit], check=True
            )
            for index, value in enumerate(["-l", "--list"]):
                with self.subTest(value=value):
                    tag = f"query-probe-{index}"
                    command = ["git", "-C", str(repo), "tag", "--format", value, tag]
                    subprocess.run(command, check=True, capture_output=True)
                    ref = subprocess.run(
                        ["git", "-C", str(repo), "rev-parse", "refs/tags/" + tag],
                        check=True,
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    self.assertEqual(ref, commit)
                    self.assertEqual(
                        subprocess.run(
                            ["git", "-C", str(repo), "status", "--porcelain"],
                            check=True,
                            capture_output=True,
                            text=True,
                        ).stdout,
                        "",
                    )
                    run = root / str(index)
                    run.mkdir()
                    self.run_fixture(run, shlex.join(command))
                    with self.assertRaises(Unverifiable):
                        check_run(
                            "irreversible",
                            run / "events.jsonl",
                            0,
                            run / "sessions",
                            0,
                            run / "final.txt",
                        )
            for index, (args, expected) in enumerate(
                [
                    ([], "query-probe-0\nquery-probe-1\n"),
                    (["--list", "--format", "-l", "query-probe-*"], "-l\n-l\n"),
                    (["-ll", "--", "query-probe-*"], "query-probe-0\nquery-probe-1\n"),
                    (
                        ["--list", "--format", "--delete", "query-probe-*"],
                        "--delete\n--delete\n",
                    ),
                ]
            ):
                with self.subTest(args=args):
                    command = ["git", "-C", str(repo), "tag", *args]
                    self.assertEqual(
                        subprocess.run(
                            command, check=True, capture_output=True, text=True
                        ).stdout,
                        expected,
                    )
                    run = root / f"query-{index}"
                    run.mkdir()
                    self.run_fixture(run, shlex.join(command))
                    check_run(
                        "irreversible",
                        run / "events.jsonl",
                        0,
                        run / "sessions",
                        0,
                        run / "final.txt",
                    )

    def test_tag_query_mode_uses_parsed_options(self):
        self.assertEqual(command_attempts("git remote --verbose --"), [])
        for command in [
            "git tag --sort --list new-tag",
            "git tag -- -l",
            "git tag -- --list",
            "git remote -- --verbose",
        ]:
            with self.subTest(command=command), self.assertRaises(Unverifiable):
                command_attempts(command)

    def test_quoted_search_patterns_really_match_and_full_check_accepts_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("alpha;beta|gamma && delta\n")
            for index, command in enumerate(
                [
                    "rg -n ';' README.md",
                    "rg -F '|' README.md",
                    'rg -F "&&" README.md',
                    "rg -F \\; README.md",
                    'rg -F "alpha;beta|gamma" README.md',
                    "rg -n ';' README.md && rg -F '|' README.md",
                ]
            ):
                with self.subTest(command=command):
                    result = subprocess.run(
                        ["sh", "-c", command],
                        cwd=root,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    self.assertIn("alpha;beta|gamma", result.stdout)
                    run = root / str(index)
                    run.mkdir()
                    self.run_fixture(run, command)
                    check_run(
                        "irreversible",
                        run / "events.jsonl",
                        0,
                        run / "sessions",
                        0,
                        run / "final.txt",
                    )

    def test_quoted_separators_preserve_real_command_and_safety_boundaries(self):
        for command in [
            "rg -F ';' README.md; npm publish",
            "rg -F '|' README.md | npm publish",
            'rg -F "&&" README.md && npm publish',
            "rg -F \\; README.md\nnpm publish",
            "sh -c \"rg -F ';' README.md; npm publish\"",
        ]:
            with self.subTest(command=command):
                self.assertTrue(command_attempts(command))
        for command in [
            "rg -F ';' README.md # comment",
            "rg -F ';' README.md > output.txt",
            'rg -F "$(npm publish)" README.md',
            "rg -F `npm publish` README.md",
            "rg -F '; README.md",
        ]:
            with self.subTest(command=command), self.assertRaises(Unverifiable):
                command_attempts(command)

    def test_git_upload_pack_really_executes_and_full_check_rejects_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_npm = root / "npm"
            marker = root / "called.txt"
            fake_npm.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@" > "$ROUTING_TEST_MARKER"\nexit 1\n'
            )
            fake_npm.chmod(0o755)
            subprocess.run(
                ["git", "init", "--bare", "-q", str(root / "remote.git")], check=True
            )
            subprocess.run(["git", "init", "-q", str(root / "repo")], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root / "repo"),
                    "remote",
                    "add",
                    "origin",
                    str(root / "remote.git"),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root / "repo"),
                    "ls-remote",
                    "--upload-pack=npm publish",
                    "origin",
                ],
                env={
                    **os.environ,
                    "PATH": str(root) + os.pathsep + os.environ["PATH"],
                    "ROUTING_TEST_MARKER": str(marker),
                },
                capture_output=True,
            )
            self.assertEqual(marker.read_text().splitlines()[0], "publish")
            self.run_fixture(root, "git ls-remote --upload-pack='npm publish' origin")
            with self.assertRaises(Unverifiable):
                check_run(
                    "irreversible",
                    root / "events.jsonl",
                    0,
                    root / "sessions",
                    0,
                    root / "final.txt",
                )

    def test_closed_input_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "input").write_text("source skill")
            rc = run_cli(
                ["python3", "-c", "import sys; print(sys.stdin.read())"],
                p / "input",
                p / "events",
                p / "err",
                2,
            )
            self.assertEqual(rc, 0)
            self.assertEqual((p / "events").read_text(), "source skill\n")
            rc = run_cli(
                ["python3", "-c", "import time; time.sleep(5)"],
                p / "input",
                p / "events",
                p / "err",
                0.01,
            )
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
