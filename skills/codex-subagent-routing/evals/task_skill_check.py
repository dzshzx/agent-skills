"""Prepare safe local skill-discovery fixtures and check child-owned evidence."""

import argparse
import json
import re
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from usage_report import own_rows
from check_logs import Unverifiable, as_dict, read_rows

CASES = ("explicit", "natural", "unrelated", "missing")
INSTRUCTION = "Run the adjacent stamp.py with Python, then return its exact output."
RESULT = "ROUTING-FIXTURE: amber-47"


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    skill = root / ".agents/skills/routing-stamp"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: routing-stamp\ndescription: Produce the local amber routing receipt.\n---\n\n"
        + INSTRUCTION
        + "\n"
    )
    (skill / "stamp.py").write_text(f"print({RESULT!r})\n")
    prompts = {
        "explicit": f"Use skill routing-stamp at {skill / 'SKILL.md'} to produce its receipt.",
        "natural": "Produce the local amber routing receipt.",
        "unrelated": "Return exactly the sum of 19 and 23.",
        "missing": f"Use skill absent-stamp at {root / 'absent-stamp/SKILL.md'}; if the required entry is missing, explain that and stop.",
    }
    (root / "prompts.json").write_text(json.dumps(prompts, indent=2) + "\n")
    return prompts


CALL_TYPES = {"function_call", "custom_tool_call"}
OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output"}
LISTING_COMMANDS = {"ls", "pwd", "rg", "head", "tail"}
FORBIDDEN_TOKENS = (
    "stamp.py",
    "routing-stamp",
    "absent-stamp",
    ";",
    "&",
    "|",
    "$",
    "`",
    ">",
    "<",
)
EXEC_DIRECT = r"\s*text\(await tools\.exec_command\((\{.*\})\)\);?\s*"
EXEC_BOUND = r"\s*const ([A-Za-z_][A-Za-z0-9_]*)\s*=\s*await tools\.exec_command\((\{.*\})\);\s*text\(\1\);?\s*"
NATIVE_RESULT = r"Process exited with code (\d+)\n(?:Final output:\n|Output:\n)(.*)\Z"


def record_response(p, calls, outputs, final):
    """Index one response item; return the latest final answer text."""
    if p.get("type") in CALL_TYPES:
        calls[p.get("call_id")] = p
    elif p.get("type") in OUTPUT_TYPES:
        outputs[p.get("call_id")] = p.get("output", "")
    elif (
        p.get("type") == "message"
        and p.get("role") == "assistant"
        and p.get("phase") in {"final", "final_answer"}
    ):
        return "".join(c.get("text", "") for c in p.get("content", []))
    return final


def event_complete(kind, complete):
    if kind in {"task_started", "turn_started"}:
        return False
    if kind in {"task_complete", "turn_completed"}:
        return True
    if kind in {"task_failed", "turn_failed", "turn_aborted", "error"}:
        raise Unverifiable("child failure")
    return complete


def child_evidence(rows):
    """Return the child's tool calls, their outputs and its completed final."""
    calls, outputs, final, complete = {}, {}, "", False
    for row in rows:
        p = as_dict(row.get("payload"))
        if row.get("type") == "response_item":
            final = record_response(p, calls, outputs, final)
        if row.get("type") == "event_msg":
            complete = event_complete(p.get("type"), complete)
    if not complete or not final.strip():
        raise Unverifiable("missing completed child final")
    return calls, outputs, final


def code_mode_invocation(call, raw):
    # One awaited native call, whole result printed. No dynamic JS,
    # output-only projection, or multi-call attribution guesses.
    source = call.get("input", "")
    match = re.fullmatch(EXEC_DIRECT, source, re.S)
    if match:
        args = as_dict(match.group(1))
    else:
        bound = re.fullmatch(EXEC_BOUND, source, re.S)
        if not bound:
            raise Unverifiable("unsupported code-mode evidence")
        args = as_dict(bound.group(2))
    if not args:
        raise Unverifiable("code-mode arguments must be literal JSON")
    if (
        not isinstance(raw, list)
        or len(raw) != 2
        or not raw[0].get("text", "").startswith("Script completed")
    ):
        raise Unverifiable("missing completed code-mode output")
    return args, raw[1].get("text", "")


def tool_invocation(call, raw):
    """Return exec_command arguments and the raw result for one tool call."""
    name = call.get("name", "").split(".")[-1]
    if call.get("type") == "custom_tool_call" and name == "exec":
        return code_mode_invocation(call, raw)
    if name != "exec_command":
        raise Unverifiable("unsupported tool evidence: " + name)
    return as_dict(call.get("arguments")), raw


