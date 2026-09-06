---
name: cross-agent-delegation
description: Hand a task to a different vendor's coding agent CLI — Claude Code, Codex, or Kimi Code — by running it as a headless subprocess. Use when the user names one of them for a piece of work ("have Codex look at this", "give this one to Kimi", "ask Claude"), in any direction and for any kind of task. Not for subagents inside your own runtime, not for switching models within one harness, and not for delegation the user did not ask for.
---

# Cross-agent delegation

Each of these CLIs is a process: a dispatch starts work, observation tracks it, and acceptance
checks the delivered result. One CLI invocation may make many model requests; its detailed
reading, commands, and reasoning stay in captured logs for selective inspection.
Any of the three takes any kind of work — planning, implementing,
reviewing, explaining — and which one goes is the user's call, made per dispatch.

**You are one of them.** When the named delegate is the runtime you already are, do the work
directly; there is no subprocess.

**Read the contract for the CLI you were named, and only that one:**
[`references/claude.md`](references/claude.md), [`references/codex.md`](references/codex.md),
[`references/kimi.md`](references/kimi.md). Each holds the minimal correct command, where the
answer and the continuation id sit in the output, and the failures that cost a retry.
`evals/live-check.sh` holds the contracts to the installed CLIs: doubt a line when that script
goes red, not when a version number moves.

## Prepare the handoff

Run `command -v <cli>` for the CLI you were named. A spawned shell may not carry your PATH, and
not every machine has all three. A missing binary is a stop, not a workaround.

**Set the working directory explicitly** — run the command from it, in a `( cd "$DIR" && … )`
subshell or through your runtime's working-directory parameter. All three resolve the project,
the repository, and their trust and permission scope from cwd, and none of them takes it from the
prompt text. When the delegate will write, that directory is an isolated worktree whenever the
host project's rules call for one; follow those rules rather than inventing isolation here.

**Know what the delegate brings.** It carries none of your conversation, the files you read, or
the decisions already made. It does load its own user and project instruction files, hooks,
skills, MCP servers, credentials and saved sessions for that cwd — it arrives configured like the
user's own session in that CLI, and whatever that layer allows or forbids applies to the dispatch.

The brief includes the goal, execution root, allowed modification scope, acceptance criteria,
evidence locations, and return format with a length budget. Ask the delegate to do its assigned
work itself rather than delegate onward. A simple task needs only a short paragraph; for a
complex task, map deliverables to individual acceptance criteria. Check required inputs,
output directories, and tool permissions before launch, using the authorization already in
force. Diagnose the specific missing permission before changing the invocation; difficulty
enumerating commands does not authorize broader permissions.

**Write the brief to a file; never interpolate it into the command string.** A brief carries
newlines, quotes, backticks and `$(...)`, all of which the shell executes or mangles before the
delegate ever sees them. The brief, any agent file and the captured output share one scratch
directory outside the delegate's cwd, so the `git status` you read afterwards shows the
delegate's work and nothing of yours:

```bash
SCRATCH=$(mktemp -d); BRIEF=$SCRATCH/brief.md; OUT=$SCRATCH/out; ERR=$SCRATCH/err
cat > "$BRIEF" <<'EOF'
...the brief...
EOF
[ -s "$BRIEF" ] || exit 1
```

Every contract's command then takes the prompt as its last argument, `-- "$(cat "$BRIEF")"`: the
quoting keeps the whole brief one argv entry, so backticks, `$(...)`, quotes and newlines reach
the delegate byte for byte, and the `--` stops Claude and Codex from reading a brief whose first
line starts with `-` — a Markdown list item, a `---` front-matter fence — as an option (without
it they fail at parse time, `unknown option` / `unexpected argument`, before any model call).
Kimi takes the brief as the value of `-p` and needs no `--`. Building the command by
concatenating prompt text into it is how a delegation silently runs something else. Two limits:
an empty brief is rejected by Claude and Kimi but sent by Codex as a real turn (hence the `-s`
check), and one argv entry is capped at 128 KiB on Linux — a brief that inlines a large diff or
log fails with `Argument list too long` before the CLI starts; point the delegate at the file
instead.

**Bound every dispatch, first or resumed, and capture a fresh pair of output files**, for
example `timeout 1800 <command> >"$OUT" 2>"$ERR"`; use the task's agreed timeout when specified.
Run through the host's existing background execution facility. Dispatches run for minutes: a
foreground tool timeout shorter than the dispatch limit can kill the dispatch itself — no exit 124, no complete
`$OUT` — and without `timeout` a hung CLI is a process you wait on forever. Capture stderr: a CLI
that cannot start — bad flag, missing credentials, rate limit — writes the reason there; stdout is
not necessarily empty, since Claude also reports the failure inside its JSON (`.is_error`) and
Codex as a `turn.failed` event. The contract commands are written bare and expect this wrapper.

## What the dispatch may do

