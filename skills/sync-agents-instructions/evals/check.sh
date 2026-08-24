#!/usr/bin/env bash
# 机械门：对 config-fixtures 跑 scripts/validate_config.py，核对退出码与错误关键词；
# references/config-example.toml 也必须通过 schema 校验。不碰文件系统（--schema-only），CI 可跑。
set -u
DIR=$(cd "$(dirname "$0")/.." && pwd)
V="$DIR/scripts/validate_config.py"
FAIL=0
expect() { # expect <rc> <file> [substring-that-stderr-must-contain]
  local want=$1 file=$2 needle=${3:-} err rc
  err=$(python3 "$V" --schema-only "$file" 2>&1 >/dev/null); rc=$?
  if [ "$rc" -ne "$want" ]; then printf 'FAIL %s: rc=%s want %s\n%s\n' "$file" "$rc" "$want" "$err"; FAIL=1; return; fi
  if [ -n "$needle" ] && ! printf '%s' "$err" | grep -qF -- "$needle"; then
    printf 'FAIL %s: stderr 缺少 %s\n%s\n' "$file" "$needle" "$err"; FAIL=1; return
  fi
  printf 'ok   %-24s rc=%s%s\n' "$(basename "$file")" "$rc" "${needle:+  ~ $needle}"
}
F="$DIR/evals/config-fixtures"
expect 0 "$DIR/references/config-example.toml"
expect 0 "$F/valid.toml"
expect 1 "$F/duplicate-owner.toml"    'normalizes to the same owner'
expect 1 "$F/readonly-unmatched.toml" "'GEMINI.md' is not another configured agent"
expect 1 "$F/readonly-unmatched.toml" "is this agent's own surface"
expect 1 "$F/missing-field.toml"      "missing required key 'always_load_mode'"
expect 1 "$F/missing-field.toml"      'load: must be one of'
expect 1 "$F/unknown-key.toml"        "unknown key 'project_glob'"
expect 1 "$F/unknown-key.toml"        'must be repo-relative'
expect 2 "$DIR/evals/check.sh"
exit $FAIL
