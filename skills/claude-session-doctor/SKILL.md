---
name: claude-session-doctor
description: >-
  Diagnose and rescue local Claude Code sessions via csctl (>= 0.8.0): list
  live sessions, fix resume lookup/rejection problems, and print the exact
  resume command for past sessions across directories. Use when a Claude
  session cannot be resumed or found, /resume is rejected or unhelpful, the
  user asks which sessions are running, wants to reattach/接回/接管 a
  session, or is confused by bg agent, daemon, bridge, or remote-control
  behavior. Triggers: 会话找不到, 接回会话, 串会话, 会话好乱, /resume 不行,
  resume 被拒, 哪些会话在跑, can't resume, session not showing.
---

# Claude Session Doctor (csctl)

诊断与接回本机（Linux/WSL）的 Claude Code 会话。会话形态多样、活/死判定互不相通，原生 `/resume` 还会隐藏会话——本 skill 给确定的命令，别让模型现编。

适用 **csctl >= 0.8.0**。0.8.0 起 headless CLI 收窄为四个入口：`csctl`（无参启动 TUI）、`csctl agents`、`csctl resume [...]`、`csctl resume --take-over <sid>`；旧版本的 `csctl prune` / `csctl env` / `csctl skill` / `csctl rc *` 在 0.8.0 已整体移除，等价能力全部收进 TUI（见下）。

所有能力由 `csctl`（PyPI 包 `cc-session-control`）提供，任意目录可跑。没有 `csctl` 时先装：`uv tool install cc-session-control`；升级：`uv tool upgrade cc-session-control`。

## 交互式 TUI

```bash
csctl          # 三个 tab（tmux-first，启动落在项目 tab）：项目（launcher）/ 会话 / 后台 agent；清理在会话 tab 的子菜单
```

项目 tab（launcher）键位：`Enter` 在项目自己的 per-project tmux session 里新建 `claude` 并进入（不杀不确认）· `o` 启动 Remote Control（RC server，需项目有效受信任）· `c` 切换该项目的自动远控（`remoteControlAtStartup`）。

会话 tab 键位：方向键移动 · `/` 过滤 · `Enter` tmux 接回（主操作：恢复进 per-project tmux 窗口并进入，断线不死；已驻留 ⧉ 会话就地进入；接活会话先确认）· `t` 终端接回（裸终端兜底，真接续自动重新判活并安全接管）· `f` 分叉进 tmux · `s` 停止活会话(确认) · `R` 转后台（进 tmux 不进入、不开远控，留在 csctl）· `d` 删除已结束会话 · `y` 复制命令到剪贴板 · `h` 桥接/SDK 显隐 · `c` 清理子菜单（见下）· `r` 刷新 · `q` 退出。接回 = 离开 csctl（attach 进 tmux 或 exec 成 claude）。

后台 tab 键位：`Enter` tmux 接回 · `t` 终端接回 · `s` 停止 · `R` 重启（respawn）· `d` 删除已结束 job。

## 心智模型：会话形态

| 形态 | 怎么产生 | 判活 |
|------|---------|------|
| **local** 前台 | 裸 `claude` 起的交互会话 | `claude agents` (kind=interactive) |
| **remote-control / bridge** | `claude --remote-control` 或 claude.ai 网页控制本机会话（transcript 带 `bridge-session` + `cse_` 云中继，**计算仍在本机**） | `claude agents` + 网页 |
| **bg agent** | detach 残留 / fleet 视图派生 / SDK 子 agent | `claude agents` (kind=background) |

**会话与后台 agent 的判活以 csctl 的组合结果为准**：它合并
`claude agents --json`、session/job registry 与 `/proc`，并用进程存在性清除
已经死亡但仍被 CLI 列出的 pid。Project RC Server 不出现在
`claude agents --json`，只能在 Linux/WSL 通过 `/proc` 识别；没有 `/proc`
时破坏性操作会降级拒绝。bg agent 把 daemon 钉住是正常的，跑完自动放。

## 看现在有哪些会话/后台 agent 在跑

```bash
csctl agents   # 后台 agent 一览（live/settled、tempo、目录）
```

跨目录的会话清单（含隐藏会话）用 `csctl resume`（见下一节）；0.8.0 起没有单独的 headless bridge-环境列表命令——想看当前绑定的 Remote Control（session/项目 RC server）状态，进 TUI 项目 tab，或在会话内用 `/remote-control`。

status=busy/working 的**别杀**。

## 接回会话 / 修「/resume 找不到或被拒」

**先理解为什么找不到**（原生 `/resume` 两条硬规则）：

