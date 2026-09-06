"""Exercise the full entrypoint in a disposable repository with recording CLIs."""
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / 'scripts'
        scripts.mkdir()
        shutil.copyfile(Path(__file__).resolve().parents[1] / 'verify.sh', scripts / 'verify.sh')
        (scripts / 'validate_repository.py').write_text('pass\n')
        for name in ('check-offline.sh', 'check-commit-subjects.sh'):
            (scripts / name).write_text('exit 0\n')
        for name in ('alpha', 'beta', 'sync-agents-instructions'):
            directory = self.root / 'skills' / name / 'evals'
            directory.mkdir(parents=True)
            (directory / 'live-check.sh').write_text(f'codex {name}\nclaude {name}\nkimi {name}\n')
            (directory / 'check.sh').write_text('exit 0\n')
        binaries = self.root / 'bin'
        binaries.mkdir()
        self.record = self.root / 'calls'
        for name in ('codex', 'claude', 'kimi', 'shellcheck'):
            path = binaries / name
            body = 'exit 0' if name == 'shellcheck' else 'printf "%s\\n" "$0 $*" >> "$CALL_RECORD"'
            path.write_text('#!/bin/sh\n' + body + '\n')
            path.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
                    'CALL_RECORD': str(self.record), 'BASH_ENV': '/dev/null'}
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '-qm', 'chore: fixture')
        self.git('update-ref', 'refs/remotes/origin/master', 'HEAD')

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)

    def run_verify(self, *args):
        self.record.unlink(missing_ok=True)
        result = subprocess.run(['bash', 'scripts/verify.sh', *args], cwd=self.root,
                                env=self.env, capture_output=True, text=True, timeout=20)
        calls = self.record.read_text().splitlines() if self.record.exists() else []
        return result, calls

    def test_no_live_is_order_independent(self):
        cases = [('--no-live',)]
        for choices in (('--no-live', 'alpha'), ('--no-live', '--all'),
                        ('--no-live', 'alpha', 'beta')):
            cases.extend(itertools.permutations(choices))
        for args in cases:
            with self.subTest(args=args):
                result, calls = self.run_verify(*args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(calls, [])

    def test_all_and_named_is_always_usage_error(self):
        for args in itertools.permutations(('--no-live', '--all', 'alpha')):
            result, calls = self.run_verify(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])
        for args in (('--all', 'alpha'), ('alpha', '--all')):
            result, calls = self.run_verify(*args)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])

    def test_existing_live_selection(self):
        for args, expected in (((), 0), (('alpha',), 3), (('--all',), 9)):
            result, calls = self.run_verify(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(calls), expected)
        (self.root / 'skills/alpha/SKILL.md').write_text('changed\n')
        result, calls = self.run_verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls), 3)

    def test_mechanical_failure_propagates_offline(self):
        (self.root / 'scripts/check-offline.sh').write_text('exit 1\n')
        result, calls = self.run_verify('--no-live', 'alpha')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
