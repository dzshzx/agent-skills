---
name: sync-agents-instructions
description: Govern per-agent project instruction surfaces (CLAUDE.md, AGENTS.md, ...) across a workspace of repos — route each rule to the right level and vertical slice via a per-machine config, keep every surface isolated to its one owner, and remove a project-local rule only when that same owner provably loads it from a shared source. Use when asked to sync AGENTS.md/CLAUDE.md rules, add or update shared agent instructions, make per-agent project instruction surfaces independent, or deduplicate agent rules.
---

# Sync Agents Instructions

## Overview

Govern agent instruction files across the projects of one machine. Every
configured agent owns exactly one project instruction surface; a surface
serves its declared owner and is never a wrapper, shortcut, or authority
pointer for another agent's surface.

Two actions share one flow:

- **Add or update:** put a reusable rule in a shared user-level source and
  wire it through each applicable owner's entry file.
- **Converge:** remove a project-local copy only when that *same owner*
  demonstrably receives it from a shared source.

## Machine topology comes from config

This skill contains no machine-specific paths. Read the topology from the
config the user names, or from
`$XDG_CONFIG_HOME/agent-instructions/sync-config.toml` (conventional config
home when unset). If no config exists, stop and offer to create one — do not
infer a topology from directory listings. See
[references/config-example.toml](references/config-example.toml).

- `[workspace]` — `project_globs` (repo candidates, expanded non-recursively),
  `off_limits` (paths this skill never writes), optional
  `inject_budget_lines` (default 300).
- `[[shared_sources]]` — `path`, `role` (what belongs there), `domain`
  (slice), `load` = `"always"` | `"on-demand"`.
- `[[agents]]` — one per agent: `name`, `entry_file`,
  `project_instruction_file` (the one repo-relative surface it owns),
  `always_load_mode` (`"native"` = the runtime expands the entry's imports;
  `"mandatory-entry-read"` = the entry carries an unconditional
  read-before-work instruction covering every `load = "always"` source);
  optional `agent_specific_file`, `skill_dirs`, `runtime_constructs`.
  Supporting a new agent means adding an entry here, not changing this skill.
- `[[repository_exclusions]]` — `glob` + `reason`; the only way to exempt a
  repo candidate. Do not prune heuristically.

Validate the config before acting. On missing files, malformed or missing
required fields, or two agents/surfaces normalizing to the same owner, stop
and ask instead of guessing.

## Isolation invariant

A project surface may state project facts, but it must never `@`-import,
link to, read/defer to, or claim authority from **another owner's surface or
a user-level file** — each of those creates a second injection channel.
Shared rules reach an owner only through that owner's own `entry_file` load
route. A plain-prose mention of a user-level boundary (one that neither loads
the source nor tells the owner to obtain instructions from it) is fine.
Fix a violation by removing the cross-reference — never by making one project
surface depend on a different one.

## Placement Decision Model

**Axis 1 — level.**

1. Contains a project-specific atom (repo path, deployment gate, domain
   boundary, spec pointer) → the current owner's project surface.
2. Is project workflow or executable convention (how to test/branch/release)
   → its `off_limits` owner; report it, never absorb it.
3. Holds across two or more projects with no project atoms → user level.
   Rule of two: promote on the second sighting, not the first.
4. Unsure → leave it local and flag it as a promotion candidate.

**Axis 2 — vertical slice within the user level.**

| Rule applies to | Destination | Load |
| --- | --- | --- |
| every task, any domain | behavior contract | `always` |
| every task, machine-dependent | machine facts | `always` |
| one technical domain | that domain's slice | `on-demand` (one-line trigger in entries) |
| only one agent | that agent's entry file (or `agent_specific_file`) | that owner's scope |

Anti-fragmentation: a new slice needs roughly five rules or one cohesive
theme; below that, use a named section of the nearest existing file. Keep
each owner's natively loaded surface (entry + all `always` sources) within
`inject_budget_lines`; when over budget, demote domain sections to
`on-demand` before trimming content.

## Removal rule

Remove a project-local rule only when all three hold **for the same owner**:

1. A configured shared source carries all of its meaning.
2. That owner's entry file verifiably loads that source — native expansion,
   an unconditional read instruction, or (for `on-demand`) an explicit
   trigger whose scope covers every case the local rule applies to. Advisory
   wording ("suggest", "when useful") is not a load route.
3. Nothing project- or agent-specific is lost.

Record the covering source and load route in the plan. Similar wording in
another project's surface is promotion evidence, never removal evidence.
When coverage is partial or unclear, keep the rule and ask.

## Workflow

1. Read and validate the config; list the surfaces in scope (glob candidates
   minus configured exclusions; skip non-Git candidates with a stated
   reason). Note cross-owner references found along the way.
2. Classify each candidate rule: shared-covered / project-specific /
   parallel-project / unsure.
3. 🔴 Present the plan — additions, removals with their coverage proof,
   isolation fixes — and wait for user confirmation before any write.
4. Execute shared sources and entry load routes first, then project-local
   removals, re-checking that the recorded coverage still holds. Edit only
   the declared owner's surface; do not create missing surfaces.
5. Validate: `git status --short` and `git diff -- <surface>` per repo;
   commit with `git commit --only -- <surface>`; leave unrelated dirty paths
   untouched; confirm no cross-owner reference was introduced.

## Boundaries

- Managed or generated blocks (plugins, tools, generated sections) are
  opaque — do not interpret, reformat, or remove them.
- Gitignored instruction files are governed too: same comparison and
  confirmation, validated by content diff, reported separately as local-only;
  never force-add or commit them.
- Never write `off_limits` paths, never edit another owner's surface as a
  shortcut, never hardcode discovered topology into this skill.
