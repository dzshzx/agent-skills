# Trellis Execution Modes

This reference captures the current switching model, but Trellis behavior can
move. Before mutating a repo, re-check the official docs, source branch, and
local files.

## The Two-Axis Model (read first)

Trellis execution is **two orthogonal axes**, not one switch with three values.
The labels users say (`inline` / `subagent` / `channel`) live on different axes:

- **Axis A — dispatch style: `inline` ↔ `sub-agent`.** A Codex-only knob
  (`codex.dispatch_mode`). Class-1 hook-push platforms (Claude, Cursor,
  OpenCode, CodeBuddy) are native sub-agent with no toggle; pull-based platforms
  (Gemini, Qoder, Copilot) read their own JSONL prelude.
- **Axis B — orchestration runtime: `direct` ↔ `channel`.** Platform-neutral.
  `channel` is a separate `trellis channel` worker runtime, NOT a value of
  `codex.dispatch_mode`. Any platform can drive it from `workflow.md`.

A repo can sit on both axes at once (e.g. Codex `sub-agent` AND channel
orchestration). The inspector reports them separately as `axes.dispatch_style`
and `axes.orchestration`, plus `switchable_here` per detected platform.

Why the asymmetry: the hook flow differs by platform. Class-1 platforms inject
sub-agent context via a `PreToolUse` hook (`inject-subagent-context.py`), so
sub-agent dispatch is native. Codex sub-agents run with `fork_turns="none"` and
cannot inherit parent context, so Codex defaults to `inline` and only the
`<codex-mode>` banner + `*-inline` tag flip (both gated by `platform == "codex"`)
opt it into `sub-agent`.

## Official Sources To Check

- Docs index: https://docs.trytrellis.app/llms.txt
- Configuration: https://docs.trytrellis.app/rc/advanced/configuration.md
- Runtime flow: https://docs.trytrellis.app/rc/start/how-it-works.md
- Multi-platform: https://docs.trytrellis.app/rc/advanced/multi-platform.md
- Custom agents: https://docs.trytrellis.app/rc/advanced/custom-agents.md
- Custom skills (install paths): https://docs.trytrellis.app/rc/advanced/custom-skills.md
- Changelog: https://docs.trytrellis.app/changelog
- Source: https://github.com/mindfold-ai/Trellis (default branch `main`)
- Marketplace index: https://raw.githubusercontent.com/mindfold-ai/marketplace/main/index.json

Useful source files in the Trellis repository:

- `packages/cli/src/templates/trellis/config.yaml`
- `packages/cli/src/templates/shared-hooks/inject-workflow-state.py`
- `packages/cli/src/templates/trellis/scripts/common/workflow_phase.py`
- `packages/cli/src/commands/channel/index.ts`
- `packages/cli/src/commands/channel/guard.ts`

Useful marketplace workflow files:

- `workflows/native/workflow.md`
- `workflows/tdd/workflow.md`
- `workflows/channel-driven-subagent-dispatch/workflow.md`

Built-in fallback templates for this skill live in `mode-templates.md`. Use
them when the CLI or marketplace is unavailable; prefer official CLI output when
it can be fetched and diffed.

## Skill Install Paths (per platform)

The same skill body is copied — not symlinked — into each agent's skill dir:

- Claude Code: `.claude/skills/{name}/SKILL.md`
- Codex: `.codex/skills/{name}/SKILL.md` (plus `.agents/skills/`, the shared layer)
- Cursor / Gemini / Qoder / Copilot / …: `.cursor/`, `.gemini/`, `.qoder/`,
  `.github/skills/`, … each with its own `skills/{name}/SKILL.md`.

Keep every installed copy byte-identical; platform differences are resolved at
runtime by the inspector's detection, never by shipping different files.

## Shared Invariants

- `.trellis/config.yaml` is the project config source for
  `codex.dispatch_mode` and `channel.worker_guard`.
- `.trellis/workflow.md` is the workflow source of truth. Hooks and
  `get_context.py --mode phase` parse it; they should not be treated as a
  second workflow definition.
- `codex.dispatch_mode` is Codex-only. Other platforms ignore it.
- Invalid or missing Codex dispatch mode should be treated as effectively
  `inline`.
- `workflow.md` platform markers use virtual Codex platforms:
  `codex-inline` and `codex-sub-agent`.
- Codex hooks emit a `<codex-mode>` banner and pick
  `[workflow-state:STATUS-inline]` for inline mode when present. Non-codex
  platforms get the plain status and no banner.
- `implement.jsonl` and `check.jsonl` are context manifests for workers or
  sub-agents. They do not replace `prd.md`, `design.md`, or `implement.md`.

## Inline Mode

Canonical state:

