# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 这个仓库是什么

一组遵循 [Agent Skills](https://agentskills.io) 开放标准的可复用 agent skill，可经 `npx skills add dzshzx/agent-skills` 跨 AI 编码 agent（Claude Code、Codex、Cursor……）安装。每个 skill 是 `skills/<name>/` 下的一个目录，含一个 `SKILL.md`（YAML frontmatter：`name` + `description`），外加可选的 `references/`、`scripts/`、`tests/` 和 `agents/`（per-agent 接口元数据，如 `agents/openai.yaml`）。

这里的 skill 是 **prompt-instructions-as-product**：SKILL.md 正文即交付物，对它的编辑就是对每个安装它的 agent 的行为改动。

## 设计规则（强制，来自 README）

- **SKILL.md 内不放机器专属事实。** 路径、主机名和机器拓扑放在 per-machine config 文件里（见 `skills/sync-agents-instructions/references/config-example.toml`），或相对 skill 目录解析（Claude Code 上用 `${CLAUDE_SKILL_DIR}`；其他环境用「包含本 SKILL.md 的目录」）。
- **平台事实可以；机器事实不行。** skill 可以依赖某个 agent 平台如何存储数据，但绝不依赖某一台机器的布局。若某改动会把探得的拓扑硬编码进 SKILL.md，改为放进 config schema/example。
- 给 `sync-agents-instructions` 增加对一个新 agent 的支持，意味着往 machine config 里加一条 `[[agents]]` 条目——SKILL.md 正文必须保持 agent-generic。
- Release 打 tag 以保证安装可复现。

## 开发 skill

- skill 描述（frontmatter `description`）同时充当 agent 决定何时调用该 skill 的触发/路由文本——编辑时保持触发短语和范围边界（「不负责 X」）完整。
- 这些 skill 也以安装拷贝形式存在于 agent runtime 目录（如 `~/.claude/skills/`、`~/.agents/skills/`）——本仓是唯一真源（基线在 initial commit 中从 runtime 目录导入）。在这里编辑一个 skill 后，安装拷贝在重新 install/sync 前即过期；不要直接编辑 runtime 拷贝。
- 提交信息沿用既有模式：`skill(<name>): ...` / `feat(<name>): ...` / `chore: ...`，且 README 的 skill 表应与 `skills/` 下的内容保持同步。

## Agent skills

### Issue tracker

issue 跟踪在 GitHub Issues（`dzshzx/agent-skills`，经 `gh` CLI 读写）。见 `docs/agents/issue-tracker.md`。

### Triage labels

沿用五个默认 triage 标签（`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`）。见 `docs/agents/triage-labels.md`。

### Domain docs

single-context 布局——根目录 `CONTEXT.md` + `docs/adr/`（按需惰性创建）。见 `docs/agents/domain.md`。
