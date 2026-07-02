---
name: sync-agents-instructions
description: Governs shared agent instruction rules across a workspace of repos and any set of AI agents (Claude Code, Codex, Cursor, ...) — adds new shared rules, syncs references, and converges duplicate project-local rules into the shared sources, driven by a per-machine config file, and routes each rule along two axes — project vs user level, and vertical domain slices (behavior contract, machine facts, code standards, frontend standards, ...) with native-inject vs lazy-load placement. Inspect-plan-execute flow with dirty-worktree protection, governed handling of gitignored instruction files, and per-repo target-only commits. Use when asked to sync AGENTS.md/CLAUDE.md rules, add or update shared agent instructions, or deduplicate agent rules across a workspace.
---

# Sync Agents Instructions

## Overview

Use this skill to govern shared agent instruction rules across the projects of
one machine. Governance has two equally important actions:

- **Add or update**: put new or revised reusable rules into a shared
  instruction source and ensure project instruction files reference it.
- **Converge**: find project-local rules that duplicate or overlap a shared
  rule, remove the covered copies, and preserve project-specific content.

Both actions follow the same inspect-plan-execute-validate flow.

## Machine Topology Comes From Config, Not From This File

This skill contains **no machine-specific paths**. The instruction topology of
the current machine is read from a config file:

1. If the user names a config path, use it.
2. Otherwise read `~/.config/agent-instructions/sync-config.toml`.
3. If no config exists, **stop and offer to create one** by asking the user
   for each field below (do not guess a topology from directory listings).

Config schema — see [references/config-example.toml](references/config-example.toml)
for a complete annotated example:

- `[workspace]` — `project_globs` (where project repos live) and
  `project_instruction_files` (which per-repo filenames are governed, e.g.
  `AGENTS.md`, `CLAUDE.md`).
- `[[shared_sources]]` — each shared instruction file with:
  - `role` — what belongs here (the config owner's split; this skill enforces
    the split it is given, it does not invent one);
  - `domain` — the vertical slice it covers (`behavior`, `machine-facts`,
    `code-standards`, `frontend`, `docs-writing`, ... free-form);
  - `load` — `"always"` (wired into agent entry files, natively injected
    where the agent expands references) or `"on-demand"` (entry files carry
    only a one-line trigger pointer: *when doing X, read Y*).
- `[workspace].off_limits` — glob patterns for files this skill must never
  write or restructure (project workflow specs such as `.trellis/**`,
  `docs/agents/**`, repo `conventions/**`). Rules that belong there are
  reported, never moved.
- `[[agents]]` — one entry per AI agent on the machine: `name`, `entry_file`
  (the file that agent loads globally), optional `agent_specific_file`
  (rules only that agent should see), optional `runtime_constructs`
  (identifiers that mark a rule as agent-bound, e.g. tool names such as
  `apply_patch` or `WebFetch`). Adding support for a new agent = adding an
  `[[agents]]` entry, not editing this skill.

## Placement Decision Model（rule routing along two axes）

Route every rule through both axes before writing anything.

**Axis 1 — level (project vs user):**

1. Contains a project-specific atom (repo path, deployment gate, domain
   boundary, spec pointer) → **project instruction file**.
2. Is project workflow / executable convention (how to test, branch, release,
   spec layers) → **project workflow owner** (`off_limits` territory, e.g.
   `.trellis/spec/`, `docs/agents/`). Report it; never absorb it. This skill
   governs instruction surfaces, not project workflows.
3. Holds across ≥2 projects with no project atoms → **user level**. Apply the
   *rule of two*: promote when a rule shows up in a second project, not on
   first sight.
4. Unsure → leave at project level and flag as a promotion candidate. A wrong
   global rule pollutes every project; a not-yet-promoted local rule costs one
   duplicate.

**Axis 2 — vertical slice (within user level), by change-driver × task scope:**

| Rule applies to | Slice | Load |
| --- | --- | --- |
| every task, any domain | behavior contract | `always` (native inject — keep this file small) |
| every task, changes when the machine changes | machine facts | `always` |
| only tasks in one technical domain (frontend, code style, docs writing, ...) | that domain's slice file | `on-demand` (entry carries a one-line trigger pointer) |
| only one agent | that agent's `agent_specific_file` | per agent |

**Anti-fragmentation:** a new slice file needs minimum mass — roughly ≥5
rules or one cohesive theme. Below that, the rule goes into a named section
of the nearest existing file; the section is the future slice's seed and can
be promoted later (e.g. a skills/agent-assets routing section stays inside
the behavior contract until it outgrows it).

**Injection budget:** the natively-injected surface (entry files plus all
`load = "always"` sources, as expanded by the most eager agent) should stay
within the budget set in config (`[workspace].inject_budget_lines`, default
300). When over budget, demote domain sections to `on-demand` slices before
trimming content.

## Workflow

