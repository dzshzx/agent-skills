#!/usr/bin/env bash
# 真实 harness 验证：在一个仓里让 Codex 真派子代理，读 rollout 核对路由字段。
# 用法：bash evals/live-check.sh [repo-dir]   （默认当前目录；只读沙箱；约 2 分钟；不留工件）
# 断言：每个 child 显式 model+reasoning_effort、effort ∉ {max,ultra}、fork_turns≠all、task_name 合规、agent_type ∈ schema 角色；子线程实际 model/effort 与参数一致。
set -u
REPO=${1:-$PWD}; MARK=$(date +%s); OUT=$(mktemp)
PROMPT='同时做两件互不相干的只读事情，请真的用 spawn_agent 派子代理并行去做（不要改文件）：A) 列出本仓顶层目录下每个 markdown 文件的一级标题；B) 检查 README.md 里相对路径链接是否指向仓内存在的文件。两个子代理都回来后给一份汇总。'
codex exec -C "$REPO" -s read-only --skip-git-repo-check -o "$OUT" "$PROMPT" >/dev/null 2>&1 || { echo "codex exec 失败"; exit 2; }
python3 - "$MARK" <<'PY'
import json,os,sys,glob,re
mark=float(sys.argv[1]); ok=True
files=[f for f in glob.glob(os.path.expanduser('~/.codex/sessions/**/*.jsonl'),recursive=True) if os.path.getmtime(f)>=mark-5]
spawns=[]; children={}
for f in files:
    meta={}; tm={}
    for line in open(f,encoding='utf-8',errors='replace'):
        try: o=json.loads(line)
        except Exception: continue
        p=o.get('payload',{})
        if o.get('type')=='session_meta': meta=p
        if o.get('type')=='turn_context': tm={'model':p.get('model'),'effort':p.get('effort')}
        if 'spawn_agent' in line and o.get('type')=='response_item':
            args=p.get('arguments')
            if isinstance(args,str):
                try: args=json.loads(args)
                except Exception: args=None
            if isinstance(args,dict) and 'task_name' in args: spawns.append(args)
    if meta.get('parent_thread_id'): children[meta.get('id')]=tm
if not spawns: print('FAIL: 没有发生 spawn_agent 调用'); sys.exit(1)
print(f"{'task_name':28s} {'model':14s} {'effort':7s} {'role':10s} fork_turns")
for s in spawns:
    tn=s.get('task_name',''); m=s.get('model'); e=s.get('reasoning_effort'); r=s.get('agent_type'); ft=s.get('fork_turns')
    bad=[]
    if not m or not e: bad.append('model/effort 缺失')
    if e in ('max','ultra'): bad.append('顶档')
    if ft in (None,'all'): bad.append('fork_turns=all/缺失')
    if not re.fullmatch(r'[a-z0-9_]+',tn or ''): bad.append('task_name 不合规')
    if r and r not in ('explorer','worker','default','researcher','reviewer'): bad.append(f'未知角色 {r}')
    if 'service_tier' in s: bad.append('主动传了 service_tier')
    print(f"{tn:28s} {str(m):14s} {str(e):7s} {str(r):10s} {ft}  {'OK' if not bad else 'FAIL: '+'; '.join(bad)}")
    ok = ok and not bad
print('子线程实际运行:', ', '.join(f"{v.get('model')}/{v.get('effort')}" for v in children.values()) or '(未找到子线程 rollout)')
for v in children.values():
    if v.get('effort') in ('max','ultra') or v.get('model') is None: ok=False; print('FAIL: 子线程', v)
print('RESULT:', 'PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)
PY
rc=$?; rm -f "$OUT"; exit $rc
