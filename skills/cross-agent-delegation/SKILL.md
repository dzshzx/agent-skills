---
name: cross-agent-delegation
description: Hand a task to a different vendor's coding agent CLI — Claude Code, Codex, or Kimi Code — by running it as a headless subprocess. Use when the user names one of them to do the work ("have Codex review this", "let Kimi implement it", "ask Claude for a plan"). Not for subagents inside your own runtime, not for switching models within one harness, and not for delegation the user did not ask for.
---

# Cross-agent delegation

Each of these CLIs is a process: prompt in, final text out. One dispatch costs you a single
call and returns a finished result — the delegate's reading, commands, and reasoning never
enter your context.

**You are one of them.** When the named delegate is the runtime you already are, do the work
directly; there is no subprocess.

Contracts here were established on Claude Code 2.1.241, Codex CLI 0.149.0 and Kimi Code
0.38.0, and they hold from those versions onward until an assertion actually breaks. A newer
CLI is not itself a reason to distrust a line here. `evals/live-check.sh` is the arbiter: its
default tier re-checks every flag and every rejection **without spending a model call**, and
`--smoke` re-checks the field names, silent failures and permission behaviour that `--help`
never confesses. Doubt a contract when that script goes red, not when a version number moves.

## Before dispatch

Run `command -v claude codex kimi`. A spawned shell may not carry your PATH, and only some of
these are installed on any given machine. A missing binary is a stop, not a workaround.

**Set the working directory explicitly.** All three resolve the project, the repository, and
their trust and permission scope from cwd, and none of them takes it from the prompt text. The
delegate inherits your cwd, environment, and filesystem visibility — and nothing else.

**Never interpolate the prompt into the command string.** A brief carries newlines, quotes,
backticks and `$(...)`, all of which the shell will execute or mangle before the delegate ever
sees them. Write the brief to a file and pass it as a single quoted argument:

```bash
cat > "$BRIEF" <<'EOF'
...the brief...
EOF
codex exec --skip-git-repo-check --sandbox read-only -o "$OUT" "$(cat "$BRIEF")" </dev/null
```

The quoted `"$(cat …)"` keeps the whole brief one argv entry. Building the command by
concatenating prompt text into it is how a delegation silently runs something else.

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
  must be machine-readable, run `codex exec review --json` (or `-o <file>`) instead — the
  event stream is not free, the flag is what produces it.

### Kimi Code

```bash
kimi -p "<prompt>" --output-format stream-json
```

- **Answer: the last `role: "assistant"` line carrying a `content` string.** A multi-step run
  emits one such line per step — the earlier ones are progress narration, and steps that call
  tools emit `assistant` lines carrying `tool_calls` instead. Concatenating them all hands you
  the delegate's thinking-out-loud along with its answer. The default `text` format interleaves
  the same material, so always request `stream-json`.
- **Continue with `-S <session_id>`**, taking the id from the closing
  `{"role":"meta","type":"session.resume_hint","session_id":…}` line. That same line prints a
  hint reading `kimi -r <id>`; `-r` is not a flag. It is accepted silently, ignored, and you
  get a fresh session that remembers nothing — a wrong answer with no error.
- Failure is the exit code. A rejected launch writes its reason to stderr and emits **no stdout
  events at all**, so a consumer reading only stdout sees an empty stream rather than an error.
- **`-p` takes no permission flag at all.** `--auto`, `-y`, `--yolo` and `--plan` each abort
  the run with `Cannot combine --prompt with <flag>`. Headless is pinned to the `auto` posture
  and executes tool calls — writes included — with no approval gate. Adding one of those flags
  to make a run safe does not restrict it; it prevents it.
- **Read-only comes from the tool set instead.** `--agent-file <file.md>` selects an agent
  definition whose frontmatter `tools:` list is a whitelist, and the excluded tools are really
  gone: pressed to write under a persona that wanted to comply, such a run enumerates only the
  tools it was given and reports that it has no write capability. This composes with `-p`.

  ```markdown
  ---
  description: Read-only
  tools: [Read, Grep, Glob]
  ---
  Report what you find; you are not changing files.
  ```

## What the dispatch may touch

Decide this per dispatch, from what this piece of work needs. Two questions settle it.

**Does it need to change files?** If yes, grant writes and point them at the directory the work
belongs in. If no, take them away — a delegate that can write eventually will, and asking it not
to in the brief is a request, not a constraint.

**Would you be able to tell if it wrote anyway?** This is the question that decides *which* CLI
gets the dispatch. When what you want back is a judgement — is this right, what is wrong here,
what should we do — an unenforced restriction leaves you unable to separate "found nothing" from
"found something and quietly fixed it". That is when the restriction has to be enforced rather
than requested:

- **Codex — `--sandbox read-only`.** Enforced by the sandbox, so writes fail no matter which
  command attempts them, and the delegate can still run things to check its own claims.
- **Claude — `--permission-mode dontAsk`.** Everything outside the allow-rules and the
  read-only command set is denied, so read-only commands still run.
- **Kimi — `--agent-file` with a `tools:` whitelist**, which matches tool names, so the
  strength you get depends on which two you can live without:
  - `tools: [Read, Grep, Glob]` — mechanically read-only, and no commands at all.
  - `tools: [Read, Grep, Glob, Bash]` — commands run, `Write` and `Edit` are genuinely gone,
    and shell-borne writes rest on the brief saying not to. This is the vendor's own recipe:
    the built-in `explore` agent ships exactly this set and calls it "prompt-enforced
    read-only behavior". `[[permission.rules]]` matches `Bash(<pattern>)`, but a denylist over
    shell commands is not a boundary — `tee`, `sed -i` and `python -c` walk through it.

  Kimi decides read-only at tool-name granularity and does not judge whether a given command
  writes; `--plan` gates edits mechanically but cannot be combined with `-p`.

When the dispatch is supposed to change things, none of the above applies — send it plainly.
Kimi arrives in that posture already, which is the same fact seen from the other side: a Kimi
dispatch with no agent file will change files whatever the brief says.

## The brief

The delegate carries none of your context — not the conversation, not the files you have read,
not the decisions already made. Everything it needs travels in the brief:

- the goal, and the bounded piece this delegate owns
- the exact file or directory scope it may touch
- acceptance criteria, so it can tell done from not-done
- the return format and a length budget
- that it performs the task itself rather than delegating onward

## Handing results onward

When one dispatch's result feeds another, put it in a file rather than carrying it through your
own context. That file is at once the next dispatch's input and the point you restart from, so a
failure re-runs one dispatch instead of everything before it. When a dispatch should continue
rather than start over, resume it by id.

Delegations that write files belong in an isolated worktree whenever the host project's rules
call for one; follow those rules rather than inventing isolation here.

## Cost shapes the grain

Every delegate reloads its own full instruction layer on each dispatch. That cost is paid per
invocation, not per token of work. So when the split is yours to choose, **delegate coarse**:
one dispatch carries a task block large enough to dwarf the startup, and small lookups stay
with your own runtime's subagents, which already hold the loaded context. When the user names
the delegate and the task, dispatch it as asked — the cost is theirs to spend.

Dispatches run for minutes. Start them as background or long-timeout subprocesses; a default
command timeout cuts them off mid-task and the work is lost.
