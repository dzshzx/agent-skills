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
| [`sync-agents-instructions`](skills/sync-agents-instructions/SKILL.md) | Governs shared agent instruction rules across a workspace: converges duplicated rules from per-repo `AGENTS.md`/`CLAUDE.md` into shared instruction sources and keeps references wired, for any set of agents. Machine topology comes from a per-machine config file (`references/config-example.toml`), so the skill itself stays generic. |

## Design rules

- **No machine-specific facts in SKILL.md.** Paths, hostnames, and topology
  live in per-machine config files or are resolved relative to the skill
  directory (`${CLAUDE_SKILL_DIR}` on Claude Code; "the folder containing this
  SKILL.md" elsewhere).
- **Platform facts are fine; machine facts are not.** A skill may rely on how
  an agent stores its data (platform-generic); it may not hardcode one
  machine's layout.
- Releases are tagged; install a specific version with the skills CLI when
  reproducibility matters.

## License

MIT
