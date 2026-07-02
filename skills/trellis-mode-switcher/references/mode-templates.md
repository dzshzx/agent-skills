# Trellis Mode Templates

These are built-in merge templates for `trellis-mode-switcher`. Use them when a
mode switch needs concrete config or workflow text, especially when the
`trellis` CLI is unavailable or the marketplace cannot be fetched.

They are patch templates, not replacement files. Merge only the missing or stale
mode-specific blocks into the target repo's existing `.trellis/config.yaml`,
`.trellis/workflow.md`, and `.trellis/agents/*.md`.

## Merge Rules

- Preserve the repo's local task lifecycle, planning artifacts, spec-update,
  commit, archive, and finish-work contracts.
- Keep `[workflow-state:...]` tag names and closing tags byte-exact.
- Keep both `planning`/`in_progress` and `planning-inline`/`in_progress-inline`
  blocks when a repo supports switching back later.
- Do not remove `.codex/agents/trellis-*.toml`; those remain native Codex assets
  and channel fallback assets.
- Do not delete `channel.worker_guard` when switching away from channel. It is
  harmless in direct modes and useful when the repo switches back.
- If official `trellis workflow --template <id> --create-new` output is
  available, diff it against the live workflow first. Prefer official wording
  for changed Trellis details, then preserve local workflow contracts.

## Config Templates

### Inline Config

Use for Codex inline mode. Update an existing `codex:` block if present; append
the block only when no `codex:` block exists.

```yaml
codex:
  dispatch_mode: inline
```

### Native Sub-Agent Config

Use for Codex native sub-agent dispatch.

```yaml
codex:
  dispatch_mode: sub-agent
```

### Channel Config

Use for channel orchestration. Keep Codex inline unless the user separately asks
for native Codex sub-agents; channel workers carry the implementation/check
split.

```yaml
codex:
  dispatch_mode: inline

channel:
  worker_guard:
    idle_timeout: 5m
    max_live_workers: 6
```

## Workflow Templates

### Inline Workflow Patch

Use when `codex.dispatch_mode: inline` is selected and the inspector warns that
inline workflow blocks are missing.

```markdown
[workflow-state:planning-inline]
Load `trellis-brainstorm`; stay in planning.
Lightweight tasks may be PRD-only. Complex tasks need `prd.md`, `design.md`,
and `implement.md`; ask for review before `task.py start`.
Inline mode: skip jsonl curation; Phase 2 reads artifacts/specs via
`trellis-before-dev`.
[/workflow-state:planning-inline]

[workflow-state:in_progress-inline]
Flow: `trellis-before-dev` -> edit -> `trellis-check` -> `trellis-update-spec`
-> commit (Phase 3.4) -> `/trellis:finish-work`.
The main Codex session edits directly. Read `prd.md`, then `design.md` if
present, then `implement.md` if present, plus relevant `.trellis/spec/` docs
before editing.
[/workflow-state:in_progress-inline]
```

Active task routing patch:

```markdown
[codex-inline, Kilo, Antigravity, Devin]

- Planning or unclear requirements -> `trellis-brainstorm`.
- Before editing -> `trellis-before-dev`; after editing -> `trellis-check`.
- Repeated debugging -> `trellis-break-loop`; spec updates -> `trellis-update-spec`.

[/codex-inline, Kilo, Antigravity, Devin]
```

### Native Sub-Agent Workflow Patch

Use when `codex.dispatch_mode: sub-agent` is selected and the inspector warns
that native sub-agent routing is missing. Keep any existing non-Codex platform
entries.

```markdown
[Claude Code, Cursor, OpenCode, codex-sub-agent, Kiro, Gemini, Qoder, CodeBuddy, Copilot, Droid, Pi]

- Planning or unclear requirements -> `trellis-brainstorm`.
- `in_progress` implementation/check -> dispatch `trellis-implement` / `trellis-check`.
- Repeated debugging -> `trellis-break-loop`; spec updates -> `trellis-update-spec`.

[/Claude Code, Cursor, OpenCode, codex-sub-agent, Kiro, Gemini, Qoder, CodeBuddy, Copilot, Droid, Pi]
```

Phase 2 prompt patch:

```markdown
[workflow-state:in_progress]
Flow: dispatch `trellis-implement` -> dispatch `trellis-check` ->
`trellis-update-spec` -> commit (Phase 3.4) -> `/trellis:finish-work`.
Sub-agent dispatch prompt must start with `Active task: <task path from task.py current>`.
The main session coordinates, integrates results, updates specs, commits, and
finishes; implementation/checking belongs to the worker agents unless the user
asks for inline work.
[/workflow-state:in_progress]
```

### Channel Workflow Patch

Use when orchestration should become channel-driven. This is the local fallback
for marketplace template `channel-driven-subagent-dispatch`.

Phase index patch:

```markdown
Phase 1: Plan    -> classify, get task-creation consent, then write planning artifacts
Phase 2: Execute -> implement/check through `trellis channel` workers
Phase 3: Finish  -> verify, update spec, commit, and wrap up
```

Planning patch:

```markdown
[workflow-state:planning]
Load `trellis-brainstorm`; stay in planning.
Lightweight tasks may be PRD-only. Complex tasks need `prd.md`, `design.md`,
and `implement.md`; ask for review before `task.py start`.
Channel-worker mode: curate `implement.jsonl` and `check.jsonl` as
spec/research manifests before start.
[/workflow-state:planning]
```

Execution patch for normal sub-agent-capable platforms:

