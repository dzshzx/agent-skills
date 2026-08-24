#!/usr/bin/env bash
# 真实 harness 验证：在一个仓里让 Codex 真派子代理，从**本次会话**的 rollout 核对路由字段。
# 用法：bash evals/live-check.sh [repo-dir]   （默认当前目录；只读沙箱；约 2 分钟）
# 工件：仓库内不留任何文件；$CODEX_HOME/sessions 下会新增本次 parent 与各 child 的 rollout（Codex 自己的会话记录）。
# 关联（不看别的会话，不按顺序配对）：
#   `codex exec --json` 的 thread.started 事件给出本次 parent thread id → 只读该 id 的 rollout；
#   每次 spawn_agent 的返回值 {task_name:"/root/<name>", nickname} 对应 child rollout 的
#   session_meta.source.subagent.thread_spawn.{agent_path, agent_nickname}，且 parent_thread_id 必须等于本次 id。
# 断言（任一不成立即 FAIL，退出 1）：
#   至少一次 spawn_agent；每次 spawn 显式 model+reasoning_effort、effort ∉ {max,ultra}、fork_turns 存在且 ≠ all、
#   task_name 合规、agent_type ∈ schema 角色、不传 service_tier；每次 spawn 恰好对上一份 child rollout；
#   child 实际 turn_context 的 model/effort 与 spawn 参数相等，agent_role 与 agent_type 相等（未传则两边都空）。
set -u
REPO=${1:-$PWD}
EVENTS=$(mktemp); ERR=$(mktemp); trap 'rm -f "$EVENTS" "$ERR"' EXIT
MARK=$(date +%s)
PROMPT='同时做两件互不相干的只读事情，请真的用 spawn_agent 派子代理并行去做（不要改文件）：A) 列出本仓顶层目录下每个 markdown 文件的一级标题；B) 检查 README.md 里相对路径链接是否指向仓内存在的文件。两个子代理都回来后给一份汇总。'
if ! codex exec -C "$REPO" -s read-only --skip-git-repo-check --json "$PROMPT" >"$EVENTS" 2>"$ERR"; then
  echo "FAIL: codex exec 失败，stderr 尾巴："; tail -c 600 "$ERR"; echo; exit 2
fi
python3 - "$EVENTS" "$MARK" <<'PY'
import glob, json, os, re, sys

events, mark = sys.argv[1], float(sys.argv[2])
home = os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex')
sessions = os.path.join(home, 'sessions')

def D(x):
    return x if isinstance(x, dict) else {}

