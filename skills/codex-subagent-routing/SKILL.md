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

The active `spawn_agent` tool schema is the authority for model names in the
current turn. Read its exposed overrides before every spawn and never route to
a model that the live schema does not offer. The table below records the
models exposed in the current Codex environment; update it when the runtime
schema changes.

Models:

| Model | Description |
|---|---|
| gpt-5.6-terra | General-purpose model. |
| gpt-5.6-sol | Highest-capability model. |

Reasoning efforts:

| Effort | Description |
|---|---|
| low | Low reasoning depth. |
| medium | Medium reasoning depth. |
| high | High reasoning depth. |
| xhigh | Extra-high reasoning depth. |

Prohibited child reasoning efforts: max, ultra. The top reasoning tiers stay
parent-only: a child holding a bounded, pre-scoped brief must not carry the
maximum reasoning depth its parent used to scope it.

## Managed identities (optional layer)

Use these agent_type values only when the identities are declared in the
active configuration (for Codex: `config.toml` `[agents.*]` entries);
otherwise omit agent_type and route by model and effort alone.

- researcher: Primary-source researcher for external documentation, APIs, specifications, and upstream code.
- reviewer: Read-only reviewer for one bounded diff axis.

## Spawn contract

- Choose every routed child explicitly with model and reasoning_effort.
- Choose `model` only from the active `spawn_agent` schema; do not infer an
  unavailable lightweight tier from product-family naming.
- Set agent_type when a suitable declared role exists; omit it otherwise.
- On MultiAgent V2, also set task_name (lowercase letters, digits, and underscores only) and fork_turns="none" for independent work or a positive integer string for limited recent context; do not use full-history all with explicit routing.
- On stable MultiAgent V1, leave fork_context false or omitted; do not spawn full-history forks with explicit routing.
- Do not omit routed fields or silently rewrite them.

## Task packet template

Fill this skeleton for every child message:

```markdown
# Task identity
You are the {agent_type} for this delegated task. Do not spawn further agents.

## Goal
- Overall goal:
- Your bounded subgoal:

## Boundaries
- May read:
- May write (if any):
- Do not touch:

## Return contract
- Return conclusions with file:line evidence coordinates and confidence.
- Do not paste large source excerpts.
- Structure and length budget:

## Acceptance
- Done when:
- Required verification:
- On missing information: report the gap; do not guess.
```

## Result contract

- Ask children for conclusions plus file:line evidence coordinates, not pasted file bodies; read coordinates on demand.
- Give every child an explicit return structure and length budget.
- Split parallel children across disjoint files, modules, or topics.
- Retry a failed child only when you can name what went wrong and change the brief to address it; a repeat failure of the same kind means the task is not delegable as framed — take the work back into the parent instead of re-spawning.
- Each child costs a fixed startup overhead; do not delegate work smaller than that overhead.
