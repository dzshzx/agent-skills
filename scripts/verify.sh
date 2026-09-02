#!/usr/bin/env bash
# 标准验证流程（push 前跑）：机械门 + 真跑门。
# 用法：scripts/verify.sh [--all | --no-live] [skill ...]
#   机械门：validate_repository.py、shellcheck、sync-agents-instructions 的 fixtures 门、
#           check-commit-subjects.sh（origin/master..HEAD 的提交主题形态）——与 CI 同一组命令。
#   真跑门：对「相对 origin/master 有改动（含未提交）」的 skill 跑 skills/<name>/evals/live-check.sh；
#           --all 跑全部 skill（查 CLI 版本漂移）；显式给 skill 名只跑那些；--no-live 只跑机械门。
#   真跑会计费（Claude / Codex / Kimi 真调用）且要求本机装有对应 CLI 与凭证，因此只在本地跑，不进 CI。
#   每个 skill 以其完整档运行（cross-agent-delegation 传 --smoke）。
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT" || exit 2
MODE=changed; NAMED=()
for a in "$@"; do
  case $a in
    --all) MODE=all;; --no-live) MODE=none;;
    -h|--help) sed -n '2,9p' "$0"; exit 0;;
    -*) echo "未知选项 $a"; exit 2;;
    *) MODE=named; NAMED+=("$a");;
  esac
done
FAIL=0
run(){ printf '\n== %s\n' "$*"; if "$@"; then echo "   -> ok"; else echo "   -> FAIL"; FAIL=1; fi; }

echo "#### 机械门（与 CI 相同）"
run python3 scripts/validate_repository.py
run shellcheck -S warning skills/*/evals/*.sh scripts/*.sh
run bash skills/sync-agents-instructions/evals/check.sh
run bash scripts/check-commit-subjects.sh
[ "$MODE" = none ] && { echo; echo "#### 结果：$([ $FAIL -eq 0 ] && echo PASS || echo FAIL)（未跑真跑门）"; exit $FAIL; }

if [ "$MODE" = changed ]; then
  if BASE=$(git merge-base HEAD origin/master 2>/dev/null); then
    mapfile -t NAMED < <({ git diff --name-only "$BASE" HEAD -- skills; git status --porcelain -- skills | cut -c4-; } \
      | awk -F/ '$1=="skills" && $2!="" {print $2}' | sort -u)
  else
    echo "没有 origin/master 可比较，改为 --all"; MODE=all
  fi
fi
[ "$MODE" = all ] && mapfile -t NAMED < <(ls skills)

echo; echo "#### 真跑门：${NAMED[*]:-（相对 origin/master 没有 skill 改动，跳过；--all 可强制全跑）}"
for s in "${NAMED[@]}"; do
  LC="skills/$s/evals/live-check.sh"
  [ -f "$LC" ] || { printf '\n== %s\n   -> FAIL：缺少 %s\n' "$s" "$LC"; FAIL=1; continue; }
  ARGS=(); [ "$s" = cross-agent-delegation ] && ARGS=(--smoke)
  run timeout 1800 bash "$LC" "${ARGS[@]}"
done
echo; echo "#### 结果：$([ $FAIL -eq 0 ] && echo PASS || echo FAIL)"
exit $FAIL
