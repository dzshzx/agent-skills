# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 这个仓库是什么

一组遵循 [Agent Skills](https://agentskills.io) 开放标准的可复用 agent skill，可经 `npx skills add dzshzx/agent-skills` 跨 AI 编码 agent（Claude Code、Codex、Cursor……）安装。每个 skill 是 `skills/<name>/` 下的一个目录，含一个 `SKILL.md`（YAML frontmatter：`name` + `description`），外加可选的 `references/`、`scripts/`、`evals/`（每个 skill 必备的 `live-check.sh` 真跑门；`evals.json` 是 Codex 用的参考题库）和 `agents/`（per-agent 接口元数据，如 `agents/openai.yaml`）。

这里的 skill 是 **prompt-instructions-as-product**：SKILL.md 正文即交付物，对它的编辑就是对每个安装它的 agent 的行为改动。

## 设计规则（强制，来自 README）

- **SKILL.md 内不放机器专属事实。** 路径、主机名和机器拓扑放在 per-machine config 文件里（见 `skills/sync-agents-instructions/references/config-example.toml`），或相对 skill 目录解析（Claude Code 上用 `${CLAUDE_SKILL_DIR}`；其他环境用「包含本 SKILL.md 的目录」）。
- **平台事实可以；机器事实不行。** skill 可以依赖某个 agent 平台如何存储数据，但绝不依赖某一台机器的布局。若某改动会把探得的拓扑硬编码进 SKILL.md，改为放进 config schema/example。
- 给 `sync-agents-instructions` 增加对一个新 agent 的支持，意味着往 machine config 里加一条 `[[agents]]` 条目——SKILL.md 正文必须保持 agent-generic。
- Release 候选先合入 `master`，等待该同一 SHA 的 CI 通过，再创建匹配的带注解
  `vX.Y.Z` tag 以保证安装可复现。远端发布 tag 不移动、不复用；失败修复使用
  下一个 patch 版本。

## 开发 skill

- skill 描述（frontmatter `description`）同时充当 agent 决定何时调用该 skill 的触发/路由文本——编辑时保持触发短语和范围边界（「不负责 X」）完整。
- 这些 skill 也以安装拷贝形式存在于 agent runtime 目录（如 `~/.claude/skills/`、`~/.agents/skills/`）——本仓是唯一真源（基线在 initial commit 中从 runtime 目录导入）。在这里编辑一个 skill 后，安装拷贝在重新 install/sync 前即过期；不要直接编辑 runtime 拷贝。
- **验证只有一道门，一条命令**：push 前跑 `scripts/verify.sh`——先机械门（与 CI 同一组：`validate_repository.py`、shellcheck、sync fixtures），再对相对 `origin/master` 有改动的 skill 跑各自的 `skills/<name>/evals/live-check.sh`（真调用、计费、需本机 CLI 与凭证，所以只在本地跑；`--all` 全跑，用于查 CLI 版本漂移）。每个 skill 必须有 live-check（`validate_repository.py` 强制），断言写在脚本头部，绿只证明断言的行为。**SKILL.md 里出现的每条命令行都要被真正执行过一次，不能只让 agent 复述它打算跑什么**——复述能通过的无效 flag 会一路穿过验证。不引入评分表、多轮爬山或 grader 子代理（2026-08-22 实证：纸面评分与真实行为会翻转，流程本身成仪式）。`evals/evals.json` 是参考题库，不是门禁。
- 提交信息沿用既有模式：`skill(<name>): ...` / `feat(<name>): ...` / `chore: ...`，且 README 的 skill 表应与 `skills/` 下的内容保持同步。

## Agent skills

### Issue tracker

issue 跟踪在 GitHub Issues（`dzshzx/agent-skills`，经 `gh` CLI 读写）。见 `docs/agents/issue-tracker.md`。