Send it with the working permissions the task needs and existing authorization permits. Use
the named CLI's reference for directory access, command permissions, and tool restrictions.
When you want a report rather than edits, say so in the brief; that is enough for ordinary
delegations.

Restrict mechanically when the user asks for a locked-down run, or when a stray write would be
expensive to notice. The three restrict differently, and the user's choice of delegate stands:
when the named CLI cannot enforce the requested boundary, complete independent preparation
and explain the unsupported restriction before dispatch. Ask for the missing alternative
decision; a brief-level instruction is sufficient only when the user has not required a
mechanical restriction. Keep the user's choice of delegate unless they authorize a change.

- **Codex `--sandbox read-only`** — restricts local commands in the OS sandbox. For a
  mechanically read-only dispatch, also inspect approval settings and enabled MCP/App tools:
  these use separate controls and can affect remote state. See the
  [official boundary documentation](https://learn.chatgpt.com/docs/agent-approvals-security#traffic-outside-the-command-network-proxy).
- **Claude `--tools Read,Grep,Glob --strict-mcp-config`** — removes the built-in tools and every
  MCP server's tools; `--permission-mode dontAsk` is only as tight as the cwd's permission
  policy. The contract has the policy detail.
- **Kimi `--agent explore`** (the shell stays) **or `--agent-file` with a `tools:` whitelist**
  (drop it there) — restricts by tool set, not by flag. The contract has the set, the file-name
  rule and what a resume keeps.

## Observe execution

Keep a compact task summary, acceptance checklist, current checkpoint, and evidence index in
the supervisor's working context. Detailed logs stay in the task artifact directory; read
relevant excerpts when diagnosing an anomaly or checking a deliverable. Prefer the host's
completion notifications. If polling is needed, reuse the same run identifier and read a short
status; follow the host's user-update requirements rather than a skill-wide polling interval.
Update the summary on phase changes, blockers, or delivery. A quiet log alone does not show a
stalled task and is not a reason to restart it.

Intervene when the delegate reports a blocker, there is clear scope drift, an agreed checkpoint
is reached, or an assessable result is delivered. Ordinary tasks default to acceptance after
full delivery; complex tasks may warrant an earlier check when a key contract is settled.
Inspect unfinished code deeply only to investigate a specific risk. Independent acceptance
preparation may run alongside execution with clear ownership; avoid implementing the same
feature or running the same checks twice.

These are optional, trimmable handoff notes, not a schema or a requirement for a status file:

| Information | Example contents |
| --- | --- |
| Status | Running, blocked, awaiting acceptance, or accepted complete; note process failure or interruption and its cause separately |
| Checkpoint | Current commit, input version, or identifiable artifact |
| Progress | Completed and remaining work |
| Action needed | Specific blocker or decision for the supervisor |
| Evidence | Result, check output, and relevant log locations |
| Continuation | Host task identifier and CLI session ID, when available |

Delivery means **awaiting acceptance**; only the supervisor's completed checks establish
**accepted complete**.

## Accept and continue

Check the process exit and the CLI's failure fields first, even when the exit is zero; use the
named reference to extract the final answer and continuation ID. Then check the task's
acceptance criteria. Successful process exit, the delegate's completion claim, and task
acceptance are separate judgments. When permission denials appear, identify affected steps
and inspect subsequent evidence: if a required step remains incomplete, mark it blocked
regardless of successful wording.

For work that can write, inspect scope with `git status` and `git diff` in the execution root
and verify the actual artifacts. Tie check evidence to a commit, file version, or input
snapshot; without Git, use explicit input and output identifiers. Rerun affected checks when
code, inputs, environment, or key assumptions change; reuse unaffected evidence.

Consolidate confirmed findings into one repair handoff and prefer resuming the original
session. A resume is a new invocation: explicitly restore the directory, permission, and
output parameters required by that CLI's reference, including its exceptions for restored
agent settings. Preserve a fresh output pair for each invocation.

`timeout` exit 124 means interrupted work, not completion. For other nonzero exits, inspect
the CLI failure fields and relevant stderr. Missing credentials or rate limits require
resolution before another dispatch. After any timeout or interruption, inspect partial changes
and evidence before continuing. If the session cannot resume, hand over the checkpoint and
remaining work to a new session rather than restarting blindly.

One invocation per task the user named — each reloads the delegate's whole instruction layer and
may take many model turns — split only where a later dispatch would restart from a saved result.
When one dispatch's result feeds another, put it in a file rather than carrying it through your
own context. That file is at once the next dispatch's input and the point you restart from, so a
failure re-runs one dispatch instead of everything before it. When a dispatch should continue
rather than start over, resume it by id.

When evaluating supervision cost on an actual task, record supervisor request count, input
size, cached input, output, repair rounds, and acceptance once at completion. Reuse available
stage totals; do not wake models just to collect metrics. Keep CLI invocation counts separate
from internal model requests, and report unavailable metrics as unavailable. These observations
are improvement evidence, not a per-task reporting gate, a promised saving, or a conversion
from tokens to subscription quota.
