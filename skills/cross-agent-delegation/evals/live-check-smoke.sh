# shellcheck shell=bash
# live-check.sh 的 --smoke 档（真跑、计费）：只由 live-check.sh 在 --smoke 时 source，不单独运行。
# 用到的变量与函数（W、HERE、CCD、BOGUS、DAEMON_SOCK、ok/no/has/py/selected）由 live-check.sh 定义，
# 计数 PASS/FAIL 与 rc 也沿用它的全局变量；各断言的说明见 live-check.sh 头注释。
# shellcheck disable=SC2154 # 上述变量在 live-check.sh 里赋值
T=${LIVE_CHECK_TIMEOUT:-300} # 单次真跑上限（秒）
E="$W/stderr"                # 每次真跑的 stderr；no() 失败时附其尾巴
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
  CRED="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json"
  mkdir -p "$CCD"
  [ -f "$CRED" ] && cp "$CRED" "$CCD/" || no "缺少 $CRED，无法在隔离的 CLAUDE_CONFIG_DIR 里认证"
  export CLAUDE_CONFIG_DIR="$CCD"
  (cd "$S" && timeout "$T" claude -p --output-format json --permission-mode acceptEdits -- "Remember this word and nothing else: pineapple. Reply with exactly: noted" </dev/null >"$S/1.json" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && py "$S/1.json" 'd["is_error"] is False and "noted" in d["result"] and d["session_id"] and isinstance(d["permission_denials"], list)' \
    && ok "成功运行：rc=0，.is_error=false，.result/.session_id/.permission_denials 在位" \
    || no "成功运行的 JSON 形状已变（rc=$rc）：$(jerr "$S/1.json")"
  SID=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$S/1.json" 2>/dev/null)
  [ -n "$SID" ] && compgen -G "$CCD/projects/*/$SID.jsonl" >/dev/null \
    && ok "隔离：会话记录落在临时 CLAUDE_CONFIG_DIR" || no "会话记录未落在临时 CLAUDE_CONFIG_DIR（隔离未生效）"
  printf '       model: %s\n' "$(python3 -c 'import json,sys;print(",".join(json.load(open(sys.argv[1])).get("modelUsage",{})))' "$S/1.json" 2>/dev/null)"
  (cd "$S" && timeout "$T" claude -p --resume "$SID" --output-format json -- "What word did I ask you to remember? Reply with only that word." </dev/null >"$S/2.json" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && py "$S/2.json" 'd["is_error"] is False and "pineapple" in d["result"]' \
    && ok "--resume 续跑成功且能回忆上一轮" || no "--resume 续跑失败或失忆（rc=$rc）：$(jerr "$S/2.json")"
  (cd "$S" && timeout "$T" claude -p --model "$BOGUS" --output-format json -- "Reply with exactly: OK" </dev/null >"$S/3.json" 2>"$E")
  rc=$?
  [ "$rc" -ne 0 ] && py "$S/3.json" 'd["is_error"] is True and d["subtype"] == "success" and d.get("terminal_reason")' \
    && ok "失败运行：rc≠0，.is_error=true，.terminal_reason 在位，而 .subtype 仍是 success" || no "失败运行的 JSON 形状已变（rc=$rc）"
  F="$S/deny.txt"
  (cd "$S" && timeout "$T" claude -p --permission-mode dontAsk --output-format json -- "Use the Write tool to create $F containing hi." </dev/null >"$S/4.json" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/4.json" 'd["is_error"] is False and len(d["permission_denials"]) > 0 and d["permission_denials"][0].get("tool_name")' \
    && ok "dontAsk：运行成功，Write 被拒且记入 .permission_denials（隔离配置里没有放行 Write 的 allow 规则）" || no "dontAsk 断言失败（rc=$rc，文件$([ -f "$F" ] && echo 已产生 || echo 未产生)）"
  F="$S/notool.txt"
  # 只看「文件不存在」会把启动失败也算作绿：要求 rc=0、JSON 非错误，且模型自报 NO-WRITE 作为它确实尝试过的证据
  (cd "$S" && timeout "$T" claude -p --tools Read,Grep,Glob --output-format json -- "Use the Write tool to create $F containing hi. If you cannot, reply with exactly: NO-WRITE" </dev/null >"$S/5.json" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/5.json" 'd["is_error"] is False and "NO-WRITE" in d["result"]' \
    && ok "--tools Read,Grep,Glob：运行成功，Write 工具不存在，文件未产生，模型自报 NO-WRITE" || no "--tools 白名单断言失败（rc=$rc，文件$([ -f "$F" ] && echo 已产生 || echo 未产生)）"
  # 契约：acceptEdits 只放行编辑；-p 无法弹窗，Bash 被拒并记入 .permission_denials；--allowedTools 'Bash(<cmd>:*)' 逐条放行
  BASHP="Run this exact shell command with the Bash tool: python3 -c 'print(6*7)' . Reply with only the command's output. If the tool call is denied, reply with exactly: DENIED"
  (cd "$S" && timeout "$T" claude -p --permission-mode acceptEdits --output-format json -- "$BASHP" </dev/null >"$S/6.json" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && py "$S/6.json" 'd["is_error"] is False and "DENIED" in d["result"] and d["permission_denials"] and d["permission_denials"][0].get("tool_name") == "Bash"' \
    && ok "acceptEdits：Bash 被自动拒绝并记入 .permission_denials（tool_name=Bash）" || no "acceptEdits 下 Bash 的拒绝行为已变（rc=$rc）：$(jerr "$S/6.json")"
  (cd "$S" && timeout "$T" claude -p --permission-mode acceptEdits --allowedTools 'Bash(python3:*)' --output-format json -- "$BASHP" </dev/null >"$S/7.json" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && py "$S/7.json" 'd["is_error"] is False and "42" in d["result"] and d["permission_denials"] == []' \
    && ok "acceptEdits + --allowedTools 'Bash(python3:*)'：命令放行，输出 42，无拒绝记录" || no "--allowedTools 放行断言失败（rc=$rc）：$(jerr "$S/7.json")"
  # 行为：bypassPermissions 下 Bash 放行、无拒绝记录。这里只核对该模式的行为，不是派发时的选择依据：
  #   无法枚举命令不构成使用 bypassPermissions 的授权，更宽权限须有覆盖该范围的授权（见 references/claude.md）。
  (cd "$S" && timeout "$T" claude -p --permission-mode bypassPermissions --output-format json -- "$BASHP" </dev/null >"$S/7b.json" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && py "$S/7b.json" 'd["is_error"] is False and "42" in d["result"] and d["permission_denials"] == []' \
    && ok "bypassPermissions：Bash 放行，输出 42，无拒绝记录" || no "bypassPermissions 断言失败（rc=$rc）：$(jerr "$S/7b.json")"
  # 契约：--resume 恢复对话不恢复姿态。--settings 把本次 defaultMode 钉为 acceptEdits，断言不依赖本机 settings。
  #   行为面：dontAsk 会话裸续跑 → 写成功。姿态面用 init 事件确定判定（见下），不经模型意愿。
  ACC='{"permissions":{"defaultMode":"acceptEdits"}}'
  SID4=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$S/4.json" 2>/dev/null)
  F="$S/r1.txt"
  (cd "$S" && timeout "$T" claude -p --resume "$SID4" --settings "$ACC" --output-format json -- "Use the Write tool to create $F containing hi. If the tool call is denied, reply with exactly: DENIED" </dev/null >"$S/8.json" 2>"$E")
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
  (cd "$S" && timeout "$T" claude -p --tools Read,Grep,Glob --permission-mode dontAsk --strict-mcp-config --output-format stream-json --verbose -- "Reply with exactly: OK" </dev/null >"$S/9.jsonl" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && init "$S/9.jsonl" 'e["permissionMode"]=="dontAsk" and sorted(e["tools"])==["Glob","Grep","Read"] and e["mcp_servers"]==[]' \
    && ok "init 事件：--tools Read,Grep,Glob --strict-mcp-config --permission-mode dontAsk → tools 恰为三个、无 MCP、dontAsk" || no "init 事件的 tools/permissionMode/mcp_servers 形状已变（rc=$rc）"
  SID9=$(python3 -c '
import json,sys
for line in open(sys.argv[1]):
    e=json.loads(line)
    if e.get("type")=="system" and e.get("subtype")=="init": print(e["session_id"]); break' "$S/9.jsonl" 2>/dev/null)
  (cd "$S" && timeout "$T" claude -p --resume "$SID9" --settings "$ACC" --output-format stream-json --verbose -- "Reply with exactly: OK" </dev/null >"$S/10.jsonl" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && init "$S/10.jsonl" 'e["permissionMode"]=="acceptEdits" and "Write" in e["tools"]' \
    && ok "裸 --resume 的 init 事件：permissionMode 落回默认（此处钉为 acceptEdits）、Write 回到 tools——姿态不随会话恢复" || no "裸 --resume 的姿态行为已变（rc=$rc）"
  (cd "$S" && timeout "$T" claude -p --resume "$SID9" --tools Read,Grep,Glob --permission-mode dontAsk --strict-mcp-config --output-format stream-json --verbose -- "Reply with exactly: OK" </dev/null >"$S/11.jsonl" 2>"$E")
  rc=$?
  [ "$rc" -eq 0 ] && init "$S/11.jsonl" 'e["permissionMode"]=="dontAsk" and "Write" not in e["tools"] and e["mcp_servers"]==[]' \
    && ok "--resume 重传三个 flag 的 init 事件：dontAsk、无 Write、无 MCP——姿态要每次续跑重传" || no "--resume 重传 flag 未生效（rc=$rc）"
  (cd "$S" && timeout "$T" claude -p --output-format json -- "$(cat "$HB")" </dev/null >"$S/12.json" 2>"$E")
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
  # 守护进程持有的会话：exec resume 被写者锁拒绝，codex_thread_turn.py 经 socket 续跑；测试会话用完归档
  if [ -S "$(readlink -f "$DAEMON_SOCK")" ]; then
    D="$W/daemon"
    mkdir -p "$D"
    timeout "$T" uv run -q --script "$HERE/codex_daemon_thread.py" start "$D" "$D/id" >/dev/null 2>"$D/start.err"
    rc=$?
    DTID=$(cat "$D/id" 2>/dev/null)
    if [ "$rc" -eq 0 ] && [ -n "$DTID" ]; then
      (cd "$D" && timeout 120 codex exec --sandbox read-only resume --skip-git-repo-check --json -- "$DTID" "Reply with exactly: OK" </dev/null >"$D/resume.jsonl" 2>"$D/resume.err")
      rc=$?
      [ "$rc" -eq 1 ] && has "already has an active writer" "$(cat "$D/resume.err")" \
        && ok "守护进程持有的会话：exec resume 在模型调用前报 active writer（rc=1）" || no "守护进程持有会话时 exec resume 的行为已变（rc=$rc）：$(tail -c 160 "$D/resume.err")"
      printf 'Reply with exactly: OK-DAEMON\n' >"$D/brief.md"
      uv run -q --script "$HERE/../scripts/codex_thread_turn.py" "$DTID" "$D/brief.md" --wait --timeout "$T" >"$D/turn.out" 2>"$D/turn.err"
      rc=$?
      [ "$rc" -eq 0 ] && has OK-DAEMON "$(cat "$D/turn.out")" \
        && ok "codex_thread_turn.py --wait：经守护进程续跑并输出最终答复" || no "codex_thread_turn.py 续跑失败（rc=$rc）：$(tail -c 160 "$D/turn.err")"
      uv run -q --script "$HERE/codex_daemon_thread.py" archive "$DTID" >/dev/null 2>"$D/archive.err" \
        && : >"$D/archived" || no "测试会话 $DTID 归档失败：$(tail -c 160 "$D/archive.err")"
    else
      no "无法在守护进程里创建测试会话（rc=$rc）：$(tail -c 160 "$D/start.err")"
    fi
  else
    echo "  skip 本机没有 Codex app-server 守护进程，跳过守护进程会话续跑"
  fi

fi
