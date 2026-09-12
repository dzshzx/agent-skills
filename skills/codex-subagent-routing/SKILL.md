---
name: codex-subagent-routing
description: Configure or troubleshoot Codex subagent routing, context inheritance, lifecycle, task-skill discovery, and usage accounting. Ordinary delegation follows runtime role descriptions and resident instructions.
---

# Codex subagent routing

## Configuration and diagnosis

1. Read the live spawn and continuation schemas and managed configuration
   source. Keep machine-specific model tables, role files, concurrency and
   fallback effort in that source. Check the native review model separately.
   Render candidates and validate with the installed CLI.
2. Match roles to bounded work and explicitly pass their default effort at
   creation, subject to the user's budget. Count the parent in total slots.
   Only the parent dispatches children. Consider startup, inherited input,
   repeated investigation and coordination when deciding whether to delegate.
3. Independent tasks default to `fork_turns="none"`. Use the least recent
   context needed, or full inheritance when broad background is essential.
   Full forks can prohibit model/effort overrides; follow the live schema.
   `none` still receives base system/project instructions and the skill
   catalog. Neither recent nor full inheritance guarantees all original tool
   output: supply readable paths for critical evidence.
4. Supply a self-contained task packet: goal, working directory, necessary
   facts, evidence paths, acceptance and concise return requirements.
   Writers get explicit file/module ownership and notice that others are
   editing in parallel: preserve and accommodate their changes.
   Explicitly required skills travel with name, entry path and relevant
   requirements; the child loads them through its own native mechanism.
5. Reuse a child for supplements or rework on the same task. Independent tasks
   and role changes need a new child. Continuation cannot change model or
   effort: hand off findings, evidence and unresolved questions to a newly
   created child when changing resources. After failure, timeout or model
   unavailability, use available evidence to choose more information, another
   role or parent execution. Handle any still-running old task before replacement
   to avoid duplicate cost and competing writes. Without new evidence, do not
   relaunch the same task.
6. Keep irreversible execution in the parent under existing authorization.
   Children return results the parent can verify. Authorized read-only use of
   existing credentials may be delegated without exposing their values;
   rotation and permission changes stay in the parent.

## Verification

For configuration or evaluator changes, read [verification.md](references/verification.md).
Separate source-injection, natural-trigger and actual-delivery evidence.
Changed configuration needs freshly started Codex sessions and new children
for behavior acceptance; old agents retain settings and context.
Parent skill reads do not prove child skill use. Check the child's own reads,
execution and result together. A claim or a read alone is insufficient.
Run offline checks first. Run real agent scenarios only within the user's
authorization; explicitly retain untested behavior as pending.

## Usage analysis

Run the on-demand [usage report](references/usage.md) during acceptance or when
requested. Report parent, children and task totals, plus missing fields.
Routing and concurrency reduce avoidable spending; they are not a hard total
quota. Compare equal-quality completed tasks by whole-task cost and elapsed
time. Historical accounting alone cannot establish savings from a new policy.
