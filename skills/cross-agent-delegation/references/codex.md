# Codex CLI — headless contract

```bash
codex exec --skip-git-repo-check --sandbox <read-only|workspace-write> --json -o "$SCRATCH/last.txt" -- "$(cat "$BRIEF")" </dev/null
```

- `--` before the prompt (and before `<thread_id>` on a resume): a brief whose first line starts
  with `-` is otherwise an `unexpected argument` (exit 2, no model call). An empty prompt is not
  rejected — it starts a real turn.
- `--skip-git-repo-check`: outside a trusted git repository Codex refuses to start — `resume`
  and `review` included.
- `</dev/null`: on a non-TTY stdin it reads additional prompt text from stdin until EOF before
  running, so an open pipe hangs it until `timeout` fires.
- `--json` emits JSONL events; the answer is the `item.completed` event whose `item.type` is
  `agent_message`, in `item.text`. `-o <file>` writes that final message text on its own — plain
  prose, easier to capture than the event stream, not a structured document. Both are
  per-invocation flags: a resume without them prints plain text.
- Continue: `codex exec --sandbox <mode> resume --skip-git-repo-check --json -o "$SCRATCH/last.txt" -- <thread_id> "$(cat "$BRIEF")" </dev/null`,
  with the id from the `thread.started` event. `--sandbox` is an `exec` option and goes *before*
  `resume` — after it, it is an unexpected argument (same rule as `review` below); `--skip-git-repo-check`,
  `--json` and `-o` are accepted after `resume`.
- `--sandbox workspace-write` keeps `~/.codex` read-only even when `writable_roots` covers
  `$HOME`, so Codex's own memory writes fail with `Read-only file system`. That is noise in the
  run, not a task failure; the posture stays.
- A run that cannot reach the API (401, rate limit) still emits `thread.started` and ends with a
  `turn.failed` event carrying the message on stdout; stderr repeats the error. Exit 1.
- The API's safety layer can refuse a whole turn the same way: `turn.failed` with "flagged for
  possible cybersecurity risk", exit 1, stderr silent. Probe-like wording — `whoami`, "pwned",
  shell metacharacters presented as a test — trips it, and it is not deterministic: the same
  brief can pass once and fail the next time. A custom `model_instructions_file` rides on every
  turn, so its wording trips the filter just the same — when harmless briefs keep failing,
  re-run with a stock config. Not a CLI failure — rephrase and re-dispatch.
- Review has two entry points. `codex review …` prints prose for a human and has no `--json` or
  `-o`; `codex exec … review` takes them. `--sandbox` is an `exec` option and goes *before*
  `review` — after it, it is an unexpected argument. A target and a custom prompt are exclusive:
  `--uncommitted`, `--base <branch>` or `--commit <sha>` *or* a prompt argument, never both.

```bash
codex exec --sandbox read-only review --uncommitted --json -o "$SCRATCH/last.txt" </dev/null
codex exec --sandbox read-only review --json -o "$SCRATCH/last.txt" -- "$(cat "$BRIEF")" </dev/null
```
