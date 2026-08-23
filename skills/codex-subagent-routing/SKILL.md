---
name: codex-subagent-routing
description: Route Codex subagent spawns — every child gets an explicit model and reasoning_effort (never max or ultra), a schema-listed role only when it fits, and a self-contained brief with a return-length budget; publishing, deletion, credentials and production changes stay in the parent. Use whenever you call spawn_agent, split work across subagents, or write a child brief, even if the user never mentions routing.
---

# Codex subagent routing

`spawn_agent` defaults a child to the parent's model, the parent's reasoning
effort, and `fork_turns="all"` — a top-tier parent would hand its tier and its
whole history to every bounded child. Decide those fields on purpose, per
child, from the live `spawn_agent` schema (the only authority for model names,
efforts, and roles; it changes between Codex versions).

1. **Delegate or not.** The tool's bar applies: a concrete, bounded subtask
   that can run while the parent keeps working. Steps that are hard to undo —
   publishing, payments, deletion, credentials, account or production
   changes — stay in the parent and run only after the user's explicit
   go-ahead; say so instead of treating the request as the go-ahead. A child
   costs a fixed startup overhead, so never split finer than that (forty tiny
   files is one child or the parent, not forty).
2. **`model` + `reasoning_effort`, explicit for every child.** Mechanical or
   look-up work (renames, enumerations, link checks, test runs, `explorer`
   questions) gets the lightest suitable tier, low or medium; judgment work
   (review, design, diagnosis) gets high. Children never get max or ultra.
   Models with no stated capability difference share one model, with compute
   expressed through effort alone.
3. **`agent_type` only from roles the schema lists** — built-ins such as
   `explorer` (specific codebase questions and enumerations, parallelizable)
   and `worker` (bounded execution with explicit file ownership), plus
   configured identities (`config.toml` `[agents.*]`, e.g. `researcher`,
   `reviewer`). A listed role is not a free default: pass it only when its
   description fits the child's job (a link audit is not research); no fit →
   omit.
4. **`task_name`** (lowercase letters, digits, underscores) **and
   `fork_turns`.** Independent work: `"none"` — the child sees no parent
   history, so its brief must stand alone. Work continuing a recent discussion:
   a concrete positive integer string such as `"3"`, never a placeholder. Never
   leave `all` on a routed child; never omit or silently rewrite routed fields.
   Leave `service_tier` unset unless the user asks for it.
5. **Self-contained brief**: goal (overall plus the child's bounded subgoal);
   boundaries (may read, may write, must not touch — workers get explicit file
   ownership and "others are editing in parallel; do not revert their work");
   a line that the user-level shared instruction slices and the agent's memory
   files are already applied by the parent and must not be re-read by the
   child — the brief carries the facts the child needs;
   acceptance (done-when, verification, what to do when information is
   missing); return shape with a length budget — conclusions plus file:line
   coordinates, never pasted file bodies. Parallel children get disjoint files,
   modules, or topics.
6. **Recover**: a child that fails or returns noise gets one retry with a brief
   that names what went wrong; a second failure of the same kind means the work
   is not delegable as framed — take it back into the parent.
