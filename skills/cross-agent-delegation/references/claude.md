# Claude Code — headless contract

```bash
claude -p "$(cat "$BRIEF")" --output-format json --permission-mode acceptEdits </dev/null
```

- Answer: `.result`. Continuation handle: `.session_id`.
- **Failure lives in `.is_error` and `.terminal_reason`, never `.subtype`.** A failed run exits
  non-zero with `"is_error":true` while `subtype` still reads `"success"`. Branching on
  `subtype` reports every failure as a success.
- Continue: `claude -p --resume <session_id> "$(cat "$BRIEF")" --output-format json </dev/null`.
  A resumed session keeps the permission mode it had unless you pass one again.
- Permissions: `acceptEdits` lets it write. `dontAsk` auto-denies whatever would have prompted
  and runs only `permissions.allow` rules from the cwd's settings scopes, the built-in read-only
  command set and hook-approved calls — what it denies depends on that policy, not on the flag
  alone. `--allowedTools` widens a specific tool or command pattern; `--tools Read,Grep,Glob`
  restricts the tool set itself, which holds regardless of policy.
- A denied call is reported in `.permission_denials`, naming the tool and its arguments. A run
  whose array is non-empty did not do what you asked, however finished its prose sounds — check
  the array, not the wording.
