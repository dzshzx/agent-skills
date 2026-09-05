#!/usr/bin/env bash
# 真实 harness 验证：在临时 workspace 里让 Claude Code 按**源** SKILL.md 跑一次 Converge 和一次 Add-or-update，断言文件级结果。
# 用法：bash evals/live-check.sh   （计费：2 次 claude -p 真跑，约 3–8 分钟；全部落在 mktemp 目录，结束即删）
# 隔离：CLAUDE_CONFIG_DIR 指向临时目录（只复制 ~/.claude/.credentials.json 进去），所以本机真实的用户级 CLAUDE.md、
#   settings、hooks、MCP 都不进被测 run；config 里 claude-code 的 entry_file 就是该临时目录的 CLAUDE.md——它确实被加载。
# 场景：repo-a 有 CLAUDE.md 与 AGENTS.md（都已跟踪）；config 声明 claude-code / codex 两个 owner；shared.md 经 claude-code
#   的 entry_file @-import、经 codex 的 entry 无条件读取指令覆盖；CLAUDE.md 含一条与 shared.md 逐字相同的规则（shared-covered）
#   和一条项目专属规则；AGENTS.md 含跨 owner 引用 `@CLAUDE.md`（isolation 违规）和同一条项目专属规则；docs/agents/notes.md
#   命中 off_limits。repo-b 的 CLAUDE.md **未跟踪**且含同一条 shared-covered 规则——任务已授权收敛，Git 状态本身不增加确认点。
# 断言 A（Converge，任一不成立即 FAIL）：claude -p rc=0 且 result 非错误；临时 CLAUDE_CONFIG_DIR 被使用（其中生成 .claude.json）；
#   模型 Read 了**源** SKILL.md（`Skill` 工具被禁、`--add-dir` 放行源目录与临时目录）；模型真跑了
#   `validate_config.py` 与 `git diff`（从 stream-json 的 Bash 调用里核对）；提交方式由执行方选择，结果范围在下文校验；repo-a：shared-covered 规则从
#   CLAUDE.md 消失、项目专属规则在 CLAUDE.md 与 AGENTS.md 都保留（sibling 相似 ≠ coverage）、AGENTS.md 不再提及 CLAUDE.md、
#   两个 surface 都已提交且工作树干净、init 之后的提交只触及这两个文件；docs/agents/notes.md 字节不变；repo-b：shared-covered
#   规则被移除、文件仍未跟踪，且模型报告里提到了 repo-b。
# 断言 B（Add-or-update）：rc=0 且非错误；模型 Read 了源 SKILL.md；新规则写进了共享源 shared.md；没有写进任何项目 surface
#   （repo-a 工作树仍干净、repo-b CLAUDE.md 字节不变）；两个 entry 的加载路由行仍在。
# 绿只证明这些断言；分类判断的其它分支它不证明。
set -u
SRC=$(cd "$(dirname "$0")/.." && pwd)
command -v claude >/dev/null 2>&1 || { echo "缺少 claude，无法检测"; exit 2; }
CRED="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json"
[ -f "$CRED" ] || { echo "缺少 $CRED，无法在隔离的 CLAUDE_CONFIG_DIR 里认证"; exit 2; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
CC="$T/cc"; A="$T/ws/repo-a"; B="$T/ws/repo-b"
mkdir -p "$CC" "$T/home/.codex" "$T/shared" "$T/config" "$A/docs/agents" "$B"
cp "$CRED" "$CC/"
RULE='Reply in Simplified Chinese; keep commands, paths and identifiers verbatim.'
PROJ='The API contract for this repo lives in docs/api.md; read it before changing handlers.'
RULE2='Prefer early returns over nested conditionals.'
printf '%s\n' '# Shared behavior' '' "- $RULE" > "$T/shared/shared.md"
printf '%s\n' '# Claude entry' '' "@$T/shared/shared.md" > "$CC/CLAUDE.md"
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
entry_file = "$CC/CLAUDE.md"
always_load_mode = "native"
project_instruction_file = "CLAUDE.md"

[[agents]]
name = "codex"
entry_file = "$T/home/.codex/AGENTS.md"
always_load_mode = "mandatory-entry-read"
project_instruction_file = "AGENTS.md"
EOF
GITC=(-c user.name=live-check -c user.email=live-check@localhost)
printf '%s\n' '# repo-a (Claude Code)' '' "- $RULE" "- $PROJ" > "$A/CLAUDE.md"
printf '%s\n' '# repo-a (Codex)' '' 'Project rules: see @CLAUDE.md for the full list.' "- $PROJ" > "$A/AGENTS.md"
printf '%s\n' '# Agent workflow (owned elsewhere)' '' '- Run make check before committing.' > "$A/docs/agents/notes.md"
git -C "$A" init -q -b master && git -C "$A" add CLAUDE.md AGENTS.md docs && git -C "$A" "${GITC[@]}" commit -q -m init
A_INIT=$(git -C "$A" rev-parse HEAD)
printf '%s\n' '# repo-b' > "$B/README.md"
git -C "$B" init -q -b master && git -C "$B" add README.md && git -C "$B" "${GITC[@]}" commit -q -m init
printf '%s\n' '# repo-b (Claude Code, untracked)' '' "- $RULE" > "$B/CLAUDE.md"
NOTES_BEFORE=$(sha256sum < "$A/docs/agents/notes.md")
ALLOW='Bash(python3:*),Bash(git:*),Bash(cat:*),Bash(ls:*),Bash(rg:*),Bash(grep:*),Bash(sed:*),Bash(head:*),Bash(wc:*),Bash(diff:*),Bash(find:*)'
COMMON="Read $SRC/SKILL.md and follow it exactly — that source file, not any installed copy of the skill.
The machine config is $T/config/sync-config.toml; validate it first with
\`python3 $SRC/scripts/validate_config.py $T/config/sync-config.toml\` and use no other config.
The task authorizes the requested writes in the config-declared scope; do not add another confirmation point.
Do not touch off_limits paths or perform unrelated destructive actions. Commit with
\`-c user.name=live-check -c user.email=live-check@localhost\`. Finish with a short report."
printf '%s\n' "$COMMON" 'Task: run **Converge** over the workspace that config declares.' > "$T/brief-a.md"
printf '%s\n' "$COMMON" "Task: **Add or update** — add the rule \"$RULE2\" as a shared, always-loaded behavior rule for every configured agent." > "$T/brief-b.md"

# dispatch <brief> <out.jsonl>：隔离的 CLAUDE_CONFIG_DIR 里跑一次 claude -p；返回其 rc
dispatch(){ ( cd "$T/ws" && CLAUDE_CONFIG_DIR="$CC" timeout 900 claude -p --permission-mode acceptEdits --allowedTools "$ALLOW" \
    --disallowedTools Skill --add-dir "$T" "$SRC" --output-format stream-json --verbose \
    "$(cat "$1")" </dev/null >"$2" 2>"$2.err" ); }
# parse <out.jsonl> <parsed.json>：最终 result 行 + Read 过的路径 + Bash 跑过的命令
parse(){ python3 - "$1" "$SRC/SKILL.md" >"$2" <<'PY'
import json, sys
res, reads, cmds = {}, set(), []
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    try:
        o = json.loads(line)
    except ValueError:
        continue
    if o.get('type') == 'result':
        res = o
    elif o.get('type') == 'assistant':
        for b in (o.get('message') or {}).get('content') or []:
            if not (isinstance(b, dict) and b.get('type') == 'tool_use'):
                continue
            inp = b.get('input') or {}
            if b.get('name') == 'Read':
                reads.add(str(inp.get('file_path')))
            elif b.get('name') == 'Bash':
                cmds.append(str(inp.get('command')))
print(json.dumps({'is_error': res.get('is_error'), 'terminal_reason': res.get('terminal_reason'),
                  'result': res.get('result') or '', 'read_src': sys.argv[2] in reads, 'reads': sorted(reads),
                  'cmds': cmds}))
PY
}
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
no(){ FAIL=$((FAIL+1)); printf '  FAIL %s\n' "$1"; }
jfield(){ python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(str(d.get(sys.argv[2]))[:int(sys.argv[3])])' "$1" "$2" "$3" 2>/dev/null; }
# ran <parsed.json> <regex>：某条 Bash 调用匹配该正则（git 允许带 -C <repo> / -c key=value）
ran(){ python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if any(re.search(sys.argv[2], c) for c in d["cmds"]) else 1)' "$1" "$2" 2>/dev/null; }
# gitcmds <parsed.json>：打印含 git 的 Bash 调用（失败取证用）
gitcmds(){ python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(" | ".join(c.replace("\n"," ")[:160] for c in d["cmds"] if "git" in c))' "$1" 2>/dev/null; }
mentions(){ python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if sys.argv[2] in d["result"] else 1)' "$1" "$2" 2>/dev/null; }

echo "== A. Converge"
dispatch "$T/brief-a.md" "$T/a.jsonl"; rc=$?
parse "$T/a.jsonl" "$T/a.json"; P="$T/a.json"
if [ "$rc" -eq 0 ] && [ "$(jfield "$P" is_error 8)" = "False" ]; then ok "claude -p 运行成功（rc=0，result.is_error=false）"
else no "claude -p 失败（rc=$rc）：$(jfield "$P" terminal_reason 80) | $(tail -c 300 "$T/a.jsonl.err" | tr '\n' ' ')"; fi
[ -f "$CC/.claude.json" ] && ok "隔离的 CLAUDE_CONFIG_DIR 被使用（生成了 .claude.json；本机用户级 CLAUDE.md/settings/hooks 未进入 run）" || no "CLAUDE_CONFIG_DIR 未被使用"
[ "$(jfield "$P" read_src 8)" = "True" ] && ok "模型 Read 了源 SKILL.md（不是安装副本）" || no "模型没有 Read 源 SKILL.md；它读过：$(jfield "$P" reads 300)"
for c in 'validate_config\.py' 'git(\s+-[cC]\s*\S+)*\s+diff\b'; do
  ran "$P" "$c" && ok "SKILL.md 的命令行真跑过：$c" || no "SKILL.md 的命令行没跑：$c；git 调用：$(gitcmds "$P")"
done
grep -qF -- "$RULE" "$A/CLAUDE.md" && no "repo-a：shared-covered 规则仍留在 CLAUDE.md" || ok "repo-a：shared-covered 规则已从 CLAUDE.md 收敛"
grep -qF -- "$PROJ" "$A/CLAUDE.md" && ok "repo-a：项目专属规则保留在 CLAUDE.md" || no "repo-a：项目专属规则从 CLAUDE.md 被误删"
grep -qF -- "$PROJ" "$A/AGENTS.md" && ok "repo-a：项目专属规则保留在 AGENTS.md（sibling 相似 ≠ coverage）" || no "repo-a：项目专属规则从 AGENTS.md 被误删"
grep -q 'CLAUDE.md' "$A/AGENTS.md" && no "repo-a：AGENTS.md 仍提及 CLAUDE.md（跨 owner 引用未清）" || ok "repo-a：AGENTS.md 的跨 owner 引用已移除"
st=$(git -C "$A" status --porcelain); touched=$(git -C "$A" diff --name-only "$A_INIT" HEAD | sort | tr '\n' ' ')
[ -z "$st" ] && [ "$touched" = "AGENTS.md CLAUDE.md " ] \
  && ok "repo-a：两个 surface 都已提交、工作树干净、init 之后的提交只触及 AGENTS.md CLAUDE.md" \
  || no "repo-a：提交状态不符（status='${st:-clean}'，提交触及='${touched}'）"
[ "$(sha256sum < "$A/docs/agents/notes.md")" = "$NOTES_BEFORE" ] && ok "repo-a：off_limits 文件字节不变" || no "repo-a：off_limits 文件被改动"
stb=$(git -C "$B" status --porcelain -- CLAUDE.md)
! grep -qF -- "$RULE" "$B/CLAUDE.md" && case "$stb" in '??'*) true;; *) false;; esac \
  && ok "repo-b：shared-covered 规则已移除，CLAUDE.md 仍未跟踪" || no "repo-b：规则未收敛或 git 状态变为 '${stb:-clean/tracked}'"
mentions "$P" 'repo-b' && ok "repo-b：模型报告提到了已执行的收敛" || no "repo-b：模型报告没有提到 repo-b"
B_AFTER=$(sha256sum < "$B/CLAUDE.md")
echo "-- A 模型报告（前 500 字）--"; jfield "$P" result 500; echo

echo "== B. Add or update"
dispatch "$T/brief-b.md" "$T/b.jsonl"; rc=$?
parse "$T/b.jsonl" "$T/b.json"; P="$T/b.json"
if [ "$rc" -eq 0 ] && [ "$(jfield "$P" is_error 8)" = "False" ]; then ok "claude -p 运行成功（rc=0，result.is_error=false）"
else no "claude -p 失败（rc=$rc）：$(jfield "$P" terminal_reason 80) | $(tail -c 300 "$T/b.jsonl.err" | tr '\n' ' ')"; fi
[ "$(jfield "$P" read_src 8)" = "True" ] && ok "模型 Read 了源 SKILL.md" || no "模型没有 Read 源 SKILL.md；它读过：$(jfield "$P" reads 300)"
grep -qF -- "$RULE2" "$T/shared/shared.md" && ok "新规则写进了共享源 shared.md" || no "新规则没有进入 shared.md"
! grep -qF -- "$RULE2" "$A/CLAUDE.md" "$A/AGENTS.md" "$B/CLAUDE.md" && ok "新规则没有写进任何项目 surface" || no "新规则被写进了项目 surface"
[ -z "$(git -C "$A" status --porcelain)" ] && [ "$(sha256sum < "$B/CLAUDE.md")" = "$B_AFTER" ] \
  && ok "Add-or-update 范围只在 [[agents]] 条目：repo-a 工作树仍干净、repo-b CLAUDE.md 字节不变" || no "Add-or-update 碰了项目仓"
grep -qF -- "@$T/shared/shared.md" "$CC/CLAUDE.md" && grep -qF -- "read $T/shared/shared.md in full" "$T/home/.codex/AGENTS.md" \
  && ok "两个 entry 的加载路由行仍在" || no "entry 的加载路由行被改坏"
echo "-- B 模型报告（前 400 字）--"; jfield "$P" result 400; echo
echo "== $PASS ok / $FAIL fail"
[ "$FAIL" -eq 0 ]
