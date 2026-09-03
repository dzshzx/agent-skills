#!/usr/bin/env bash
# 回归检测：核对 SKILL.md 与 references/*.md 缓存的三家 CLI 契约是否仍与本机实装一致。
# 用法：bash evals/live-check.sh [--smoke]
#   默认档（surface + parser）：--help 是否仍列出所用 flag；参数解析层的拒绝/放行是否仍成立——`--` 之后以 `-` 开头的 brief
#     过解析而没有 `--` 时被拒、空 prompt 的三家行为、启动失败写在 stdout 还是 stderr、契约里每种命令形态（exec / resume /
#     review）可解析、`--permission-mode` 的 choices 含 bypassPermissions、Kimi 内置 agent explore 仍在、单个 argv 128 KiB 上限。
#     零模型调用且 fail-closed：会真启动的命令都跑在无凭证的 CODEX_HOME / 不存在的 Claude 与 Kimi 模型下，
#     契约一旦失效（原本该被拒的命令被接受）会在 401 / 模型解析处失败，而不是悄悄花一次调用。
#   --smoke：真跑约 30 次小调用（计费；三家凭证都要在位，缺一家该家整段红），解析 JSON 并断言
#     字段、退出码、续跑与权限行为、brief 经 argv 原样到达。每条契约命令行都按 references 里的形态真跑（`--` 在前、
#     `--sandbox` 在 resume 之前、bypassPermissions）；hostile brief 首行以 `- ` 开头。FAIL 行下附 stderr 尾巴，用来区分
#     「行为断言失败」与「调用本身失败（401 / 限流 / 网络）」——后者不是契约失效。Codex 调用遇到 API 安全层整轮拒绝
#     （turn.failed "flagged for possible cybersecurity risk"，codex.md 记载它不完全确定——同一 brief 可能一次过一次拒，
#     brief 或自定义 model_instructions_file 的措辞都可能触发）时按契约重新派发，最多两次；仍拒才交给断言。
#   绿灯只证明下面逐条断言的行为；没断言的东西它什么都不证明。
set -u
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
no(){ FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; [ -s "${E:-}" ] && printf '       stderr: %s\n' "$(tail -c 200 "$E" | tr '\n' ' ')"; }
has(){ printf '%s' "$2" | grep -qF -- "$1"; }
T=300                                   # 单次真跑上限（秒）
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
NOAUTH="$W/codex-home"; mkdir -p "$NOAUTH"   # 空 CODEX_HOME：无凭证，启动后必 401
BOGUS=bogus-model-live-check                 # 不存在的模型名：Claude 在 API 调用前、Kimi 在模型解析处失败
NONGIT="$W/nongit"; mkdir -p "$NONGIT"
# py <file> <expr>：对 JSON 文件求值；<expr> 里用 d 表示解析结果，结果为真则退出 0
py(){ python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if eval(sys.argv[2]) else 1)' "$1" "$2" 2>/dev/null; }

for c in claude codex kimi; do
  command -v "$c" >/dev/null 2>&1 || { echo "缺少 $c，无法检测"; exit 2; }
done

echo "== 实装版本（契约是否成立由下面的断言决定，不由版本号决定）"
printf '  claude %s\n  codex  %s\n  kimi   %s\n' \
  "$(claude --version 2>/dev/null)" "$(codex --version 2>/dev/null)" "$(kimi --version 2>/dev/null)"

echo "== Claude：flag 面"
H=$(claude --help 2>&1)
for f in " -p, --print" "--output-format" "--permission-mode" "--allowedTools" "--tools" "--resume" "--strict-mcp-config"; do
  has "$f" "$H" && ok "claude --help 有 $f" || no "claude --help 缺 $f"
done
for m in dontAsk acceptEdits bypassPermissions; do
  has "$m" "$H" && ok "--permission-mode 仍列出 $m" || no "--permission-mode 不再列出 $m"
done

