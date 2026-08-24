---
name: sync-agents-instructions
description: Govern per-agent project instruction surfaces (CLAUDE.md, AGENTS.md) via a per-machine config. Use when asked to sync AGENTS.md/CLAUDE.md rules, add or update shared agent instructions, make surfaces independent, or deduplicate agent rules.
---

# Sync Agents Instructions

## Overview

Govern agent instruction files across the projects of one machine. Every
configured agent owns exactly one project instruction surface; a surface
serves its declared owner and is never a wrapper, shortcut, or authority
pointer for another agent's surface.

Two actions, two scopes:

- **Add or update:** put a reusable rule in a shared user-level source and
  wire it through each applicable owner's `entry_file` load route. Scope is
  the `[[agents]]` entries only — do not enumerate `project_globs`.
- **Converge:** enumerate the project surfaces under `project_globs` and
  remove a project-local copy only when that *same owner* demonstrably
  receives it from a shared source.

## Machine topology comes from config

This skill contains no machine-specific paths. Read the topology from the
config the user names, or from
`$XDG_CONFIG_HOME/agent-instructions/sync-config.toml` (conventional config
home when unset). If no config exists, stop and offer to create one — do not
infer a topology from directory listings. See
[references/config-example.toml](references/config-example.toml).

- `[workspace]` — `project_globs` (repo candidates, expanded non-recursively),
  `off_limits` (paths this skill never writes).
- `[[shared_sources]]` — `path`, `role` (what belongs there), `domain`
  (slice), `load` = `"always"` | `"on-demand"`.
- `[[agents]]` — one per agent: `name`, `entry_file`,
  `project_instruction_file` (the one repo-relative surface it owns),
  `always_load_mode` (`"native"` = the runtime expands the entry's imports;
  `"mandatory-entry-read"` = the entry carries an unconditional
  read-before-work instruction covering every `load = "always"` source);
  optional `agent_specific_file`, `skill_dirs`, `runtime_constructs`,
  `readonly_project_surfaces` (surfaces owned by *other* configured agents
  that this agent's runtime also auto-loads; each entry must match another
  agent's `project_instruction_file`; read visibility only, never edit
  rights or ownership).
  Supporting a new agent means adding an entry here, not changing this skill.
- `[[repository_exclusions]]` — `glob` + `reason`; the only way to exempt a
  repo candidate. Do not prune heuristically.

Validate the config before acting: run `python3 scripts/validate_config.py
<config>` from this skill's directory (`${CLAUDE_SKILL_DIR}` on Claude Code;
the directory containing this SKILL.md elsewhere). It checks the schema
above, rejects unknown keys, two agents or surfaces normalizing to the same
owner, `readonly_project_surfaces` that name no other configured owner, and
referenced files that do not exist. On any error, stop and ask instead of
guessing.

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
   Promote when the rule is stated without project atoms and would apply
   unchanged to any repo on this machine — a second sighting corroborates
   that, it is not a precondition. Similar wording in another project is
   corroboration too, never proof on its own.
4. Unsure → leave it local and flag it as a promotion candidate.

**Axis 2 — vertical slice within the user level.**

| Rule applies to | Destination | Load |
| --- | --- | --- |
| every task, any domain | behavior contract | `always` |
| every task, machine-dependent | machine facts | `always` |
| one technical domain | that domain's slice | `on-demand` (one-line trigger in entries) |
| only one agent | that agent's entry file (or `agent_specific_file`) | that owner's scope |

Anti-fragmentation: a new slice needs one cohesive theme that an entry file
can point at with a single trigger sentence; below that, use a named section
of the nearest existing file.

Size the natively loaded surface (entry + all `always` sources) by value, not
by line count — lines are a poor proxy, since the same rule can be one long
line or five short ones. Demote the least-used domain section to `on-demand`
when any of these show up: the surface needs an index to stay readable; one
rule has to be repeated in several places to make sense; a section only
matters for a few task shapes yet loads every time; or an agent measurably
starts missing the rules near the end.

## Removal rule

Remove a project-local rule only when all three hold **for the same owner**:

1. A configured shared source carries all of its meaning.
2. That owner's entry file verifiably loads that source — native expansion,
   an unconditional read instruction, or (for `on-demand`) an explicit
   trigger whose scope covers every case the local rule applies to. Advisory
   wording ("suggest", "when useful") is not a load route.
3. Nothing project- or agent-specific is lost.

When another configured agent lists this surface in
`readonly_project_surfaces`, the same three checks must also pass through
that reader's own entry load route; a rule covered only for the owner stays.

Report every removal in the execution report with its covering source, load
route, and diff. Similar wording in another project's surface is promotion
evidence, never removal evidence.
When coverage is partial or unclear, keep the rule and note it in the
summary; ask only when the ambiguity changes what you would write.

## Workflow

1. Read and validate the config. For **Add or update**, list only the
   `[[agents]]` entry files and their load routes. For **Converge**, list the
   surfaces in scope (glob candidates minus configured exclusions; skip
   non-Git candidates with a stated reason) and note cross-owner references
   found along the way.
2. Classify each candidate rule: shared-covered / project-specific /
   parallel-project / unsure.
3. Execute the plan directly — additions, isolation fixes, and removals of
   project-local rules all proceed within the current request; report every
   write with its diff, and every removal with its covering source and load
   route. 🔴 Confirm first only for the one write Git cannot restore:
   writing a gitignored instruction file (no second copy). `off_limits`
   paths are never written, confirmed or not (see Boundaries).
4. Execute shared sources and entry load routes first, then project-local
   removals, re-checking that the recorded coverage still holds. Edit only
   the declared owner's surface; do not create missing surfaces.
5. Validate: `git status --short` and `git diff -- <surface>` per repo;
   commit a tracked surface with `git commit --only -- <surface>` (it rejects
   untracked paths). A surface that exists untracked and not ignored is
   reported as such and left unstaged — ask before adding it to version
   control; a gitignored surface follows Boundaries. Leave unrelated dirty
   paths untouched; confirm no cross-owner reference was introduced.

## Boundaries

- Managed or generated blocks (plugins, tools, generated sections) are
  opaque — do not interpret, reformat, or remove them.
- Gitignored instruction files are governed too: same comparison and
  confirmation, validated by content diff, reported separately as local-only;
  never force-add or commit them.
- Never write `off_limits` paths, never edit another owner's surface as a
  shortcut, never hardcode discovered topology into this skill.
