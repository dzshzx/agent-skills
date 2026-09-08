"""Extract completed Bash calls and recognize bounded command evidence."""
from __future__ import annotations

import json
from pathlib import Path
import shlex


def parse(path: Path, source: str) -> dict:
    result, reads, calls, completed = {}, set(), {}, []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get('type') == 'result':
            result = obj
        message = obj.get('message')
        if not isinstance(message, dict):
            continue
        for block in message.get('content', []):
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'tool_use':
                inp = block.get('input') or {}
                if block.get('name') == 'Read':
                    reads.add(str(inp.get('file_path')))
                if block.get('name') == 'Bash':
                    calls[block['id']] = str(inp.get('command', ''))
            elif block.get('type') == 'tool_result' and block.get('tool_use_id') in calls:
                content = block.get('content', '')
                if isinstance(content, list):
                    content = '\n'.join(b.get('text', '') for b in content if isinstance(b, dict))
                completed.append({'command': calls[block['tool_use_id']],
                                  'output': str(content), 'failed': bool(block.get('is_error'))})
    return {'is_error': result.get('is_error'), 'terminal_reason': result.get('terminal_reason'),
            'result': result.get('result') or '', 'read_src': source in reads,
            'reads': sorted(reads), 'cmds': list(calls.values()), 'completed': completed}


def segments(command: str) -> list[list[str]]:
    # Only simple commands joined by ; or && are supported. Other shell
    # constructs remain unverified rather than being mistaken for execution.
    if any(c in command for c in ('\n', '`', '$', '(', ')', '|', '<', '>')):
        return []
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&')
        lexer.whitespace_split = True
        parts = [[]]
        for word in lexer:
            if word in (';', '&&'):
                parts.append([])
            elif word and all(c in ';&' for c in word):
                return []
            else:
                parts[-1].append(word)
        return [p for p in parts if p]
    except ValueError:
        return []


def git_subcommand(words: list[str]) -> str | None:
    if not words or words[0] != 'git':
        return None
    i = 1
    while i < len(words):
        if words[i] in ('-C', '-c'):
            i += 2
        elif words[i] in ('--no-pager', '--paginate'):
            i += 1
        else:
            return words[i]
    return None


def ran(data: dict, kind: str) -> bool:
    for call in data['completed']:
        if call['failed']:
            continue
        parts = segments(call['command'])
        if kind == 'git-diff':
            matches = [p for p in parts if git_subcommand(p) == 'diff']
            # A standalone successful diff may be empty. In a compound call,
            # require an actual patch and reject text-producing siblings.
            safe = all(git_subcommand(p) in ('diff', 'status') or p[0] in ('cp', 'diff', 'cd') or
                       (p[0] == 'echo' and 'diff --git' not in ' '.join(p[1:])) for p in parts)
            if matches and (len(parts) == 1 or (safe and 'diff --git ' in call['output'])):
                return True
        elif kind == 'validator':
            if any(p[:1] == ['python3'] and len(p) > 1 and
                   Path(p[1]).name == 'validate_config.py' for p in parts):
                if all(p[0] in ('cd', 'python3') for p in parts) and call['output'].startswith('OK: '):
                    return True
    return False


if __name__ == '__main__':
    import sys
    if sys.argv[1] == 'parse':
        print(json.dumps(parse(Path(sys.argv[2]), sys.argv[3])))
    else:
        raise SystemExit(0 if ran(json.loads(Path(sys.argv[2]).read_text()), sys.argv[3]) else 1)