```markdown
[workflow-state:in_progress]
Flow: channel-driven `implement` worker -> channel-driven `check` worker ->
`trellis-update-spec` -> commit (Phase 3.4) -> `/trellis:finish-work`.
Main-session default: use `trellis channel spawn` with
`.trellis/agents/implement.md` and `.trellis/agents/check.md`; do not use
native host sub-agents unless the user explicitly requests native dispatch or a
host-only capability requires it.
Worker context order: jsonl entries -> `prd.md` -> `design.md` if present ->
`implement.md` if present. Read results with `trellis channel messages --raw`
when precision matters.
[/workflow-state:in_progress]
```

Execution patch for inline platforms:

```markdown
[workflow-state:in_progress-inline]
Flow: `trellis-before-dev` -> edit -> channel-driven `check` worker ->
validation -> `trellis-update-spec` -> commit (Phase 3.4) ->
`/trellis:finish-work`.
Inline implementation is allowed only when the user asked for it or the change
is too small to justify a worker. After editing, prefer
`trellis channel spawn --agent check` for independent review.
Read context before editing: `prd.md` -> `design.md` if present ->
`implement.md` if present, plus relevant spec/research loaded by skills.
[/workflow-state:in_progress-inline]
```

Active task routing patch:

```markdown
[Claude Code, Cursor, OpenCode, codex-sub-agent, Kiro, Gemini, Qoder, CodeBuddy, Copilot, Droid, Pi]

- Planning or unclear requirements -> `trellis-brainstorm`.
- `in_progress` implementation -> `trellis channel spawn --agent implement`.
- `in_progress` quality check -> `trellis channel spawn --agent check`.
- Repeated debugging -> `trellis-break-loop`; spec updates -> `trellis-update-spec`.

[/Claude Code, Cursor, OpenCode, codex-sub-agent, Kiro, Gemini, Qoder, CodeBuddy, Copilot, Droid, Pi]

[codex-inline, Kilo, Antigravity, Devin]

- Planning or unclear requirements -> `trellis-brainstorm`.
- Before editing -> `trellis-before-dev`; after editing -> prefer a channel-driven `check` worker.
- Repeated debugging -> `trellis-break-loop`; spec updates -> `trellis-update-spec`.

[/codex-inline, Kilo, Antigravity, Devin]
```

Phase 2 implement command patch:

```bash
TASK=.trellis/tasks/<active-task>
CH=impl-<topic>
trellis channel create "$CH" --task "$TASK" --by main --ephemeral
trellis channel spawn "$CH" \
  --agent implement \
  --as implement \
  --jsonl "$TASK/implement.jsonl" \
  --file "$TASK/prd.md" \
  --file "$TASK/design.md" \
  --file "$TASK/implement.md" \
  --cwd "$PWD" \
  --timeout 60m
trellis channel send "$CH" --as main --to implement --text-file /tmp/implement-brief.md
# Wait using the bounded liveness policy in `references/trellis-modes.md`.
trellis channel messages "$CH" --raw --from implement --last 20
```

Phase 2 check command patch:

```bash
TASK=.trellis/tasks/<active-task>
CH=cr-<topic>
trellis channel create "$CH" --task "$TASK" --by main --ephemeral
trellis channel spawn "$CH" \
  --agent check \
  --as check \
  --jsonl "$TASK/check.jsonl" \
  --file "$TASK/prd.md" \
  --file "$TASK/design.md" \
  --file "$TASK/implement.md" \
  --cwd "$PWD" \
  --timeout 30m
trellis channel send "$CH" --as main --to check --text-file /tmp/check-brief.md
# Wait using the bounded liveness policy in `references/trellis-modes.md`.
trellis channel messages "$CH" --raw --from check --last 40
```

Omit `--file "$TASK/design.md"` or `--file "$TASK/implement.md"` when the file
does not exist. Worker briefs must state the active task, goal, editable scope,
forbidden actions, validation commands, and expected completion summary.

## Channel Worker Agent Templates

Use these only when `.trellis/agents/implement.md` or `.trellis/agents/check.md`
is missing. If an official `trellis update` can backfill them, prefer that
output. The default provider matches the official template; override with
`trellis channel spawn --provider <provider>` when the repo uses another model.

### `.trellis/agents/implement.md`

```markdown
---
name: implement
description: |
  Code implementation expert for the Trellis channel runtime. Understands specs
  and task artifacts, then implements features. No git commit allowed.
provider: claude
labels: [trellis, implement]
---

# Implement Agent (channel runtime)

You are spawned by `trellis channel spawn --agent implement`. You receive
`Active task: <path>` in your inbox; use it to locate task artifacts.

Read in order: `implement.jsonl` if present, `prd.md`, `design.md` if present,
`implement.md` if present, then relevant `.trellis/spec/` docs.

Implement the requested change, run scoped lint/typecheck when available, and
report files touched, key decisions, verification results, and open questions.
Do not run `git commit`, `git push`, or `git merge`.
```

### `.trellis/agents/check.md`

```markdown
---
name: check
description: |
  Code quality auditor for the Trellis channel runtime. Reviews uncommitted diffs
  against task artifacts and specs, self-fixes small issues, and reports results.
provider: claude
labels: [trellis, check]
---

# Check Agent (channel runtime)

You are spawned by `trellis channel spawn --agent check`. You receive
`Active task: <path>` in your inbox; use it to locate task artifacts.

Read in order: `check.jsonl` if present, `prd.md`, `design.md` if present,
`implement.md` if present, then relevant `.trellis/spec/` docs. Inspect
`git diff` / `git diff --staged`, verify the diff against artifacts and specs,
self-fix small mechanical issues, and run scoped lint/typecheck when available.

Report files checked, issues fixed, issues left open, and verification results.
Do not run `git commit`, `git push`, or `git merge`.
```
