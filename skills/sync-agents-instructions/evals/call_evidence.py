"""Extract completed Bash calls and recognize bounded command evidence."""

from __future__ import annotations

import json
from pathlib import Path
import shlex


def parse(path: Path, source: str) -> dict:
    result, reads, calls, completed = {}, set(), {}, []
    for obj in events(path):
        if obj.get("type") == "result":
            result = obj
        for block in content_blocks(obj):
            if block.get("type") == "tool_use":
                record_tool_use(block, reads, calls)
            elif (
                block.get("type") == "tool_result" and block.get("tool_use_id") in calls
            ):
                completed.append(completed_call(block, calls))
    return {
        "is_error": result.get("is_error"),
        "terminal_reason": result.get("terminal_reason"),
        "result": result.get("result") or "",
        "read_src": source in reads,
        "reads": sorted(reads),
        "cmds": list(calls.values()),
        "completed": completed,
    }


def events(path: Path):
    """Yield each JSON line of the stream-json transcript; skip unparsable lines."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            yield json.loads(line)
        except ValueError:
            continue


def content_blocks(obj: dict) -> list[dict]:
    message = obj.get("message")
    if not isinstance(message, dict):
        return []
    return [block for block in message.get("content", []) if isinstance(block, dict)]


def record_tool_use(block: dict, reads: set[str], calls: dict[str, str]) -> None:
    inp = block.get("input") or {}
    if block.get("name") == "Read":
        reads.add(str(inp.get("file_path")))
    if block.get("name") == "Bash":
        calls[block["id"]] = str(inp.get("command", ""))


def completed_call(block: dict, calls: dict[str, str]) -> dict:
    content = block.get("content", "")
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return {
        "command": calls[block["tool_use_id"]],
        "output": str(content),
        "failed": bool(block.get("is_error")),
    }


def segments(command: str) -> list[list[str]]:
    # Only simple commands joined by ; or && are supported. Other shell
    # constructs remain unverified rather than being mistaken for execution.
    if any(c in command for c in ("\n", "`", "$", "(", ")", "|", "<", ">")):
        return []
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&")
        lexer.whitespace_split = True
        parts = [[]]
        for word in lexer:
            if word in (";", "&&"):
                parts.append([])
            elif word and all(c in ";&" for c in word):
                return []
            else:
                parts[-1].append(word)
        return [p for p in parts if p]
    except ValueError:
        return []


def git_subcommand(words: list[str]) -> str | None:
    if not words or words[0] != "git":
        return None
    i = 1
    while i < len(words):
        if words[i] in ("-C", "-c"):
            i += 2
        elif words[i] in ("--no-pager", "--paginate"):
            i += 1
        else:
            return words[i]
    return None


def ran(data: dict, kind: str) -> bool:
    accepts = {"git-diff": shows_git_diff, "validator": ran_validator}.get(kind)
    if accepts is None:
        return False
    return any(
        not call["failed"] and accepts(segments(call["command"]), call["output"])
        for call in data["completed"]
    )


def shows_git_diff(parts: list[list[str]], output: str) -> bool:
    if not any(git_subcommand(p) == "diff" for p in parts):
        return False
    # A standalone successful diff may be empty. In a compound call,
    # require an actual patch and reject text-producing siblings.
    if len(parts) == 1:
        return True
    return all(quiet_diff_sibling(p) for p in parts) and "diff --git " in output


def quiet_diff_sibling(p: list[str]) -> bool:
    """True when segment p cannot itself print text that looks like a patch."""
    return (
        git_subcommand(p) in ("diff", "status")
        or p[0] in ("cp", "diff", "cd")
        or (p[0] == "echo" and "diff --git" not in " ".join(p[1:]))
    )


def ran_validator(parts: list[list[str]], output: str) -> bool:
    if not any(validator_target(p) for p in parts):
        return False
    return all(
        p[0] == "cd" or validator_target(p) for p in parts
    ) and output.startswith("OK: ")


def validator_target(p):
    """True when p runs validate_config.py via its locked uv entry or python3."""
    if p[:4] == ["uv", "run", "--script", "--locked"]:
        p = p[4:]
    elif p[:1] == ["python3"]:
        p = p[1:]
    return len(p) >= 1 and Path(p[0]).name == "validate_config.py"


if __name__ == "__main__":
    import sys

    if sys.argv[1] == "parse":
        print(json.dumps(parse(Path(sys.argv[2]), sys.argv[3])))
    else:
        raise SystemExit(
            0 if ran(json.loads(Path(sys.argv[2]).read_text()), sys.argv[3]) else 1
        )
