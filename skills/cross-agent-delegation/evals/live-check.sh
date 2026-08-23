#!/usr/bin/env bash
# 回归检测：核对 SKILL.md 与 references/*.md 缓存的三家 CLI 契约是否仍与本机实装一致。
# 用法：bash evals/live-check.sh [--smoke]
#   默认档（surface + parser）：--help 是否仍列出所用 flag；参数解析层的拒绝是否仍成立。
#     零模型调用且 fail-closed：会真启动的命令都跑在无凭证的 CODEX_HOME / 不存在的 Kimi 模型下，
#     契约一旦失效（原本该被拒的命令被接受）会在 401 / 模型解析处失败，而不是悄悄花一次调用。
#   --smoke：真跑约 13 次小调用（计费；三家凭证都要在位，缺一家该家整段红），解析 JSON 并断言
#     字段、退出码、续跑与权限行为。FAIL 行下附 stderr 尾巴，用来区分「行为断言失败」与「调用本身失败
#     （401 / 限流 / 网络）」——后者不是契约失效。
#   绿灯只证明下面逐条断言的行为；没断言的东西它什么都不证明。
set -u
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
no(){ FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; [ -s "${E:-}" ] && printf '       stderr: %s\n' "$(tail -c 200 "$E" | tr '\n' ' ')"; }
has(){ printf '%s' "$2" | grep -qF -- "$1"; }
T=300                                   # 单次真跑上限（秒）
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
NOAUTH="$W/codex-home"; mkdir -p "$NOAUTH"   # 空 CODEX_HOME：无凭证，启动后必 401
BOGUS=bogus-model-live-check                 # 不存在的 Kimi 模型别名：到模型解析即失败
NONGIT="$W/nongit"; mkdir -p "$NONGIT"
# py <file> <expr>：对 JSON 文件求值；<expr> 里用 d 表示解析结果，结果为真则退出 0
py(){ python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if eval(sys.argv[2]) else 1)' "$1" "$2" 2>/dev/null; }

for c in claude codex kimi; do
  command -v "$c" >/dev/null 2>&1 || { echo "缺少 $c，无法检测"; exit 2; }
done

echo "== 版本（契约建立于 Claude 2.1.241 / Codex 0.149.0 / Kimi 0.38.0）"
printf '  claude %s\n  codex  %s\n  kimi   %s\n' \
  "$(claude --version 2>/dev/null)" "$(codex --version 2>/dev/null)" "$(kimi --version 2>/dev/null)"
echo "  契约是否成立由下面的断言决定，不由版本号决定。"

echo "== Claude：flag 面"
H=$(claude --help 2>&1)
for f in " -p, --print" "--output-format" "--permission-mode" "--allowedTools" "--tools" "--resume"; do
  has "$f" "$H" && ok "claude --help 有 $f" || no "claude --help 缺 $f"
done
for m in dontAsk acceptEdits; do
  has "$m" "$H" && ok "--permission-mode 仍列出 $m" || no "--permission-mode 不再列出 $m"
done

echo "== Codex：flag 面"
H=$(codex exec --help 2>&1)
for f in "--skip-git-repo-check" "--sandbox" "--json" "--output-last-message"; do
  has "$f" "$H" && ok "codex exec --help 有 $f" || no "codex exec --help 缺 $f"
done
H=$(codex exec resume --help 2>&1)
for f in "--skip-git-repo-check" "--json" "--output-last-message"; do
  has "$f" "$H" && ok "codex exec resume --help 有 $f" || no "codex exec resume --help 缺 $f"
done
H=$(codex review --help 2>&1)
has "--json" "$H" && no "codex review 现在有 --json 了（契约说它没有）" || ok "codex review 仍无 --json"
has "--output-last-message" "$H" && no "codex review 现在有 -o 了" || ok "codex review 仍无 -o"
H=$(codex exec review --help 2>&1)
for f in "--json" "--output-last-message" "--uncommitted" "--base" "--commit"; do
  has "$f" "$H" && ok "codex exec review --help 有 $f" || no "codex exec review --help 缺 $f"
