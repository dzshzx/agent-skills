# Acceptance boundaries

Run repository `scripts/verify.sh --no-live`. The offline fixtures cover
parameter combinations, successful termination, count limits, missing and
duplicate evidence, inherited-history exclusion and child skill-read ownership.
They validate checkers, not model compliance.

Existing `evals/live-check.sh` scenarios inject source text. They prove only
their explicit assertions, not natural routing-skill discovery or ordinary
delegation. Use `--scenario` to select a bounded scenario after authorization.

For task-skill acceptance, `evals/task_skill_check.py prepare <directory>`
creates a local fixture project and four recorded task prompts:
explicit skill name, natural trigger, unrelated task, and missing entry.
It has no external targets. With user authorization, start a fresh parent
Codex session in that project after applying the candidate config, and let it
create a new `none` child for each selected prompt (one at a time is sufficient).
Supply the directory and the exact prompt; do not paste skill contents.
The project skill catalog provides native discovery for the natural case.
For the missing-entry case, give the nonexistent path specified in the prompt.

Export the child's own complete rollout and check with
`python3 evals/task_skill_check.py check <case> <child-rollout> <fixture-directory>`.
The checker accepts direct native `exec_command` reads and executions, or a
single code-mode `text(await tools.exec_command({...}));` with literal JSON
arguments and the whole tool result. Give this evidence-format requirement
in the test prompt; it carries no fixture skill content. Opaque orchestration
is unverifiable, not evidence of failure to use skills. Routine instruction
reads are allowed. A single `const r = await tools.exec_command({...}); text(r);`
binding is also accepted; reassignment and output projection are not.
Skill reads may use `cat` or a numeric `sed -n 'START,ENDp'` range.
A successful read must contain the exact fixture instruction;
a successful fixture-script execution and the exact final result are also
required. The unrelated case must complete its own task without fixture reads
or execution; missing-entry must show a failed read and a final explanation.
Parent reads, historical reads, claimed use, and reads without execution fail.

Record CLI version, config/role hashes, installed skill hash, fresh parent and
child IDs, prompt, own-rollout boundary, result and usage report. Preserve three
separate conclusions: configuration/offline checks, natural discovery and
actual task delivery. Until authorized live tests run, the latter two remain
pending; neither fixture success nor historical totals establish savings.