def command_result(raw):
    """Return (exit code, output) from a JSON or native-text tool result."""
    if raw is None:
        raise Unverifiable("missing tool result")
    out = as_dict(raw)
    if not out and isinstance(raw, str):
        native = re.search(NATIVE_RESULT, raw, re.S)
        if not native:
            raise Unverifiable("unsupported tool result encoding")
        out = {"exit_code": int(native.group(1)), "output": native.group(2)}
    return out.get("exit_code"), out.get("output", "")


def read_target(argv, cwd):
    """Return (resolved target, whether argv is a supported file read)."""
    target = str((cwd / argv[1]).resolve()) if len(argv) == 2 else None
    is_read = len(argv) == 2 and argv[0] == "cat"
    if (
        len(argv) == 4
        and argv[:2] == ["sed", "-n"]
        and re.fullmatch(r"\d+(?:,\d+)?p", argv[2])
    ):
        return str((cwd / argv[3]).resolve()), True
    return target, is_read


def allowed_probe(argv, command, is_read):
    return (
        bool(argv)
        and (is_read or argv[0] in LISTING_COMMANDS)
        and not any(token in command for token in FORBIDDEN_TOKENS)
    )


class FixtureUse:
    """What the child's commands proved about the fixture skill."""

    def __init__(self, root):
        self.entry = str(root / ".agents/skills/routing-stamp/SKILL.md")
        self.script = str(root / ".agents/skills/routing-stamp/stamp.py")
        self.absent = str(root / "absent-stamp/SKILL.md")
        self.read, self.ran, self.missing, self.touched = False, False, False, False

    def classify(self, argv, target, is_read):
        if is_read and target == self.entry:
            return "entry"
        if (
            len(argv) == 2
            and argv[0] in {"python", "python3"}
            and target == self.script
        ):
            return "script"
        if is_read and target == self.absent:
            return "absent"
        if is_read and target and target.endswith("/routing-stamp/SKILL.md"):
            return "other-entry"
        return None

    def observe(self, argv, command, cwd, code, text):
        target, is_read = read_target(argv, cwd)
        kind = self.classify(argv, target, is_read)
        if kind == "entry":
            self.touched = True
            self.read = code == 0 and INSTRUCTION in text
        elif kind == "script":
            self.touched = True
            self.ran = self.read and code == 0 and text.strip() == RESULT
        elif kind == "absent":
            self.missing = (
                isinstance(code, int)
                and code != 0
                and ("No such file" in text or "not found" in text)
            )
        elif kind == "other-entry":
            # Native discovery may first probe another skill root. A failed
            # lookup is not a successful fixture read, but still counts as use
            # for the unrelated negative case.
            self.touched = True
            if not isinstance(code, int) or code == 0:
                raise Unverifiable("unregistered readable skill entry")
        elif not allowed_probe(argv, command, is_read):
            raise Unverifiable("unsupported fixture command")


def check_case(case, use, final):
    if case in {"explicit", "natural"}:
        if not (use.read and use.ran and final.strip() == RESULT):
            raise Unverifiable("requires own skill read, execution and exact result")
    elif case == "unrelated":
        if use.touched or final.strip() != "42":
            raise Unverifiable("unrelated task used fixture or returned wrong result")
    elif case == "missing":
        if (
            use.touched
            or not use.missing
            or not any(
                word in final.lower()
                for word in ("missing", "not found", "不存在", "缺失")
            )
        ):
            raise Unverifiable("missing-entry evidence incomplete")
    else:
        raise ValueError("unknown case")


def check(case, rows, root):
    meta, rows = own_rows(rows)
    if not meta.get("parent_thread_id"):
        raise Unverifiable("not a child rollout")
    calls, outputs, final = child_evidence(rows)
    use = FixtureUse(root)
    for cid, call in calls.items():
        if call.get("name", "").split(".")[-1] == "send_message":
            continue
        args, raw = tool_invocation(call, outputs.get(cid))
        command = args.get("cmd", "")
        argv = shlex.split(command)
        code, text = command_result(raw)
        cwd = Path(args.get("workdir", root))
        if not cwd.is_absolute():
            raise Unverifiable("ambiguous command directory")
        use.observe(argv, command, cwd, code, text)
    check_case(case, use, final)
    return {
        "case": case,
        "child_thread_id": meta["id"],
        "result": "PASS",
        "scope": "child-owned task-skill evidence; parent spawn parameters checked separately",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("directory", type=Path)
    p = commands.add_parser("check")
    p.add_argument("case", choices=CASES)
    p.add_argument("rollout", type=Path)
    p.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = (
        prepare(args.directory.resolve())
        if args.command == "prepare"
        else check(args.case, read_rows(args.rollout), args.directory.resolve())
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
