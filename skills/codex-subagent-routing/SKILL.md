---
name: codex-subagent-routing
description: Configure or troubleshoot Codex subagent routing, model budgets, context inheritance, and writer ownership.
---

# Codex subagent routing

Read the live `spawn_agent` schema before routing. It is the authority for
available models, reasoning efforts, roles, and field constraints; do not
copy a version-specific model list into this skill.

1. **Choose a useful boundary.** Delegate a concrete subtask with an
   independent result and clear completion condition when its parallelism or
   specialization repays child startup and model cost. Keep small, direct
   lookups in the parent when delegation adds no value.
2. **Budget each child.** Set an explicit budget for child count, compute or
   time, and return length. Select compatible `model` and `reasoning_effort`
   values from the live schema according to the judgment required and the
   user's constraints. Do not impose one effort tier on every task shape.
3. **Use context and roles deliberately.** Pass `agent_type` only when a
   schema-listed role fits the work; otherwise omit it. Set `fork_turns` to
   the amount of recent context the child needs. A context-free child needs a
   fully self-contained brief.
4. **Write the brief as a task packet**: `task_name`; goal (overall plus the
   child's bounded subgoal);
   boundaries (may read, may write, must not touch — workers get explicit file
   ownership and "others are editing in parallel; do not revert their work");
   acceptance (done-when, verification, what to do when information is
   missing); return shape with a length budget — conclusions plus file:line
   coordinates, never pasted file bodies. The child loads the runtime's own
   instruction files (user and project `AGENTS.md`, memory) itself, like any
   session: do not restate them and do not tell it to skip them; what the
   brief carries is the task's facts — the parent's conversation and the
   files it read are not there unless written in. Parallel writers get
   disjoint files or modules and explicit ownership.
5. **Keep irreversible execution in the parent.** Children may inspect or
   prepare, but publishing, payments, deletion, credential use, and account or
   production changes are executed by the parent under the authorization and
   safety rules already in force. A clear user request counts as authorization;
   do not add a second confirmation requirement here.
