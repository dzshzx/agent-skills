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
T=${LIVE_CHECK_TIMEOUT:-300} # 单次真跑上限（秒）
W=$(mktemp -d "${LIVE_CHECK_EVIDENCE_DIR:-${TMPDIR:-/tmp}}/cross-agent-live.XXXXXX")
cleanup() {
  rm -rf "$NOAUTH"
  echo "Evidence: $W"
}
trap cleanup EXIT
NOAUTH="$W/codex-home"
mkdir -p "$NOAUTH"           # 空 CODEX_HOME：无凭证，启动后必 401
BOGUS=bogus-model-live-check # 不存在的模型名：Claude 在 API 调用前失败
NONGIT="$W/nongit"
mkdir -p "$NONGIT"
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
  (cd "$NONGIT" && timeout 60 claude -p "- item" --model "$BOGUS" --output-format json </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "unknown option" "$(cat "$W/e")" \
    && ok "没有 -- 时以 - 开头的 brief 被当作选项拒绝（rc=$rc）——契约要求 --" || no "以 - 开头的 brief 不再被当作选项（rc=$rc）：$(head -c 120 "$W/e")"
  (cd "$NONGIT" && timeout 60 claude -p --model "$BOGUS" --output-format json -- "- item" </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && ! has "unknown option" "$(cat "$W/e")" && py "$W/o" 'd["is_error"] is True' \
    && ok "-- 之后以 - 开头的 brief 过解析；启动失败写进 stdout 的 JSON（is_error=true，rc=$rc）" || no "-- 形式或启动失败的 JSON 形状已变（rc=$rc）：$(head -c 120 "$W/e")"
  (cd "$NONGIT" && timeout 60 claude -p "" --model "$BOGUS" --output-format json </dev/null >"$W/o" 2>"$W/e")
  rc=$?
  [ "$rc" -ne 0 ] && has "Input must be provided" "$(cat "$W/e")" \
    && ok "空 prompt 在解析层被拒（rc=$rc）" || no "空 prompt 的处理已变（rc=$rc）：$(head -c 120 "$W/e")"
  (cd "$NONGIT" && timeout 60 claude -p hi --permission-mode bogusMode --model "$BOGUS" </dev/null >"$W/o" 2>"$W/e")
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
  E="$W/stderr"       # 每次真跑的 stderr；no() 失败时附其尾巴
  CM="--model sonnet" # 默认模型 Fable 5 的 API 安全层会间歇性整轮拒绝这类探针式 prompt（api_error）；契约测的是 CLI，不是模型
  S="$W/a"
  mkdir -p "$S" # 目录名不用 claude：实测 cwd basename 为 claude 时会被 API 安全层误拦
  # jerr <json>：失败归因——Claude 的错误进 JSON 而非 stderr，打印 terminal_reason 与 result 头
  jerr() { python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("terminal_reason"),"|",str(d.get("result"))[:160])' "$1" 2>&1 | head -c 200; }
  # 契约（SKILL.md）：brief 写进文件、以 -- "$(cat "$BRIEF")" 作单个 argv 传入（首行以 - 开头），shell 敏感片段原样到达。两家各跑一次。
  # 用中性 token（echo tick / echo dollar）：whoami / pwned 这类探针措辞会被 OpenAI 的 API 安全层整轮拒绝（见 codex.md）
  HB="$W/hostile.md"
  cat >"$HB" <<'EOF'
- Reply with exactly the text on the line between the two marker lines, byte for byte, with no code fence and nothing else.
<<<
tick `echo tick` dollar $(echo dollar) quote "dq" 'sq' backslash \n marker-7f3a
>>>
EOF
  # intact <textfile>：brief 里每个 shell 敏感片段都原样出现在答复里
  intact() {
    python3 - "$1" <<'PY'
import sys
t=open(sys.argv[1]).read()
need=["`echo tick`","$(echo dollar)",'"dq"',"'sq'","\\n","marker-7f3a"]
sys.exit(0 if all(x in t for x in need) else 1)
PY
  }
  if selected claude; then
    echo "== smoke：Claude（真跑）"
    (cd "$S" && timeout "$T" claude -p --output-format json --permission-mode acceptEdits $CM -- "Remember this word and nothing else: pineapple. Reply with exactly: noted" </dev/null >"$S/1.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && py "$S/1.json" 'd["is_error"] is False and "noted" in d["result"] and d["session_id"] and isinstance(d["permission_denials"], list)' \
      && ok "成功运行：rc=0，.is_error=false，.result/.session_id/.permission_denials 在位" \
      || no "成功运行的 JSON 形状已变（rc=$rc）：$(jerr "$S/1.json")"
    SID=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$S/1.json" 2>/dev/null)
    (cd "$S" && timeout "$T" claude -p --resume "$SID" --output-format json $CM -- "What word did I ask you to remember? Reply with only that word." </dev/null >"$S/2.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && py "$S/2.json" 'd["is_error"] is False and "pineapple" in d["result"]' \
      && ok "--resume 续跑成功且能回忆上一轮" || no "--resume 续跑失败或失忆（rc=$rc）：$(jerr "$S/2.json")"
    (cd "$S" && timeout "$T" claude -p --model "$BOGUS" --output-format json -- "Reply with exactly: OK" </dev/null >"$S/3.json" 2>"$E")
    rc=$?
    [ "$rc" -ne 0 ] && py "$S/3.json" 'd["is_error"] is True and d["subtype"] == "success" and d.get("terminal_reason")' \
      && ok "失败运行：rc≠0，.is_error=true，.terminal_reason 在位，而 .subtype 仍是 success" || no "失败运行的 JSON 形状已变（rc=$rc）"
    F="$S/deny.txt"
    (cd "$S" && timeout "$T" claude -p --permission-mode dontAsk --output-format json $CM -- "Use the Write tool to create $F containing hi." </dev/null >"$S/4.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/4.json" 'd["is_error"] is False and len(d["permission_denials"]) > 0 and d["permission_denials"][0].get("tool_name")' \
      && ok "dontAsk：运行成功，Write 被拒且记入 .permission_denials（本机 allow 规则未放行 Write）" || no "dontAsk 断言失败（rc=$rc，文件$([ -f "$F" ] && echo 已产生 || echo 未产生)）"
    F="$S/notool.txt"
    # 只看「文件不存在」会把启动失败也算作绿：要求 rc=0、JSON 非错误，且模型自报 NO-WRITE 作为它确实尝试过的证据
    (cd "$S" && timeout "$T" claude -p --tools Read,Grep,Glob --output-format json $CM -- "Use the Write tool to create $F containing hi. If you cannot, reply with exactly: NO-WRITE" </dev/null >"$S/5.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/5.json" 'd["is_error"] is False and "NO-WRITE" in d["result"]' \
      && ok "--tools Read,Grep,Glob：运行成功，Write 工具不存在，文件未产生，模型自报 NO-WRITE" || no "--tools 白名单断言失败（rc=$rc，文件$([ -f "$F" ] && echo 已产生 || echo 未产生)）"
    # 契约：acceptEdits 只放行编辑；-p 无法弹窗，Bash 被拒并记入 .permission_denials；--allowedTools 'Bash(<cmd>:*)' 逐条放行
    BASHP="Run this exact shell command with the Bash tool: python3 -c 'print(6*7)' . Reply with only the command's output. If the tool call is denied, reply with exactly: DENIED"
    (cd "$S" && timeout "$T" claude -p --permission-mode acceptEdits --output-format json $CM -- "$BASHP" </dev/null >"$S/6.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && py "$S/6.json" 'd["is_error"] is False and "DENIED" in d["result"] and d["permission_denials"] and d["permission_denials"][0].get("tool_name") == "Bash"' \
      && ok "acceptEdits：Bash 被自动拒绝并记入 .permission_denials（tool_name=Bash）" || no "acceptEdits 下 Bash 的拒绝行为已变（rc=$rc）：$(jerr "$S/6.json")"
    (cd "$S" && timeout "$T" claude -p --permission-mode acceptEdits --allowedTools 'Bash(python3:*)' --output-format json $CM -- "$BASHP" </dev/null >"$S/7.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && py "$S/7.json" 'd["is_error"] is False and "42" in d["result"] and d["permission_denials"] == []' \
      && ok "acceptEdits + --allowedTools 'Bash(python3:*)'：命令放行，输出 42，无拒绝记录" || no "--allowedTools 放行断言失败（rc=$rc）：$(jerr "$S/7.json")"
    # 行为：bypassPermissions 下 Bash 放行、无拒绝记录。这里只核对该模式的行为，不是派发时的选择依据：
    #   无法枚举命令不构成使用 bypassPermissions 的授权，更宽权限须有覆盖该范围的授权（见 references/claude.md）。
    (cd "$S" && timeout "$T" claude -p --permission-mode bypassPermissions --output-format json $CM -- "$BASHP" </dev/null >"$S/7b.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && py "$S/7b.json" 'd["is_error"] is False and "42" in d["result"] and d["permission_denials"] == []' \
      && ok "bypassPermissions：Bash 放行，输出 42，无拒绝记录" || no "bypassPermissions 断言失败（rc=$rc）：$(jerr "$S/7b.json")"
    # 契约：--resume 恢复对话不恢复姿态。--settings 把本次 defaultMode 钉为 acceptEdits，断言不依赖本机 settings。
    #   行为面：dontAsk 会话裸续跑 → 写成功。姿态面用 init 事件确定判定（见下），不经模型意愿。
    ACC='{"permissions":{"defaultMode":"acceptEdits"}}'
    SID4=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$S/4.json" 2>/dev/null)
    F="$S/r1.txt"
    (cd "$S" && timeout "$T" claude -p --resume "$SID4" --settings "$ACC" --output-format json $CM -- "Use the Write tool to create $F containing hi. If the tool call is denied, reply with exactly: DENIED" </dev/null >"$S/8.json" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && [ -f "$F" ] && py "$S/8.json" 'd["is_error"] is False and d["permission_denials"] == []' \
      && ok "dontAsk 会话裸 --resume：写成功——权限模式不随会话恢复" || no "dontAsk 会话裸 --resume 的行为已变（rc=$rc，文件$([ -f "$F" ] && echo 已产生 || echo 未产生)）：$(jerr "$S/8.json")"
    # 契约：stream-json --verbose 首条 system/init 事件带 permissionMode 与 tools，是本次运行实际拿到的姿态。
    # init <jsonl> <expr>：对 init 事件求值，expr 里 e 为该事件；没有 init 事件即失败
    init() { python3 -c '
import json,sys
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("type")=="system" and e.get("subtype")=="init": sys.exit(0 if eval(sys.argv[2]) else 1)
sys.exit(1)' "$1" "$2" 2>/dev/null; }
    (cd "$S" && timeout "$T" claude -p --tools Read,Grep,Glob --permission-mode dontAsk --strict-mcp-config --output-format stream-json --verbose $CM -- "Reply with exactly: OK" </dev/null >"$S/9.jsonl" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && init "$S/9.jsonl" 'e["permissionMode"]=="dontAsk" and sorted(e["tools"])==["Glob","Grep","Read"] and e["mcp_servers"]==[]' \
      && ok "init 事件：--tools Read,Grep,Glob --strict-mcp-config --permission-mode dontAsk → tools 恰为三个、无 MCP、dontAsk" || no "init 事件的 tools/permissionMode/mcp_servers 形状已变（rc=$rc）"
    SID9=$(python3 -c '
import json,sys
for line in open(sys.argv[1]):
    e=json.loads(line)
    if e.get("type")=="system" and e.get("subtype")=="init": print(e["session_id"]); break' "$S/9.jsonl" 2>/dev/null)
    (cd "$S" && timeout "$T" claude -p --resume "$SID9" --settings "$ACC" --output-format stream-json --verbose $CM -- "Reply with exactly: OK" </dev/null >"$S/10.jsonl" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && init "$S/10.jsonl" 'e["permissionMode"]=="acceptEdits" and "Write" in e["tools"]' \
      && ok "裸 --resume 的 init 事件：permissionMode 落回默认（此处钉为 acceptEdits）、Write 回到 tools——姿态不随会话恢复" || no "裸 --resume 的姿态行为已变（rc=$rc）"
    (cd "$S" && timeout "$T" claude -p --resume "$SID9" --tools Read,Grep,Glob --permission-mode dontAsk --strict-mcp-config --output-format stream-json --verbose $CM -- "Reply with exactly: OK" </dev/null >"$S/11.jsonl" 2>"$E")
    rc=$?
    [ "$rc" -eq 0 ] && init "$S/11.jsonl" 'e["permissionMode"]=="dontAsk" and "Write" not in e["tools"] and e["mcp_servers"]==[]' \
      && ok "--resume 重传三个 flag 的 init 事件：dontAsk、无 Write、无 MCP——姿态要每次续跑重传" || no "--resume 重传 flag 未生效（rc=$rc）"
    (cd "$S" && timeout "$T" claude -p --output-format json $CM -- "$(cat "$HB")" </dev/null >"$S/12.json" 2>"$E")
    rc=$?
    python3 -c 'import json,sys;open(sys.argv[2],"w").write(str(json.load(open(sys.argv[1])).get("result","")))' "$S/12.json" "$S/12.txt" 2>/dev/null
    [ "$rc" -eq 0 ] && intact "$S/12.txt" \
      && ok '-- "$(cat "$BRIEF")"：首行以 - 开头、含反引号、$()、引号与 \n 的 brief 原样到达（.result）' || no "brief 经 argv 传递被改写或展开（rc=$rc）：$(head -c 120 "$S/12.txt" 2>/dev/null)"

  fi
  if selected codex; then
    echo "== smoke：Codex（真跑）"
    C="$W/b"
    mkdir -p "$C"
    # cx <dir> <stdout-file> <codex args…>：在 dir 里跑一次 codex（timeout、</dev/null、stderr→$E）；API 安全层整轮拒绝时
    #   按契约重新派发，最多两次；仍拒才把失败交给断言
    cx() {
      local dir=$1 out=$2 n arg previous='' final=''
      shift 2
      for arg in "$@"; do
        if [ "$previous" = -o ]; then final=$arg; fi
        previous=$arg
      done
      for n in 1 2 3; do
        E="$out.stderr"
        printf '%s\n' "$@" >"$out.argv"
        (cd "$dir" && timeout "$T" "$@" </dev/null >"$out" 2>"$E")
        rc=$?
        printf '%s\n' "$rc" >"$out.rc"
        if ! grep -q 'flagged for possible cybersecurity risk' "$out" "$E" 2>/dev/null; then
          [ "$rc" -eq 0 ] || return "$rc"
          if has --json "$*"; then uv run --locked --project "$HERE/../../.." python "$HERE/check_codex_run.py" "$out" "$rc" "$final" || return 1; fi
          return "$rc"
        fi
        cp "$out" "$out.attempt-$n"
        cp "$E" "$E.attempt-$n"
        [ "$n" -lt 3 ] && {
          echo "       (API 安全层整轮拒绝，第 $n 次；按契约重新派发)"
          sleep 5
        }
      done
      # 持续失败事件即失败，即使 CLI 异常返回 0 也不能绕过成功校验。
      [ "$rc" -eq 0 ] && return 1
      return "$rc"
    }
    # cerr <jsonl>：失败归因——Codex 的 turn.failed / error 消息在 stdout 事件流里，不在 stderr
    cerr() { python3 -c '
import json,sys
msg=""
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("type")=="turn.failed": msg=(e.get("error") or {}).get("message") or msg
    elif e.get("type")=="error": msg=e.get("message") or msg
print(msg[:160] if msg else "(无 turn.failed；见 stderr)")' "$1" 2>/dev/null; }
    cx "$C" "$C/1.jsonl" codex exec --skip-git-repo-check --sandbox read-only --json -o "$C/1.txt" -- "Reply with exactly: OK"
    rc=$?
    # codex_parse <jsonl> <last.txt>：两行输出——thread.started.thread_id；agent_message 的 text 是否含 OK 且与 -o 文件整段一致（same/diff）
    codex_parse() {
      python3 - "$1" "$2" <<'PY'
import json,sys
tid=msg=None
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("type")=="thread.started": tid=e.get("thread_id")
    if e.get("type")=="item.completed" and e.get("item",{}).get("type")=="agent_message": msg=e["item"].get("text")
last=open(sys.argv[2]).read() if msg is not None else ""
print(tid or ""); print("same" if msg is not None and "OK" in msg and msg.strip()==last.strip() else "diff")
PY
    }
    {
      read -r TID
      read -r SAME
    } < <(codex_parse "$C/1.jsonl" "$C/1.txt")
    [ "$rc" -eq 0 ] && [ -n "$TID" ] && [ "$SAME" = same ] \
      && ok "--json：thread.started.thread_id 与 item.completed/agent_message.text 在位，-o 内容等于该 text" || no "--json/-o 的输出契约已变（rc=$rc）：$(cerr "$C/1.jsonl")"
    cx "$C" "$C/2.jsonl" codex exec --sandbox read-only resume --skip-git-repo-check --json -o "$C/2.txt" -- "$TID" "Reply with exactly: OK2"
    rc=$?
    [ "$rc" -eq 0 ] && has '"agent_message"' "$(cat "$C/2.jsonl")" && [ -s "$C/2.txt" ] \
      && ok "exec --sandbox read-only resume -- <thread_id> 续跑成功（契约形态），-o 每次都要重新给" || no "exec resume 续跑失败（rc=$rc）：$(cerr "$C/2.jsonl")"
    cx "$C" "$C/2b.txt" codex exec --sandbox read-only resume --skip-git-repo-check -- "$TID" "Reply with exactly: OK3"
    rc=$?
    [ "$rc" -eq 0 ] && [ -s "$C/2b.txt" ] && [ "$(head -c 1 "$C/2b.txt")" != "{" ] \
      && ok "resume 不带 --json/-o 时输出纯文本（两 flag 确为 per-invocation）" || no "resume 无 flag 的输出形态已变（rc=$rc）"
    R="$W/repo"
    mkdir -p "$R"
    (cd "$R" && git init -q -b master && printf 'a\n' >f.txt && git add f.txt && git -c user.name=lc -c user.email=lc@x commit -qm init && printf 'b\n' >>f.txt)
    RE="$W/review" # 证据放在被审查仓之外：写进仓里会成为 --uncommitted 的审查对象
    mkdir -p "$RE"
    cx "$R" "$RE/3.jsonl" codex exec --sandbox read-only review --uncommitted --json -o "$RE/3.txt"
    rc=$?
    [ "$rc" -eq 0 ] && [ -s "$RE/3.txt" ] && ok "exec --sandbox read-only review --uncommitted --json -o 可跑" || no "review --uncommitted 形式失败（rc=$rc）：$(cerr "$RE/3.jsonl")"
    cx "$R" "$RE/4.jsonl" codex exec --sandbox read-only review --json -o "$RE/4.txt" -- "Review the working tree change to f.txt in one sentence."
    rc=$?
    [ "$rc" -eq 0 ] && [ -s "$RE/4.txt" ] && ok "exec --sandbox read-only review --json -o <prompt> 可跑" || no "review 自定义 prompt 形式失败（rc=$rc）：$(cerr "$RE/4.jsonl")"
    P="$W/perm"
    mkdir -p "$P"
    cx "$P" "$P/ro.jsonl" codex exec --skip-git-repo-check --sandbox read-only --json -o "$P/ro-final.txt" -- "Write a text file at $P/ro.txt whose content is the word hi, then confirm in one sentence."
    rc=$?
    [ "$rc" -eq 0 ] && [ ! -f "$P/ro.txt" ] \
      && uv run --locked --project "$HERE/../../.." python "$HERE/check_codex_run.py" --posture "$P/ro.jsonl" read-only \
      && ok "read-only：运行成功且文件未产生；此断言不证明 OS 拒写" || no "read-only 下产生了文件或运行异常（rc=$rc）：$(cerr "$P/ro.jsonl")"
    cx "$P" "$P/rw.jsonl" codex exec --skip-git-repo-check --sandbox workspace-write --json -o "$P/rw-final.txt" -- "Write a text file at $P/rw.txt whose content is the word hi, then confirm in one sentence."
    rc=$?
    [ "$rc" -eq 0 ] && [ -f "$P/rw.txt" ] && [ "$(cat "$P/rw.txt")" = hi ] && ok "workspace-write：运行成功且文件内容为 hi" || no "workspace-write 下写未生效（rc=$rc）：$(cerr "$P/rw.jsonl")"
    # 独立本机命令确保确实尝试写入；模型未尝试不作为 OS 拒写证据。
    codex sandbox -c 'sandbox_mode="read-only"' -- python3 -c 'import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("hi")' "$P/os-denied.txt" >"$P/os.stdout" 2>"$P/os.stderr"
    os_rc=$?
    printf '%s\n' "$os_rc" >"$P/os.rc"
    [ "$os_rc" -ne 0 ] && [ ! -e "$P/os-denied.txt" ] && grep -Eq 'PermissionError:|Read-only file system' "$P/os.stderr" \
      && ok "本机 sandbox 命令尝试写入且收到 OS 拒写错误" || no "本机 sandbox OS 拒写证据不足（rc=$os_rc）"
    cx "$C" "$C/h.jsonl" codex exec --skip-git-repo-check --sandbox read-only --json -o "$C/h.txt" -- "$(cat "$HB")"
    rc=$?
    [ "$rc" -eq 0 ] && intact "$C/h.txt" \
      && ok '-- "$(cat "$BRIEF")"：首行以 - 开头、含反引号、$()、引号与 \n 的 brief 原样到达（-o 文本）' || no "brief 经 argv 传递被改写或展开（rc=$rc）：$(cerr "$C/h.jsonl") | $(head -c 120 "$C/h.txt" 2>/dev/null)"

  fi
fi

echo "== $PASS ok / $FAIL fail"
[ "$FAIL" -eq 0 ]