```yaml
codex:
  dispatch_mode: inline
```

Expected behavior:

- Effective platform is `codex-inline`.
- The hook uses `[workflow-state:planning-inline]` and
  `[workflow-state:in_progress-inline]` when those blocks exist.
- The main Codex session reads task artifacts/specs and edits directly.
- Normal implementation path is `trellis-before-dev -> edit -> trellis-check`.
- Do not dispatch native `trellis-implement` or `trellis-check` sub-agents.

Switch checklist:

1. Set or insert `codex.dispatch_mode: inline` using `mode-templates.md`.
2. Confirm `.trellis/workflow.md` has the `*-inline` workflow-state blocks.
3. Confirm `get_context.py --mode phase --platform codex` surfaces
   `codex-inline` instructions.
4. Keep native `.codex/agents/trellis-*.toml` files unless the user explicitly
   asks to remove platform support.

## Native Sub-Agent Mode

Canonical state:

```yaml
codex:
  dispatch_mode: sub-agent
```

Expected behavior:

- Effective platform is `codex-sub-agent`.
- The hook uses the plain `[workflow-state:planning]` and
  `[workflow-state:in_progress]` blocks.
- The main session coordinates, clarifies, updates specs, commits, and
  finishes.
- Implementation/check/research can be delegated to host-native Codex agents:
  `.codex/agents/trellis-implement.toml`,
  `.codex/agents/trellis-check.toml`, and
  `.codex/agents/trellis-research.toml`.
- Dispatch prompts must start with `Active task: <task path from task.py current>`
  on platforms where sub-agents need to resolve context.

Switch checklist:

1. Set or insert `codex.dispatch_mode: sub-agent` using `mode-templates.md`.
2. Confirm native Codex agent definitions exist.
3. Confirm workflow platform blocks include `codex-sub-agent`.
4. Confirm Phase 1 context curation rules mention `implement.jsonl` and
   `check.jsonl` where needed.
5. Confirm sub-agent files contain recursion guards so workers do not spawn
   `trellis-implement` / `trellis-check` again.

## Channel Mode

Canonical state:

```yaml
codex:
  dispatch_mode: inline

channel:
  worker_guard:
    idle_timeout: 5m
    max_live_workers: 6
```

Expected behavior:

- Codex remains `inline` at the hook/config layer to avoid native sub-agent
  context isolation.
- The workflow routes meaningful implementation/check work through
  `trellis channel` workers.
- `.trellis/agents/implement.md` and `.trellis/agents/check.md` define channel
  workers used by `trellis channel spawn --agent implement|check`.
- Channel events live under `~/.trellis/channels/<project>/<channel>/`.
- Use `trellis channel messages --raw` for audit-quality results; pretty output
  may be truncated or dashboard-oriented.

Preferred switch path:

```bash
trellis workflow --template channel-driven-subagent-dispatch --create-new
```

If the command or marketplace fetch is unavailable, use
`mode-templates.md#channel-workflow-patch` as the local fallback.

Then:

1. Diff `.trellis/workflow.md.new` against `.trellis/workflow.md`.
2. Merge channel execution rules into the live workflow without dropping local
   task lifecycle, planning, commit, or spec-update contracts.
3. Set `codex.dispatch_mode: inline`.
4. Add or update `.trellis/agents/implement.md` and `.trellis/agents/check.md`.
5. Keep `.trellis/.template-hashes.json` changes when they are produced by the
   official workflow command.
6. Do not make `.codex/agents/trellis-*.toml` the normal path in channel mode;
   they are fallback/native platform assets.

Typical channel flow (this mirrors the official template's single blocking
`wait`; for production use replace the `wait` line per **Wait Policy** below):

```bash
TASK=.trellis/tasks/<active-task>
trellis channel create impl-<topic> --task "$TASK" --by main --ephemeral
trellis channel spawn impl-<topic> --agent implement --as implement --jsonl "$TASK/implement.jsonl" --cwd "$PWD" --timeout 60m
trellis channel send impl-<topic> --as main --to implement --text-file /tmp/implement-brief.md
trellis channel wait impl-<topic> --as main --kind done --from implement --timeout 60m
trellis channel messages impl-<topic> --raw --from implement --last 20
```

For check:

```bash
TASK=.trellis/tasks/<active-task>
trellis channel create cr-<topic> --task "$TASK" --by main --ephemeral
trellis channel spawn cr-<topic> --agent check --as check --jsonl "$TASK/check.jsonl" --cwd "$PWD" --timeout 30m
trellis channel send cr-<topic> --as main --to check --text-file /tmp/check-brief.md
trellis channel wait cr-<topic> --as main --kind done --from check --timeout 30m
trellis channel messages cr-<topic> --raw --from check --last 40
```

