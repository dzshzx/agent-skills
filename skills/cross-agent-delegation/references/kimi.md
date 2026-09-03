# Kimi Code — headless contract

```bash
kimi -p "$(cat "$BRIEF")" --output-format stream-json
```

- **Answer: the last `role: "assistant"` line carrying a `content` string.** A multi-step run
  emits one such line per step — the earlier ones are progress narration, and steps that call
  tools emit `assistant` lines carrying `tool_calls` instead. Concatenating them all hands you
  the delegate's thinking-out-loud along with its answer. The default `text` format interleaves
  the same material, so always request `stream-json`.
- **Continue with `-S <session_id>`**, taking the id from the closing
  `{"role":"meta","type":"session.resume_hint","session_id":…}` line. That line also prints
  `kimi -r <id>`; `-r` is absent from `--help` but resumes the same session (both forms recall
  earlier turns). A resumed session takes no `--agent`/`--agent-file`: the agent bound at
  creation is restored automatically, so a read-only dispatch resumes read-only.
- `-p` takes the brief as its value; no `</dev/null` and no `--` needed — a first line starting
  with `-` or `---` arrives as text. An empty prompt is rejected (`Prompt cannot be empty`, exit
  1), as is a mistyped flag, both at parse time. A command line with no `-p` at all — `kimi -r <id>` alone — opens the
  interactive TUI and waits for a keypress, the trust prompt first in a cwd Kimi has not seen; a
  closed stdin does not release it. Only the `timeout` around the dispatch turns that hang into a
  failure.
- Failure is the exit code. A rejected launch writes its reason to stderr, and stdout holds at
  most the `system.version` meta line — a consumer reading only stdout sees an empty stream
  rather than an error.
- **`-p` takes no permission flag at all.** `--auto`, `-y`, `--yolo` and `--plan` each abort
  the run with `Cannot combine --prompt with <flag>`. Headless is pinned to the `auto` posture
  and executes tool calls — writes included — with no approval gate.
- **Read-only comes from the tool set.** Without `--agent`, `-p` runs the full default set —
  `Write`, `Edit`, `ReadMediaFile` and the rest — so a plain dispatch reads images and writes
  files alike.
  - `--agent explore` selects the vendor's built-in read-only agent — `Read, Grep, Glob, Bash,
    ReadMediaFile, FetchURL, WebSearch` when asked to enumerate itself — with nothing to write
    beforehand: the shell returns, `Write` and `Edit` stay gone, and shell-borne writes ride on
    the brief. It reads images (`ReadMediaFile` delivers pixels, not bytes) and reaches the
    network.
  - `--agent-file <file.md>` selects your own definition, whose frontmatter `tools:` list is a
    whitelist; the excluded tools are really gone — pressed to write under a persona that wanted
    to comply, such a run enumerates only the tools it was given and reports no write capability.
    Drop `Bash` there for a hard no-shell boundary; a whitelist that must see images lists
    `ReadMediaFile` itself. The agent takes its name from the file's basename, which must be
    kebab-case: `$SCRATCH/read-only.md` launches, a `mktemp` name is rejected before any model
    call with `Invalid agent name … expected kebab-case`. `[[permission.rules]]` can deny
    `Bash(<pattern>)`, but a denylist over shell commands is not a boundary.

```markdown
---
description: Read-only, no shell
tools: [Read, Grep, Glob]
---
Report what you find; you are not changing files.
```
