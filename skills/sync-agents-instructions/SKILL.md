---
name: sync-agents-instructions
description: Governs independent per-agent project instruction surfaces across a workspace of repos and AI agents (Claude Code, Codex, Cursor, ...) — adds or updates shared rules only through each owner's user-level load scope, removes only owner-proven duplicates, and prevents cross-owner project-surface imports or delegation. Config-driven inspect-plan-execute-validate flow with fail-closed schema preflight, dirty-worktree protection, isolation checks, full-estate post-check, and per-repo target-only commits. Use when asked to sync AGENTS.md/CLAUDE.md rules, add or update shared agent instructions, make per-agent project instruction surfaces independent, or deduplicate agent rules.
---

# Sync Agents Instructions

## Overview

Use this skill to govern agent instructions across the projects of one
machine. Every configured agent owns one independent project instruction
surface. A surface serves its declared owner; it is never a wrapper, shortcut,
or authority pointer for another agent's surface.

Governance has two equally important actions:

- **Add or update:** put a reusable rule in a shared source and wire that
  source through each applicable owner's user-level entry/load scope.
- **Converge:** remove a project-local copy only when that *same owner* is
  demonstrably covered by the shared source. Similar wording in another
  project surface is evidence of a possible promotion, never evidence that a
  local rule can be removed.

Both actions use the same fail-closed inspect-plan-execute-validate flow.

## Machine Topology Comes From Config, Not From This File

This skill contains **no machine-specific paths**. Read the current machine's
topology from a config file:

