# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of reusable agent skills following the [Agent Skills](https://agentskills.io) open standard, installable across AI coding agents (Claude Code, Codex, Cursor, ...) via `npx skills add dzshzx/agent-skills`. Each skill is a directory under `skills/<name>/` with a `SKILL.md` (YAML frontmatter: `name` + `description`) plus optional `references/`, `scripts/`, `tests/`, and `agents/` (per-agent interface metadata, e.g. `agents/openai.yaml`).

Skills here are **prompt-instructions-as-product**: the SKILL.md body is the deliverable, and edits to it are behavior changes for every agent that installs it.

## Commands

Only `trellis-mode-switcher` has executable code. Its tests are plain `unittest`, run directly:

```bash
python3 skills/trellis-mode-switcher/tests/test_inspect_trellis_mode.py
```

Run them only when `scripts/` or `tests/` of that skill changed — SKILL.md/reference edits don't need them. The tests invoke the inspector as a subprocess against temp repos, so no fixtures or dependencies are needed (stdlib only).

## Design rules (enforced, from README)

- **No machine-specific facts in SKILL.md.** Paths, hostnames, and machine topology live in per-machine config files (see `skills/sync-agents-instructions/references/config-example.toml`) or are resolved relative to the skill directory (`${CLAUDE_SKILL_DIR}` on Claude Code; "the folder containing this SKILL.md" elsewhere).
- **Platform facts are fine; machine facts are not.** A skill may rely on how an agent platform stores data, but never on one machine's layout. If a change would hardcode discovered topology into a SKILL.md, put it in the config schema/example instead.
- Adding support for a new agent to `sync-agents-instructions` means adding an `[[agents]]` entry to the machine config — the SKILL.md body must stay agent-generic.
- Releases are tagged for reproducible installs.

## Working on skills

- Skill descriptions (frontmatter `description`) double as the trigger/routing text agents use to decide when to invoke the skill — keep trigger phrases and scope boundaries ("not responsible for X") intact when editing.
- These skills also exist as installed copies in agent runtime dirs (e.g. `~/.claude/skills/`, `~/.agents/skills/`) — this repo is the source of truth (baseline was imported from runtime dirs in the initial commit). After editing a skill here, installed copies are stale until re-installed/synced; don't edit runtime copies directly.
- Commit messages follow the existing pattern: `skill(<name>): ...` / `feat(<name>): ...` / `chore: ...`, and README's skill table should stay in sync with what's under `skills/`.
