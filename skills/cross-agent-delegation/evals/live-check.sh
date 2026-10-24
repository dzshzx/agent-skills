#!/usr/bin/env bash
# 回归检测：核对 SKILL.md 与 references/*.md 缓存的两家 CLI 契约是否仍与本机实装一致。
# 用法：bash evals/live-check.sh [--smoke] [--cli claude|codex|all]
# Codex 成功须 rc=0、turn.completed、非空最终答复且无失败事件；只读文件未产生与 OS 拒写分开断言。
#   默认档（surface + parser）：--help 是否仍列出所用 flag；参数解析层的拒绝/放行是否仍成立——`--` 之后以 `-` 开头的 brief
#     过解析而没有 `--` 时被拒、空 prompt 的两家行为、启动失败写在 stdout 还是 stderr、契约里每种命令形态（exec / resume /
#     review）可解析、`--permission-mode` 的 choices 含 bypassPermissions、单个 argv 128 KiB 上限。
#     零模型调用且 fail-closed：会真启动的命令都跑在无凭证的 CODEX_HOME / 不存在的 Claude 模型下，
#     契约一旦失效（原本该被拒的命令被接受）会在 401 / 模型解析处失败，而不是悄悄花一次调用。
#   --smoke：真跑约 30 次小调用（计费；两家凭证都要在位，缺一家该家整段红），解析 JSON 并断言
#     字段、退出码、续跑与权限行为、brief 经 argv 原样到达。每条契约命令行都按 references 里的形态真跑（`--` 在前、
#     `--sandbox` 在 resume 之前、bypassPermissions）；hostile brief 首行以 `- ` 开头。FAIL 行下附 stderr 尾巴，用来区分
#     「行为断言失败」与「调用本身失败（401 / 限流 / 网络）」——后者不是契约失效。Codex 调用遇到 API 安全层整轮拒绝
#     （turn.failed "flagged for possible cybersecurity risk"，codex.md 记载它不完全确定——同一 brief 可能一次过一次拒，
#     brief 或自定义 model_instructions_file 的措辞都可能触发）时按契约重新派发，最多两次；仍拒才交给断言。
#   --smoke 的 Claude 段整段跑在临时 CLAUDE_CONFIG_DIR 里（只复制 .credentials.json，结束即删临时凭据）：用户级 CLAUDE.md、
#     settings（含 advisorModel）、hooks、MCP 都不进被测 run，会话记录也不进用户的配置目录（--resume 沿用同一目录才找得到会话）；模型取 Claude Code 自身默认。
#     默认档不调模型，解析层的 claude 命令跑在空的临时 CLAUDE_CONFIG_DIR 里（不复制凭据），会话记录同样不进用户目录。
#   绿灯只证明下面逐条断言的行为；没断言的东西它什么都不证明。
set -u
CLI=all
SMOKE=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --smoke)
      SMOKE=1
      shift
      ;;
    --cli)
      [ "$#" -ge 2 ] || {
        echo '--cli requires a value' >&2
        exit 2
      }
      CLI=$2
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done
case "$CLI" in claude | codex | all) ;; *)
  echo "Invalid CLI: $CLI" >&2
  exit 2
  ;;
