# Agent Rules

Full development guide (layout, authoring rules, workflow) lives in `CLAUDE.md` — reading @CLAUDE.md once at the start of a session is recommended; no need to re-read it later in the same session.
Machine-wide behavior contract and machine facts are carried by the global instruction layer; this file only records project facts a non-Claude agent must know.

## Project boundaries

- This repo is the source of truth for every skill. Installed copies under agent runtime dirs (`~/.claude/skills`, `~/.agents/skills`) go stale after edits — re-install/sync; never edit runtime copies directly.
- No machine-specific facts inside a committed `SKILL.md`: machine topology belongs in per-machine config (see `skills/sync-agents-instructions/references/config-example.toml` for the pattern); platform facts are OK, machine facts are not.
- Frontmatter `description` doubles as routing logic — preserve trigger phrases, exclusions, and scope boundaries when editing it.
- Commit convention: `skill(<name>): …` / `feat(<name>): …` / `chore: …`; keep the README skill table in sync with `skills/`.
- Releases are tagged so `npx skills add dzshzx/agent-skills` installs stay reproducible.
