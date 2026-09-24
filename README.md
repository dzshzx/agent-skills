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
| [`codex-subagent-routing`](skills/codex-subagent-routing/SKILL.md) | Diagnose or configure routing: missing or unwanted delegation, role model and effort, context inheritance, child task-skill use, usage accounting and acceptance. Ordinary delegation follows the runtime-injected contract. |
| [`cross-agent-delegation`](skills/cross-agent-delegation/SKILL.md) | Hands user-named work to a different vendor's CLI (Claude Code, Codex, Kimi Code) as a headless subprocess. A shared handoff, observation, acceptance, and continuation flow uses host background facilities and compact checkpoints; `references/` owns each CLI's directory, permission, result, and resume parameters. Ships `evals/live-check.sh`: a fail-closed default tier for flags and parse-level rejections without model calls, plus `--smoke` for result, resume, and permission behavior. |
| [`sync-agents-instructions`](skills/sync-agents-instructions/SKILL.md) | Maintains shared rules and independent project entry points using a machine topology config. Valid duplicates require same-owner shared coverage; explicitly retired rules may be deleted under the user's authorization. Generic tutorials are not promoted into global instructions. |

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
The summary states whether any `live-check.sh` was launched. `--no-live` and an
empty changed-skill selection explicitly report that no real CLI was called;
missing selected files fail the gate and are counted as unrun. When a
live-check runs, its own output and evidence establish which CLI calls occurred;
the entrypoint does not infer that from a script's exit code.
Live checks (`skills/<name>/evals/live-check.sh`, one per skill, enforced by
the validator) make real, billed CLI calls and need the CLIs and credentials
on the machine, so they run locally when the changed command, script, or
runtime behavior warrants them. If the user forbids a live flow, skip it and
state the resulting verification limit.

The routing source-injection check embeds the source skill in each recorded input
and compares child rollouts with role configuration, spawn overrides and resource
defaults. History inheritance is checked separately from resource selection. The
task-skill fixture separately checks child-owned reads, execution and results;
natural discovery and actual delivery require fresh authorized sessions.
On-demand usage accounting reads existing logs without model calls; see the
[routing skill](skills/codex-subagent-routing/SKILL.md) for report and acceptance entrypoints.
The irreversible-command assertion supports a finite shell grammar; unsupported
dynamic commands fail as unverifiable, even when no mutation is observed. The
sync check compares each stage's file inventory, hashes and Git history.
Codex smoke checks require successful termination and a final answer; file
absence and an observed OS sandbox denial are separate assertions. Live
checks retain their diagnostic evidence and print its location; temporary
credential copies are removed on exit.

Before changing a release version, print the complete read-only version plan:

```bash
python scripts/version_plan.py plan \
  --repository dzshzx/agent-skills \
  --target v=X.Y.Z
```

The plan is derived from the remote `v` tag history. The exact next patch can
proceed under existing release authorization. A minor,
major, or skipped-patch target pauses until the user explicitly confirms that
exact baseline-to-target plan. Unknown baselines and downgrades stop the release.

Then push the candidate and wait for CI on its exact SHA. For a confirmed
cross-level plan, preserve the printed digest in the annotated tag; a patch tag
does not need the trailer:

```bash
scripts/candidate.sh
```

After promotion, tag the exact green master SHA. Choose one of the following
tag commands. For the exact next patch:

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
```

For a confirmed minor, major, or skipped-patch plan:

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z" \
  -m "Version-Approval: sha256:<digest printed by version_plan.py>"
```

Then push the annotated tag:

```bash
git push origin vX.Y.Z
```

The release workflow rebuilds the plan from remote tags before accepting the
tag. A changed baseline or target invalidates the confirmation. It excludes the
tag being verified from the baseline search, so retrying a failed workflow does
not turn that tag into approval evidence. The digest records plan consistency;
it is not an independent identity approval.

`v0.1.1` (2026-07-25) predates the annotated-tag rule and is a lightweight
tag; it is left as-is and never repaired.

## License

MIT
