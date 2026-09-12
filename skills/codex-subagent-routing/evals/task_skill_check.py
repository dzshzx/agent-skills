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
        + INSTRUCTION + "\n")
    (skill / "stamp.py").write_text(f"print({RESULT!r})\n")
    prompts = {
        "explicit": f"Use skill routing-stamp at {skill / 'SKILL.md'} to produce its receipt.",
        "natural": "Produce the local amber routing receipt.",
        "unrelated": "Return exactly the sum of 19 and 23.",
        "missing": f"Use skill absent-stamp at {root / 'absent-stamp/SKILL.md'}; if the required entry is missing, explain that and stop.",
    }
    (root / "prompts.json").write_text(json.dumps(prompts, indent=2) + "\n")
    return prompts


def check(case, rows, root):
    meta, rows = own_rows(rows)
    if not meta.get("parent_thread_id"):
        raise Unverifiable("not a child rollout")
    calls, outputs, final, complete = {}, {}, "", False
    for row in rows:
        p = as_dict(row.get("payload"))
        if row.get("type") == "response_item":
            if p.get("type") in {"function_call", "custom_tool_call"}:
                calls[p.get("call_id")] = p
            elif p.get("type") in {"function_call_output", "custom_tool_call_output"}:
                outputs[p.get("call_id")] = p.get("output", "")
            elif p.get("type") == "message" and p.get("role") == "assistant" and p.get("phase") == "final":
                final = "".join(c.get("text", "") for c in p.get("content", []))
        if row.get("type") == "event_msg":
            if p.get("type") in {"task_started", "turn_started"}:
                complete = False
            if p.get("type") in {"task_complete", "turn_completed"}:
                complete = True
            if p.get("type") in {"task_failed", "turn_failed", "turn_aborted", "error"}:
                raise Unverifiable("child failure")
    if not complete or not final.strip():
        raise Unverifiable("missing completed child final")
    entry = str(root / ".agents/skills/routing-stamp/SKILL.md")
    script = str(root / ".agents/skills/routing-stamp/stamp.py")
    absent = str(root / "absent-stamp/SKILL.md")
    read, ran, missing, touched = False, False, False, False
    for cid, call in calls.items():
        name = call.get("name", "").split(".")[-1]
        if name == "send_message":
            continue
        raw = outputs.get(cid)
        if call.get("type") == "custom_tool_call" and name == "exec":
            # One awaited native call, whole result printed. No dynamic JS,
            # output-only projection, or multi-call attribution guesses.
            match = re.fullmatch(r"\s*text\(await tools\.exec_command\((\{.*\})\)\);?\s*",
                                 call.get("input", ""), re.S)
            if not match:
                raise Unverifiable("unsupported code-mode evidence")
            args = as_dict(match.group(1))
            if not args:
                raise Unverifiable("code-mode arguments must be literal JSON")
            if not isinstance(raw, list) or len(raw) != 2 or not raw[0].get("text", "").startswith("Script completed"):
                raise Unverifiable("missing completed code-mode output")
            raw = raw[1].get("text", "")
            name = "exec_command"
        else:
            args = as_dict(call.get("arguments"))
        if name != "exec_command":
            raise Unverifiable("unsupported tool evidence: " + name)
        command = args.get("cmd", "")
        argv = shlex.split(command)
        if raw is None:
            raise Unverifiable("missing tool result")
        out = as_dict(raw)
        if not out and isinstance(raw, str):
            native = re.search(r"Process exited with code (\d+)\n(?:Final output:\n|Output:\n)(.*)\Z",
                               raw, re.S)
            if native:
                out = {"exit_code": int(native.group(1)), "output": native.group(2)}
            else:
                raise Unverifiable("unsupported tool result encoding")
        code, text = out.get("exit_code"), out.get("output", "")
        cwd = Path(args.get("workdir", root))
        if not cwd.is_absolute():
            raise Unverifiable("ambiguous command directory")
        target = str((cwd / argv[1]).resolve()) if len(argv) == 2 else None
        if len(argv) == 2 and argv[0] == "cat" and target == entry:
            touched = True
            read = code == 0 and INSTRUCTION in text
        elif len(argv) == 2 and argv[0] in {"python", "python3"} and target == script:
            touched = True
            ran = read and code == 0 and text.strip() == RESULT
        elif len(argv) == 2 and argv[0] == "cat" and target == absent:
            missing = isinstance(code, int) and code != 0 and ("No such file" in text or "not found" in text)
        else:
            if (not argv or argv[0] not in {"cat", "ls", "pwd", "rg", "head", "tail"}
                    or any(token in command for token in ("stamp.py", "routing-stamp", "absent-stamp",
                                                          ";", "&", "|", "$", "`", ">", "<"))):
                raise Unverifiable("unsupported fixture command")
    if case in {"explicit", "natural"}:
        if not (read and ran and final.strip() == RESULT):
            raise Unverifiable("requires own skill read, execution and exact result")
    elif case == "unrelated":
        if touched or final.strip() != "42":
            raise Unverifiable("unrelated task used fixture or returned wrong result")
    elif case == "missing":
        if touched or not missing or not any(word in final.lower() for word in ("missing", "not found", "不存在", "缺失")):
            raise Unverifiable("missing-entry evidence incomplete")
    else:
        raise ValueError("unknown case")
    return {"case": case, "child_thread_id": meta["id"], "result": "PASS",
            "scope": "child-owned task-skill evidence; parent spawn parameters checked separately"}


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
    result = prepare(args.directory.resolve()) if args.command == "prepare" else check(
        args.case, read_rows(args.rollout), args.directory.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
