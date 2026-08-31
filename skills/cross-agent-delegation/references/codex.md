# Codex CLI — headless contract

```bash
codex exec --skip-git-repo-check --sandbox <read-only|workspace-write> --json -o "$OUT" "$(cat "$BRIEF")" </dev/null
```

- `--skip-git-repo-check`: outside a trusted git repository Codex refuses to start — `resume`
  and `review` included.
- `</dev/null`: on a non-TTY stdin it waits on stdin before running.
- `--json` emits JSONL events; the answer is the `item.completed` event whose `item.type` is
  `agent_message`, in `item.text`. `-o <file>` writes that final message text on its own — plain
  prose, easier to capture than the event stream, not a structured document. Both are
  per-invocation flags: a resume without them prints plain text.
- Continue: `codex exec --sandbox <mode> resume --skip-git-repo-check --json -o "$OUT" <thread_id> "$(cat "$BRIEF")" </dev/null`,
  with the id from the `thread.started` event. `--sandbox` is an `exec` option and goes *before*
  `resume` — after it, it is an unexpected argument (same rule as `review` below); `--skip-git-repo-check`,
  `--json` and `-o` are accepted after `resume`.
- `--sandbox workspace-write` keeps Codex's own state under `~/.codex` read-only even when
  `writable_roots` covers `$HOME` — writes to `~/.codex/memories` fail with `Read-only file
  system` (observed on 0.151.0). A dispatch that must write there needs
  `--sandbox danger-full-access`.
- Review has two entry points. `codex review …` prints prose for a human and has no `--json` or
  `-o`; `codex exec … review` takes them. `--sandbox` is an `exec` option and goes *before*
  `review` — after it, it is an unexpected argument. A target and a custom prompt are exclusive:
  `--uncommitted`, `--base <branch>` or `--commit <sha>` *or* a prompt argument, never both.

```bash
codex exec --sandbox read-only review --uncommitted --json -o "$OUT" </dev/null
codex exec --sandbox read-only review --json -o "$OUT" "$(cat "$BRIEF")" </dev/null
```