1. **Collect.** Inventory Git repos under every `project_globs` entry, pruning
   `node_modules`, `vendor`, archives, temporary worktrees, and third-party
   clones. For each repo, report: which governed instruction files exist;
   whether they reference shared sources; ignored / dirty / staged status;
   unrelated dirty paths. Non-Git directories are listed as skipped with
   reason "not a Git repo".
2. **Compare.** Read project instruction files and identify rules that overlap
   a shared source. Compare against a single rule candidate when adding or
   updating one, or against the full shared-source content when converging
   existing duplicates. Classify each match as:
   - **Covered** — all meaning is already in the shared source and the rule
     contains no agent- or project-specific atoms (repo-only paths, commands,
     deployment gates, ADR/spec boundaries, managed-block markers, or
     **agent-runtime constructs** from any `[[agents]].runtime_constructs`
     list); safe to remove.
   - **Project-specific** — contains one or more specific atoms listed above;
     must be preserved even if parts overlap. An agent-runtime construct stays
     in that agent's own file (the shared file states the rule generically).
   - **Needs confirmation** — partial overlap, or a rule whose placement the
     config's role split does not clearly decide; present to the user.
3. **Plan.** 🔴 **STOP — present the plan and wait for user confirmation
   before any write.** The plan must list, per file:
   - Shared source: what will be added or changed.
   - Each project instruction file: rules to remove (covered), rules to
     preserve (project-specific), rules needing confirmation, references to add.
   - Repos skipped (no governed file, non-Git, or unsafe Git state).
   - Gitignored instruction files, reported **separately** (see below).
4. **Execute.** After user confirmation (if the user rejects the plan, report
   unexecuted repos and stop):
   a. Back up each shared source (`cp <file> <file>.bak-YYYYMMDD`) before
      writing. If the backup fails, stop that shared source and report.
   b. Write and verify shared sources first.
   c. Then apply project instruction file changes. If the shared-source write
      failed or its content does not match the plan, stop — do not touch
      project files.
   d. Re-run inventory immediately before each project edit to catch
      intervening changes.
5. **Validate.**
   - Run per-file Git checks (see Validation section below).
   - **Completion self-check**: grep governed files for distinctive clause
     text from the converged rule. Any match not already marked as preserved
     or confirmed in the plan means the task is not done.

## Gitignored Instruction Files Are Governed, Not Skipped

A gitignored instruction file still changes agent behavior in that workspace.
Treat it as a distinct governance class:

- Include it in inventory and Compare exactly like tracked files.
- Never silently skip it; never force-add or commit it.
- Writes to it require explicit user confirmation and produce a visible
  before/after diff; validation uses content diff + clause grep, not Git
  status.
- Report these files under a separate "local-only governed files" heading so
  the user can distinguish repo-committed changes from local-only ones.

## Allowed Changes

- Shared instruction sources: add, update, or restructure rules. Do not create
  project Git commits for these files (they live outside project repos).
- Project instruction files: remove rules covered by a shared source; add
  missing references to shared sources (in the reference syntax the owning
  agent understands, e.g. `@<path>` lines). Do not rewrite, sort, or reformat
  other project content.

## Preservation Rules

- Managed blocks (Trellis, plugins, tools, generated sections) are opaque —
  do not interpret, normalize, sort, reformat, or remove them.
- A project-local rule may only be removed when Compare classifies it as
  **Covered**. When in doubt, preserve and flag for the user.

## Git Safety

- Dirty repos are eligible if the governed file itself has no unsafe
  pre-existing changes. Record and preserve unrelated dirty paths.
- If the governed file has staged changes, pause that repo and wait for user
  confirmation before editing.
- If the governed file has pre-existing unstaged changes, process only when
  those changes are explicitly confirmed or clearly attributable to this run.
- Use target-only commits (`git commit --only -- <file>`); do not unstage,
  stash, reset, checkout, or clean unrelated changes.

## Do Not

- Do not create missing project instruction files.
- Do not rewrite, sort, reformat, or "clean up" project content that is not a
  covered duplicate.
- Do not remove a rule that contains any project-specific atom, even if most
  of it overlaps with the shared source.
- Do not touch managed blocks.
- Do not commit shared instruction sources.
- Do not force-add a gitignored instruction file.
- Do not stash, reset, checkout, or clean unrelated dirty paths.
- Do not hardcode discovered machine topology back into this SKILL.md — it
  belongs in the config file.
- Do not write into `off_limits` paths (project workflow specs); rules that
  belong there are reported to the user, not moved or rewritten.
- Do not create a new slice file below minimum mass, and do not slice finer
  than task-scope domains (no per-language micro-files on day one).

## Validation

Before each project instruction file commit:

```bash
git status --short
git diff -- <file>
git check-ignore -v -- <file>
git diff --check -- <file>
```

After each commit, verify unrelated staged paths remain staged and report
remaining dirty paths. Final output must state which repos were changed,
preserved, or skipped, and list local-only (gitignored) governed files
separately.
