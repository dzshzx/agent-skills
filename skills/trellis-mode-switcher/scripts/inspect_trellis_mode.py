#!/usr/bin/env python3
"""Read-only Trellis execution-mode inspector.

Reports the project's execution model along TWO orthogonal axes and, when it can
tell, which agent triggered the skill so the caller knows what is actually
switchable here. It never writes files.

Axis A - dispatch style (inline vs sub-agent):
    A Codex-only knob (`codex.dispatch_mode: inline | sub-agent`). Class-1
    hook-push platforms (Claude, Cursor, OpenCode, CodeBuddy) are native
    sub-agent and have NO inline/subagent toggle. Pull-based platforms
    (Gemini, Qoder, Copilot) read their own JSONL prelude.

Axis B - orchestration runtime (direct vs channel):
    Platform-neutral. `channel` is a separate `trellis channel` worker runtime
    driven from workflow.md plus `.trellis/agents/{implement,check}.md`; it is
    NOT a value of `codex.dispatch_mode`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


VALID_DISPATCH = {"inline", "sub-agent"}

# Platforms whose sub-agent context is pushed by a PreToolUse hook: sub-agent
# dispatch is native and there is no inline/subagent toggle to switch.
CLASS1_HOOK_PUSH = {"claude", "cursor", "opencode", "codebuddy"}
# Platforms with no sub-agent hook: the agent reads its own JSONL prelude.
PULL_BASED = {"gemini", "qoder", "copilot"}
KNOWN_PLATFORMS = (
    {"codex"} | CLASS1_HOOK_PUSH | PULL_BASED | {"kiro", "droid", "pi", "kilo"}
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def detect_platform(override: str | None = None) -> tuple[str | None, str]:
    """Best-effort detection of the agent that triggered this skill.

    Returns (platform, source). Mirrors the precedence used by Trellis's own
    `inject-workflow-state.py` hook, then adds skill-runtime signals that the
    hook does not see (the hook runs with `*_PROJECT_DIR` set; a skill does
    not always).
    """
    if override:
        return override.lower(), "override"

    # 1. Trellis-native context id, e.g. "claude_<uuid>" / "codex_<uuid>".
    ctx = os.environ.get("TRELLIS_CONTEXT_ID", "")
    if "_" in ctx:
        prefix = ctx.split("_", 1)[0].lower()
        if prefix in KNOWN_PLATFORMS:
            return prefix, "TRELLIS_CONTEXT_ID"

    # 2. AI_AGENT, e.g. "claude-code_2-1-177_agent".
    ai = os.environ.get("AI_AGENT", "").lower()
    if ai:
        if ai.startswith("claude") or "claude-code" in ai:
            return "claude", "AI_AGENT"
        for slug in KNOWN_PLATFORMS:
            if ai.startswith(slug) or slug in ai:
                return slug, "AI_AGENT"

    # 3. Host-specific marker env vars.
    if os.environ.get("CLAUDECODE") or any(
        k.startswith("CLAUDE_CODE_") for k in os.environ
    ):
        return "claude", "CLAUDECODE"
    if any(k.startswith("CODEX_") for k in os.environ):
        return "codex", "CODEX_env"
    if any(k.startswith("CURSOR_") for k in os.environ):
        return "cursor", "CURSOR_env"

    # 4. The hook's *_PROJECT_DIR map (present when a hook, not a skill, runs).
    project_dir_map = {
        "CLAUDE_PROJECT_DIR": "claude",
        "CURSOR_PROJECT_DIR": "cursor",
        "CODEBUDDY_PROJECT_DIR": "codebuddy",
        "FACTORY_PROJECT_DIR": "droid",
        "GEMINI_PROJECT_DIR": "gemini",
        "QODER_PROJECT_DIR": "qoder",
        "KIRO_PROJECT_DIR": "kiro",
        "COPILOT_PROJECT_DIR": "copilot",
    }
    for env_name, platform in project_dir_map.items():
        if os.environ.get(env_name):
            return platform, env_name

    # 5. Where this skill copy is installed (.claude/skills, .codex/skills, ...).
    script_parts = set(Path(sys.argv[0]).resolve().parts)
    for marker, platform in (
        (".claude", "claude"),
        (".codex", "codex"),
        (".cursor", "cursor"),
        (".gemini", "gemini"),
        (".qoder", "qoder"),
        (".codebuddy", "codebuddy"),
        (".factory", "droid"),
        (".kiro", "kiro"),
    ):
        if marker in script_parts:
            return platform, "install_path"

    return None, "undetected"


def parse_codex_dispatch(config_text: str) -> tuple[str | None, str]:
    in_codex = False
    codex_indent = 0
    found: str | None = None

    for line in config_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if re.match(r"^codex:\s*(#.*)?$", stripped):
            in_codex = True
            codex_indent = indent
            continue
        if in_codex and indent <= codex_indent and not stripped.startswith("-"):
            in_codex = False
        if in_codex:
            match = re.match(r"^dispatch_mode:\s*([^#]+)", stripped)
            if match:
                found = match.group(1).strip().strip("\"'")
                break

    effective = found if found in VALID_DISPATCH else "inline"
    return found, effective


def workflow_state_tags(workflow: str) -> list[str]:
    visible = re.sub(r"```.*?```", "", workflow, flags=re.DOTALL)
    visible = re.sub(r"<!--.*?-->", "", visible, flags=re.DOTALL)
    tag_re = re.compile(
        r"\[workflow-state:([A-Za-z0-9_-]+)\]\s*\n.*?\n\s*\[/workflow-state:\1\]",
        re.DOTALL,
    )
    return sorted(set(tag_re.findall(visible)))


def agent_frontmatter(path: Path) -> dict[str, str]:
    text = read_text(path)
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    out: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip("\"'")
    return out


def resolve_dispatch_style(platform: str | None, effective: str) -> str:
    """Axis A value as seen by the triggering platform."""
    if platform == "codex":
        return effective  # inline | sub-agent
    if platform in CLASS1_HOOK_PUSH:
        return "native-subagent"
    if platform in PULL_BASED:
        return "pull-jsonl-prelude"
    return "unknown"


def inspect(repo: Path, platform_override: str | None = None) -> dict[str, Any]:
    repo = repo.resolve()
    trellis = repo / ".trellis"
    config_path = trellis / "config.yaml"
    workflow_path = trellis / "workflow.md"
    hook_path = repo / ".codex" / "hooks" / "inject-workflow-state.py"

    config_text = read_text(config_path)
    workflow = read_text(workflow_path)
    hook = read_text(hook_path)
    configured, effective = parse_codex_dispatch(config_text)
    platform, detection_source = detect_platform(platform_override)

    tags = workflow_state_tags(workflow)
    channel_agent_dir = trellis / "agents"
    channel_agents = {}
    if channel_agent_dir.is_dir():
        for path in sorted(channel_agent_dir.glob("*.md")):
            channel_agents[path.stem] = agent_frontmatter(path)

    codex_agent_dir = repo / ".codex" / "agents"
    codex_agents = []
    if codex_agent_dir.is_dir():
        codex_agents = sorted(path.name for path in codex_agent_dir.glob("trellis-*.toml"))

    mentions_channel = "trellis channel" in workflow
    has_worker_guard = "worker_guard:" in config_text
    has_inline_tags = "planning-inline" in tags and "in_progress-inline" in tags
    has_channel_agents = {"implement", "check"}.issubset(channel_agents.keys())
    has_codex_subagent_markers = "codex-sub-agent" in workflow
    has_codex_inline_markers = "codex-inline" in workflow

    # Axis A - dispatch style (Codex-only toggle); Axis B - orchestration runtime.
    dispatch_style = resolve_dispatch_style(platform, effective)
    orchestration = "channel" if mentions_channel else "direct"
    switchable_here = {
        # inline<->sub-agent is only a real, file-backed switch on Codex.
        "dispatch_style": platform == "codex",
        # channel is platform-neutral: workflow.md + .trellis/agents + worker_guard.
        "orchestration": True,
    }

    # Legacy single-field model, kept for backward compatibility.
    inferred = "inline"
    if mentions_channel:
        inferred = "channel"
    elif effective == "sub-agent":
        inferred = "subagent"

    warnings: list[str] = []
    if not trellis.is_dir():
        warnings.append("No .trellis directory found.")
    if configured is not None and configured not in VALID_DISPATCH:
        warnings.append(
            f"Invalid codex.dispatch_mode={configured!r}; effective mode is inline."
        )
    if effective == "sub-agent" and len(codex_agents) < 2:
        warnings.append("Sub-agent mode selected but native .codex/agents look incomplete.")
    if effective == "inline" and not has_inline_tags:
        warnings.append("Inline mode selected but workflow-state inline tags are missing.")
    if mentions_channel and not has_channel_agents:
        warnings.append("Workflow mentions trellis channel but .trellis/agents implement/check are missing.")
    if has_channel_agents and not mentions_channel:
        warnings.append("Channel worker definitions exist but workflow does not mention trellis channel.")
    if (
        platform is not None
        and platform != "codex"
        and configured in VALID_DISPATCH
    ):
        warnings.append(
            f"codex.dispatch_mode={configured!r} is set but platform "
            f"{platform!r} ignores it (Codex-only knob). On this platform "
            f"only channel orchestration is switchable."
        )

    return {
        "repo": str(repo),
        "trellis_present": trellis.is_dir(),
        "version": read_text(trellis / ".version").strip() or None,
        "triggering_platform": platform,
        "platform_detection_source": detection_source,
        "codex_dispatch_mode_configured": configured,
        "codex_dispatch_mode_effective": effective,
        "inferred_execution_model": inferred,
        "axes": {
            "dispatch_style": {
                "value": dispatch_style,
                "switchable_here": switchable_here["dispatch_style"],
            },
            "orchestration": {
                "value": orchestration,
                "switchable_here": switchable_here["orchestration"],
            },
        },
        "switchable_here": switchable_here,
        "workflow_state_tags": tags,
        "workflow_mentions": {
            "trellis_channel": mentions_channel,
            "trellis_before_dev": "trellis-before-dev" in workflow,
            "trellis_implement": "trellis-implement" in workflow,
            "codex_inline_marker": has_codex_inline_markers,
            "codex_sub_agent_marker": has_codex_subagent_markers,
        },
        "hook_support": {
            "exists": hook_path.is_file(),
            "reads_dispatch_mode": "dispatch_mode" in hook,
            "emits_codex_mode_banner": "<codex-mode>" in hook,
        },
        "channel": {
            "worker_guard_configured": has_worker_guard,
            "agents": channel_agents,
        },
        "codex_agents": codex_agents,
        "warnings": warnings,
    }


def print_text(report: dict[str, Any]) -> None:
    print(f"repo: {report['repo']}")
    print(f"trellis_present: {report['trellis_present']}")
    print(f"version: {report['version']}")
    print(
        "triggering_platform: "
        f"{report['triggering_platform']} "
        f"(via {report['platform_detection_source']})"
    )
    print(
        "codex.dispatch_mode: "
        f"configured={report['codex_dispatch_mode_configured']} "
        f"effective={report['codex_dispatch_mode_effective']}"
    )
    axes = report["axes"]
    print("axes:")
    print(
        "  A dispatch_style: "
        f"{axes['dispatch_style']['value']} "
        f"(switchable_here={axes['dispatch_style']['switchable_here']})"
    )
    print(
        "  B orchestration: "
        f"{axes['orchestration']['value']} "
        f"(switchable_here={axes['orchestration']['switchable_here']})"
    )
    print(f"inferred_execution_model (legacy): {report['inferred_execution_model']}")
    print("workflow_mentions:")
    for key, value in report["workflow_mentions"].items():
        print(f"  {key}: {value}")
    print("hook_support:")
    for key, value in report["hook_support"].items():
        print(f"  {key}: {value}")
    print("channel:")
    print(f"  worker_guard_configured: {report['channel']['worker_guard_configured']}")
    agents = report["channel"]["agents"]
    print(f"  agents: {', '.join(sorted(agents)) if agents else '(none)'}")
    print(
        "codex_agents: "
        + (", ".join(report["codex_agents"]) if report["codex_agents"] else "(none)")
    )
    if report["warnings"]:
        print("warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")
    else:
        print("warnings: (none)")


def print_brief(report: dict[str, Any]) -> None:
    axes = report["axes"]
    print(
        "mode: "
        f"platform={report['triggering_platform']} "
        f"source={report['platform_detection_source']} "
        f"codex={report['codex_dispatch_mode_configured']}"
        f"->{report['codex_dispatch_mode_effective']} "
        f"A={axes['dispatch_style']['value']}"
        f"/switchable={axes['dispatch_style']['switchable_here']} "
        f"B={axes['orchestration']['value']}"
        f"/switchable={axes['orchestration']['switchable_here']} "
        f"legacy={report['inferred_execution_model']}"
    )
    if report["warnings"]:
        print("warnings: " + " | ".join(report["warnings"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Path to the Trellis project")
    parser.add_argument(
        "--platform",
        default=None,
        help="Override detected platform (claude, codex, cursor, ...)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--brief", action="store_true", help="Emit one-line summary")
    args = parser.parse_args()

    report = inspect(Path(args.repo), platform_override=args.platform)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.brief:
        print_brief(report)
    else:
        print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
