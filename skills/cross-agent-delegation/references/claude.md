# Claude Code — headless contract

```bash
claude -p --output-format json --permission-mode acceptEdits -- "$(cat "$BRIEF")" </dev/null
```

- Answer: `.result`. Continuation handle: `.session_id`.
- External inputs and reports: add `--add-dir "$INPUT_DIR" "$REPORT_DIR"` when the task
  needs directories outside cwd. Check that they exist before launch. This grants directory
  access; it does not allow Bash commands. For example, use the same task parameters on both
  invocations (with the common timeout and output capture around each):

  ```bash
  claude -p --output-format json --permission-mode acceptEdits --add-dir "$INPUT_DIR" "$REPORT_DIR" --allowedTools 'Bash(python3:*)' -- "$(cat "$BRIEF")" </dev/null
  claude -p --resume "$SESSION_ID" --output-format json --permission-mode acceptEdits --add-dir "$INPUT_DIR" "$REPORT_DIR" --allowedTools 'Bash(python3:*)' -- "$(cat "$BRIEF")" </dev/null
  ```

  Set `SESSION_ID` from the first result's `.session_id`, replace the brief with the follow-up,
  and allow only commands needed by the task under its existing authorization.
- `--` before the prompt: a brief whose first line starts with `-` is otherwise parsed as an
  option (`error: unknown option '- …'`, exit 1, no model call). An empty prompt is rejected at
  the same stage. A start that fails before any API call — unknown model, missing credentials —
  still writes the JSON result to stdout with `is_error: true`; stderr gets a one-line tag.
- **Failure lives in `.is_error` and `.terminal_reason`, never `.subtype`.** A failed run exits
  non-zero with `"is_error":true` while `subtype` still reads `"success"`. Branching on
  `subtype` reports every failure as a success.
- Continue: `claude -p --resume <session_id> --output-format json --permission-mode <mode> -- "$(cat "$BRIEF")" </dev/null`.
  **A resume restores the conversation, not the posture.** It starts under the cwd's default
  permission mode with the full tool set: a `dontAsk` session resumed bare wrote the file it had
  just been denied, and a `--tools Read,Grep,Glob` session resumed bare lists `Write` in its
  init event again. Every required `--add-dir`, `--permission-mode`, `--allowedTools`, `--tools`
  and `--strict-mcp-config` goes on every resume, from the explicit execution root with the
  output format selected again.
- Permissions: `acceptEdits` auto-approves edits and nothing else. `-p` cannot prompt, so every
  other request — Bash first of all — is denied and logged, not asked; a dispatch that runs
  tests, builds or git takes `--allowedTools 'Bash(<cmd>:*)'` per required command already
  authorized. If denied, distinguish missing directory access from command permission and
  diagnose the specific gap. Difficulty enumerating commands is not authorization to use
  `bypassPermissions`; broader permissions require authorization covering that scope.
  `dontAsk` auto-denies
  whatever would have prompted and runs only `permissions.allow` rules from the cwd's settings
  scopes, the built-in read-only command set and hook-approved calls — what it denies depends on
  that policy, not on the flag alone. `--tools Read,Grep,Glob` restricts the built-in tool set,
  which holds regardless of policy; the MCP servers the user's and cwd's config load keep every
  tool they bring, so a locked-down run adds `--strict-mcp-config` (with no `--mcp-config`) to
  drop them all. The Bash sandbox (`sandbox.filesystem.denyWrite`) is a further settings-level
  layer.
- `--output-format stream-json --verbose` opens with a `system`/`init` event whose
  `permissionMode`, `tools` and `mcp_servers` are the posture the run actually got — read them
  when a restriction matters, rather than asking the delegate what it can do.
- A denied call is reported in `.permission_denials`, naming the tool and its arguments.
  Check the affected step and subsequent evidence under the common
  [acceptance flow](../SKILL.md#accept-and-continue): a later permitted operation may complete
  it, but any required step still missing is blocked. Neither `.result` wording nor exit 0
  overrides an unresolved denial.
- The API's safety layer can refuse a whole turn before any work is done: `is_error: true`,
  `terminal_reason: "api_error"`, result text "safeguards flagged". A cwd whose basename is
  `claude` trips it every time; short probe-like prompts trip it intermittently on the default
  model. Neither is a CLI failure — rename the directory, or rephrase / `--model` another tier.
