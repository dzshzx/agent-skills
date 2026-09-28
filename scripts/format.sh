#!/usr/bin/env bash
# 统一格式化入口：Python 用 ruff format，JS/TS 与 Markdown/YAML/JSON 用 prettier，Shell 用 shfmt。
# 用法：scripts/format.sh [--check]
#   无参数：就地格式化本仓跟踪的文件；--check：只检查，不一致时列出文件并非零退出（CI 用）。
# 工具版本只在下方常量固定；各工具配置：ruff.toml、.prettierrc.json/.prettierignore、.editorconfig（shfmt）。
set -euo pipefail

RUFF_VERSION=0.16.9
PRETTIER_VERSION=3.9.9
SHFMT_VERSION=3.14.1
# 来自 GitHub release 资产 digest（mvdan/sh v3.14.1）。
declare -A SHFMT_SHA256=(
  [linux_amd64]=76e77641faa025814b77f153b29796b8e6fa2fca03e0c76a691608b86c7ea7bf
  [linux_arm64]=5f2db09dae91fca848f7adbdd014632e921a383863a2ad7e0450ad3aba0c6489
  [darwin_amd64]=d33eee0da0f92835b3562e9767a05cee7e4eaeef47daa03bfd09da17b4b590a6
  [darwin_arm64]=b7c872db63553ccffc7253aba3ed7d4885a27d83f1ba567b1138c6315a5847e5
)
# 生成物与第三方目录（git pathspec），三种语言共用。
EXCLUDE=(':(exclude)**/node_modules/**' ':(exclude)**/vendor/**' ':(exclude)**/dist/**')

CHECK=0
case "${1:-}" in
  "") ;;
  --check) CHECK=1 ;;
  -h | --help)
    sed -n '2,5p' "$0"
    exit 0
    ;;
  *)
    echo "未知参数：$1" >&2
    exit 2
    ;;
esac
[ $# -le 1 ] || {
  echo "参数过多" >&2
  exit 2
}

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

files() {
  local f
  git ls-files -z -- "$@" "${EXCLUDE[@]}" | while IFS= read -r -d '' f; do
    [ -f "$f" ] && printf '%s\0' "$f"
  done
}

ruff() {
  if command -v uvx >/dev/null 2>&1; then
    uvx -q "ruff==$RUFF_VERSION" "$@"
  else
    pipx run --spec "ruff==$RUFF_VERSION" ruff "$@"
  fi
}

shfmt_bin() {
  # 本机已装同版本（Homebrew 输出 3.x.y，官方二进制输出 v3.x.y）则直接用。
  local have
  have=$(shfmt --version 2>/dev/null || true)
  if [ -n "$have" ] && [ "${have#v}" = "$SHFMT_VERSION" ]; then
    command -v shfmt
    return
  fi
  local os arch key cache bin
  os=$(uname -s | tr '[:upper:]' '[:lower:]')
  case "$(uname -m)" in
    x86_64 | amd64) arch=amd64 ;;
    aarch64 | arm64) arch=arm64 ;;
    *) arch=$(uname -m) ;;
  esac
  key="${os}_${arch}"
  [ -n "${SHFMT_SHA256[$key]:-}" ] || {
    echo "format: 没有 shfmt $key 的固定校验和" >&2
    return 1
  }
  cache="${XDG_CACHE_HOME:-$HOME/.cache}/format-sh/shfmt-$SHFMT_VERSION"
  bin="$cache/shfmt_$key"
  if [ ! -x "$bin" ]; then
    mkdir -p "$cache"
    curl -fsSL -o "$bin.tmp" "https://github.com/mvdan/sh/releases/download/v$SHFMT_VERSION/shfmt_v${SHFMT_VERSION}_$key"
    echo "${SHFMT_SHA256[$key]}  $bin.tmp" | sha256sum -c --quiet - >&2 || {
      rm -f "$bin.tmp"
      echo "format: shfmt 校验和不符" >&2
      return 1
    }
    chmod +x "$bin.tmp"
    mv "$bin.tmp" "$bin"
  fi
  echo "$bin"
}

mapfile -d '' PY < <(files '*.py' '*.pyi')
mapfile -d '' PRETTIER < <(files '*.js' '*.mjs' '*.cjs' '*.jsx' '*.ts' '*.mts' '*.cts' '*.tsx' \
  '*.md' '*.yml' '*.yaml' '*.json')
mapfile -d '' SH < <(files '*.sh' '*.bash')

FAIL=0
if [ ${#PY[@]} -gt 0 ]; then
  if [ "$CHECK" -eq 1 ]; then
    ruff format --check --output-format concise -- "${PY[@]}" || FAIL=1
  else
    ruff format -- "${PY[@]}"
  fi
fi
if [ ${#PRETTIER[@]} -gt 0 ]; then
  if [ "$CHECK" -eq 1 ]; then
    npm_config_loglevel=warn npx --yes "prettier@$PRETTIER_VERSION" --check -- "${PRETTIER[@]}" || FAIL=1
  else
    npm_config_loglevel=warn npx --yes "prettier@$PRETTIER_VERSION" --write --log-level warn -- "${PRETTIER[@]}"
  fi
fi
if [ ${#SH[@]} -gt 0 ]; then
  SHFMT=$(shfmt_bin)
  if [ "$CHECK" -eq 1 ]; then
    # -l 在有不一致文件或解析失败时都非零退出，两种都算失败。
    rc=0
    bad=$("$SHFMT" -l -- "${SH[@]}") || rc=$?
    if [ -n "$bad" ] || [ "$rc" -ne 0 ]; then
      printf 'shfmt: 需要重排：\n%s\n' "$bad"
      FAIL=1
    fi
  else
    "$SHFMT" -w -- "${SH[@]}"
  fi
fi

if [ "$CHECK" -eq 1 ]; then
  if [ "$FAIL" -eq 0 ]; then
    echo "format: ok"
  else
    echo "format: 格式不一致，运行 scripts/format.sh 修复" >&2
  fi
fi
exit "$FAIL"