Worker briefs should include active task path, goal, editable scope, forbidden
actions, validation commands, and expected completion summary.

### Wait Policy: Base On The Official Template, Replace The Wait

`channel-driven-subagent-dispatch` is a **marketplace** workflow template (not
bundled; the default `workflow.md` has no channel content). It is the official
convention and the correct base — reuse its phase structure, platform blocks,
and anti-takeover prose. But know its two gaps before shipping it as-is:

- **What it covers:** channel is the default execution model; the main session
  must NOT do large inline work or fall back to native sub-agents unless the
  user asks or a host-only capability is required (anti-takeover, prose-only).
- **What it omits:** any stall / deadlock recovery. Its wait is a single
  blocking `trellis channel wait --kind done --timeout 60m` (30m for check).
  Two failure modes follow: (1) under Codex's per-shell-command timeout, that
  long blocking call is killed early, the main agent reads it as "worker gone"
  and takes over inline despite the prose rule; (2) if the worker truly hangs,
  the main session waits the full hard timeout with no liveness check or
  recovery.

**Policy: keep the official template as the base; the only change is to replace
its single blocking `wait` line with a bounded, liveness-gated poll loop plus an
escalation ladder.** This preserves Trellis's anti-takeover intent while adding
the command-timeout robustness and genuine stall recovery the template lacks.
Decide continuation by *liveness evidence* (a `done`, new messages, or a live
worker in `channel list`), not by elapsed time.

```bash
CH=impl-<topic>
HARD_DEADLINE=$(( $(date +%s) + 3600 ))   # 60m absolute backstop (match template)
SILENCE_LIMIT=3                            # consecutive empty windows (~3m true silence) before suspecting a stall
silent=0; last_seen=""

while :; do
  # Short timeout so each command returns well inside Codex's per-command limit.
  if trellis channel wait "$CH" --as main --kind done --from implement --timeout 60s; then
    echo "done"; break
  fi
  # No done yet: is the worker alive / progressing?
  snapshot=$(trellis channel messages "$CH" --raw --from implement --last 1 2>/dev/null)
  alive=$(trellis channel list 2>/dev/null | grep -E "$CH.*(running|busy|idle)")
  if [ -z "$alive" ]; then
    echo "worker process gone (exited / reaped by worker_guard)"; break   # escalate
  elif [ "$snapshot" != "$last_seen" ]; then
    last_seen="$snapshot"; silent=0                                       # progress -> stay patient
  else
    silent=$((silent+1))
  fi
  if [ "$silent" -ge "$SILENCE_LIMIT" ] || [ "$(date +%s)" -ge "$HARD_DEADLINE" ]; then
    echo "suspected stall -> escalate"; break
  fi
done
```

Escalation ladder after the loop exits without `done` (recover before falling
back; never silently take over):

1. `trellis channel interrupt "$CH" ...` with a nudge, then wait one more window.
2. Still silent / process dead -> `trellis channel kill` then re-`spawn` one retry.
3. Retry also fails -> only then inline takeover, and state explicitly that this
   is a degradation because the worker stalled.

`SILENCE_LIMIT` and `HARD_DEADLINE` are soft defaults; they cooperate with
`channel.worker_guard.idle_timeout` (a truly idle worker self-terminates and
then shows as gone in `channel list`). When switching to channel mode, write
this policy — not the bare `wait --timeout 60m` — into the worker-coordination
block of `workflow.md`.

## Validation Matrix

Always:

```bash
git status --short
git diff --check
python3 ./.trellis/scripts/get_context.py --mode phase --platform codex
python3 ./.trellis/scripts/get_context.py --mode phase --step 2.1 --platform codex
python3 ./.trellis/scripts/get_context.py --mode phase --step 2.2 --platform codex
python3 ./.trellis/scripts/task.py current --source
```

Inline:

- Phase 2 should point the main session at direct reading/editing and
  `trellis-before-dev` / `trellis-check`.
- Hook output should mention `inline` in `<codex-mode>`.

Sub-agent:

- Phase 2 should instruct native dispatch of `trellis-implement` and
  `trellis-check`.
- Hook output should mention `sub-agent` in `<codex-mode>`.

Channel:

```bash
trellis channel --help
trellis channel list
```

- Phase 2 should mention `trellis channel spawn --agent implement` and
  `trellis channel spawn --agent check`.
- `.trellis/agents/implement.md` and `.trellis/agents/check.md` should be
  resolvable by `trellis channel spawn --agent`.
- A live worker smoke test can consume time, tokens, provider quota, and may
  modify files if the prompt is too broad. Ask before running it unless the user
  explicitly requested runtime proof.
