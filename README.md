# agent-skills

Reusable agent skills, installable across AI coding agents (Claude Code,
Codex, Cursor, ...) via the [skills CLI](https://skills.sh):

```bash
npx skills add dzshzx/agent-skills            # all skills
npx skills add dzshzx/agent-skills --skill <name>
```

Pass `--skill` space-separated. The CLI does not recognise `--skill=<name>`;
it silently drops the flag and installs every skill in the repository.

Skills follow the [Agent Skills](https://agentskills.io) open standard: each
skill is a directory under `skills/` with a `SKILL.md` plus optional
`references/`, `scripts/`, and `evals/` (`live-check.sh` and `evals.json` for
Codex skills).

## Skills

| Skill | What it does |
| --- | --- |
| [`codex-subagent-routing`](skills/codex-subagent-routing/SKILL.md) | Routes Codex subagent spawns with an explicit model + reasoning-effort decision per child: delegation signals, the live `spawn_agent` schema as the only model/effort authority, a parent-only rule for the top reasoning tiers, an optional managed-identity layer gated on the active configuration, and task-packet/result contracts. Distilled from the retired `codex-subagent-router` project. |
| [`cross-agent-delegation`](skills/cross-agent-delegation/SKILL.md) | Hands a task to a different vendor's coding agent CLI (Claude Code, Codex, Kimi Code) as a headless subprocess: per-CLI invocation contracts, a role-to-permission table, and the brief and handoff rules a context-free delegate needs. |
| [`sync-agents-instructions`](skills/sync-agents-instructions/SKILL.md) | Governs independent per-agent project instruction surfaces across a workspace: each configured agent owns one project file; a local rule is converged only when a shared source is proven available through that same owner’s user-level load scope, while cross-owner imports and delegation are rejected. Machine topology comes from a per-machine config file (`references/config-example.toml`), so the skill itself stays generic. |

`refactor-batch-landing` was removed on 2026-08-06. It only orchestrated the
Matt Pocock skills family (`codebase-design`, `implement`, `tdd`,
`code-review`, `to-spec`, `to-tickets`, `grill-with-docs`), which is installed
separately via the skills CLI and is not part of this repo; the orchestrator
had no execution surface of its own. Recover it from git history if needed.

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
- Release candidates land on `master` first. After CI passes on that exact
  commit, create its annotated `vX.Y.Z` tag. Published tags are immutable and
  never reused; a failed release is fixed in the next patch version. Install a
  specific tag with the skills CLI when reproducibility matters.

## Releases

Before tagging, run the same repository validation locally:

```bash
python scripts/validate_repository.py
```

Then push the candidate, wait for CI on its exact SHA, and tag that commit:

```bash
git push origin master
# Wait for CI on this exact master SHA to pass.
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

`v0.1.1` (2026-07-25) predates the annotated-tag rule and is a lightweight
tag; it is left as-is and never repaired.

## License

MIT
