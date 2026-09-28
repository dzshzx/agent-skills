#!/usr/bin/env bash
# 提交标题门：用 commitlint 按仓库根的 commitlint.config.mjs 校验范围内的提交（merge、revert 等按 commitlint 默认跳过）。
# 用法：scripts/check-commit-subjects.sh [<range>]
#   默认 origin/master..HEAD（本地：commit 后、push 前）。CI 传 <before>..<sha>；<before> 不是可解析的
#   提交（新分支、首推、workflow_call）时回落到 origin/master..HEAD。范围为空即通过。
#   需要 Node（npx）；commitlint 版本固定在下方，首次运行会下载。
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 2
COMMITLINT_VERSION=21.2.3
RANGE=${1:-origin/master..HEAD}
BEFORE=${RANGE%%..*}
git rev-parse --verify -q "${BEFORE}^{commit}" >/dev/null 2>&1 || RANGE=origin/master..HEAD
FROM=${RANGE%%..*}
TO=${RANGE#*..}
if [ -z "$(git rev-list -n1 "$RANGE" --)" ]; then
  echo "提交标题：范围 $RANGE 为空，通过"
  exit 0
fi
command -v npx >/dev/null 2>&1 || {
  echo "缺少 npx（Node），无法运行 commitlint" >&2
  exit 2
}
if npx --yes -p "@commitlint/cli@$COMMITLINT_VERSION" -p "@commitlint/config-conventional@$COMMITLINT_VERSION" \
  commitlint --from "$FROM" --to "$TO" --verbose; then
  echo "提交标题：范围 $RANGE 全部通过"
else
  echo "提交标题不合 commitlint.config.mjs（范围 $RANGE）；规则见 npx commitlint --print-config" >&2
  exit 1
fi
