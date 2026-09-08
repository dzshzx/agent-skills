---
name: sync-agents-instructions
description: Maintain shared agent rules and independent AGENTS.md / CLAUDE.md entry points using a machine topology config.
---

# Sync Agents Instructions

Every configured agent owns its project instruction surface. Each surface
serves that owner independently; it is never a wrapper, shortcut, or
authority pointer for another owner's surface.

Two actions, two scopes:

- **Add or update:** put a reusable rule in a shared user-level source and
  wire it through each applicable owner's `entry_file` load route. Scope is
  the `[[agents]]` entries only — do not enumerate `project_globs`.
- **Converge:** enumerate project surfaces under `project_globs`; remove
  valid duplicates with same-owner shared coverage, or delete rules the user
  has explicitly retired within the authorized scope.

## Machine topology comes from config

Read topology from the config the user names, or from
`$XDG_CONFIG_HOME/agent-instructions/sync-config.toml` (conventional config
home when unset). If no config exists, stop and offer to create one — do not
infer a topology from directory listings. See
[references/config-example.toml](references/config-example.toml). Machine
paths in the config may use `~` and `$VAR`.

- `[workspace]` — `project_globs` (repo candidates, expanded non-recursively),
  optional `off_limits` (paths this skill never writes).
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
referenced files that do not exist. Then read only the entry files, shared
sources, project surfaces, and direct references needed for the requested
change; do not require a full read of every configured or referenced file.

## Isolation invariant

A project surface may state project facts, but it must never `@`-import,
link to, read/defer to, or claim authority from **another owner's surface or
a user-level file** — each of those creates a second injection channel.
Shared rules reach an owner only through that owner's own `entry_file` load
route. A plain-prose mention of a user-level boundary (one that neither loads
the source nor tells the owner to obtain instructions from it) is fine.
Before removing a cross-reference, preserve the still-valid rules it supplies
to the owner and declared readers: put applicable project rules in their own
existing surfaces, and shared rules through their own entry load routes.
This minimal preservation is part of **Converge**. If it cannot be completed
within scope and the write boundaries, retain the reference and report the
gap. Remove the reference only after coverage is established.

## Placement

1. Contains a project-specific atom (repo path, deployment gate, domain
   boundary, spec pointer) → the current owner's project surface.
2. Is project workflow or executable convention (how to test/branch/release)
   → the project's own workflow docs (the files `off_limits` names); report
   it, never absorb it.
3. Is an active user-specific constraint with no project atoms → user level.
   Generic tutorials, engineering advice and project encyclopedias are not
   promotion candidates merely because they appear in multiple projects.
   Keep useful project knowledge in its existing documentation, linked only
   for the task that needs it; do not recreate a mandatory reading chain.
4. Unsure → leave it local and flag it as a promotion candidate.

| Rule applies to | Destination | Load |
| --- | --- | --- |
| every task, any domain | behavior contract | `always` |
| every task, machine-dependent | machine facts | `always` |
| one technical domain | that domain's slice | `on-demand` (trigger reachable from the entry: a pointer line there, or the trigger list in an `always` source the entry loads) |
| only one agent | that agent's entry file (or `agent_specific_file`) | that owner's scope |

Anti-fragmentation: a new slice needs one cohesive theme that an entry file
can point at with a single trigger sentence; below that, use a named section
of the nearest existing file.

## Removal rule

For an explicitly retired rule, record the user's retirement decision and
the affected diff; no equivalent shared rule is required. Do not re-home the
retired rule in another file. Preserve still-valid project safety boundaries.

For a still-valid duplicate, remove it only when all three hold **for the same owner**:

1. A configured shared source carries all of its meaning.
2. That owner's entry file verifiably loads that source — native expansion,
   an unconditional read instruction, or (for `on-demand`) an explicit
   trigger — in the entry, or in an `always` source the entry loads — whose
   scope covers every case the local rule applies to. Advisory
   wording ("suggest", "when useful") is not a load route.
3. Nothing project- or agent-specific is lost.

When another configured agent lists this surface in
`readonly_project_surfaces`, the same three checks must also pass through
that reader's own entry load route; a rule covered only for the owner stays.

Report each duplicate removal with its covering source, load route and diff;
report retired rules with their retirement basis and diff. Similar wording in another project's surface is promotion
evidence, never removal evidence.
When coverage is partial or unclear, keep the rule and note it in the
summary; ask only when the ambiguity changes what you would write.

## Workflow

1. Read and validate the config. For **Add or update**, inspect only the
   applicable `[[agents]]` entry files and load routes. For **Converge**,
   enumerate the configured project surfaces in scope and note cross-owner
   references; skip non-Git candidates with a stated reason.
2. Classify each candidate rule: explicitly-retired / shared-covered /
   project-specific / generic-advice / unsure.
3. Execute additions, isolation fixes, authorized retirements and covered removals within the user's
   existing authorization. Tracked, untracked, or ignored status does not by
   itself create a second confirmation requirement; preserve before/after
   evidence when Git cannot restore the original. Ask only when a material
   choice is missing or an action falls outside the authorized scope. Report
   every write with its diff and each removal with its retirement basis or
   covering source and load route. Never write `off_limits` paths.
4. Execute shared sources and entry load routes first, then project-local
   removals, re-checking that the recorded coverage still holds. Edit only
   the declared owner's surface; do not create missing surfaces.
5. Validate each changed surface with status and content diff, including a
   saved before/after comparison for files outside Git. Leave unrelated dirty
   paths untouched and confirm no cross-owner reference was introduced.
   Commit, push, or publish only when the request and active repository rules
   authorize it.

## Boundaries

- Managed or generated blocks (plugins, tools, generated sections) are
  opaque — do not interpret, reformat, or remove them.
- Gitignored instruction files are governed too: validate them by content
  diff and report them separately as local-only; never force-add them.
- Never write `off_limits` paths, never edit another owner's surface as a
  shortcut, never hardcode discovered topology into this skill.
