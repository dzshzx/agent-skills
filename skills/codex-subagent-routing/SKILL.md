---
name: codex-subagent-routing
description: Route Codex subagent spawns. Every child gets an explicit model and reasoning_effort (never max or ultra), a role only when one in the live spawn_agent schema fits the job, and a self-contained brief with a return-length budget; publishing, deletion, payments, credentials and production changes never leave the parent. Use whenever you are about to call spawn_agent, split work across subagents, parallelize tasks, or write a child task packet — even if the user never mentions routing.
---

# Codex subagent routing

Why this skill exists: `spawn_agent` defaults every child to the parent's model
and reasoning effort and to `fork_turns="all"`. A parent running at the top
tier would hand that tier, plus its whole history, to every bounded child.
Routing is the act of deciding those fields on purpose, per child.

## Procedure

1. **Decide whether to delegate.** The tool's own rule is the bar: a concrete,
   bounded subtask that can run independently while the parent keeps doing
   useful work. Signals for delegating: two or more independent workstreams; a
   broad read, search, or enumeration whose intermediate noise would flood the
   parent; work across several files or sources that returns a compact
   conclusion; an independent check that offsets the parent's self-confirmation
   bias. Keep in the parent: a simple question, status query, or single-file
   edit; strongly sequential work (each step needs the previous result);
   anything answerable from context already loaded; and every step that is
   hard to undo — publishing, payments, deletion, credentials, account or
   production changes — which the parent runs itself and only after the
   user's explicit go-ahead; say so in the reply instead of assuming the
   request was the go-ahead. Each child costs a fixed startup overhead, so never split
   work finer than that overhead (forty tiny files is one child or the parent,
   not forty children).
2. **Read the live `spawn_agent` schema** before every spawn. It is the only
   authority for model names, reasoning efforts, and available roles; it changes
   between Codex versions, so never route from memory or from a model's name.
3. **Choose `model` and `reasoning_effort` explicitly for every child.**
   Mechanical or look-up work (renames, enumerations, link checks, running a
   test suite, `explorer` questions about the codebase) gets the schema's
   lightest suitable tier — low or medium; judgment work (review, design,
   diagnosis) gets a higher one such as high. Children never get max or ultra — the
   top tiers stay with the parent that scoped the work. Models with no stated
   capability difference get the same model, with compute expressed through
   reasoning_effort alone.
4. **Choose `agent_type` from the roles the schema lists** — built-in ones such
   as `explorer` (specific codebase questions and enumerations — "find every
   X", "how does Y reach Z" — fast and parallelizable) and `worker` (bounded
   execution with explicit file ownership), plus any identity the
   configuration declares (`config.toml` `[agents.*]`, e.g. `researcher`,
   `reviewer`). Pass a role only when its description fits the child's job; a
   declared role is not a free default (`researcher` carries a primary-source
   research brief, so a link audit does not get it). No fit → omit the field.
   Never pass a role the schema does not list.
5. **Set `task_name` (lowercase letters, digits, underscores — required) and
   `fork_turns`.** Independent work gets `fork_turns="none"`: the child then
   sees nothing of the parent's history, which is the point — its brief must
   stand on its own. Work that genuinely continues a recent discussion gets a
   positive integer string such as `"3"` covering just those turns — pick the
   number now, never a placeholder. Never leave the default `all` on a routed
   child. Never omit or silently rewrite routed
   fields.
6. **Write a self-contained brief.** The child has no parent history, so the
   brief carries: the goal (overall, plus the child's bounded subgoal);
   boundaries (may read, may write, must not touch — for workers, explicit file
   ownership and "others are editing in parallel; do not revert their changes");
   plus, for every Codex child, a line that the user-level shared instruction
   slices (`~/.config/agent-instructions/shared*.md`, `git-task-isolation.md`)
   and the memory files under `~/.codex/memories/` are already applied by the
   parent and must not be re-read — the brief itself carries the facts the
   child needs;
   acceptance (done-when, required verification, what to do when information
   is missing); and a return shape with an explicit length budget — conclusions
   plus file:line evidence coordinates, never pasted file bodies, so the parent
   reads coordinates on demand instead of absorbing the child's context.
   Parallel children get disjoint files, modules, or topics.
7. **Collect and recover.** A child that returns noise, or fails, gets one
   retry only with a brief that names what went wrong (for example "return
   conclusions with file:line, budget 300 words, no file bodies"); a second
   failure of the same kind means the work is not delegable as framed — take it
   back into the parent rather than re-spawning.
