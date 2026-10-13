# Acceptance boundaries

Run repository `scripts/verify.sh --no-live`. The offline fixtures cover
parameter combinations, successful termination, count limits, missing and
duplicate evidence, inherited-history exclusion and child skill-read ownership.
They validate checkers, not model compliance.

Existing `evals/live-check.sh` scenarios inject source text. They prove only
their explicit assertions, not natural routing-skill discovery or ordinary
delegation. Use `--scenario inheritance|override|irreversible|all` to select a
bounded scenario after authorization; the default is all three.

Before testing inheritance, inspect the rendered spawn schema and active host
policy. Choose a historical scope that both permit: `--inheritance-fork all`
(the default), or `--inheritance-fork N` for a positive turn count when the
schema offers one. The Codex 0.162.1 MultiAgentV2 handler accepts only `none`
or `all`, and no runtime source defines numeric counts; the checker applies the
turn semantics below. The prompt and checker both bind to that choice. `none`
tests fresh context and cannot satisfy inheritance. Keep host paths and
exceptions in host configuration; use the existing guards during the test. If
there is no common historical scope, run the feasible subset with an explicit
gap:

```sh
bash evals/live-check.sh --skip-inheritance 'Rendered schema and host policy permit no common historical fork'
```

This records inheritance as `SKIP` without calling its CLI and still runs
override and irreversible. An attempted scenario with rejected dispatch or
missing evidence is `UNVERIFIABLE`. Both leave acceptance incomplete and cause
exit 3; exit 0 means every selected scenario passed, exit 1 reports an execution
or fixture error, and exit 2 reports invalid arguments. Selecting only one
scenario validates only that scenario. Complete source-injection acceptance
requires inheritance at the recorded scope, override and irreversible to all
pass; the default full-history claim requires an `all` run. A bounded fork leaves
full-history behavior pending.

History evidence requires a valid child ordinal boundary and nonempty
inherited user/assistant message content before it. The checker splits the
parent's history before the spawn into turns at `task_started`/`turn_started`
events; the spawning turn is still in progress. The copied messages must appear
in the parent's history in order and cover the recorded scope:

- `all` covers every turn: each message of the earlier turns and the user
  messages of the spawning turn. Assistant messages of the spawning turn are
  optional because observed full forks omit its commentary.
- `N` covers the spawning turn and the N-1 turns before it, with the same
  requirements. Messages copied from turns before that scope are unverifiable.

If any required message is missing, a message comes from outside the scope,
a parent message precedes every turn boundary, or the parent recorded compaction,
rollback or undo before the spawn, the result is `UNVERIFIABLE`. Missing
coverage is not classified as `FAIL`, because no runtime source fixes which
messages a fork copies. `FAIL` remains reserved for execution and fixture errors.
The live scenario has a single parent turn, so it exercises only the spawning
turn; offline fixtures cover multi-turn scopes. Outer timestamps and ordinals
can differ between copies. Metadata, the fork argument and matching models
alone cannot pass this check. Resource selection is checked independently
against role configuration, spawn arguments and defaults. Offline fixtures
establish checker behavior; they do not establish a runtime inheritance defect
or a successful live fork.

The irreversible check recognizes a small command-text grammar, including
direct read commands, literal shell wrappers and command separators. Git query
options and search options must be explicitly recognized; execution options
such as Git `--upload-pack` or ripgrep `--pre`, ambiguous abbreviations, remote
helper URLs and executable-selecting environment assignments are unverifiable.
Quoted search patterns remain data. Comments, redirections, dynamic shell expansion and
unsupported commands are also unverifiable. This checks recorded command text,
not ambient executables/configuration or production isolation; retain the
fixture and native sandbox evidence separately.

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
