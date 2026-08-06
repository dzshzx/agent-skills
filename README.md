# agent-skills

Reusable agent skills, installable across AI coding agents (Claude Code,
Codex, Cursor, ...) via the [skills CLI](https://skills.sh):

```bash
npx skills add dzshzx/agent-skills            # all skills
npx skills add dzshzx/agent-skills --skill=<name>
```

Skills follow the [Agent Skills](https://agentskills.io) open standard: each
skill is a directory under `skills/` with a `SKILL.md` plus optional
`references/`, `scripts/`, and `tests/`.

## Skills

| Skill | What it does |
| --- | --- |
| [`codex-subagent-routing`](skills/codex-subagent-routing/SKILL.md) | Routes Codex subagent spawns with an explicit model + reasoning-effort decision per child: delegation signals, current model/effort catalogs, a parent-only rule for the top reasoning tiers, an optional managed-identity layer gated on the active configuration, and task-packet/result contracts. Distilled from the retired `codex-subagent-router` project. |
| [`sync-agents-instructions`](skills/sync-agents-instructions/SKILL.md) | Governs independent per-agent project instruction surfaces across a workspace: each configured agent owns one project file; a local rule is converged only when a shared source is proven available through that same owner’s user-level load scope, while cross-owner imports and delegation are rejected. Machine topology comes from a per-machine config file (`references/config-example.toml`), so the skill itself stays generic. |
| [`claude-session-doctor`](skills/claude-session-doctor/SKILL.md) | Diagnoses and rescues local Claude Code sessions via `csctl` (>= 0.8.0): lists live sessions/background agents, fixes `/resume` lookup and rejection problems, prints exact resume/take-over commands across directories, and points to the TUI for cleanup and remote-control toggles. Imported from the retired `cc-session-control` bundled skill and rewritten for csctl 0.8.0's narrowed CLI surface. |

`refactor-batch-landing` was removed on 2026-08-06. It orchestrated the Matt
Pocock skills family (`codebase-design`, `implement`, `tdd`, `code-review`,
`to-spec`, `to-tickets`, `grill-with-docs`) and had no execution surface once
that family was uninstalled. Recover it from git history if the family returns.

## Design rules

- **No machine-specific facts in SKILL.md.** Paths, hostnames, and topology
  live in per-machine config files or are resolved relative to the skill
  directory (`${CLAUDE_SKILL_DIR}` on Claude Code; "the folder containing this
  SKILL.md" elsewhere).
- **Platform facts are fine; machine facts are not.** A skill may rely on how
  an agent stores its data (platform-generic); it may not hardcode one
  machine's layout.
- **Project instruction surfaces are independent per agent.** Each
  `[[agents]]` entry declares its own `project_instruction_file`; a surface
  may not import, defer to, or treat another owner’s surface as authority.
- Releases are tagged; install a specific version with the skills CLI when
  reproducibility matters.

## License

MIT
