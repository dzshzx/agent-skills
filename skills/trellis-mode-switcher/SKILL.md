---
name: trellis-mode-switcher
description: "Switch Trellis mode quickly: Codex inline/sub-agent or Trellis channel. Use when the user asks to switch/inspect mode, mentions inline/subagent/channel, codex.dispatch_mode, or channel-driven-subagent-dispatch."
---

# Trellis Mode Switcher

Run a tight switch: inspect -> edit one axis -> minimal validation -> compact
report. Do not turn inline/subagent into channel migration.

## Mode Map

| User label | Axis | Canonical target | Switchable where |
|------------|------|------------------|------------------|
| `inline` | A: dispatch style | `codex.dispatch_mode: inline` | Codex only |
| `subagent` / `sub-agent` | A: dispatch style | `codex.dispatch_mode: sub-agent` | Codex only |
| `channel` | B: orchestration runtime | workflow routes through `trellis channel` workers | any platform |

Class-1 platforms (Claude, Cursor, OpenCode, CodeBuddy) are already native
sub-agent. Pull-based platforms (Gemini, Qoder, Copilot) do not use the Codex
dispatch knob. For those platforms, only `channel` is a meaningful switch.

## Fast Path

1. Identify the target repo and requested label.
2. Follow the repo's `AGENTS.md` / local instructions.
3. Resolve `SKILL_DIR` as the folder containing this `SKILL.md`.
4. Inspect compactly:

   ```bash
   python3 "$SKILL_DIR/scripts/inspect_trellis_mode.py" --repo <repo> --brief
   ```

   Add `--platform codex|claude|cursor|...` when known.
5. Before editing, read `references/mode-templates.md` for the requested mode.
   For channel, also read `references/trellis-modes.md` sections `Channel Mode`
   and `Wait Policy`.

Completion criterion: you know the requested axis, whether it is switchable for
the triggering platform, the exact built-in template section to apply, and
whether there is a warning that blocks the switch.

## Apply

### Inline Or Sub-Agent

For Codex, edit only `.trellis/config.yaml`: set `codex.dispatch_mode` to
`inline` or `sub-agent` using the config template in
`references/mode-templates.md`.

Keep `.codex/agents/trellis-*.toml`; they are native Codex assets and channel
fallback assets. Do not edit `.trellis/workflow.md` for a plain inline/subagent
request unless the inspector shows the matching workflow blocks are missing. If
they are missing, merge only the matching workflow patch from
`references/mode-templates.md`; do not replace the whole workflow.

If the triggering platform is not Codex, do not claim Axis A was switched for it.
Only edit `codex.dispatch_mode` when the user explicitly wants Codex's future
behavior changed.

Completion criterion: the config contains exactly the requested
`codex.dispatch_mode`, and the inspector reports the expected effective mode.

### Channel

Channel is a workflow migration, not a `codex.dispatch_mode` value. Before
editing, read `references/trellis-modes.md` sections `Channel Mode` and
`Wait Policy`.

Use the official workflow template when available:

```bash
trellis workflow --template channel-driven-subagent-dispatch --create-new
```

If the CLI is unavailable or the marketplace cannot be fetched, use the built-in
templates in `references/mode-templates.md` as the source. Merge compatible
channel routing into the live workflow. Preserve local task lifecycle, planning,
commit, spec-update, and finish contracts.

Completion criterion: workflow Phase 2 routes implementation/checking through
`trellis channel`, `.trellis/agents/implement.md` and
`.trellis/agents/check.md` exist, `channel.worker_guard` is configured, and the
inspector reports `B=channel`.

## Safety

- Run `git status --short` before edits; preserve unrelated dirty files.
- Use manual patches; do not overwrite customized workflow files.
- Do not edit global npm installs or `node_modules`.
- If editing this skill, find installed copies first and keep every copy
  byte-identical. If only one copy exists, say so.

## Validate

Plain inline/subagent switch:

```bash
git diff --check
python3 "$SKILL_DIR/scripts/inspect_trellis_mode.py" --repo <repo> --platform codex --brief
python3 ./.trellis/scripts/get_context.py --mode phase --step 2.1 --platform codex
python3 ./.trellis/scripts/get_context.py --mode phase --step 2.2 --platform codex
```

Channel adds:

```bash
trellis channel --help
trellis channel list
```

Only run a live worker smoke test if the user explicitly asks; it can consume
time, tokens, and provider quota.

Only when this skill's scripts/tests changed:

```bash
python3 "$SKILL_DIR/tests/test_inspect_trellis_mode.py"
```

## Report

Keep the final report compact. Include only:

- selected mode and effective route
- files changed
- validation commands and pass/fail
- remaining mismatch or warning, if any

Do not paste full inspector or `get_context.py` output unless the user asks.