echo "== Claude：解析层（模型名不存在，API 调用前即失败）"
( cd "$NONGIT" && timeout 60 claude -p "- item" --model "$BOGUS" --output-format json </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "unknown option" "$(cat "$W/e")" \
  && ok "没有 -- 时以 - 开头的 brief 被当作选项拒绝（rc=$rc）——契约要求 --" || no "以 - 开头的 brief 不再被当作选项（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 claude -p --model "$BOGUS" --output-format json -- "- item" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && ! has "unknown option" "$(cat "$W/e")" && py "$W/o" 'd["is_error"] is True' \
  && ok "-- 之后以 - 开头的 brief 过解析；启动失败写进 stdout 的 JSON（is_error=true，rc=$rc）" || no "-- 形式或启动失败的 JSON 形状已变（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 claude -p "" --model "$BOGUS" --output-format json </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "Input must be provided" "$(cat "$W/e")" \
  && ok "空 prompt 在解析层被拒（rc=$rc）" || no "空 prompt 的处理已变（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 claude -p hi --permission-mode bogusMode --model "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "bypassPermissions" "$(cat "$W/e")" \
  && ok "--permission-mode 的 choices 在解析层校验，仍含 bypassPermissions（rc=$rc）" || no "--permission-mode 的 choices 校验已变（rc=$rc）：$(head -c 160 "$W/e")"

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
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --json "noop" </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
  && ok "非 git 目录 exec 仍要求 --skip-git-repo-check（rc=$rc）" || no "非 git 目录 exec 不再拒绝启动（rc=$rc）"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec resume --json 00000000-0000-0000-0000-000000000000 "noop" </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
  && ok "非 git 目录 exec resume 同样要求 --skip-git-repo-check（rc=$rc）" || no "exec resume 不再受 git 门禁（rc=$rc）"
CODEX_HOME="$NOAUTH" codex exec resume --sandbox read-only --json 00000000-0000-0000-0000-000000000000 "noop" </dev/null >/dev/null 2>"$W/e"; rc=$?
[ "$rc" -eq 2 ] && has "unexpected argument '--sandbox'" "$(cat "$W/e")" \
  && ok "resume 之后的 --sandbox 仍被拒（rc=2）" || no "resume 之后的 --sandbox 不再被拒（rc=$rc）"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --sandbox read-only review --uncommitted --json </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "--skip-git-repo-check" "$(cat "$W/e")" \
  && ok "--sandbox 放在 review 之前可解析，review 也受 git 门禁（rc=$rc）" || no "--sandbox … review 解析或门禁行为已变（rc=$rc）"
CODEX_HOME="$NOAUTH" codex exec review --sandbox read-only --json </dev/null >/dev/null 2>"$W/e"; rc=$?
[ "$rc" -eq 2 ] && has "unexpected argument '--sandbox'" "$(cat "$W/e")" \
  && ok "review 之后的 --sandbox 仍被拒（rc=2）" || no "review 之后的 --sandbox 不再被拒（rc=$rc）"
CODEX_HOME="$NOAUTH" codex exec review --uncommitted --json "prompt" </dev/null >/dev/null 2>"$W/e"; rc=$?
[ "$rc" -eq 2 ] && has "cannot be used with" "$(cat "$W/e")" \
  && ok "--uncommitted 与自定义 prompt 仍互斥（rc=2）" || no "--uncommitted 与 prompt 不再互斥（rc=$rc）"
# 契约：非 TTY 且未关闭的 stdin 让 exec 一直等（读附加 prompt 直到 EOF）；</dev/null 才放行启动
( cd "$NONGIT" && sleep 8 | CODEX_HOME="$NOAUTH" timeout 5 codex exec --skip-git-repo-check --json "noop" >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -eq 124 ] && has "Reading additional" "$(cat "$W/e")" \
  && ok "未关闭的非 TTY stdin：exec 等待到 timeout（rc=124，stderr 报 Reading additional）" || no "非 TTY stdin 的等待行为已变（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --skip-git-repo-check --json "- item" </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -eq 2 ] && has "unexpected argument" "$(cat "$W/e")" \
  && ok "没有 -- 时以 - 开头的 brief 是 unexpected argument（rc=2）——契约要求 --" || no "以 - 开头的 brief 不再被拒（rc=$rc）"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 90 codex exec --skip-git-repo-check --json -- "- item" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 124 ] && [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ] && has '"turn.failed"' "$(cat "$W/o")" && has "401" "$(cat "$W/e")" \
  && ok "-- 之后以 - 开头的 brief 过解析；</dev/null 放行启动；无凭证失败写进 stdout（turn.failed）与 stderr（401，rc=$rc）" \
  || no "-- 形式、</dev/null 放行或无凭证失败的输出归属已变（rc=$rc）"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 90 codex exec --skip-git-repo-check --json "" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
has '"thread.started"' "$(cat "$W/o")" \
  && ok "空 prompt 不被拒，真的开启一个 turn（rc=$rc）——契约要求派发前检查 brief 非空" || no "空 prompt 的处理已变（rc=$rc）：$(head -c 120 "$W/o")"
CODEX_HOME="$NOAUTH" timeout 60 codex exec --sandbox read-only resume --skip-git-repo-check --json -o "$W/last.txt" -- 00000000-0000-0000-0000-000000000000 "- item" </dev/null >/dev/null 2>"$W/e"; rc=$?
[ "$rc" -ne 2 ] && has "no rollout found" "$(cat "$W/e")" \
  && ok "契约的 resume 形态（--sandbox 在 resume 之前、-- 在 thread id 之前）可解析，止于 thread 不存在（rc=$rc）" || no "契约的 resume 形态不再可解析（rc=$rc）：$(tail -c 160 "$W/e")"
( cd "$NONGIT" && CODEX_HOME="$NOAUTH" timeout 60 codex exec --sandbox read-only review --json -o "$W/last.txt" -- "- item" </dev/null >/dev/null 2>"$W/e" ); rc=$?
[ "$rc" -ne 2 ] && ! has "unexpected argument" "$(cat "$W/e")" \
  && ok "契约的 review 自定义 prompt 形态（-- 在 brief 之前）可解析（rc=$rc）" || no "review 的 -- 形态不再可解析（rc=$rc）：$(tail -c 160 "$W/e")"

echo "== Kimi：flag 面"
H=$(kimi --help 2>&1)
for f in "-S, --session" "--agent <name>" "--agent-file" "--output-format" "-p, --prompt"; do
  has "$f" "$H" && ok "kimi --help 有 $f" || no "kimi --help 缺 $f"
done
AFD="$W/ro-agent.md"; printf -- '---\ndescription: Read-only\ntools: [Read]\n---\nprobe\n' > "$AFD"
( cd "$NONGIT" && timeout 60 kimi -p noop --agent-file "$AFD" -S session_bogus -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "Cannot combine" "$(cat "$W/e")" \
  && ok "--agent-file 与 -S 的组合仍被拒（真跑解析层，rc=$rc）" || no "--agent-file 与 -S 的互斥已失效（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 kimi -p noop --agent explore -S session_bogus -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "Cannot combine" "$(cat "$W/e")" && has "restored automatically on resume" "$(cat "$W/e")" \
  && ok "--agent 与 -S 同样互斥，报错仍写明 resume 自动恢复绑定的 agent（rc=$rc）" || no "--agent 与 -S 的互斥或 resume 恢复语义已变（rc=$rc）：$(head -c 120 "$W/e")"
AFBAD="$W/tmp.notkebab.md"; cp "$AFD" "$AFBAD"   # 契约：agent 名取自文件 basename，须 kebab-case（mktemp 名会被拒）
( cd "$NONGIT" && timeout 60 kimi -p noop --agent-file "$AFBAD" -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "expected kebab-case" "$(cat "$W/e")" \
  && ok "--agent-file 非 kebab-case 文件名在模型调用前被拒（rc=$rc）" || no "--agent-file 的文件名规则已变（rc=$rc）：$(head -c 120 "$W/e")"

echo "== Kimi：解析层拒绝（模型别名不存在，fail-closed）"
for f in --auto -y --yolo --plan; do
  ( cd "$NONGIT" && timeout 60 kimi -p noop "$f" -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
  [ "$rc" -ne 0 ] && has "Cannot combine" "$(cat "$W/e")" && ! grep -q '"role":"assistant"' "$W/o" \
    && ok "kimi -p 仍拒绝 $f，原因在 stderr、stdout 无答案行（rc=$rc）" || no "kimi -p 对 $f 的拒绝行为已变（rc=$rc）"
done
( cd "$NONGIT" && timeout 60 kimi -p noop -r session_does-not-exist -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "not found" "$(cat "$W/e")" \
  && ok "-r <id> 被当作 session id 解析（不存在即报错，非静默忽略）" || no "-r 的解析行为已变（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 kimi -p "--- item" -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "not configured" "$(cat "$W/e")" \
  && ok "-p 的值以 --- 开头照常到达模型解析（无需 --，rc=$rc）" || no "-p 对以 - 开头的值的处理已变（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 kimi -p "" -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "Prompt cannot be empty" "$(cat "$W/e")" \
  && ok "空 prompt 在解析层被拒（rc=$rc）" || no "空 prompt 的处理已变（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 kimi -p noop --agent no-such-agent-live-check -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && has "Unknown agent profile" "$(cat "$W/e")" \
  && ok "未知 --agent 在模型调用前被拒（rc=$rc）" || no "--agent 的名字校验已变（rc=$rc）：$(head -c 120 "$W/e")"
( cd "$NONGIT" && timeout 60 kimi -p noop --agent explore -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -ne 0 ] && ! has "Unknown agent profile" "$(cat "$W/e")" && has "not configured" "$(cat "$W/e")" \
  && ok "内置 agent explore 仍在（止于模型解析，rc=$rc）" || no "--agent explore 不再存在或行为已变（rc=$rc）：$(head -c 120 "$W/e")"
# 契约：没有 -p 就进 TUI 挂住，关闭的 stdin 不放行；只有外层 timeout 能把它变成失败
( cd "$NONGIT" && timeout 5 kimi -m "$BOGUS" </dev/null >"$W/o" 2>"$W/e" ); rc=$?
[ "$rc" -eq 124 ] && ok "无 -p：进入 TUI 并挂住，关闭的 stdin 不放行（timeout rc=124）" || no "无 -p 的 TUI 挂住行为已变（rc=$rc）：$(head -c 120 "$W/e")"

echo "== 平台：单个 argv 上限"
BIG=$(python3 -c 'print("x"*200000)'); /bin/true "$BIG" 2>/dev/null; rc=$?
FIT=$(python3 -c 'print("x"*131000)'); /bin/true "$FIT" 2>/dev/null; rc2=$?
[ "$rc" -ne 0 ] && [ "$rc2" -eq 0 ] && ok "单个 argv 超过 128 KiB 时 exec 失败（rc=$rc），128 KiB 内放行——契约要求大材料走文件" || no "单个 argv 上限已变（200000B rc=$rc，131000B rc=$rc2）"

if [ "${1:-}" = "--smoke" ]; then
  E="$W/stderr"                           # 每次真跑的 stderr；no() 失败时附其尾巴
  CM="--model sonnet"   # 默认模型 Fable 5 的 API 安全层会间歇性整轮拒绝这类探针式 prompt（api_error）；契约测的是 CLI，不是模型
  echo "== smoke：Claude（真跑）"
  S="$W/a"; mkdir -p "$S"   # 目录名不用 claude：实测 cwd basename 为 claude 时会被 API 安全层误拦
  # jerr <json>：失败归因——Claude 的错误进 JSON 而非 stderr，打印 terminal_reason 与 result 头
  jerr(){ python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("terminal_reason"),"|",str(d.get("result"))[:160])' "$1" 2>&1 | head -c 200; }
  # 契约（SKILL.md）：brief 写进文件、以 -- "$(cat "$BRIEF")" 作单个 argv 传入（首行以 - 开头），shell 敏感片段原样到达。三家各跑一次。
  # 用中性 token（echo tick / echo dollar）：whoami / pwned 这类探针措辞会被 OpenAI 的 API 安全层整轮拒绝（见 codex.md）
  HB="$W/hostile.md"
  cat > "$HB" <<'EOF'
- Reply with exactly the text on the line between the two marker lines, byte for byte, with no code fence and nothing else.
<<<
tick `echo tick` dollar $(echo dollar) quote "dq" 'sq' backslash \n marker-7f3a
>>>
EOF
  # intact <textfile>：brief 里每个 shell 敏感片段都原样出现在答复里
  intact(){ python3 - "$1" <<'PY'
import sys
t=open(sys.argv[1]).read()
need=["`echo tick`","$(echo dollar)",'"dq"',"'sq'","\\n","marker-7f3a"]
sys.exit(0 if all(x in t for x in need) else 1)
PY
  }
  ( cd "$S" && timeout "$T" claude -p --output-format json --permission-mode acceptEdits $CM -- "Remember this word and nothing else: pineapple. Reply with exactly: noted" </dev/null >"$S/1.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && py "$S/1.json" 'd["is_error"] is False and "noted" in d["result"] and d["session_id"] and isinstance(d["permission_denials"], list)' \
    && ok "成功运行：rc=0，.is_error=false，.result/.session_id/.permission_denials 在位" \
    || no "成功运行的 JSON 形状已变（rc=$rc）：$(jerr "$S/1.json")"
  SID=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$S/1.json" 2>/dev/null)
  ( cd "$S" && timeout "$T" claude -p --resume "$SID" --output-format json $CM -- "What word did I ask you to remember? Reply with only that word." </dev/null >"$S/2.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && py "$S/2.json" 'd["is_error"] is False and "pineapple" in d["result"]' \
    && ok "--resume 续跑成功且能回忆上一轮" || no "--resume 续跑失败或失忆（rc=$rc）：$(jerr "$S/2.json")"
  ( cd "$S" && timeout "$T" claude -p --model "$BOGUS" --output-format json -- "Reply with exactly: OK" </dev/null >"$S/3.json" 2>"$E" ); rc=$?
  [ "$rc" -ne 0 ] && py "$S/3.json" 'd["is_error"] is True and d["subtype"] == "success" and d.get("terminal_reason")' \
    && ok "失败运行：rc≠0，.is_error=true，.terminal_reason 在位，而 .subtype 仍是 success" || no "失败运行的 JSON 形状已变（rc=$rc）"
  F="$S/deny.txt"
  ( cd "$S" && timeout "$T" claude -p --permission-mode dontAsk --output-format json $CM -- "Use the Write tool to create $F containing hi." </dev/null >"$S/4.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/4.json" 'd["is_error"] is False and len(d["permission_denials"]) > 0 and d["permission_denials"][0].get("tool_name")' \
    && ok "dontAsk：运行成功，Write 被拒且记入 .permission_denials（本机 allow 规则未放行 Write）" || no "dontAsk 断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)）"
  F="$S/notool.txt"
  # 只看「文件不存在」会把启动失败也算作绿：要求 rc=0、JSON 非错误，且模型自报 NO-WRITE 作为它确实尝试过的证据
  ( cd "$S" && timeout "$T" claude -p --tools Read,Grep,Glob --output-format json $CM -- "Use the Write tool to create $F containing hi. If you cannot, reply with exactly: NO-WRITE" </dev/null >"$S/5.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && py "$S/5.json" 'd["is_error"] is False and "NO-WRITE" in d["result"]' \
    && ok "--tools Read,Grep,Glob：运行成功，Write 工具不存在，文件未产生，模型自报 NO-WRITE" || no "--tools 白名单断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)）"
  # 契约：acceptEdits 只放行编辑；-p 无法弹窗，Bash 被拒并记入 .permission_denials；--allowedTools 'Bash(<cmd>:*)' 逐条放行
  BASHP="Run this exact shell command with the Bash tool: python3 -c 'print(6*7)' . Reply with only the command's output. If the tool call is denied, reply with exactly: DENIED"
  ( cd "$S" && timeout "$T" claude -p --permission-mode acceptEdits --output-format json $CM -- "$BASHP" </dev/null >"$S/6.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && py "$S/6.json" 'd["is_error"] is False and "DENIED" in d["result"] and d["permission_denials"] and d["permission_denials"][0].get("tool_name") == "Bash"' \
    && ok "acceptEdits：Bash 被自动拒绝并记入 .permission_denials（tool_name=Bash）" || no "acceptEdits 下 Bash 的拒绝行为已变（rc=$rc）：$(jerr "$S/6.json")"
  ( cd "$S" && timeout "$T" claude -p --permission-mode acceptEdits --allowedTools 'Bash(python3:*)' --output-format json $CM -- "$BASHP" </dev/null >"$S/7.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && py "$S/7.json" 'd["is_error"] is False and "42" in d["result"] and d["permission_denials"] == []' \
    && ok "acceptEdits + --allowedTools 'Bash(python3:*)'：命令放行，输出 42，无拒绝记录" || no "--allowedTools 放行断言失败（rc=$rc）：$(jerr "$S/7.json")"
  # 契约：无法枚举命令时用 bypassPermissions——Bash 放行、无拒绝记录
  ( cd "$S" && timeout "$T" claude -p --permission-mode bypassPermissions --output-format json $CM -- "$BASHP" </dev/null >"$S/7b.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && py "$S/7b.json" 'd["is_error"] is False and "42" in d["result"] and d["permission_denials"] == []' \
    && ok "bypassPermissions：Bash 放行，输出 42，无拒绝记录" || no "bypassPermissions 断言失败（rc=$rc）：$(jerr "$S/7b.json")"
  # 契约：--resume 恢复对话不恢复姿态。--settings 把本次 defaultMode 钉为 acceptEdits，断言不依赖本机 settings。
  #   行为面：dontAsk 会话裸续跑 → 写成功。姿态面用 init 事件确定判定（见下），不经模型意愿。
  ACC='{"permissions":{"defaultMode":"acceptEdits"}}'
  SID4=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["session_id"])' "$S/4.json" 2>/dev/null)
  F="$S/r1.txt"
  ( cd "$S" && timeout "$T" claude -p --resume "$SID4" --settings "$ACC" --output-format json $CM -- "Use the Write tool to create $F containing hi. If the tool call is denied, reply with exactly: DENIED" </dev/null >"$S/8.json" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && [ -f "$F" ] && py "$S/8.json" 'd["is_error"] is False and d["permission_denials"] == []' \
    && ok "dontAsk 会话裸 --resume：写成功——权限模式不随会话恢复" || no "dontAsk 会话裸 --resume 的行为已变（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)）：$(jerr "$S/8.json")"
  # 契约：stream-json --verbose 首条 system/init 事件带 permissionMode 与 tools，是本次运行实际拿到的姿态。
  # init <jsonl> <expr>：对 init 事件求值，expr 里 e 为该事件；没有 init 事件即失败
  init(){ python3 -c '
import json,sys
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("type")=="system" and e.get("subtype")=="init": sys.exit(0 if eval(sys.argv[2]) else 1)
sys.exit(1)' "$1" "$2" 2>/dev/null; }
  ( cd "$S" && timeout "$T" claude -p --tools Read,Grep,Glob --permission-mode dontAsk --strict-mcp-config --output-format stream-json --verbose $CM -- "Reply with exactly: OK" </dev/null >"$S/9.jsonl" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && init "$S/9.jsonl" 'e["permissionMode"]=="dontAsk" and sorted(e["tools"])==["Glob","Grep","Read"] and e["mcp_servers"]==[]' \
    && ok "init 事件：--tools Read,Grep,Glob --strict-mcp-config --permission-mode dontAsk → tools 恰为三个、无 MCP、dontAsk" || no "init 事件的 tools/permissionMode/mcp_servers 形状已变（rc=$rc）"
  SID9=$(python3 -c '
import json,sys
for line in open(sys.argv[1]):
    e=json.loads(line)
    if e.get("type")=="system" and e.get("subtype")=="init": print(e["session_id"]); break' "$S/9.jsonl" 2>/dev/null)
  ( cd "$S" && timeout "$T" claude -p --resume "$SID9" --settings "$ACC" --output-format stream-json --verbose $CM -- "Reply with exactly: OK" </dev/null >"$S/10.jsonl" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && init "$S/10.jsonl" 'e["permissionMode"]=="acceptEdits" and "Write" in e["tools"]' \
    && ok "裸 --resume 的 init 事件：permissionMode 落回默认（此处钉为 acceptEdits）、Write 回到 tools——姿态不随会话恢复" || no "裸 --resume 的姿态行为已变（rc=$rc）"
  ( cd "$S" && timeout "$T" claude -p --resume "$SID9" --tools Read,Grep,Glob --permission-mode dontAsk --strict-mcp-config --output-format stream-json --verbose $CM -- "Reply with exactly: OK" </dev/null >"$S/11.jsonl" 2>"$E" ); rc=$?
  [ "$rc" -eq 0 ] && init "$S/11.jsonl" 'e["permissionMode"]=="dontAsk" and "Write" not in e["tools"] and e["mcp_servers"]==[]' \
    && ok "--resume 重传三个 flag 的 init 事件：dontAsk、无 Write、无 MCP——姿态要每次续跑重传" || no "--resume 重传 flag 未生效（rc=$rc）"
  ( cd "$S" && timeout "$T" claude -p --output-format json $CM -- "$(cat "$HB")" </dev/null >"$S/12.json" 2>"$E" ); rc=$?
  python3 -c 'import json,sys;open(sys.argv[2],"w").write(str(json.load(open(sys.argv[1])).get("result","")))' "$S/12.json" "$S/12.txt" 2>/dev/null
  [ "$rc" -eq 0 ] && intact "$S/12.txt" \
    && ok '-- "$(cat "$BRIEF")"：首行以 - 开头、含反引号、$()、引号与 \n 的 brief 原样到达（.result）' || no "brief 经 argv 传递被改写或展开（rc=$rc）：$(head -c 120 "$S/12.txt" 2>/dev/null)"

  echo "== smoke：Codex（真跑）"
  C="$W/b"; mkdir -p "$C"
  # cx <dir> <stdout-file> <codex args…>：在 dir 里跑一次 codex（timeout、</dev/null、stderr→$E）；API 安全层整轮拒绝时
  #   按契约重新派发，最多两次；仍拒才把失败交给断言
  cx(){ local dir=$1 out=$2 n; shift 2
    for n in 1 2 3; do
      ( cd "$dir" && timeout "$T" "$@" </dev/null >"$out" 2>"$E" ); rc=$?
      grep -q 'flagged for possible cybersecurity risk' "$out" "$E" 2>/dev/null || return "$rc"
      [ "$n" -lt 3 ] && { echo "       (API 安全层整轮拒绝，第 $n 次；按契约重新派发)"; sleep 5; }
    done
    return "$rc"
  }
  # cerr <jsonl>：失败归因——Codex 的 turn.failed / error 消息在 stdout 事件流里，不在 stderr
  cerr(){ python3 -c '
import json,sys
msg=""
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("type")=="turn.failed": msg=(e.get("error") or {}).get("message") or msg
    elif e.get("type")=="error": msg=e.get("message") or msg
print(msg[:160] if msg else "(无 turn.failed；见 stderr)")' "$1" 2>/dev/null; }
  cx "$C" "$C/1.jsonl" codex exec --skip-git-repo-check --sandbox read-only --json -o "$C/1.txt" -- "Reply with exactly: OK"; rc=$?
  # codex_parse <jsonl> <last.txt>：两行输出——thread.started.thread_id；agent_message 的 text 是否含 OK 且与 -o 文件整段一致（same/diff）
  codex_parse(){ python3 - "$1" "$2" <<'PY'
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
  { read -r TID; read -r SAME; } < <(codex_parse "$C/1.jsonl" "$C/1.txt")
  [ "$rc" -eq 0 ] && [ -n "$TID" ] && [ "$SAME" = same ] \
    && ok "--json：thread.started.thread_id 与 item.completed/agent_message.text 在位，-o 内容等于该 text" || no "--json/-o 的输出契约已变（rc=$rc）：$(cerr "$C/1.jsonl")"
  cx "$C" "$C/2.jsonl" codex exec --sandbox read-only resume --skip-git-repo-check --json -o "$C/2.txt" -- "$TID" "Reply with exactly: OK2"; rc=$?
  [ "$rc" -eq 0 ] && has '"agent_message"' "$(cat "$C/2.jsonl")" && [ -s "$C/2.txt" ] \
    && ok "exec --sandbox read-only resume -- <thread_id> 续跑成功（契约形态），-o 每次都要重新给" || no "exec resume 续跑失败（rc=$rc）：$(cerr "$C/2.jsonl")"
  cx "$C" "$C/2b.txt" codex exec --sandbox read-only resume --skip-git-repo-check -- "$TID" "Reply with exactly: OK3"; rc=$?
  [ "$rc" -eq 0 ] && [ -s "$C/2b.txt" ] && [ "$(head -c 1 "$C/2b.txt")" != "{" ] \
    && ok "resume 不带 --json/-o 时输出纯文本（两 flag 确为 per-invocation）" || no "resume 无 flag 的输出形态已变（rc=$rc）"
  R="$W/repo"; mkdir -p "$R"; ( cd "$R" && git init -q -b master && printf 'a\n' > f.txt && git add f.txt && git -c user.name=lc -c user.email=lc@x commit -qm init && printf 'b\n' >> f.txt )
  cx "$R" "$R/3.jsonl" codex exec --sandbox read-only review --uncommitted --json -o "$R/3.txt"; rc=$?
  [ "$rc" -eq 0 ] && [ -s "$R/3.txt" ] && ok "exec --sandbox read-only review --uncommitted --json -o 可跑" || no "review --uncommitted 形式失败（rc=$rc）：$(cerr "$R/3.jsonl")"
  cx "$R" "$R/4.jsonl" codex exec --sandbox read-only review --json -o "$R/4.txt" -- "Review the working tree change to f.txt in one sentence."; rc=$?
  [ "$rc" -eq 0 ] && [ -s "$R/4.txt" ] && ok "exec --sandbox read-only review --json -o <prompt> 可跑" || no "review 自定义 prompt 形式失败（rc=$rc）：$(cerr "$R/4.jsonl")"
  P="$W/perm"; mkdir -p "$P"
  cx "$P" "$P/ro.jsonl" codex exec --skip-git-repo-check --sandbox read-only --json -- "Write a text file at $P/ro.txt whose content is the word hi, then confirm in one sentence."; rc=$?
  [ ! -f "$P/ro.txt" ] && has '"agent_message"' "$(cat "$P/ro.jsonl")" \
    && ok "read-only：写被 OS sandbox 拦下，运行正常收尾（rc=$rc）" || no "read-only 下产生了文件或运行异常（rc=$rc）：$(cerr "$P/ro.jsonl")"
  cx "$P" "$P/rw.jsonl" codex exec --skip-git-repo-check --sandbox workspace-write --json -- "Write a text file at $P/rw.txt whose content is the word hi, then confirm in one sentence."; rc=$?
  [ -f "$P/rw.txt" ] && ok "workspace-write：写被放行（rc=$rc）" || no "workspace-write 下写未生效（rc=$rc）：$(cerr "$P/rw.jsonl")"
  cx "$C" "$C/h.jsonl" codex exec --skip-git-repo-check --sandbox read-only --json -o "$C/h.txt" -- "$(cat "$HB")"; rc=$?
  [ "$rc" -eq 0 ] && intact "$C/h.txt" \
    && ok '-- "$(cat "$BRIEF")"：首行以 - 开头、含反引号、$()、引号与 \n 的 brief 原样到达（-o 文本）' || no "brief 经 argv 传递被改写或展开（rc=$rc）：$(cerr "$C/h.jsonl") | $(head -c 120 "$C/h.txt" 2>/dev/null)"

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
  A2="$K/rw.md"; printf -- '---\ndescription: Read-only with shell\ntools: [Read, Grep, Glob, Bash]\n---\nReport what you find; you are not changing files.\n' > "$A2"
  F="$K/w2.txt"
  # 自报走 shell：没有 Write 时模型只能用 Bash echo 出 NO-WRITE-TOOL，落在 tool 结果流里——grep jsonl 断言，不看散文
  ( cd "$K" && timeout "$T" kimi -p "创建文件 $F，内容 hi——只用 Write 工具，不要用 Bash 写文件。如果你的工具集没有 Write 工具，就用 Bash 运行 echo NO-WRITE-TOOL 代替。" --agent-file "$A2" --output-format stream-json >"$K/5.jsonl" 2>"$E" ); rc=$?
  # called <jsonl>：单行输出本 run 调用过的工具名——shell 恢复看 tool_calls 证据，不只信模型自报
  called(){ python3 - "$1" <<'PY'
import json,sys
names=set()
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    for tc in (e.get("tool_calls") or []):
        n=(tc.get("function") or {}).get("name") or tc.get("name")
        if n: names.add(n)
print(" ".join(sorted(names)))
PY
  }
  CALLED=$(called "$K/5.jsonl")
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && has Bash "$CALLED" && ! has Write "$CALLED" && grep -q NO-WRITE-TOOL "$K/5.jsonl" \
    && ok "放宽白名单 [Read,Grep,Glob,Bash]：Bash 在（回显 NO-WRITE-TOOL），Write 缺席（调用面：$CALLED）" || no "放宽白名单断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)，调用面：$CALLED）"
  F="$K/w3.txt"
  # 契约：--agent explore 是同一工具面的单 flag 形式——不写 agent 文件，Bash 在、Write 缺席
  ( cd "$K" && timeout "$T" kimi -p "创建文件 $F，内容 hi——只用 Write 工具，不要用 Bash 写文件。如果你的工具集没有 Write 工具，就用 Bash 运行 echo NO-WRITE-TOOL 代替。" --agent explore --output-format stream-json >"$K/6.jsonl" 2>"$E" ); rc=$?
  CALLED=$(called "$K/6.jsonl")
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && has Bash "$CALLED" && ! has Write "$CALLED" && grep -q NO-WRITE-TOOL "$K/6.jsonl" \
    && ok "--agent explore：Bash 在（回显 NO-WRITE-TOOL），Write 缺席，无需 agent 文件（调用面：$CALLED）" || no "--agent explore 的工具面断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)，调用面：$CALLED）"
  # 契约：-S 续跑不接 --agent，创建时绑定的 agent 自动恢复——explore 会话续跑仍无 Write
  { read -r XSID; read -r _; } < <(last "$K/6.jsonl")
  F="$K/w5.txt"
  ( cd "$K" && timeout "$T" kimi -p "创建文件 $F，内容 hi——只用 Write 工具，不要用 Bash 写文件。如果你的工具集没有 Write 工具，就用 Bash 运行 echo NO-WRITE-TOOL 代替。" -S "$XSID" --output-format stream-json >"$K/9.jsonl" 2>"$E" ); rc=$?
  CALLED=$(called "$K/9.jsonl")
  [ "$rc" -eq 0 ] && [ ! -f "$F" ] && has Bash "$CALLED" && ! has Write "$CALLED" && grep -q NO-WRITE-TOOL "$K/9.jsonl" \
    && ok "--agent explore 会话 -S 续跑：Write 仍缺席、Bash 在（调用面：$CALLED）——agent 随会话恢复" || no "explore 会话续跑的工具面断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)，调用面：$CALLED）"
  # 契约：explore 能读图——ReadMediaFile 在工具面里且真的被调用（text-heavy-visual-workflow 的美学咨询/交付前检查靠它）；
  # 默认姿态（无 --agent）同样读图且可写。证据看 tool_calls 与落盘文件，不看模型自报。
  IMG="$K/px.png"; python3 -c 'import zlib,struct,sys
def chunk(t,d): return struct.pack(">I",len(d))+t+d+struct.pack(">I",zlib.crc32(t+d)&0xffffffff)
raw=b"".join(b"\x00"+bytes([255,0,0]*2) for _ in range(2))
sys.stdout.buffer.write(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",2,2,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b""))' > "$IMG"
  ( cd "$K" && timeout "$T" kimi -p "Look at the image file $IMG and reply with only its dominant color name." --agent explore --output-format stream-json >"$K/7.jsonl" 2>"$E" ); rc=$?
  CALLED=$(called "$K/7.jsonl")
  [ "$rc" -eq 0 ] && has ReadMediaFile "$CALLED" \
    && ok "--agent explore：读图走 ReadMediaFile（调用面：$CALLED）" || no "--agent explore 读图断言失败（rc=$rc，调用面：$CALLED）"
  F="$K/w4.txt"
  ( cd "$K" && timeout "$T" kimi -p "Look at the image file $IMG, then create the file $F containing only its dominant color name." --output-format stream-json >"$K/8.jsonl" 2>"$E" ); rc=$?
  CALLED=$(called "$K/8.jsonl")
  [ "$rc" -eq 0 ] && has ReadMediaFile "$CALLED" && [ -f "$F" ] \
    && ok "默认姿态：读图走 ReadMediaFile 且文件已落盘（可读图、可写；调用面：$CALLED）" || no "默认姿态断言失败（rc=$rc，文件$( [ -f "$F" ] && echo 已产生 || echo 未产生)，调用面：$CALLED）"
  # kans <jsonl> <out>：把最后一条带 content 的 assistant 行原样写进文件（多行答复不经 read 截断）
  kans(){ python3 - "$1" "$2" <<'PY'
import json,sys
ans=""
for line in open(sys.argv[1]):
    try: e=json.loads(line)
    except Exception: continue
    if e.get("role")=="assistant" and isinstance(e.get("content"),str): ans=e["content"]
open(sys.argv[2],"w").write(ans)
PY
  }
  ( cd "$K" && timeout "$T" kimi -p "$(cat "$HB")" --output-format stream-json >"$K/h.jsonl" 2>"$E" ); rc=$?
  kans "$K/h.jsonl" "$K/h.txt"
  [ "$rc" -eq 0 ] && intact "$K/h.txt" \
    && ok '"$(cat "$BRIEF")"：首行以 - 开头、含反引号、$()、引号与 \n 的 brief 原样到达（最后一条 assistant content，-p 取值无需 --）' || no "brief 经 argv 传递被改写或展开（rc=$rc）：$(head -c 120 "$K/h.txt" 2>/dev/null)"
fi

echo "== $PASS ok / $FAIL fail"
[ "$FAIL" -eq 0 ]
