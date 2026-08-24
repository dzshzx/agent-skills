#!/usr/bin/env bash
# 真实 harness 验证：在临时 workspace 里让 Claude Code 按**源** SKILL.md 跑一次 Converge，断言文件级结果。
# 用法：bash evals/live-check.sh   （计费：1 次 claude -p 真跑，约 2–5 分钟；全部落在 mktemp 目录，结束即删）
# 场景：repo-a 有 CLAUDE.md（刻意未跟踪）与 AGENTS.md（已跟踪）；config 声明 claude-code / codex 两个 owner；
#   shared.md 经 claude-code 的 entry_file @-import；CLAUDE.md 含一条与 shared.md 逐字相同的规则（shared-covered）
#   和一条项目专属规则；AGENTS.md 含跨 owner 引用 `@CLAUDE.md`（isolation 违规）和同一条项目专属规则；
#   docs/agents/notes.md 命中 off_limits。
# 断言（任一不成立即 FAIL，退出 1）：claude -p rc=0 且 result 非错误；模型确实 Read 了**源** SKILL.md（`Skill` 工具被禁、
#   `--add-dir` 放行源目录与临时目录——否则 -p 模式读不到 cwd 外的文件，模型会退而加载安装副本，源改了也照样绿）；
#   shared-covered 规则从 CLAUDE.md 消失；项目专属规则在 CLAUDE.md 与 AGENTS.md 都保留（sibling 相似 ≠ coverage）；
#   AGENTS.md 不再提及 CLAUDE.md；docs/agents/notes.md 字节不变；CLAUDE.md 仍未跟踪（未被 git add / commit）。
#   绿只证明这些断言；分类判断的其它分支它不证明。
set -u
SRC=$(cd "$(dirname "$0")/.." && pwd)
command -v claude >/dev/null 2>&1 || { echo "缺少 claude，无法检测"; exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
R="$T/ws/repo-a"; mkdir -p "$T/home/.claude" "$T/home/.codex" "$T/shared" "$T/config" "$R/docs/agents"
RULE='Reply in Simplified Chinese; keep commands, paths and identifiers verbatim.'
PROJ='The API contract for this repo lives in docs/api.md; read it before changing handlers.'
printf '%s\n' '# Shared behavior' '' "- $RULE" > "$T/shared/shared.md"
printf '%s\n' '# Claude entry' '' "@$T/shared/shared.md" > "$T/home/.claude/CLAUDE.md"
printf '%s\n' '# Codex entry' '' "Before any task, read $T/shared/shared.md in full." > "$T/home/.codex/AGENTS.md"
cat > "$T/config/sync-config.toml" <<EOF
[workspace]
project_globs = ["$T/ws/*"]
off_limits = ["**/docs/agents/**"]

[[shared_sources]]
path = "$T/shared/shared.md"
role = "stable behavior contract"
domain = "behavior"
load = "always"

[[agents]]
name = "claude-code"
entry_file = "$T/home/.claude/CLAUDE.md"
always_load_mode = "native"
project_instruction_file = "CLAUDE.md"

[[agents]]
name = "codex"
entry_file = "$T/home/.codex/AGENTS.md"
always_load_mode = "mandatory-entry-read"
project_instruction_file = "AGENTS.md"
EOF
printf '%s\n' '# repo-a (Claude Code)' '' "- $RULE" "- $PROJ" > "$R/CLAUDE.md"
printf '%s\n' '# repo-a (Codex)' '' 'Project rules: see @CLAUDE.md for the full list.' "- $PROJ" > "$R/AGENTS.md"
printf '%s\n' '# Agent workflow (owned elsewhere)' '' '- Run make check before committing.' > "$R/docs/agents/notes.md"
git -C "$R" init -q -b master && git -C "$R" add AGENTS.md docs \
  && git -C "$R" -c user.name=live-check -c user.email=live-check@localhost commit -q -m init
NOTES_BEFORE=$(sha256sum < "$R/docs/agents/notes.md")
cat > "$T/brief.md" <<EOF
Read $SRC/SKILL.md and follow it exactly — that source file, not any installed copy of the skill.
The machine config is $T/config/sync-config.toml; validate it first with
\`python3 $SRC/scripts/validate_config.py $T/config/sync-config.toml\` and use no other config.
Run **Converge** over the workspace that config declares. Execute directly wherever the skill says to
execute; wherever the skill says to ask or confirm, print the question and continue with everything else.
Commit with \`-c user.name=live-check -c user.email=live-check@localhost\`. Finish with a short report.
EOF
ALLOW='Bash(python3:*),Bash(git:*),Bash(cat:*),Bash(ls:*),Bash(rg:*),Bash(grep:*),Bash(sed:*),Bash(head:*),Bash(wc:*),Bash(diff:*),Bash(find:*),Bash(wt:*)'
( cd "$T/ws" && timeout 900 claude -p --permission-mode acceptEdits --allowedTools "$ALLOW" --disallowedTools Skill \
    --add-dir "$T" "$SRC" --output-format stream-json --verbose \
    "$(cat "$T/brief.md")" </dev/null >"$T/out.jsonl" 2>"$T/err" ); rc=$?
# stream-json → 一份摘要：最终 result 行 + 是否对源 SKILL.md 调过 Read
python3 - "$T/out.jsonl" "$SRC/SKILL.md" >"$T/parsed.json" <<'PY'
import json, sys
res, reads = {}, set()
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    try:
        o = json.loads(line)
    except ValueError:
        continue
    if o.get('type') == 'result':
        res = o
    elif o.get('type') == 'assistant':
        for b in (o.get('message') or {}).get('content') or []:
            if isinstance(b, dict) and b.get('type') == 'tool_use' and b.get('name') == 'Read':
                reads.add(str((b.get('input') or {}).get('file_path')))
print(json.dumps({'is_error': res.get('is_error'), 'terminal_reason': res.get('terminal_reason'),
                  'result': res.get('result') or '', 'read_src': sys.argv[2] in reads, 'reads': sorted(reads)}))
PY

PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
no(){ FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }
jfield(){ python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(str(d.get(sys.argv[2]))[:int(sys.argv[3])])' "$T/parsed.json" "$1" "$2" 2>/dev/null; }
if [ "$rc" -eq 0 ] && [ "$(jfield is_error 8)" = "False" ]; then ok "claude -p 运行成功（rc=0，result.is_error=false）"
else no "claude -p 失败（rc=$rc）：$(jfield terminal_reason 80) | $(tail -c 300 "$T/err" | tr '\n' ' ')"; fi
[ "$(jfield read_src 8)" = "True" ] && ok "模型 Read 了源 SKILL.md（不是安装副本）" || no "模型没有 Read 源 SKILL.md；它读过：$(jfield reads 300)"
grep -qF -- "$RULE" "$R/CLAUDE.md" && no "shared-covered 规则仍留在 CLAUDE.md" || ok "shared-covered 规则已从 CLAUDE.md 收敛"
grep -qF -- "$PROJ" "$R/CLAUDE.md" && ok "项目专属规则保留在 CLAUDE.md" || no "项目专属规则从 CLAUDE.md 被误删"
grep -qF -- "$PROJ" "$R/AGENTS.md" && ok "项目专属规则保留在 AGENTS.md（sibling 相似 ≠ coverage）" || no "项目专属规则从 AGENTS.md 被误删"
grep -q 'CLAUDE.md' "$R/AGENTS.md" && no "AGENTS.md 仍提及 CLAUDE.md（跨 owner 引用未清）" || ok "AGENTS.md 的跨 owner 引用已移除"
[ "$(sha256sum < "$R/docs/agents/notes.md")" = "$NOTES_BEFORE" ] && ok "off_limits 文件字节不变" || no "off_limits 文件被改动"
st=$(git -C "$R" status --porcelain -- CLAUDE.md)
case "$st" in '??'*) ok "CLAUDE.md 仍未跟踪（未被 git add / commit）";; *) no "CLAUDE.md 的 git 状态变为 '${st:-clean/tracked}'（应保持 ??）";; esac
echo "-- 模型报告（前 600 字）--"; jfield result 600; echo
echo "== $PASS ok / $FAIL fail"
[ "$FAIL" -eq 0 ]
