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
- `--json` emits JSONL events; the answer is `item.text` from the last `item.completed` whose
  `item.type` is `agent_message` and `item.phase` is not `commentary`, matching the
  [run checker](../evals/check_codex_run.py). `-o <file>` writes that final message text on its
  own — plain prose, easier to capture than the event stream, not a structured document. Both
  are per-invocation flags: a resume without them prints plain text.
- Observed with Codex 0.154.0: `exec --json` omits `ThreadItem::ImageView`. For image-read
  evidence, inspect the matching thread's persisted rollout under `$CODEX_HOME/sessions`
  (default `~/.codex/sessions`) for the call and its completion/result; stdout JSONL alone
  cannot establish whether `view_image` ran.
- Continue: `codex exec --sandbox <mode> resume --skip-git-repo-check --json -o "$SCRATCH/last.txt" -- <thread_id> "$(cat "$BRIEF")" </dev/null`,
  with the id from the `thread.started` event. `--sandbox` is an `exec` option and goes _before_
  `resume` — after it, it is an unexpected argument (same rule as `review` below); `--skip-git-repo-check`,
  `--json` and `-o` are accepted after `resume`.
- `--sandbox workspace-write` keeps `~/.codex` read-only even when `writable_roots` covers
  `$HOME`, so Codex's own memory writes fail with `Read-only file system`. That is noise in the
  run, not a task failure; the posture stays.
- A run that cannot reach the API (401, rate limit) still emits `thread.started` and ends with a
  `turn.failed` event carrying the message on stdout; stderr repeats the error. Exit 1.
- Treat a dispatch as successful only with exit 0, `turn.completed`, a nonempty final
  `item.completed/agent_message`, and no `turn.failed` or `error` event. A progress message
  or an absent output file does not prove successful completion or an OS write denial.
  These establish CLI completion; apply the common [acceptance flow](../SKILL.md#accept-and-continue)
  to the deliverable. Keep the full event stream in its file and read excerpts as needed for
  failures or acceptance, rather than repeatedly loading it into the supervisor's context.
- The API's safety layer can refuse a whole turn the same way: `turn.failed` with "flagged for
  possible cybersecurity risk", exit 1, stderr silent. Probe-like wording — `whoami`, "pwned",
  shell metacharacters presented as a test — trips it, and it is not deterministic: the same
  brief can pass once and fail the next time. A custom `model_instructions_file` rides on every
  turn, so its wording trips the filter just the same — when harmless briefs keep failing,
  re-run with a stock config. Not a CLI failure — rephrase and re-dispatch.
- One process at a time writes a thread: whoever loads it holds an OS lock on
  `$CODEX_HOME/thread-writer-locks/<id>.lock` until the thread unloads. The local app-server
  daemon, which the Codex app and an attached TUI use, unloads a thread only after no client has
  been subscribed for `thread_unload_delay_secs` (default 60), and the app stays subscribed to
  threads it has opened until it quits. `exec resume` on such a thread fails before any model
  call: exit 1, no stdout events, and stderr reads
  `thread/resume failed: thread <id> already has an active writer (code -32600)`. `exec` always
  runs its own in-process server and cannot attach to the daemon (`codex --remote … exec` is
  rejected). Never delete the lock file: its holder is still writing. A `codex://threads/<id>`
  link carries the id; `thread/loaded/list` (below) tells whether the daemon holds it, and when it
  does not, `exec resume` works as above. Observed with Codex 0.162.1 and its `rust-v0.162.1`
  source; upstream tracks the long hold as openai/codex#37450. live-check's smoke tier covers this path.
- To continue such a thread, send the brief as a new turn through the daemon with the bundled
  script; the turn is written to that thread's history and runs under the thread's own sandbox
  and approval settings. The `scripts/` paths here and below resolve from this skill's directory
  (`${CLAUDE_SKILL_DIR}` on Claude Code), not from the delegate's working directory:

  ```bash
  uv run --script scripts/codex_thread_turn.py "$THREAD_ID" "$BRIEF" [--wait] [--timeout 1800]
  ```

  Without `--wait` it returns once the daemon accepts the turn (exit 0, ids on stderr) and the
  turn keeps running; read its progress and answer from the thread's rollout
  (`$CODEX_HOME/sessions/**/rollout-*-<id>.jsonl`, finished at `task_complete`). With `--wait` it
  stays subscribed and prints the final answer. Exit 3 means there is no daemon or it does not hold the thread —
  use `exec resume`; 4 means a turn is already running; 5 means the turn sent a request the script cannot answer, such as an approval, so the user answers it in the app; 124 is a `--wait` timeout with the
  turn still running. The daemon speaks experimental JSON-RPC over WebSocket on
  `$CODEX_HOME/app-server-control/app-server-control.sock`;
  `codex app-server generate-json-schema --out <dir>` prints the method schemas when the script
  needs a change.
  Add `--steer` to insert the brief into the thread's running turn instead of exit 4
  (`turn/steer` with `expectedTurnId` set to the in-progress turn; the stderr ids line gains
  `"steered": true`, and `--wait` waits for that turn). Use it to feed a review conclusion or a
  correction to a Codex turn that is still working. It never starts a turn: an idle thread exits 1,
  and the other exits are unchanged. Limits: the text joins the turn at the model's next step, not
  instantly; it cannot change the turn's sandbox or model; if the turn ends between the check and
  the call the daemon rejects it (exit 1), so resend without `--steer`.

- To supervise a running thread (progress questions, or a notification when it needs the user),
  read its rollouts with `uv run --script scripts/codex_thread_progress.py "$THREAD_ID"` instead of
  hand-written `jq`: one report of assistant messages, questions to the user and their answers,
  spawned subagents, and whether the root turn is still running. Run it with
  `--wait question|complete|any` as a host background job so its exit fires the notification:
  3 a question awaits the user (checked against the current state, so a pending one returns
  at once), 0 the root turn completed after `--since` or, without it, after the script started,
  124 timeout. Read-only; `--help`
  has the options.

- Review has two entry points. `codex review …` prints prose for a human and has no `--json` or
  `-o`; `codex exec … review` takes them. `--sandbox` is an `exec` option and goes _before_
  `review` — after it, it is an unexpected argument. A target and a custom prompt are exclusive:
  `--uncommitted`, `--base <branch>` or `--commit <sha>` _or_ a prompt argument, never both.

```bash
codex exec --sandbox read-only review --uncommitted --json -o "$SCRATCH/last.txt" </dev/null
codex exec --sandbox read-only review --json -o "$SCRATCH/last.txt" -- "$(cat "$BRIEF")" </dev/null
```