1. If the user names a config path, use it.
2. Otherwise use the per-user default config location
   `$XDG_CONFIG_HOME/agent-instructions/sync-config.toml` (falling back to the
   user's conventional config home when `XDG_CONFIG_HOME` is unset).
3. If no config exists, **stop and offer to create one** by asking the user
   for each field below. Do not infer a topology from directory listings.

See [references/config-example.toml](references/config-example.toml) for a
complete annotated example.

### Schema preflight — mandatory and fail closed

Parse and validate the config before inventory, comparison, planning, or any
write. A failed preflight means **stop with no partial plan or edit**; report
every failed check that can be determined safely.

The current schema has no flat list of project instruction files. Instead,
each `[[agents]]` record declares the one project-relative
`project_instruction_file` it owns.

Fail closed when any of the following is true:

- There is no `[[agents]]` record. A governed estate without an explicit
  project-surface owner cannot be inspected safely.
- `[workspace].project_instruction_files` is present. It is a legacy field
  and cannot be interpreted as a fallback.
- The legacy flat field and any `[[agents]].project_instruction_file` appear
  together. Report this specifically as a mixed schema; do not select either
  representation.
- An `[[agents]]` record has no non-empty `name`, `entry_file`, or
  `project_instruction_file`. The last field is the required project-surface
  owner declaration; a missing value is a missing owner.
- Two agent names normalize to the same value. Normalize by trimming and
  comparing case-insensitively; do not silently rename either agent.
- Two `project_instruction_file` values normalize to the same owner surface.
  Require a project-relative file path, normalize separators and dot segments,
  then compare case-insensitively. Reject absolute paths, paths escaping the
  repository, directories, and duplicate normalized results.
- A field needed to establish a claimed load route is malformed or missing
  (for example, a referenced shared source has no path or a load value other
  than `"always"` or `"on-demand"`).

`skill_dirs`, `agent_specific_file`, and `runtime_constructs` remain optional
agent properties. They do not create a second project-surface owner.

### Relevant config fields

- `[workspace]` — `project_globs`, `off_limits`, and optional
  `inject_budget_lines`. It does **not** own a project-instruction-file list.
- `[[shared_sources]]` — a user-level source with:
  - `role` — what belongs here (the config owner's split; this skill enforces
    the split it is given and does not invent one);
  - `domain` — the vertical slice it covers (`behavior`, `machine-facts`,
    `code-standards`, `frontend`, `docs-writing`, ... free-form);
  - `load` — `"always"` (active through an owner entry's load route) or
    `"on-demand"` (an owner entry carries an explicit task trigger).
- `[workspace].off_limits` — glob patterns for project workflow owners this
  skill must never write or restructure (for example, workflow specs,
  conventions, or agent-process documentation). Report rules that belong
  there; never move them.
- `[[agents]]` — one entry per AI agent, with required `name`, `entry_file`,
  and `project_instruction_file`; optional `agent_specific_file`, `skill_dirs`,
  and `runtime_constructs`. Adding support for an agent means adding this
  complete record, not changing this skill.

## Ownership and Isolation Model

Build an owner map from the validated `[[agents]]` records:

`normalized project_instruction_file → agent name → user entry_file`

For every repository, an existing file matching that project-relative path is
the independent project surface for that one owner. Do not infer ownership
from a familiar filename, a document heading, or a similar file in a sibling
repository. Do not create a missing surface.

### Project surfaces must stay independent

A project surface may refer to project facts and in-repository materials that
are not another configured owner surface. It must never do any of the
following with another owner surface, whether that surface is in the same
repository or a different one:

- `@`-import or otherwise include it;
- link to it, or name it as the authoritative, complete, canonical, or
  governing instruction source;
- tell its owner to read, follow, defer to, or obtain instructions from it;
- delegate rules, workflow, or responsibility to it instead of stating the
  applicable content on the current owner's surface.

User-level shared sources are wired only through the **same owner's**
`entry_file` and its declared load scope. A project surface must not import or
point at a user-level shared source either: that creates a second injection
channel. When a cross-owner dependency is found, classify it as an
**Isolation violation**. Plan its removal or replacement explicitly; never
fix it by making one project surface depend on a different one.

## Placement Decision Model

Route every rule through both axes before writing anything.

### Axis 1 — level (project vs user)

1. Contains a project-specific atom (repository path, deployment gate, domain
   boundary, spec pointer) → the rule belongs in the current owner's project
   surface.
2. Is project workflow or executable convention (how to test, branch, release,
   spec layers) → its project workflow owner (`off_limits` territory). Report
   it; never absorb it. This skill governs instruction surfaces, not project
   workflows.
3. Holds across two or more projects with no project atoms → user level. Apply
   the *rule of two*: promote when a rule appears in a second project, not on
   first sight.
4. Unsure → leave it in the current owner’s project surface and flag it as a
   promotion candidate. A wrong global rule pollutes every project; a
   not-yet-promoted local rule costs one duplicate.

**Reference and ownership invariant:** only a validated owner can govern its
project surface. Project surfaces do not route to each other or to user-level
sources. The relevant user-level source must instead be loaded through the
same owner's `entry_file`; a project-level reference into a user directory is
a duplicate injection channel, not coverage proof.

### Axis 2 — vertical slice (within user level)

| Rule applies to | Slice | Load |
| --- | --- | --- |
| every task, any domain | behavior contract | `always` (native load — keep this file small) |
| every task, changes when the machine changes | machine facts | `always` |
| only tasks in one technical domain (frontend, code style, docs writing, ...) | that domain's slice file | `on-demand` (the owner entry carries a one-line trigger pointer) |
| only one agent | that agent's `agent_specific_file` | that owner's user-level scope |

**Anti-fragmentation:** a new slice file needs minimum mass — roughly five
rules or one cohesive theme. Below that, keep the rule in a named section of
the nearest existing file; the section is the future slice's seed and can be
promoted later.

**Injection budget:** the natively loaded surface (an owner entry plus all
its `load = "always"` sources, as expanded by the most eager agent) should
stay within `[workspace].inject_budget_lines` (default 300). When over budget,
demote domain sections to `on-demand` slices before trimming content.

## Owner-Bound Comparison and Removal Proof

Start every comparison from the current surface's declared owner. A matching
rule is not enough: its replacement must be demonstrably available in that
same agent's user-level scope.

Classify each candidate as follows:

| Classification | Meaning | May remove the project-local rule? |
| --- | --- | --- |
| **SharedCovered** | All meaning is in a configured shared source, the rule has no project- or agent-specific atom, and the plan records a complete same-owner load proof. | Yes, after confirmation. |
| **Project-specific** | The rule contains a project atom, an `off_limits` boundary, a managed-block marker, or an agent-runtime construct from the current owner's `runtime_constructs`. | No; preserve it. |
| **ParallelProject** | A semantically similar rule exists in another configured project surface, whether for a different owner in this repo or in another repository. | No; it is promotion evidence only. |
| **Needs confirmation** | Coverage is partial, source placement is unclear, the load route is missing, or an on-demand scope does not exactly cover the rule. | No; ask the user. |

A `SharedCovered` claim needs a proof packet in the plan containing all of:

1. The current project surface's normalized path and declared owner name.
2. That owner's `entry_file` and the concrete route from it to the shared
   source: a native include/configured expansion for `load = "always"`, or an
   explicit owner-entry trigger for `load = "on-demand"`.
3. The shared source path, its `load` value, and the matching rule or section.
4. For `on-demand`, the exact task scope named by the trigger and proof that
   the project-local rule applies only within that scope.
5. Evidence that the local rule contains no project-specific or owner-specific
   atom that the shared rule cannot carry.

If any item is absent, the candidate is not `SharedCovered`. Similar wording
in a sibling surface must be recorded as `ParallelProject`; it can justify a
future promotion proposal, but it **never** supplies removal evidence and
never authorizes a cross-owner reference.

## Workflow

1. **Preflight and collect.** Run schema preflight first. Then inventory the
   full estate: every Git repository under every `project_globs` entry,
   pruning dependency trees, archives, temporary worktrees, and third-party
   clones. For every repository and every declared owner, report whether that
   owner's project surface exists; its ignored, dirty, and staged state; and
   unrelated dirty paths. List non-Git directories as skipped with reason
   `not a Git repo`.

   Also inspect every existing project surface for isolation: cross-owner
   `@`-imports, links, authority claims, deferrals, and delegated instructions.
   Inventory the relevant owner `entry_file` and shared-source load route so
   later `SharedCovered` claims have evidence. This is an estate-wide check,
   not just a scan of files expected to change.

2. **Compare.** For each rule candidate, use the surface's declared owner and
   the owner-bound classification table above. Compare against the proposed or
   existing shared source *and* verify the same-owner load proof. Do not use a
   sibling surface as a shared source, fallback, or coverage proxy. Record
   every sibling match as `ParallelProject` and every prohibited dependency as
   an Isolation violation.

3. **Plan.** 🔴 **STOP — present the plan and wait for user confirmation
   before any write.** For each repository, owner, and existing project
   surface, list:
   - isolation status and every planned removal of a cross-owner dependency;
   - `SharedCovered` rules to remove, including the complete proof packet;
   - `Project-specific` and `ParallelProject` rules to preserve;
   - `Needs confirmation` rules and the unresolved decision;
   - user-level shared-source or owner-entry changes needed to create a valid
     load route, before any project-local removal;
   - repositories or surfaces skipped for absence, `off_limits`, unsafe Git
     state, or another reason.

   Report gitignored instruction files separately as local-only governed
   files. End the plan with the full-estate post-check: all repositories and
   all configured owner surfaces that will be rescanned after execution, plus
   the isolation and load-route assertions that must pass.

4. **Execute.** After user confirmation, back up every user-level source or
   entry file that will change. Write and verify shared sources and owner
   entry-file load routes first. If any planned user-level write fails or its
   content differs from the approved plan, stop: do not remove a project-local
   rule.

   Before each project edit, re-run that repository's inventory to catch
   intervening changes. Edit only the current owner's declared surface; do not
   create missing surfaces or alter a sibling owner surface as a shortcut.
   Remove a local rule only when its recorded `SharedCovered` proof remains
   true. Apply isolation fixes exactly as planned. If the user rejects the
   plan, report unexecuted repositories and stop.

5. **Validate.** Run the per-file Git checks below. Then run the full-estate
   post-check across every discovered repository and every configured owner,
   including untouched surfaces. Confirm all of the following:
   - config preflight still passes and every normalized surface has one owner;
   - no project surface imports, links to, treats as authority, or delegates
     to another owner surface;
   - every removed rule has its recorded same-owner `SharedCovered` proof;
   - no `ParallelProject` rule was removed because of sibling similarity;
   - each owner entry still provides the planned `always` or `on-demand` load
     route, without project-level duplicate injection;
   - distinctive clauses from converged rules have no surviving unplanned
     copies. Remaining sibling copies are reported as `ParallelProject`, not
     silently treated as failures or removal candidates.

   If the post-check finds an unplanned isolation violation, missing route, or
   ambiguous surviving clause, report it and return to planning; do not claim
   the estate is converged.

## Gitignored Instruction Files Are Governed, Not Skipped

A gitignored instruction file still changes agent behavior in that workspace.
Treat it as a distinct governance class:

- Include it in full-estate inventory, isolation checks, and owner-bound
  comparison exactly like a tracked surface.
- Never silently skip it; never force-add or commit it.
- Writes require explicit user confirmation and produce a visible before/after
  diff; validation uses content diff, owner-load proof, isolation checks, and
  clause search rather than Git status.
- Report these files under a separate **local-only governed files** heading so
  the user can distinguish repository-committed changes from local-only ones.

## Allowed Changes

- Shared instruction sources: add, update, or restructure rules. Do not create
  project Git commits for files outside project repositories.
- Owner user-level entry files: add or adjust only their own shared-source load
  route or on-demand trigger. Do not make an entry file point to another
  agent's project surface.
- Project instruction surfaces: remove only `SharedCovered` rules, repair a
  confirmed isolation violation, or add project-specific content for their own
  owner. Do not rewrite, sort, or reformat unrelated content.

## Preservation Rules

- Managed blocks (Trellis, plugins, tools, generated sections) are opaque —
  do not interpret, normalize, sort, reformat, or remove them.
- A project-local rule may only be removed when Compare classifies it as
  `SharedCovered` and the owner-bound proof packet is complete. When in doubt,
  preserve it and flag it for the user.
- `ParallelProject` is always preserved. Promote it only through a separately
  confirmed shared-source and same-owner load-route plan.

## Git Safety

- Dirty repositories are eligible if the current owner's surface has no unsafe
  pre-existing changes. Record and preserve unrelated dirty paths.
- If an owner surface has staged changes, pause that repository and wait for
  user confirmation before editing.
- If an owner surface has pre-existing unstaged changes, process it only when
  those changes are explicitly confirmed or clearly attributable to this run.
- Use target-only commits (`git commit --only -- <owner-surface>`). Do not
  unstage, stash, reset, checkout, or clean unrelated changes.

## Do Not

- Do not accept the legacy flat `project_instruction_files` field, infer an
  owner, or choose a winner from a mixed schema.
- Do not create missing project instruction surfaces.
- Do not use one project surface as an import, link target, authority,
  delegation target, fallback, or proof of coverage for another owner.
- Do not remove a rule because another project surface has similar wording.
- Do not remove a rule containing a project-specific or owner-specific atom,
  even if most of it overlaps with a shared source.
- Do not touch managed blocks, force-add a gitignored file, commit shared
  sources, or write into `off_limits` paths.
- Do not stash, reset, checkout, or clean unrelated dirty paths.
- Do not hardcode discovered machine topology back into this SKILL.md; it
  belongs in the per-machine config file.
- Do not create a new slice file below minimum mass or slice finer than
  task-scope domains (no per-language micro-files on day one).

## Validation

Before each project instruction-file commit, run:

```bash
git status --short
git diff -- <owner-surface>
git check-ignore -v -- <owner-surface>
git diff --check -- <owner-surface>
```

For user-level files, use a content diff and verify the approved owner load
route. After each project commit, verify unrelated staged paths remain staged
and report remaining dirty paths. The final output must state which
repositories and owner surfaces changed, were preserved, or were skipped;
list local-only governed files separately; and report the full-estate
post-check outcome, including isolation and same-owner coverage results.
