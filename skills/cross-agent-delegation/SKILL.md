---
name: cross-agent-delegation
description: Hand a task to a different vendor's coding agent CLI — Claude Code, Codex, or Kimi Code — by running it as a headless subprocess. Use when the user names one of them to do the work ("have Codex review this", "let Kimi implement it", "ask Claude for a plan"). Not for subagents inside your own runtime, not for switching models within one harness, and not for delegating the user did not ask for.
---

# Cross-agent delegation

Each of these CLIs is a process: prompt in, final text out. One dispatch costs you a single
call and returns a finished result — the delegate's reading, commands, and reasoning never
enter your context.

**You are one of them.** When the named delegate is the runtime you already are, do the work
directly; there is no subprocess.

Contracts here are verified against Claude Code 2.1.241, Codex CLI 0.149.0, Kimi Code 0.38.0.
On version drift, confirm a flag with `--help` before trusting the line that names it.

## Before dispatch

Run `command -v claude codex kimi`. A spawned shell may not carry your PATH, and only some of
these are installed on any given machine. A missing binary is a stop, not a workaround.

## Invocation contracts

Each block is the minimal correct form plus the failures that cost a retry.

### Claude Code

```bash
claude -p "<prompt>" --output-format json --permission-mode <mode> </dev/null
```

- Answer: `.result`. Continuation handle: `.session_id`.
- **Failure lives in `.is_error` and `.terminal_reason`, never `.subtype`.** A failed run exits
  non-zero with `"is_error":true` while `subtype` still reads `"success"`. Branching on
  `subtype` reports every failure as a success.
- Continue: `claude -p --resume <session_id> "<prompt>"`.
- Permissions: `--permission-mode dontAsk` denies anything outside the allow-rules and the
  read-only command set, which is the locked-down mode for an unattended delegate;
  `acceptEdits` lets it write. Widen a specific command with `--allowedTools` rather than
  loosening the mode.
- A blocked call is reported in `.permission_denials`, naming the tool and its arguments. A run
  that returns a non-empty array did not do what you asked, however finished its prose sounds —
  check the array, not the wording.

### Codex CLI

```bash
codex exec --skip-git-repo-check --sandbox <mode> --json -o <file> "<prompt>" </dev/null
```

- `--skip-git-repo-check`: outside a git repository Codex refuses to start.
- `</dev/null`: on a non-TTY stdin it waits on stdin before running.
- `--json` emits JSONL events; the answer is the `item.completed` whose `item.type` is
  `agent_message`. `-o <file>` writes that final message on its own — cheaper to parse than
  the event stream.
- Continue: `codex exec resume <thread_id> "<prompt>"`, with the id from the `thread.started`
  event.
- Review is a first-class subcommand: `codex review --uncommitted`, `--base <branch>`, or
  `--commit <sha>`. It prints prose and has **no `--json` or `-o`**; when the review result
  must be machine-readable, run `codex exec review` instead and read its event stream.

### Kimi Code

```bash
kimi -p "<prompt>" --output-format stream-json --auto </dev/null
```

- Answer: the line whose `role` is `assistant`. The default `text` format interleaves the
  model's reasoning with its answer, so always request `stream-json`.
- **Continue with `-S <session_id>`.** Kimi's own output prints a hint reading
  `kimi -r <id>`; `-r` is not a flag. It is accepted silently, ignored, and you get a fresh
  session that remembers nothing — a wrong answer with no error.
- `--auto` is full autonomy. `-y/--yolo` auto-approves ordinary tool calls but still stops to
  ask questions, which strands an unattended subprocess.

## Permission by role

| Role | Permission | Why |
| --- | --- | --- |
| planner | read-only | its product is text; write access buys nothing |
| executor | write, scoped to the task's directory | the only role that should change files |
| reviewer | read-only | a reviewer that can edit repairs what it finds instead of reporting it, and the independent judgment you delegated for is gone |

Codex expresses this as `--sandbox read-only` or `workspace-write`, Claude as
`--permission-mode`, Kimi as `--auto` for the executor and its absence elsewhere.

## The brief

The subprocess inherits nothing — not the conversation, not the files you have read, not the
decisions already made. Everything it needs travels in the prompt:

- the goal, and the bounded piece this delegate owns
- the exact file or directory scope it may touch
- acceptance criteria, so it can tell done from not-done
- the return format and a length budget
- that it performs the task itself rather than delegating onward

## Handoff and recovery

Write each stage's product to a file before the next stage starts. That file is at once the
next stage's input and the restart point, so a failed stage re-runs alone instead of the whole
chain. When a stage should continue rather than restart, resume it by id.

Delegations that write files belong in an isolated worktree whenever the host project's rules
call for one; follow those rules rather than inventing isolation here.

## Cost shapes the grain

Every delegate reloads its own full instruction layer on each dispatch. That cost is paid per
invocation, not per token of work, so **delegate coarse**: one dispatch carries a task block
large enough to dwarf the startup. Small lookups — read this file, explain this function —
belong to your own runtime's subagents, which already hold the loaded context.

Dispatches run for minutes. Start them as background or long-timeout subprocesses; a default
command timeout cuts them off mid-task and the work is lost.