done

echo "== Codex：解析层拒绝（CODEX_HOME 无凭证，fail-closed）"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --json "noop" </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
  && ok "非 git 目录 exec 仍要求 --skip-git-repo-check（rc=$rc）" || no "非 git 目录 exec 不再拒绝启动（rc=$rc）"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec resume --json 00000000-0000-0000-0000-000000000000 "noop" </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
  && ok "非 git 目录 exec resume 同样要求 --skip-git-repo-check（rc=$rc）" || no "exec resume 不再受 git 门禁（rc=$rc）"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --sandbox read-only review --uncommitted --json </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
  && ok "--sandbox 放在 review 之前可解析，review 也受 git 门禁（rc=$rc）" || no "--sandbox … review 解析或门禁行为已变（rc=$rc）"
CODEX_HOME="$NOAUTH" codex exec review --sandbox read-only --json </dev/null >/dev/null 2>"$W/e"; rc=$?
[ "$rc" -eq 2 ] && has "unexpected argument '--sandbox'" "$(cat "$W/e")" \
  && ok "review 之后的 --sandbox 仍被拒（rc=2）" || no "review 之后的 --sandbox 不再被拒（rc=$rc）"
CODEX_HOME="$NOAUTH" codex exec review --uncommitted --json "prompt" </dev/null >/dev/null 2>"$W/e"; rc=$?
[ "$rc" -eq 2 ] && has "cannot be used with" "$(cat "$W/e")" \
  && ok "--uncommitted 与自定义 prompt 仍互斥（rc=2）" || no "--uncommitted 与 prompt 不再互斥（rc=$rc）"

echo "== Kimi：flag 面"
H=$(kimi --help 2>&1)
for f in "-S, --session" "--agent-file" "--output-format" "-p, --prompt"; do
  has "$f" "$H" && ok "kimi --help 有 $f" || no "kimi --help 缺 $f"
done
printf '%s' "$H" | grep -A2 -- '--agent-file' | grep -q 'Cannot be combined with --session' \
  && ok "--agent-file 仍不能与 --session 组合" || no "--agent-file 与 --session 的互斥说明已变"