esac
selected() { [ "$CLI" = all ] || [ "$CLI" = "$1" ]; }
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PASS=0
FAIL=0
ok() {
  PASS=$((PASS + 1))
  printf '  ok   %s\n' "$1"
}
no() {
  FAIL=$((FAIL + 1))
  printf '  FAIL %s\n' "$1"
  [ -s "${E:-}" ] && printf '       stderr: %s\n' "$(tail -c 200 "$E" | tr '\n' ' ')"
}
has() { printf '%s' "$2" | grep -qF -- "$1"; }
W=$(mktemp -d "${LIVE_CHECK_EVIDENCE_DIR:-${TMPDIR:-/tmp}}/cross-agent-live.XXXXXX")
cleanup() {
  # 守护进程里的测试会话：断言途中中断也要归档，免得留在用户的会话列表
  if [ -s "$W/daemon/id" ] && [ ! -e "$W/daemon/archived" ]; then
    uv run -q --script "$HERE/codex_daemon_thread.py" archive "$(cat "$W/daemon/id")" >/dev/null 2>&1
  fi
  rm -rf "$NOAUTH"
  rm -f "$CCD/.credentials.json" # smoke 的临时凭据；会话记录留作证据
  echo "Evidence: $W"
}
trap cleanup EXIT
NOAUTH="$W/codex-home"
mkdir -p "$NOAUTH"           # 空 CODEX_HOME：无凭证，启动后必 401
BOGUS=bogus-model-live-check # 不存在的模型名：Claude 在 API 调用前失败
NONGIT="$W/nongit"
mkdir -p "$NONGIT"
NOCC="$W/claude-empty" # 默认档 claude 命令的 CLAUDE_CONFIG_DIR
mkdir -p "$NOCC"
CCD="$W/claude-config" # smoke 段 claude 命令的 CLAUDE_CONFIG_DIR
# py <file> <expr>：对 JSON 文件求值；<expr> 里用 d 表示解析结果，结果为真则退出 0
py() { python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if eval(sys.argv[2]) else 1)' "$1" "$2" 2>/dev/null; }

for c in claude codex; do
  selected "$c" || continue
  command -v "$c" >/dev/null 2>&1 || {
    echo "缺少 $c，无法检测"
    exit 2
  }
done

echo "== 实装版本（契约是否成立由下面的断言决定，不由版本号决定）"
for c in claude codex; do selected "$c" && printf '  %s %s\n' "$c" "$("$c" --version 2>/dev/null)"; done

