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
| [`codex-subagent-routing`](skills/codex-subagent-routing/SKILL.md) | Configure or troubleshoot Codex subagent routing, model budgets, context inheritance and writer ownership. Ordinary delegation uses the native runtime schema and active instructions. |
| [`cross-agent-delegation`](skills/cross-agent-delegation/SKILL.md) | Hands user-named work to a different vendor's CLI (Claude Code, Codex, Kimi Code) as a headless subprocess. A shared handoff, observation, acceptance, and continuation flow uses host background facilities and compact checkpoints; `references/` owns each CLI's directory, permission, result, and resume parameters. Ships `evals/live-check.sh`: a fail-closed default tier for flags and parse-level rejections without model calls, plus `--smoke` for result, resume, and permission behavior. |
| [`sync-agents-instructions`](skills/sync-agents-instructions/SKILL.md) | Maintains shared rules and independent project entry points using a machine topology config. Valid duplicates require same-owner shared coverage; explicitly retired rules may be deleted under the user's authorization. Generic tutorials are not promoted into global instructions. |

`refactor-batch-landing` was removed on 2026-08-06. The orchestrator had no
execution surface of its own. Recover it from git history if needed.

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
- Changes reach `master` only as green candidates: push the clean, rebased
  commit with `scripts/candidate.sh` (a `candidate/**` branch), CI runs on it,
  and `promote.yml` fast-forwards `master` to that exact sha. The `master`
  ruleset requires the `validate` check on every pushed sha, so `skills add`
  never installs an unverified `master`. Release candidates are tagged from
  `master` afterwards: create the annotated `vX.Y.Z` tag on that exact commit.
  Published tags are immutable and never reused; a failed release is fixed in
  the next patch version. Install a specific tag with the skills CLI when
  reproducibility matters.

## Releases

Choose verification according to the change:

```bash
scripts/verify.sh --no-live # mechanical gate; enough for descriptions, routing metadata, and docs
scripts/verify.sh           # mechanical gate + live checks for changed skills when behavior needs them
scripts/verify.sh --all     # live checks for every skill, e.g. after an allowed CLI-upgrade check
bash skills/cross-agent-delegation/evals/live-check.sh --cli codex --smoke # targeted Codex contracts
```

The mechanical gate is `python scripts/validate_repository.py`,
`shellcheck -S warning skills/*/evals/*.sh scripts/*.sh`,
`bash skills/sync-agents-instructions/evals/check.sh` and
`bash scripts/check-offline.sh` (entrypoint, validator, event-log and scope
regressions with fixtures and fake CLIs), plus
`bash scripts/check-commit-subjects.sh` (every commit subject in the pushed
range is `type(scope): subject`, e.g. `fix(<skill>): …`; a bare `<skill>: …`
prefix fails); CI runs exactly those.
`--no-live` disables live calls regardless of argument order. `--all` and
explicit skill names are mutually exclusive (usage error, exit 2).
Live checks (`skills/<name>/evals/live-check.sh`, one per skill, enforced by
the validator) make real, billed CLI calls and need the CLIs and credentials
on the machine, so they run locally when the changed command, script, or
runtime behavior warrants them. If the user forbids a live flow, skip it and
state the resulting verification limit.

The routing check embeds the source skill in each recorded input and checks
explicit parameters or inherited parent settings against child rollouts. The
irreversible-command assertion supports a finite shell grammar; unsupported
dynamic commands fail as unverifiable, even when no mutation is observed. The
sync check compares each stage's file inventory, hashes and Git history.
Codex smoke checks require successful termination and a final answer; file
absence and an observed OS sandbox denial are separate assertions. Live
checks retain their diagnostic evidence and print its location; temporary
credential copies are removed on exit.

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
