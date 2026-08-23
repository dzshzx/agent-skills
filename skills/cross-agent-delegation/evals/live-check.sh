#!/usr/bin/env bash
# 回归检测：核对 SKILL.md 缓存的三家 CLI 契约是否仍与本机实装一致。
# 用法：bash evals/live-check.sh [--smoke]
#   默认档：只跑 --help 与参数解析层断言，**零模型调用**、秒级、不留工件。
#   --smoke：追加需要真跑一轮的断言（JSON 字段名、权限拒绝、多步输出形状、续跑），约 10 次调用。
# 存在意义：SKILL.md 缓存的正是 `--help` 不招供的东西，版本漂移时靠这个脚本判断契约是否还成立。
set -u
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
no(){ FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }
has(){ printf '%s' "$2" | grep -qF -- "$1"; }

for c in claude codex kimi; do
  command -v "$c" >/dev/null 2>&1 || { echo "缺少 $c，无法检测"; exit 2; }
done

echo "== 版本（下限：Claude 2.1.241 / Codex 0.149.0 / Kimi 0.38.0）"
printf '  claude %s\n  codex  %s\n  kimi   %s\n' \
  "$(claude --version 2>/dev/null)" "$(codex --version 2>/dev/null)" "$(kimi --version 2>/dev/null)"
echo "  高于下限不算问题；契约是否成立由下面的断言决定，不由版本号决定。"

echo "== Claude"
H=$(claude --help 2>&1)
for f in " -p, --print" "--output-format" "--permission-mode" "--allowedTools" "--resume"; do
  has "$f" "$H" && ok "claude --help 有 $f" || no "claude --help 缺 $f"
done
for m in dontAsk acceptEdits; do
  has "$m" "$H" && ok "--permission-mode 仍接受 $m" || no "--permission-mode 不再列出 $m"
done

echo "== Codex"
H=$(codex exec --help 2>&1)
for f in "--skip-git-repo-check" "--sandbox" "--json" "--output-last-message"; do
  has "$f" "$H" && ok "codex exec --help 有 $f" || no "codex exec --help 缺 $f"
done
H=$(codex review --help 2>&1)
has "--json" "$H" && no "codex review 现在有 --json 了（SKILL.md 说它没有）" || ok "codex review 仍无 --json"
has "--output-last-message" "$H" && no "codex review 现在有 -o 了" || ok "codex review 仍无 -o"
H=$(codex exec review --help 2>&1)
has "--json" "$H" && ok "codex exec review 有 --json（机器可读走这条）" || no "codex exec review 缺 --json"
# 非 git 且未信任的目录必须拒绝启动
D=$(mktemp -d); OUT=$(cd "$D" && codex exec "noop" </dev/null 2>&1 | head -5); rmdir "$D" 2>/dev/null
has "--skip-git-repo-check" "$OUT" \
  && ok "非 git 目录仍要求 --skip-git-repo-check" || no "非 git 目录不再拒绝启动（契约已过期）"

echo "== Kimi"
H=$(kimi --help 2>&1)
for f in "-S, --session" "--agent-file" "--output-format" "-p, --prompt"; do
  has "$f" "$H" && ok "kimi --help 有 $f" || no "kimi --help 缺 $f"
done
printf '%s' "$H" | grep -qE '^\s+-r[,[:space:]]' \
  && no "kimi --help 现在有 -r 了（SKILL.md 说它不是 flag）" || ok "kimi --help 仍无 -r"
# -p 与全部权限 flag 互斥，且是启动即拒（不消耗模型调用）
for f in --auto -y --yolo --plan; do
  OUT=$(kimi -p noop "$f" </dev/null 2>&1 | head -3)
  has "Cannot combine" "$OUT" && ok "kimi -p 仍拒绝 $f" || no "kimi -p 不再拒绝 $f（权限契约已变）"
done

if [ "${1:-}" = "--smoke" ]; then
  echo "== smoke（真跑，消耗模型调用）"
  J=$(claude -p "Reply with exactly: OK" --output-format json </dev/null 2>/dev/null)
  for k in result is_error terminal_reason session_id permission_denials; do
    has "\"$k\"" "$J" && ok "claude json 仍含 .$k" || no "claude json 缺 .$k"
  done
  SID=$(printf '%s' "$J" | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_id"])' 2>/dev/null)
  R=$(claude -p --resume "$SID" "Reply with exactly: OK2" --output-format json </dev/null 2>/dev/null)
  has '"is_error":false' "$R" && ok "claude --resume 可续跑" || no "claude --resume 失败"

  D=$(mktemp -d); T="$D/nope.txt"
  J=$(claude -p "Use the Write tool to create $T containing hi." --permission-mode dontAsk --output-format json </dev/null 2>/dev/null)
  [ -f "$T" ] && no "dontAsk 下写入没被拦住" || ok "dontAsk 下 Write 被拒"
  printf '%s' "$J" | grep -q '"permission_denials":\[{' && ok "被拒调用记入 .permission_denials" || no ".permission_denials 未记录被拒调用"

  E=$(codex exec --skip-git-repo-check --json "Reply with exactly: OK" </dev/null 2>/dev/null)
  has '"type":"thread.started"' "$E" && ok "codex --json 有 thread.started" || no "codex --json 缺 thread.started"
  has '"type":"agent_message"' "$E" && ok "codex --json 有 agent_message" || no "codex --json 缺 agent_message"

  K=$(kimi -p "Reply with exactly: OK" --output-format stream-json 2>/dev/null)
  has '"role":"assistant"' "$K" && ok "kimi stream-json 有 assistant 行" || no "kimi stream-json 缺 assistant 行"
  has '"type":"session.resume_hint"' "$K" && ok "kimi 收尾行带 session_id（续跑 id 出处）" || no "kimi 缺 session.resume_hint"

  A="$D/ro.md"; printf -- '---\ndescription: ro\ntools: [Read, Grep, Glob]\n---\nRead only.\n' > "$A"
  W="$D/w.txt"
  kimi -p "创建文件 $W，内容 hi。" --agent-file "$A" --output-format stream-json >/dev/null 2>&1
  [ -f "$W" ] && no "tools 白名单没能剥离写工具" || ok "tools 白名单确实剥离了写工具"
  rm -rf "$D"
fi

echo "== $PASS ok / $FAIL fail"
[ "$FAIL" -eq 0 ]