echo "== Kimi：解析层拒绝（模型别名不存在，fail-closed）"
for f in --auto -y --yolo --plan; do
  ( cd "$NONGIT" && timeout 60 kimi -p noop "$f" -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
  [ "$rc" -ne 0 ] && has "Cannot combine" "$(cat "$W/e")" && [ ! -s "$W/o" ] \
    && ok "kimi -p 仍拒绝 $f，原因在 stderr、stdout 为空（rc=$rc）" || no "kimi -p 对 $f 的拒绝行为已变（rc=$rc）"
done
( cd "$NONGIT" && timeout 60 kimi -p noop -r session_does-not-exist -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "not found" "$(cat "$W/e")" \
  && ok "-r <id> 被当作 session id 解析（不存在即报错，非静默忽略）" || no "-r 的解析行为已变（rc=$rc）：$(head -c 120 "$W/e")"

if [ "${1:-}" = "--smoke" ]; then
  E="$W/stderr"                           # 每次真跑的 stderr；no() 失败时附其尾巴
  CM="--model sonnet"   # 默认模型 Fable 5 的 API 安全层会间歇性整轮拒绝这类探针式 prompt（api_error）；契约测的是 CLI，不是模型
  echo "== smoke：Claude（真跑）"
  S="$W/a"; mkdir -p "$S"   # 目录名不用 claude：实测 cwd basename 为 claude 时会被 API 安全层误拦
  # jerr <json>：失败归因——Claude 的错误进 JSON 而非 stderr，打印 terminal_reason 与 result 头
  jerr(){ python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("terminal_reason"),"|",str(d.get("result"))[:160])' "$1" 2>&1 | head -c 200; }
  ( cd "$S" && timeout "$T" claude -p "Remember this word and nothing else: pineapple. Reply with exactly: noted" --output-format json --permission-mode acceptEdits $CM </dev/null >"$S/1.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && py "$S/1.json" 'd["is_error"] is False and "noted" in d["result"] and d["session_id"] and isinstance(d["permission_denials"], list)' \
    && ok "成功运行：rc=0，.is_error=false，.result/.session_id/.permission_denials 在位" \
    || no "成功运行的 JSON 形状已变（rc=$rc）：$(jerr "$S/1.json")"
  SID=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$S/1.json" 2>/dev/null)
  ( cd "$S" && timeout "$T" claude -p --resume "$SID" "What word did I ask you to remember? Reply with only that word." --output-format json $CM </dev/null >"$S/2.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && py "$S/2.json" 'd["is_error"] is False and "pineapple" in d["result"]' \
    && ok "--resume 续跑成功且能回忆上一轮" || no "--resume 续跑失败或失忆（rc=$rc）：$(jerr "$S/2.json")"
  ( cd "$S" && timeout "$T" claude -p "Reply with exactly: OK" --model "$BOGUS" --output-format json </dev/null >"$S/3.json" 2>"$E" ); rc=$?
  [ "$rc" -ne 0 ] && py "$S/3.json" 'd["is_error"] is True and d["subtype"] == "success" and d.get("terminal_reason")' \
    && ok "失败运行：rc≠0，.is_error=true，.terminal_reason 在位，而 .subtype 仍是 success" || no "失败运行的 JSON 形状已变（rc=$rc）"
  F="$S/deny.txt"
  ( cd "$S" && timeout "$T" claude -p "Use the Write tool to create $F containing hi." --permission-mode dontAsk --output-format json $CM </dev/null >"$S/4.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/4.json" 'd["is_error"] is False and len(d["permission_denials"]) > 0 and d["permission_denials"][0].get("tool_name")' \
    && ok "dontAsk：运行成功，Write 被拒且记入 .permission_denials（本机 allow 规则未放行 Write）" || no "dontAsk 断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)）"
  F="$S/notool.txt"
  # 只看「文件不存在」会把启动失败也算作绿：要求 rc=0、JSON 非错误，且模型自报 NO-WRITE 作为它确实尝试过的证据
  ( cd "$S" && timeout "$T" claude -p "Use the Write tool to create $F containing hi. If you cannot, reply with exactly: NO-WRITE" --tools Read,Grep,Glob --output-format json $CM </dev/null >"$S/5.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/5.json" 'd["is_error"] is False and "NO-WRITE" in d["result"]' \
    && ok "--tools Read,Grep,Glob：运行成功，Write 工具不存在，文件未产生，模型自报 NO-WRITE" || no "--tools 白名单断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)）"

  echo "== smoke：Codex（真跑）"
  C="$W/b"; mkdir -p "$C"
  ( cd "$C" && timeout "$T" codex exec --skip-git-repo-check --sandbox read-only --json -o "$C/1.txt" "Reply with exactly: OK" </dev/null >"$C/1.jsonl" 2>"$E" ); rc=$?
  # codex_parse <jsonl>：两行输出——thread.started.thread_id、item.completed/agent_message 的 text
  codex_parse(){ python3 - "$1" <<'PY'
import json,sys
tid=msg=None
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("type")=="thread.started": tid=e.get("thread_id")
    if e.get("type")=="item.completed" and e.get("item",{}).get("type")=="agent_message": msg=e["item"].get("text")
print(tid or ""); print(msg or "")
PY
  }
  { read -r TID; read -r MSG; } < <(codex_parse "$C/1.jsonl")
  [ "$rc" -eq 0 ] && [ -n "$TID" ] && [ "$MSG" = "$(cat "$C/1.txt")" ] && has OK "$MSG" \
    && ok "--json：thread.started.thread_id 与 item.completed/agent_message.text 在位，-o 内容等于该 text" || no "--json/-o 的输出契约已变（rc=$rc）"
  ( cd "$C" && timeout "$T" codex exec resume --skip-git-repo-check --json -o "$C/2.txt" "$TID" "Reply with exactly: OK2" </dev/null >"$C/2.jsonl" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && has '"agent_message"' "$(cat "$C/2.jsonl")" && [ -s "$C/2.txt" ] \
    && ok "exec resume <thread_id> 续跑成功，-o 每次都要重新给" || no "exec resume 续跑失败（rc=$rc）"
  R="$W/repo"; mkdir -p "$R"; ( cd "$R" && git init -q -b master && printf 'a\n' > f.txt && git add f.txt && git -c user.name=lc -c user.email=lc@x commit -qm init && printf 'b\n' >> f.txt )
  ( cd "$R" && timeout "$T" codex exec --sandbox read-only review --uncommitted --json -o "$R/3.txt" </dev/null >"$R/3.jsonl" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && [ -s "$R/3.txt" ] && ok "exec --sandbox read-only review --uncommitted --json -o 可跑" || no "review --uncommitted 形式失败（rc=$rc）"
  ( cd "$R" && timeout "$T" codex exec --sandbox read-only review --json -o "$R/4.txt" "Review the working tree change to f.txt in one sentence." </dev/null >"$R/4.jsonl" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && [ -s "$R/4.txt" ] && ok "exec --sandbox read-only review --json -o <prompt> 可跑" || no "review 自定义 prompt 形式失败（rc=$rc）"

  echo "== smoke：Kimi（真跑）"
  K="$W/c"; mkdir -p "$K"
  last(){ python3 - "$1" <<'PY'
import json,sys
ans=sid=None
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("role")=="assistant" and isinstance(e.get("content"),str): ans=e["content"]
    if e.get("type")=="session.resume_hint": sid=e.get("session_id")
print(sid or ""); print(ans or "")
PY
  }
  ( cd "$K" && timeout "$T" kimi -p "Remember this word and nothing else: pineapple. Reply with exactly: noted" --output-format stream-json >"$K/1.jsonl" 2>"$E" ); rc=$?
  { read -r KSID; read -r ANS; } < <(last "$K/1.jsonl")
  [ "$rc" -eq 0 ] && [ -n "$KSID" ] && has noted "$ANS" \
    && ok "stream-json：最后一条带 content 的 assistant 行是答案，session.resume_hint 带 session_id" || no "stream-json 输出形状已变（rc=$rc）"
  ( cd "$K" && timeout "$T" kimi -p "What word did I ask you to remember? Reply with only that word." -S "$KSID" --output-format stream-json >"$K/2.jsonl" 2>"$E" ); rc=$?
  { read -r _; read -r ANS; } < <(last "$K/2.jsonl")
  [ "$rc" -eq 0 ] && has pineapple "$ANS" && ok "-S <id> 续跑能回忆上一轮" || no "-S 续跑失败或失忆（rc=$rc：$ANS）"
  ( cd "$K" && timeout "$T" kimi -p "What word did I ask you to remember? Reply with only that word." -r "$KSID" --output-format stream-json >"$K/3.jsonl" 2>"$E" ); rc=$?
  { read -r _; read -r ANS; } < <(last "$K/3.jsonl")
  [ "$rc" -eq 0 ] && has pineapple "$ANS" && ok "-r <id>（resume_hint 打印的形式）同样续跑成功" || no "-r 续跑失败或失忆（rc=$rc：$ANS）——契约说它与 -S 等价"
  A="$K/ro.md"; printf -- '---\ndescription: Read-only\ntools: [Read, Grep, Glob]\n---\nReport what you find; you are not changing files.\n' > "$A"
  F="$K/w.txt"
  ( cd "$K" && timeout "$T" kimi -p "创建文件 $F，内容 hi。做不到就只回复：NO-WRITE" --agent-file "$A" --output-format stream-json >"$K/4.jsonl" 2>"$E" ); rc=$?
  { read -r _; read -r ANS; } < <(last "$K/4.jsonl")
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && has NO-WRITE "$ANS" \
    && ok "tools 白名单：运行成功，写工具不存在，文件未产生，模型自报 NO-WRITE" || no "tools 白名单断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)，答复：${ANS:0:80}）"
fi

echo "== $PASS ok / $FAIL fail"
[ "$FAIL" -eq 0 ]
