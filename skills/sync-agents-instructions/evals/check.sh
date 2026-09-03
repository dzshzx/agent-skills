#!/usr/bin/env bash
# 机械门：对 config-fixtures 跑 scripts/validate_config.py，核对退出码与错误关键词；
# references/config-example.toml 也必须通过 schema 校验。CI 可跑：schema 用例走 --schema-only，
# 文件存在性用例只引用 /nonexistent/… 与本目录里的 fixture（经 $SYNC_FIXTURE_DIR 展开），不依赖机器布局。
set -u
DIR=$(cd "$(dirname "$0")/.." && pwd)
V="$DIR/scripts/validate_config.py"
F="$DIR/evals/config-fixtures"
export SYNC_FIXTURE_DIR="$F"
FAIL=0
run() { # run <rc> <file> <substring-that-stderr-must-contain|""> [validator flags...]
  local want=$1 file=$2 needle=$3 err rc; shift 3
  err=$(python3 "$V" "$@" "$file" 2>&1 >/dev/null); rc=$?
  if [ "$rc" -ne "$want" ]; then printf 'FAIL %s: rc=%s want %s\n%s\n' "$file" "$rc" "$want" "$err"; FAIL=1; return; fi
  if [ -n "$needle" ] && ! printf '%s' "$err" | grep -qF -- "$needle"; then
    printf 'FAIL %s: stderr 缺少 %s\n%s\n' "$file" "$needle" "$err"; FAIL=1; return
  fi
  printf 'ok   %-22s %-13s rc=%s%s\n' "$(basename "$file")" "${*:-(paths)}" "$rc" "${needle:+  ~ $needle}"
}
expect() { run "$1" "$2" "${3:-}" --schema-only; }   # schema 用例
paths()  { run "$1" "$2" "${3:-}"; }                 # 含文件存在性检查的用例
expect 0 "$DIR/references/config-example.toml"
expect 0 "$F/valid.toml"
expect 0 "$F/minimal.toml"
expect 1 "$F/duplicate-owner.toml"    'normalizes to the same owner'
expect 1 "$F/duplicate-name.toml"     'agents[1].name: duplicates agents[codex]'
expect 1 "$F/readonly-unmatched.toml" "'GEMINI.md' is not another configured agent"
expect 1 "$F/readonly-unmatched.toml" "is this agent's own surface"
expect 1 "$F/path-forms.toml"         'must name a file, not a directory'
expect 1 "$F/path-forms.toml"         'must use / separators'
expect 1 "$F/path-forms.toml"         "'./AGENTS.md' is listed more than once"
expect 1 "$F/missing-field.toml"      "missing required key 'always_load_mode'"
expect 1 "$F/missing-field.toml"      'load: must be one of'
expect 1 "$F/unknown-key.toml"        "unknown key 'project_glob'"
expect 1 "$F/unknown-key.toml"        'must be repo-relative'
expect 0 "$F/missing-file.toml"
paths  1 "$F/missing-file.toml"       'file not found: /nonexistent/sync-agents-instructions/shared.md'
paths  1 "$F/missing-file.toml"       'entry_file: file not found'
paths  0 "$F/expandvars.toml"
expect 2 "$DIR/evals/check.sh"
exit $FAIL
