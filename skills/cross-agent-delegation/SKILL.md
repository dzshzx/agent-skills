---
name: cross-agent-delegation
description: Hand a task to a different vendor's coding agent CLI — Claude Code, Codex, or Kimi Code — by running it as a headless subprocess. Use when the user names one of them for a piece of work ("have Codex look at this", "give this one to Kimi", "ask Claude"), in any direction and for any kind of task. Not for subagents inside your own runtime, not for switching models within one harness, and not for delegation the user did not ask for.
---

# Cross-agent delegation

Each of these CLIs is a process: prompt in, final text out. One dispatch costs you a single
call and returns a finished result — the delegate's reading, commands, and reasoning never
enter your context. Any of the three takes any kind of work — planning, implementing,
reviewing, explaining — and which one goes is the user's call, made per dispatch.

**You are one of them.** When the named delegate is the runtime you already are, do the work
directly; there is no subprocess.

**Read the contract for the CLI you were named, and only that one:**
[`references/claude.md`](references/claude.md), [`references/codex.md`](references/codex.md),
[`references/kimi.md`](references/kimi.md). Each holds the minimal correct command, where the
answer and the continuation id sit in the output, and the failures that cost a retry. The
contracts were established on Claude Code 2.1.241, Codex CLI 0.149.0 and Kimi Code 0.38.0.
`evals/live-check.sh` re-checks them: the default tier confirms the flags and the parse-level
rejections without a model call; `--smoke` runs the behavioural assertions — JSON fields, exit
codes, resume, permission behaviour — that `--help` never confesses. Green proves exactly the
behaviours asserted there on the installed versions, nothing broader. Doubt a line when the
script goes red, not when a version number moves.

## Before dispatch

Run `command -v <cli>` for the CLI you were named. A spawned shell may not carry your PATH, and
not every machine has all three. A missing binary is a stop, not a workaround.

**Set the working directory explicitly** — run the command from it, in a `( cd "$DIR" && … )`
subshell or through your runtime's working-directory parameter. All three resolve the project,
the repository, and their trust and permission scope from cwd, and none of them takes it from the
prompt text.

**Know what the delegate brings.** It carries none of your conversation, the files you read, or
the decisions already made. It does load its own user and project instruction files, hooks,
skills, MCP servers, credentials and saved sessions for that cwd — it arrives configured like the
user's own session in that CLI, and whatever that layer allows or forbids applies to the dispatch.

**Write the brief to a file; never interpolate it into the command string.** A brief carries
newlines, quotes, backticks and `$(...)`, all of which the shell executes or mangles before the
delegate ever sees them. The brief, any agent file and the captured output share one scratch
directory outside the delegate's cwd, so the `git status` you read afterwards shows the
delegate's work and nothing of yours:

```bash
SCRATCH=$(mktemp -d); BRIEF=$SCRATCH/brief.md
cat > "$BRIEF" <<'EOF'
...the brief...
EOF
```

Every contract's command then takes the prompt as `"$(cat "$BRIEF")"`; the quoting keeps the
whole brief one argv entry. Building the command by concatenating prompt text into it is how a
delegation silently runs something else.

**Wrap every dispatch, first or resumed, as `timeout 1800 <command>`, stdout into a file under
`$SCRATCH`, and run it in the background** (or under your runtime's longest foreground timeout).
Dispatches run for minutes: a
default command timeout cuts one off mid-task and the work is lost, and without `timeout` a hung
CLI is a process you wait on forever. The contract commands are written bare and expect this
wrapper.

## What the dispatch may do

Send it with the working permissions the task needs — the posture you would take yourself for
that piece of work: Claude `--permission-mode acceptEdits`, Codex `--sandbox workspace-write`,
Kimi as it comes — `-p` takes no permission flag and has no gate. When you want a report rather
than edits, say so in the brief; that is how the vendors instruct their own review agents, and it
is enough for ordinary delegations.

Restrict mechanically when the user asks for a locked-down run, or when a stray write would be
expensive to notice. The three restrict differently, and the user's choice of delegate stands:
when the named CLI cannot enforce what was asked, say so and dispatch with the brief-level
instruction rather than re-routing to another CLI.

- **Codex `--sandbox read-only`** — an OS sandbox: commands run, writes fail whatever issues them.
- **Claude `--tools Read,Grep,Glob`** — removes the tools themselves; `--permission-mode dontAsk`
  is only as tight as the cwd's permission policy. The contract has the policy detail.
- **Kimi `--agent explore`** (the shell stays) **or `--agent-file` with a `tools:` whitelist**
  (drop it there) — restricts by tool set, not by flag. The contract has the set, the file-name
  rule and what a resume keeps.

## The brief

Everything the delegate needs travels in the brief:

- the goal, and the bounded piece this delegate owns
- the exact file or directory scope it may touch
- acceptance criteria, so it can tell done from not-done
- the return format and a length budget
- that it performs the task itself rather than delegating onward

## Handing results onward

One invocation per task the user named — each reloads the delegate's whole instruction layer and
may take many model turns — split only where a later dispatch would restart from a saved result.
When one dispatch's result feeds another, put it in a file rather than carrying it through your
own context. That file is at once the next dispatch's input and the point you restart from, so a
failure re-runs one dispatch instead of everything before it. When a dispatch should continue
rather than start over, resume it by id. A dispatch that could write and then timed out or exited
non-zero is not a clean restart — its exit code says nothing about how far it got — so look at
what it left behind (`git status` in its cwd) before re-running or resuming.

Delegations that write files belong in an isolated worktree whenever the host project's rules
call for one; follow those rules rather than inventing isolation here.

A dispatch is done when its answer — the field the contract points at — is in your hands and
checked against the brief's acceptance criteria. That answer is what reaches the user; the event
stream stays in its file.
