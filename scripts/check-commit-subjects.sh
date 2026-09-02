#!/usr/bin/env bash
# 提交主题形态门：范围内每条非 merge 提交的主题须为 `type(scope): subject` 或 `type: subject`。
#   type  = 小写字母，可用 `+` 连接（feat / fix / docs / chore / skill / docs+skill …）；不含连字符，
#           所以裸 skill 名（`cross-agent-delegation: …`）不算 type，会被拒。
#   scope = 可选，括号内 kebab-case（skill 名、ci、readme …）；`!` 破坏标记可选。
#   `Revert "…"` 原样放行；merge 提交不检查。
# 用法：scripts/check-commit-subjects.sh [<range>]
#   默认 origin/master..HEAD（本地：commit 后、push 前）。CI 传 <before>..<sha>；<before> 不是可解析的
#   提交（新分支、首推、workflow_call）时回落到 origin/master..HEAD。范围为空即通过。
set -u
RANGE=${1:-origin/master..HEAD}
BEFORE=${RANGE%%..*}
git rev-parse --verify -q "${BEFORE}^{commit}" >/dev/null 2>&1 || RANGE=origin/master..HEAD
PATTERN='^(Revert "|[a-z]+(\+[a-z]+)*(\([a-z0-9._-]+\))?!?: [^ ])'
BAD=0
while IFS=$'\t' read -r sha subject; do
  [ -n "$sha" ] || continue
  if [[ $subject =~ $PATTERN ]]; then
    printf '  ok   %s %s\n' "$sha" "$subject"
  else
    printf '  FAIL %s %s\n' "$sha" "$subject"; BAD=$((BAD+1))
  fi
done < <(git log --no-merges --format='%h%x09%s' "$RANGE" --)
if [ "$BAD" -gt 0 ]; then
  echo "$BAD 条提交主题不是 type(scope): subject 形态（范围 $RANGE）"; exit 1
fi
echo "提交主题形态：范围 $RANGE 全部通过"
