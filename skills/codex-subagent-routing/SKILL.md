---
name: codex-subagent-routing
description: Diagnose or configure Codex subagent routing — missing or unwanted delegation, role model and effort, context inheritance, child task-skill use, usage accounting and acceptance of routing changes. Ordinary delegation follows the runtime-injected contract.
---

# Codex subagent routing

## Diagnosis

1. Render the input first: `codex debug prompt-input <probe>` shows what the
   model receives in about two seconds without a model call; `-c key=value`
   renders a candidate without editing files. Read the delegation contract and
   the `<multi_agent_mode>` block in their rendered order. Below Ultra effort
   the default mode block is explicit-request-only and voids every earlier
   instruction enabling proactive delegation, so contract, AGENTS and role
   wording cannot produce it; `features.multi_agent_v2.multi_agent_mode_hint_text`
   replaces that block. Explain delegation behaviour from the rendered input
   before rewording instructions or running tasks.
2. Resources come from the managed configuration source. Role files fix the
   model and can take precedence over explicit spawn arguments; effort is passed
   at spawn. Full forks copy parent history and can prohibit model/effort
   overrides; `fork_turns="none"` still receives base instructions and the skill
   catalog. A continued child keeps its model and effort: to change resources,
   create a new child with the findings, evidence and open questions, after
   handling any still-running old task. Confirm actual resources in the child's
   own rollout. A required task skill travels in the brief as name, entry path
   and relevant requirements; the child loads it natively.
3. Behaviour tests change one variable on a small, real read-only task, with at
   least three runs per arm. Record delegation count and role per run.
4. Compare cost only once delegation occurs: split root and children, cached and
   uncached input, several runs per arm. Single paired runs swing by tens of
   percent from cache variance alone.

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
