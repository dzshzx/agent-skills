import json
from pathlib import Path
import tempfile
import unittest

from call_evidence import parse, ran


class EvidenceTests(unittest.TestCase):
    def evidence(self, command, output='', failed=False, completed=True):
        events = [{'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Bash', 'id': 'one', 'input': {'command': command}}]}}]
        if completed:
            events.append({'type': 'user', 'message': {'content': [
                {'type': 'tool_result', 'tool_use_id': 'one', 'is_error': failed, 'content': output}]}})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'events.jsonl'
            path.write_text('\n'.join(map(json.dumps, events)))
            return parse(path, '/skill.md')

    def test_git_options_and_quoted_paths(self):
        for command in ['git diff', 'git --no-pager diff',
                        'git -C "/tmp/a b" -c color.ui=false --no-pager diff',
                        'git -c color.ui=false -C /tmp/repo diff']:
            with self.subTest(command=command):
                self.assertTrue(ran(self.evidence(command), 'git-diff'))

    def test_denial_failure_missing_result_and_echo(self):
        for kwargs in [{'failed': True}, {'completed': False}]:
            self.assertFalse(ran(self.evidence('git diff', **kwargs), 'git-diff'))
        for command in ['echo "git diff"', 'false || git diff',
                        'git diff; echo "diff --git a/f b/f"', 'printf "git diff"',
                        'git diff --invalid; git show']:
            self.assertFalse(ran(self.evidence(command, 'diff --git a/f b/f'), 'git-diff'))

    def test_historical_compound_call(self):
        command = ('git -C /tmp/repo --no-pager diff; git -C /tmp/repo status --porcelain; '
                   'echo "=== repo-b ==="; cp /tmp/b /tmp/after; diff -u /tmp/before /tmp/after')
        self.assertTrue(ran(self.evidence(command, 'diff --git a/f b/f\n'), 'git-diff'))
        self.assertFalse(ran(self.evidence(command), 'git-diff'))

    def test_validator_needs_completed_output(self):
        command = 'cd /tmp/skill && python3 scripts/validate_config.py /tmp/config'
        self.assertTrue(ran(self.evidence(command, 'OK: /tmp/config'), 'validator'))
        self.assertFalse(ran(self.evidence(command, 'ERROR: invalid', failed=True), 'validator'))
        self.assertFalse(ran(self.evidence('echo validate_config.py', 'OK: fake'), 'validator'))


if __name__ == '__main__':
    unittest.main()
