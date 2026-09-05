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

- 修改前按改动范围与风险读取目标 `SKILL.md` 的相关段落；命令、schema、脚本或模板变化再读取其直接依赖。只改描述或路由元数据时不强制通读无关正文。
- skill 描述（frontmatter `description`）同时充当 agent 决定何时调用该 skill 的触发/路由文本——编辑时保持触发短语和范围边界（「不负责 X」）完整。
- 这些 skill 也以安装拷贝形式存在于 agent runtime 目录（如 `~/.claude/skills/`、`~/.agents/skills/`）——本仓是唯一真源（基线在 initial commit 中从 runtime 目录导入）。在这里编辑一个 skill 后，安装拷贝在重新 install/sync 前即过期；不要直接编辑 runtime 拷贝。
- 按变更风险验证：描述、路由元数据和文档改动运行 `scripts/verify.sh --no-live`（`validate_repository.py`、shellcheck、sync fixtures、`check-commit-subjects.sh`）；命令、脚本或运行时行为变化再执行对应检查，必要时运行目标 `skills/<name>/evals/live-check.sh`。live-check 会真调用、计费且需要本机 CLI 与凭证；用户限制禁止的 live 流程不执行，并在交付中说明未覆盖的行为。每个 skill 必须保留 live-check（`validate_repository.py` 强制），断言写在脚本头部，绿只证明断言的行为。不引入评分表、多轮爬山或 grader 子代理。`evals/evals.json` 是参考题库，不是门禁。
- 提交信息为 `type(scope): subject` 形态：`skill(<name>): ...` / `feat(<name>): ...` / `chore: ...`；裸 `<name>: ...` 不算（`scripts/check-commit-subjects.sh` 在 verify 与 CI 校验，2026-09-02 起）。README 的 skill 表应与 `skills/` 下的内容保持同步。

## Agent skills

### Issue tracker

issue 跟踪在 GitHub Issues（`dzshzx/agent-skills`，经 `gh` CLI 读写）。见 `docs/agents/issue-tracker.md`。
