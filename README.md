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
`references/`, `scripts/`, and `evals/` (`live-check.sh`, the real-harness check
every skill ships, plus `evals.json` reference prompts for Codex skills).

## Skills

| Skill | What it does |
| --- | --- |
| [`codex-subagent-routing`](skills/codex-subagent-routing/SKILL.md) | Routes Codex subagent spawns with an explicit model + reasoning-effort decision per child: delegation signals, the live `spawn_agent` schema as the only model/effort/role authority, a parent-only rule for the top reasoning tiers and for irreversible steps, roles (built-ins plus the host config's `[agents.*]` identities) passed only when they fit, and task-packet/result contracts. Distilled from the retired `codex-subagent-router` project. `evals/live-check.sh` has Codex really spawn subagents and checks, from that session's own rollout tree, that every spawn's parameters match what the child actually ran with, then confirms an irreversible request spawns nothing and asks for confirmation. |
| [`cross-agent-delegation`](skills/cross-agent-delegation/SKILL.md) | Hands a task to a different vendor's coding agent CLI (Claude Code, Codex, Kimi Code) as a headless subprocess, in any direction and for any kind of work the user names: per-CLI invocation contracts in `references/` (answer and resume-id locations, the failures that cost a retry), a permission posture that defaults to normal working permissions with per-CLI mechanical restriction when asked, and the brief and handoff rules a context-free delegate needs. Ships `evals/live-check.sh`: a fail-closed default tier that re-checks flags and parse-level rejections with no model calls, plus `--smoke` for the JSON fields, exit codes, resume and permission behaviour `--help` never confesses. |
| [`sync-agents-instructions`](skills/sync-agents-instructions/SKILL.md) | Governs independent per-agent project instruction surfaces across a workspace: each configured agent owns one project file; a local rule is converged only when a shared source is proven available through that same owner’s user-level load scope, while cross-owner imports and delegation are rejected. Machine topology comes from a per-machine config file (`references/config-example.toml`), so the skill itself stays generic; `scripts/validate_config.py` checks a config against that schema (unknown keys, duplicate owners or names, malformed repo-relative surfaces, unmatched read-only surfaces, missing files, `~`/`$VAR` expansion) and `evals/check.sh` pins it with fixtures; `evals/live-check.sh` runs a real Converge and a real Add-or-update in a throwaway workspace under an isolated `CLAUDE_CONFIG_DIR` and asserts the file-level outcome, including that an untracked surface is confirmed rather than edited and that the skill's own git commands were really run. |

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

Before pushing, run the standard verification:

```bash
scripts/verify.sh          # mechanical gate (what CI runs) + live checks for skills changed vs origin/master
scripts/verify.sh --all    # live checks for every skill, e.g. after a CLI upgrade
```

The mechanical gate is `python scripts/validate_repository.py`,
`shellcheck -S warning skills/*/evals/*.sh scripts/*.sh`,
`bash skills/sync-agents-instructions/evals/check.sh` and
`bash scripts/check-commit-subjects.sh` (every commit subject in the pushed
range is `type(scope): subject`, e.g. `fix(<skill>): …`; a bare `<skill>: …`
prefix fails); CI runs exactly those.
Live checks (`skills/<name>/evals/live-check.sh`, one per skill, enforced by
the validator) make real, billed CLI calls and need the CLIs and credentials
on the machine, so they run locally, never in CI.

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