if selected claude; then
  echo "== Claude：flag 面"
  H=$(claude --help 2>&1)
  for f in " -p, --print" "--output-format" "--permission-mode" "--allowedTools" "--add-dir" "--tools" "--resume" "--strict-mcp-config"; do
    has "$f" "$H" && ok "claude --help 有 $f" || no "claude --help 缺 $f"
  done
  for m in dontAsk acceptEdits bypassPermissions; do
    has "$m" "$H" && ok "--permission-mode 仍列出 $m" || no "--permission-mode 不再列出 $m"
  done

  echo "== Claude：解析层（模型名不存在，API 调用前即失败）"
  (cd "$NONGIT" && CLAUDE_CONFIG_DIR="$NOCC" timeout 60 claude -p "- item" --model "$BOGUS" --output-format json </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "unknown option" "$(cat "$W/e")" \
    && ok "没有 -- 时以 - 开头的 brief 被当作选项拒绝（rc=$rc）——契约要求 --" || no "以 - 开头的 brief 不再被当作选项（rc=$rc）：$(head -c 120 "$W/e")"
  (cd "$NONGIT" && CLAUDE_CONFIG_DIR="$NOCC" timeout 60 claude -p --model "$BOGUS" --output-format json -- "- item" </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && ! has "unknown option" "$(cat "$W/e")" && py "$W/o" 'd["is_error"] is True' \
    && ok "-- 之后以 - 开头的 brief 过解析；启动失败写进 stdout 的 JSON（is_error=true，rc=$rc）" || no "-- 形式或启动失败的 JSON 形状已变（rc=$rc）：$(head -c 120 "$W/e")"
  (cd "$NONGIT" && CLAUDE_CONFIG_DIR="$NOCC" timeout 60 claude -p "" --model "$BOGUS" --output-format json </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "Input must be provided" "$(cat "$W/e")" \
    && ok "空 prompt 在解析层被拒（rc=$rc）" || no "空 prompt 的处理已变（rc=$rc）：$(head -c 120 "$W/e")"
  (cd "$NONGIT" && CLAUDE_CONFIG_DIR="$NOCC" timeout 60 claude -p hi --permission-mode bogusMode --model "$BOGUS" </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "bypassPermissions" "$(cat "$W/e")" \
    && ok "--permission-mode 的 choices 在解析层校验，仍含 bypassPermissions（rc=$rc）" || no "--permission-mode 的 choices 校验已变（rc=$rc）：$(head -c 160 "$W/e")"

fi
if selected codex; then
  echo "== Codex：flag 面"
  H=$(codex exec --help 2>&1)
  for f in "--skip-git-repo-check" "--sandbox" "--json" "--output-last-message"; do
    has "$f" "$H" && ok "codex exec --help 有 $f" || no "codex exec --help 缺 $f"
  done
  H=$(codex exec resume --help 2>&1)
  for f in "--skip-git-repo-check" "--json" "--output-last-message"; do
    has "$f" "$H" && ok "codex exec resume --help 有 $f" || no "codex exec resume --help 缺 $f"
  done
  has "--sandbox" "$H" && no "codex exec resume 现在有 --sandbox 了（契约说它放 resume 之前）" || ok "codex exec resume 仍无 --sandbox"
  H=$(codex review --help 2>&1)
  has "--json" "$H" && no "codex review 现在有 --json 了（契约说它没有）" || ok "codex review 仍无 --json"
  has "--output-last-message" "$H" && no "codex review 现在有 -o 了" || ok "codex review 仍无 -o"
  H=$(codex exec review --help 2>&1)
  for f in "--json" "--output-last-message" "--uncommitted" "--base" "--commit"; do
    has "$f" "$H" && ok "codex exec review --help 有 $f" || no "codex exec review --help 缺 $f"
  done

  echo "== Codex：解析层拒绝（CODEX_HOME 无凭证，fail-closed）"
  (cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --json "noop" </dev/null >/dev/null 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
    && ok "非 git 目录 exec 仍要求 --skip-git-repo-check（rc=$rc）" || no "非 git 目录 exec 不再拒绝启动（rc=$rc）"
  (cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec resume --json 00000000-0000-0000-0000-000000000000 "noop" </dev/null >/dev/null 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
    && ok "非 git 目录 exec resume 同样要求 --skip-git-repo-check（rc=$rc）" || no "exec resume 不再受 git 门禁（rc=$rc）"
  CODEX_HOME="$NOAUTH" codex exec resume --sandbox read-only --json 00000000-0000-0000-0000-000000000000 "noop" </dev/null >/dev/null 2>"$W/e"
  rc=$?
  [ "$rc" -eq 2 ] && has "unexpected argument '--sandbox'" "$(cat "$W/e")" \
    && ok "resume 之后的 --sandbox 仍被拒（rc=2）" || no "resume 之后的 --sandbox 不再被拒（rc=$rc）"
  (cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --sandbox read-only review --uncommitted --json </dev/null >/dev/null 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
    && ok "--sandbox 放在 review 之前可解析，review 也受 git 门禁（rc=$rc）" || no "--sandbox … review 解析或门禁行为已变（rc=$rc）"
  CODEX_HOME="$NOAUTH" codex exec review --sandbox read-only --json </dev/null >/dev/null 2>"$W/e"
  rc=$?
  [ "$rc" -eq 2 ] && has "unexpected argument '--sandbox'" "$(cat "$W/e")" \
    && ok "review 之后的 --sandbox 仍被拒（rc=2）" || no "review 之后的 --sandbox 不再被拒（rc=$rc）"
  CODEX_HOME="$NOAUTH" codex exec review --uncommitted --json "prompt" </dev/null >/dev/null 2>"$W/e"
  rc=$?
  [ "$rc" -eq 2 ] && has "cannot be used with" "$(cat "$W/e")" \
    && ok "--uncommitted 与自定义 prompt 仍互斥（rc=2）" || no "--uncommitted 与 prompt 不再互斥（rc=$rc）"
  # 契约：非 TTY 且未关闭的 stdin 让 exec 一直等（读附加 prompt 直到 EOF）；</dev/null 才放行启动
  (cd "$NONGIT" && sleep 8 | CODEX_HOME="$NOAUTH" timeout 5 codex exec --skip-git-repo-check --json "noop" >/dev/null 2>"$W/e")
  rc=$?
  [ "$rc" -eq 124 ] && has "Reading additional" "$(cat "$W/e")" \
    && ok "未关闭的非 TTY stdin：exec 等待到 timeout（rc=124，stderr 报 Reading additional）" || no "非 TTY stdin 的等待行为已变（rc=$rc）：$(head -c 120 "$W/e")"
  (cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --skip-git-repo-check --json "- item" </dev/null >/dev/null 2>"$W/e")
  rc=$?
  [ "$rc" -eq 2 ] && has "unexpected argument" "$(cat "$W/e")" \
    && ok "没有 -- 时以 - 开头的 brief 是 unexpected argument（rc=2）——契约要求 --" || no "以 - 开头的 brief 不再被拒（rc=$rc）"
  (cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 90 codex exec --skip-git-repo-check --json -- "- item" </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 124 ] && [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ] && has '"turn.failed"' "$(cat "$W/o")" && has "401" "$(cat "$W/e")" \
    && ok "-- 之后以 - 开头的 brief 过解析；</dev/null 放行启动；无凭证失败写进 stdout（turn.failed）与 stderr（401，rc=$rc）" \
    || no "-- 形式、</dev/null 放行或无凭证失败的输出归属已变（rc=$rc）"
  (cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 90 codex exec --skip-git-repo-check --json "" </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  has '"thread.started"' "$(cat "$W/o")" \
    && ok "空 prompt 不被拒，真的开启一个 turn（rc=$rc）——契约要求派发前检查 brief 非空" || no "空 prompt 的处理已变（rc=$rc）：$(head -c 120 "$W/o")"
  CODEX_HOME="$NOAUTH" timeout 60 codex exec --sandbox read-only resume --skip-git-repo-check --json -o "$W/last.txt" -- 00000000-0000-0000-0000-000000000000 "- item" </dev/null >/dev/null 2>"$W/e"
  rc=$?
  [ "$rc" -ne 2 ] && has "no rollout found" "$(cat "$W/e")" \
    && ok "契约的 resume 形态（--sandbox 在 resume 之前、-- 在 thread id 之前）可解析，止于 thread 不存在（rc=$rc）" || no "契约的 resume 形态不再可解析（rc=$rc）：$(tail -c 160 "$W/e")"
  (cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --sandbox read-only review --json -o "$W/last.txt" -- "- item" </dev/null >/dev/null 2>"$W/e")
  rc=$?
  [ "$rc" -ne 2 ] && ! has "unexpected argument" "$(cat "$W/e")" \
    && ok "契约的 review 自定义 prompt 形态（-- 在 brief 之前）可解析（rc=$rc）" || no "review 的 -- 形态不再可解析（rc=$rc）：$(tail -c 160 "$W/e")"
  # 守护进程会话续跑脚本：零模型调用，只走 initialize 与 thread/loaded/list；本机没有守护进程时跳过
  DAEMON_SOCK="${CODEX_HOME:-$HOME/.codex}/app-server-control/app-server-control.sock"
  printf 'noop\n' >"$W/daemon-brief.md"
  if [ -S "$(readlink -f "$DAEMON_SOCK")" ]; then
    uv run -q --script "$HERE/../scripts/codex_thread_turn.py" 00000000-0000-7000-8000-000000000000 "$W/daemon-brief.md" >"$W/o" 2>"$W/e"
    rc=$?
    [ "$rc" -eq 3 ] && has "use exec resume" "$(cat "$W/e")" \
      && ok "codex_thread_turn.py：守护进程未持有的会话退出 3，指向 exec resume" || no "codex_thread_turn.py 对未持有会话的判定已变（rc=$rc）：$(tail -c 160 "$W/e")"
  else
    echo "  skip 本机没有 Codex app-server 守护进程，跳过 codex_thread_turn.py"
  fi

fi
echo "== 平台：单个 argv 上限"
BIG=$(python3 -c 'print("x"*200000)')
/bin/true "$BIG" 2>/dev/null
rc=$?
FIT=$(python3 -c 'print("x"*131000)')
/bin/true "$FIT" 2>/dev/null
rc2=$?
[ "$rc" -ne 0 ] && [ "$rc2" -eq 0 ] && ok "单个 argv 超过 128 KiB 时 exec 失败（rc=$rc），128 KiB 内放行——契约要求大材料走文件" || no "单个 argv 上限已变（200000B rc=$rc，131000B rc=$rc2）"

if [ "$SMOKE" -eq 1 ]; then
  # smoke 档的断言拆在同目录 live-check-smoke.sh，在本脚本的环境里执行（共用上面的变量、函数与计数）
  # shellcheck source=live-check-smoke.sh
  . "$HERE/live-check-smoke.sh"
fi

echo "== $PASS ok / $FAIL fail"
[ "$FAIL" -eq 0 ]