1. 会话按 cwd 存放在 `~/.claude/projects/<编码后的cwd>/<id>.jsonl`，`/resume` 和 `--resume` **都只在当前目录里找**。在错的目录里，连显式 `claude --resume <完整id>` 都会报 `No conversation found with session ID`——它**不会**自动切到会话原目录。所以接回前**必须先 `cd` 回会话原目录**（这就是 `csctl resume` 给的命令带 `cd` 前缀的原因）。
2. 同目录下，选择器还会隐藏带 `sdk-ts` / `bridge-session` 标记的会话（远程控制/网页/SDK 子 agent 建的）。但**在正确目录里显式 `claude --resume <完整id>` 不受这个过滤**，照样进得去。

**别跟选择器较劲，直接：**

```bash
csctl resume [关键词]            # 第1页(每页20条)，跨目录、含隐藏会话
csctl resume [关键词] --page 2   # 翻页
csctl resume [关键词] --limit 50 # 改每页条数
csctl resume [关键词] --all      # 不分页全列
```

跨目录扫全量 transcript（含隐藏会话），标 live/dead，打印可直接复制的接续命令。**关键词默认搜 transcript 正文**（sid/目录/标题先匹配，没命中再扫正文）——"标题里没有、正文里聊过"的会话也能找到（代价：常见词命中会偏多，用更具体的词缩小）。cwd 只从 transcript 读取，**从不靠目录名反推**，`cd` 路径可信；无正文的空壳会话（纯 bridge 占位）自动过滤。

**接回规则**（`csctl resume` 已按死活自动给对应命令，手动时记住）：

- 会话**已死**（不在 `claude agents`）→ `cd <dir> && claude --resume <id>`，全历史真接续。
- 会话**还活着** → 直接 `--resume` 会被拒。使用列表打印的 `csctl resume --take-over <id>`：它只保存稳定的 session id，真正执行时重新扫描 pid、`procStart`、cwd 与 current 状态，证据完整且目标唯一时才经统一安全接管路径终止旧进程并接续。不要手写或保存针对快照 PID 的终止命令；PID 复用或会话状态变化可能伤及无关进程。**不想中断**就用 TUI 查看并选择合适操作。
- 只有**想要一份分叉副本**（保留原会话另起一条）时才用 `claude --resume <id> --fork-session`，或 TUI 会话 tab 的 `f`（分叉进 tmux）。
- `csctl resume` 对**你当前所在的会话**只做标注，不给可执行接回命令；`--take-over` 执行时也会重新识别并拒绝当前会话。

## 接管远程控制 / 网页会话到本地

`claude --remote-control` 或 claude.ai 网页控制的会话，在本机就是一个普通的**活会话**（会进 `claude agents`）。想搬到本地终端接管，照「接回规则」当"还活着"处理即可；`csctl resume` 已自动给出对应命令。TUI 里选中后 `Enter` tmux 接回（或 `t` 终端接回）。会话 tab **不提供**带 `--remote-control` 的 relaunch（每个远控进程都会新铸一个云端环境）；要恢复远控暴露，用项目 tab 的 `o`（启动 RC）/`c`（切换自动远控）或会话内 `/remote-control`。

## 清理残留 bg agent

- 关窗口 / Ctrl+C 只是 **detach**，会话留成常驻 bg agent；`/exit` 才真正结束。
- 清掉**所有** bg agent（让 daemon idle-exit）：`claude daemon stop --any`（谨慎，会停所有；这是原生 `claude` 命令，不是 `csctl`）。

## 清理空/极短会话、孤儿目录、僵尸 pid 文件

0.8.0 起清理**只在 TUI 里**（`csctl prune` headless 子命令已移除）。进会话 tab 按 `c` 打开清理子菜单：

- **按提问数** prune 空壳/极短会话 transcript。
- **sid-keyed orphan** 清理（`session-env`/`file-history`/`tasks`/`uploads` 里不属于任何已知会话的残留目录）。
- **pid-keyed zombie** 清理（`sessions/<pid>.json` 指向已死进程的残留文件）。
- **age-keyed** 清理（`shell-snapshots`/`telemetry`/`plans`/`backups`/`paste-cache` 超龄目录）。

所有清理都是 **preview 优先**：先进子菜单看清单，再按一次 `Enter` 确认执行；安全边界不变——永不删**存活会话**、**当前会话**，无法判定 current 时（无 `/proc`）直接拒绝而不是硬删。

## 本 skill 的安装/升级

本 skill 不再随 `csctl` 包分发（0.8.0 移除了 `csctl skill install/uninstall`）。它来自 `dzshzx/agent-skills` 仓库，用 [skills CLI](https://skills.sh) 安装/更新：

```bash
npx skills add dzshzx/agent-skills --skill=claude-session-doctor
```