def rows(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except ValueError:
                continue

def as_dict(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = None
    return D(value)

# 1. 本次 parent thread id 来自 --json 事件流
thread_id, kinds = None, set()
for ev in rows(events):
    kinds.add(str(ev.get('type')))
    if ev.get('type') == 'thread.started':
        thread_id = ev.get('thread_id')
if not thread_id:
    print('FAIL: --json 事件流里没有 thread.started（看到的事件类型：%s）' % ', '.join(sorted(kinds)))
    sys.exit(1)

# 2. parent rollout：文件名以 thread id 结尾，必须恰好一份
parents = glob.glob(os.path.join(sessions, '**', f'rollout-*-{thread_id}.jsonl'), recursive=True)
if len(parents) != 1:
    print(f'FAIL: thread {thread_id} 的 rollout 应恰好一份，找到 {len(parents)} 份')
    sys.exit(1)
parent = parents[0]

# 3. schema 角色：内置 + 本机 config.toml 的 [agents.<name>]
roles = {'explorer', 'worker', 'default'}
cfg = os.path.join(home, 'config.toml')
if os.path.exists(cfg):
    import tomllib
    with open(cfg, 'rb') as fh:
        roles |= set(D(tomllib.load(fh).get('agents')).keys())

# 4. parent 里的 spawn 调用与其返回值，按 call_id 配对
spawns, handles = {}, {}
for o in rows(parent):
    p = D(o.get('payload'))
    if o.get('type') != 'response_item':
        continue
    if p.get('type') == 'function_call' and p.get('name') == 'spawn_agent':
        spawns[p.get('call_id')] = as_dict(p.get('arguments'))
    elif p.get('type') == 'function_call_output' and p.get('call_id') in spawns:
        out = as_dict(p.get('output'))
        if out.get('task_name'):
            handles[p['call_id']] = (out['task_name'], out.get('nickname'))
if not spawns:
    print('FAIL: 本次会话没有发生 spawn_agent 调用')
    sys.exit(1)

# 5. child rollout：只认 parent_thread_id == 本次 id；mtime 只是缩小扫描范围的粗筛
children = {}
for f in glob.glob(os.path.join(sessions, '**', 'rollout-*.jsonl'), recursive=True):
    if f == parent or os.path.getmtime(f) < mark - 5:
        continue
    meta, turn = None, {}
    for o in rows(f):
        p = D(o.get('payload'))
        if o.get('type') == 'session_meta':
            meta = p
            if meta.get('parent_thread_id') != thread_id:
                break
        elif o.get('type') == 'turn_context':
            turn = {'model': p.get('model'), 'effort': p.get('effort')}
            break
    if not meta or meta.get('parent_thread_id') != thread_id:
        continue
    spawn = D(D(D(meta.get('source')).get('subagent')).get('thread_spawn'))
    children[(spawn.get('agent_path'), spawn.get('agent_nickname'))] = {**turn, 'role': spawn.get('agent_role')}

# 6. 逐条断言
ok = True
def fail(msg):
    global ok
    ok = False
    print('  FAIL:', msg)

print(f'parent thread {thread_id}  spawn_agent {len(spawns)} 次  child rollout {len(children)} 份')
print(f"{'task_name':28s} {'model':14s} {'effort':7s} {'role':10s} {'fork_turns':10s}  child 实际 model/effort/role")
for cid, s in spawns.items():
    tn, m, e, r, ft = s.get('task_name', ''), s.get('model'), s.get('reasoning_effort'), s.get('agent_type'), s.get('fork_turns')
    h = handles.get(cid)
    c = children.get(h) if h else None
    actual = f"{c['model']}/{c['effort']}/{c['role']}" if c else '(无对应 child rollout)'
    print(f'{tn:28s} {str(m):14s} {str(e):7s} {str(r):10s} {str(ft):10s}  {actual}')
    if not m or not e: fail(f'{tn}: model/reasoning_effort 缺失')
    if e in ('max', 'ultra'): fail(f'{tn}: effort 顶档 {e}')
    if ft in (None, 'all'): fail(f'{tn}: fork_turns=all 或缺失')
    if not re.fullmatch(r'[a-z0-9_]+', tn or ''): fail(f'{tn!r}: task_name 不合规')
    if r and r not in roles: fail(f'{tn}: 未知角色 {r}')
    if 'service_tier' in s: fail(f'{tn}: 主动传了 service_tier')
    if not h:
        fail(f'{tn}: spawn_agent 没有返回 task_name/nickname，无法关联 child'); continue
    if not c:
        fail(f'{tn}: 没有 parent_thread_id={thread_id} 且 agent_path={h[0]} nickname={h[1]} 的 child rollout'); continue
    if c.get('model') != m: fail(f'{tn}: child 实际 model {c.get("model")} ≠ 参数 {m}')
    if c.get('effort') != e: fail(f'{tn}: child 实际 effort {c.get("effort")} ≠ 参数 {e}')
    if (c.get('role') or None) != (r or None): fail(f'{tn}: child agent_role {c.get("role")} ≠ 参数 agent_type {r}')
orphans = set(children) - set(handles.values())
if orphans:
    fail(f'{len(orphans)} 份 child rollout 不对应任何 spawn 调用: {sorted(orphans)}')
print('RESULT:', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
PY
