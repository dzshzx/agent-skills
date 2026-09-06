"""Fail closed on incomplete/failed Codex exec JSONL runs."""
import json
import os
import sys
from pathlib import Path


def validate(events, rc):
    if rc != 0:
        raise ValueError(f"process exited {rc}")
    if any(e.get("type") in {"turn.failed", "error"} for e in events):
        raise ValueError("failure event present")
    if not events or events[-1].get("type") != "turn.completed":
        raise ValueError("missing successful terminal event")
    messages = [e.get("item", {}).get("text") for e in events
                if e.get("type") == "item.completed"
                and e.get("item", {}).get("type") == "agent_message"
                and e.get("item", {}).get("phase") != "commentary"]
    if not messages or not isinstance(messages[-1], str) or not messages[-1].strip():
        raise ValueError("missing final answer")


def check_file(path, rc, final_path=None):
    events = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if any(not isinstance(e, dict) for e in events):
        raise ValueError("invalid event")
    validate(events, rc)
    if final_path is not None:
        final = Path(final_path).read_text().strip()
        last = next(e["item"]["text"].strip() for e in reversed(events)
                    if e.get("type") == "item.completed"
                    and e.get("item", {}).get("type") == "agent_message"
                    and e.get("item", {}).get("phase") != "commentary")
        if not final or final != last:
            raise ValueError("final output missing or differs from final agent message")


def check_posture(path, expected):
    events = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    tid = next(e["thread_id"] for e in events if e.get("type") == "thread.started")
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    records = list((home / "sessions").glob(f"**/*{tid}.jsonl"))
    contexts = []
    for record in records:
        for line in record.read_text().splitlines():
            event = json.loads(line)
            if event.get("type") == "turn_context":
                contexts.append(event["payload"])
    if not contexts:
        raise ValueError("actual turn permission context unavailable")
    actual = contexts[-1]
    evidence = {"thread_id": tid, "sandbox_policy": actual.get("sandbox_policy"),
                "approval_policy": actual.get("approval_policy"),
                "permission_profile": actual.get("permission_profile")}
    Path(str(path) + ".permissions.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if (actual.get("sandbox_policy", {}).get("type") != expected
            or actual.get("approval_policy") != "never"):
        raise ValueError(f"unexpected actual permissions: {evidence}")


if __name__ == "__main__":
    try:
        if sys.argv[1] == "--posture":
            check_posture(sys.argv[2], sys.argv[3])
        else:
            check_file(sys.argv[1], int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
    except (OSError, ValueError, IndexError, KeyError, StopIteration) as exc:
        print(f"Codex run failed: {exc}", file=sys.stderr)
        sys.exit(1)
