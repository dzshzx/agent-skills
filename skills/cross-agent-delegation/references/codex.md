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
  source; upstream tracks the long hold as openai/codex#37450. live-check does not cover this path.
- To continue such a thread, send the brief as a new turn through the daemon. The turn is written
  to that thread's history and runs under the thread's own sandbox and approval settings. The
  control socket `$CODEX_HOME/app-server-control/app-server-control.sock` speaks JSON-RPC over
  WebSocket: raw JSON lines get no reply, and `codex app-server proxy` only relays bytes, so it
  needs a WebSocket client too. Send `initialize` with `clientInfo`, the `initialized`
  notification, then `turn/start`. A `result.turn.status` of `inProgress` is the dispatch receipt,
  and the turn keeps running after you disconnect. Approval requests go to the connection that
  started the turn, so disconnecting suits threads whose approval policy does not ask; otherwise
  stay connected and answer them. Start only on an idle thread, one whose rollout
  (`$CODEX_HOME/sessions/**/rollout-*-<id>.jsonl`) ends in `task_complete`, and read that rollout
  for progress and the final answer. `codex app-server generate-json-schema --out <dir>` prints the
  method schemas when a field is in doubt.

  ```python
  # uv run --no-project --with websockets python -I send.py <thread_id> "$BRIEF"
  import asyncio, json, os, sys
  from websockets.asyncio.client import unix_connect

  async def main(thread_id, brief):
      sock = os.path.join(os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex")),
                          "app-server-control", "app-server-control.sock")
      async with unix_connect(os.path.realpath(sock), uri="ws://localhost/") as ws:
          async def call(rid, method, params):
              await ws.send(json.dumps({"id": rid, "method": method, "params": params}))
              while (m := json.loads(await ws.recv())).get("id") != rid:
                  pass
              return m
          await call(1, "initialize", {"clientInfo": {"name": "delegation", "version": "0"}})
          await ws.send(json.dumps({"method": "initialized"}))
          text = open(brief, encoding="utf-8").read()
          print(await call(2, "turn/start", {"threadId": thread_id,
                                             "input": [{"type": "text", "text": text}]}))

  asyncio.run(main(*sys.argv[1:3]))
  ```

- Review has two entry points. `codex review …` prints prose for a human and has no `--json` or
  `-o`; `codex exec … review` takes them. `--sandbox` is an `exec` option and goes _before_
  `review` — after it, it is an unexpected argument. A target and a custom prompt are exclusive:
  `--uncommitted`, `--base <branch>` or `--commit <sha>` _or_ a prompt argument, never both.

```bash
codex exec --sandbox read-only review --uncommitted --json -o "$SCRATCH/last.txt" </dev/null
codex exec --sandbox read-only review --json -o "$SCRATCH/last.txt" -- "$(cat "$BRIEF")" </dev/null
```
