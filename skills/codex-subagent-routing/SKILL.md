---
name: codex-subagent-routing
description: Route Codex subagent spawns with explicit model and reasoning effort. Use when delegating work, parallelizing tasks, or writing a child task packet.
---

# Codex subagent routing

Every routed child gets an explicit model and reasoning-effort decision;
nothing falls through to inherited or default compute. Distilled from the
retired [codex-subagent-router](https://github.com/dzshzx/codex-subagent-router)
project; the routing policy now lives directly in this document.

## When to delegate

Delegate when any signal holds:
- Two or more independent workstreams can run in parallel.
- A broad read, search, or enumeration would flood the parent context with intermediate noise.
- The work spans several files or sources but returns a compact conclusion.
- An independent check or review would reduce the parent's self-confirmation bias.

Keep in the parent thread:
- A simple question, status query, or single-file small edit.
- Strongly sequential work where each step depends on the previous result.
- Anything the parent can answer from context it already loaded.
- Publishing, payments, deletion, account, or production changes.

## Route options

The live `spawn_agent` tool schema is the sole authority for model names and
reasoning efforts. Read its exposed overrides before every spawn and never
route to a value the live schema does not offer. Every child gets `model` and
`reasoning_effort` passed explicitly.

Prohibited child reasoning efforts: max, ultra. The top reasoning tiers stay
parent-only: a child holding a bounded, pre-scoped brief must not carry the
maximum reasoning depth its parent used to scope it.

## Managed identities (optional layer)

Pass agent_type only when the active configuration already declares that
identity (for Codex: a `config.toml` `[agents.*]` entry) **and** its declared
description fits the child's job; otherwise omit it. A declared identity is
not a free default: `researcher` carries a primary-source research brief, so
a link audit, a code enumeration, or a test run gets no agent_type even
though `researcher` exists. The identity's description lives in config.toml,
not here.

## Spawn contract

- Choose every routed child explicitly with model and reasoning_effort.
- Choose `model` only from the active `spawn_agent` schema; do not infer an
  unavailable lightweight tier from product-family naming.
- Set agent_type only when a declared role fits the child's job; omit it otherwise.
- On MultiAgent V2, also set task_name (lowercase letters, digits, and underscores only) and fork_turns="none" for independent work or a positive integer string for limited recent context; do not use full-history all with explicit routing.
- On stable MultiAgent V1, leave fork_context false or omitted; do not spawn full-history forks with explicit routing.
- Do not omit routed fields or silently rewrite them.

## Task packet

A child brief must stand alone: goal, read/write boundaries, acceptance bar, and return shape — enough for the child to act without parent history. Optional checklist below; take only what the task shape calls for, not a field-by-field form.

- Goal: overall goal, child's bounded subgoal.
- Boundaries: may read, may write, must not touch.
- Acceptance: done-when, required verification, on-missing-info handling.
- Return shape: format, evidence style, length budget.

## Result contract

- Ask children for conclusions plus file:line evidence coordinates, not pasted file bodies; read coordinates on demand.
- Give every child an explicit return structure and length budget.
- Split parallel children across disjoint files, modules, or topics.
- Retry a failed child only when you can name what went wrong and change the brief to address it; a repeat failure of the same kind means the task is not delegable as framed — take the work back into the parent instead of re-spawning.
- Each child costs a fixed startup overhead; do not delegate work smaller than that overhead.
