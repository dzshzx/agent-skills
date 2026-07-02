---
name: sync-agents-instructions
description: Governs shared agent instruction rules across workspace repos — adds new shared rules, syncs references, and converges duplicate project-local rules into the shared source. Inspect-plan-execute flow with dirty-worktree protection and per-repo target-only commits. Use when asked to sync AGENTS.md, add or update shared Codex instructions, enforce public instruction rules, or deduplicate agent rules across /home/ubuntu/workspace.
---

# Sync Agents Instructions

## Overview

Use this skill to govern shared agent instruction rules across workspace
projects. Governance has two equally important actions:

- **Add or update**: put new or revised reusable rules into the shared
  instruction source and ensure project `AGENTS.md` files reference it.
- **Converge**: find project-local rules that duplicate or overlap a shared
  rule, remove the covered copies, and preserve project-specific content.

Both actions follow the same inspect-plan-execute-validate flow.

## Scope

- Shared instruction sources: `/home/ubuntu/.codex/INSTRUCTION.md`,
  `/home/ubuntu/.codex/AGENTS.md`,
  `/home/ubuntu/.config/agent-instructions/shared.md` (volatile machine facts)
  and `/home/ubuntu/.config/agent-instructions/shared-behavior.md` (stable
  agent-agnostic behavior contract) — both `@`-imported by both agents' entry
  files.
- Agent-global entry files: `/home/ubuntu/.claude/CLAUDE.md` (Claude entry) and
  the Codex entries above. These are governed for the agent-global convergence
  axis below. All shared sources and entry files live outside project repos:
  back up before write, never create a Git commit for them.
- Project instruction files: `/home/ubuntu/workspace/*/AGENTS.md` (top-level
  only; no recursive scan unless extra paths are passed explicitly).
- Do not create missing project `AGENTS.md` files.

### Two convergence axes

- **Project → Codex shared source** (the original axis): converge duplicate
  rules in `workspace/*/AGENTS.md` into the Codex shared sources.
- **Agent-global → agnostic shared files** (the new axis): converge rules
  duplicated across the agent-global entry files (`~/.claude/CLAUDE.md` and the
  Codex entries) into the agnostic shared layer, split by what drives change:
  **volatile machine/infrastructure facts** (ports, paths, endpoints, the
  web-reading ladder) go to `~/.config/agent-instructions/shared.md`; **stable
  agent-agnostic behavior contract** (response style, verify-first, file
  safety, verification, official-sources-first, file-size limits, shell
  code-vs-data) goes to `~/.config/agent-instructions/shared-behavior.md`.
  Agent-specific runtime rules (e.g. `apply_patch`, Codex skill install dirs,
  `codex/{feature}` branch naming) stay in that agent's own file
  (`~/.codex/INSTRUCTION.md` for Codex).

## Workflow

1. **Collect.** Inventory Git repos under `/home/ubuntu/workspace/`, pruning
   `node_modules`, `vendor`, archives, temporary worktrees, and third-party
   clones. For each repo, report: has `AGENTS.md`; references shared sources;
   `AGENTS.md` ignored / dirty / staged status; unrelated dirty paths.
   If a directory is not a Git repository, skip it and include it in the
   skipped-repos list with reason "not a Git repo".
2. **Compare.** Read project `AGENTS.md` content and identify rules that
   overlap with the shared source. Compare against a single rule candidate
   when adding or updating one, or against the full shared-source content
   when converging existing duplicates. Classify each match as:
   - **Covered** — all meaning is already in the shared source and the rule
     contains no agent- or project-specific atoms (repo-only paths, commands,
     deployment gates, ADR/spec boundaries, managed-block markers, or
     **agent-runtime constructs**: tool names like `WebFetch` / `apply_patch`,
     Codex skill dirs, and other runtime-bound identifiers); safe to remove.
   - **Project-specific** — contains one or more specific atoms listed above;
     must be preserved even if parts overlap. On the agent-global axis, an
     agent-runtime construct stays in that agent's own file as a footnote (the
     shared file states the rule generically).
   - **Needs confirmation** — partial overlap; or a stable engineering principle
     a caller proposes sharing (the volatility cut says keep it per-agent unless
     the user explicitly overrides); present to the user.
3. **Plan.** 🔴 **STOP — present the plan and wait for user confirmation
   before any write.** The plan must list, per file:
   - Shared source: what will be added or changed.
   - Each project `AGENTS.md`: rules to remove (covered), rules to preserve
     (project-specific), rules needing confirmation, references to add.
   - Repos skipped (no `AGENTS.md`, ignored, or unsafe Git state).
4. **Execute.** After user confirmation (if the user rejects the plan, report
   unexecuted repos and stop):
   a. Back up each shared source (`cp <file> <file>.bak`) before writing.
      If the backup fails, stop that shared source and report the error.
   b. Write and verify shared sources first.
   c. Then apply project `AGENTS.md` changes. If the shared-source write
      failed or its content does not match the plan, stop — do not touch
      project files.
   d. Re-run inventory immediately before each project edit to catch
      intervening changes.
5. **Validate.**
   - Run per-file Git checks (see Validation section below).
   - **Completion self-check**: grep project `AGENTS.md` files for distinctive
     clause text from the converged rule (e.g. a unique verb-object phrase or
     a defining term). Any match not already marked as preserved or confirmed
     in the plan means the task is not done.

## Allowed Changes

- Shared instruction sources: add, update, or restructure rules. Do not create
  project Git commits for these files (they live outside project repos).
- Project `AGENTS.md`: remove rules covered by the shared source; add missing
  `@...` references; translate standalone top-of-file public include-file
  explanation blocks into Chinese. Do not rewrite, sort, or reformat other
  project content.

## Preservation Rules

- Managed blocks (Trellis, plugins, tools, generated sections) and clearly
  marked non-Chinese blocks owned by other systems are opaque — do not
  interpret, normalize, sort, reformat, or remove them.
- A project-local rule may only be removed when Compare classifies it as
  **Covered**. When in doubt, preserve and flag for the user.
- If no `@...` reference structure exists, create a minimal Chinese
  public-reference block near the top and leave all existing content untouched.

## Git Safety

- Dirty repos are eligible if `AGENTS.md` itself has no unsafe pre-existing
  target changes. Record and preserve unrelated dirty paths.
- If `AGENTS.md` already has staged changes, pause that repo and wait for user
  confirmation before editing.
- If `AGENTS.md` has pre-existing unstaged changes, process only when those
  changes are explicitly confirmed or clearly attributable to this run.
- Use target-only commits (`git commit --only -- AGENTS.md`); do not unstage,
  stash, reset, checkout, or clean unrelated changes.
- If `AGENTS.md` is ignored by Git, skip silently. Do not force-add, block, or
  produce extra explanation.

## Do Not

- Do not create missing project `AGENTS.md` files.
- Do not rewrite, sort, reformat, or "clean up" project content that is not
  a covered duplicate.
- Do not remove a rule that contains any project-specific atom, even if most
  of it overlaps with the shared source.
- Do not touch managed blocks (Trellis, plugins, generated sections).
- Do not commit shared instruction sources (they live outside project repos).
- Do not force-add a gitignored `AGENTS.md`.
- Do not stash, reset, checkout, or clean unrelated dirty paths.

## Validation

Before each project `AGENTS.md` commit:

```bash
git status --short
git diff -- AGENTS.md
git check-ignore -v -- AGENTS.md
git diff --check -- AGENTS.md
```

After each commit, verify unrelated staged paths remain staged and report
remaining dirty paths. Final output must state which repos were changed,
preserved, or skipped.
