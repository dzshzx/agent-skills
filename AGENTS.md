# Codex Skill Editing Contract

本仓是每个 skill 的唯一真源。只编辑 `skills/<name>/` 下的源码；agent runtime
目录中的安装拷贝在重新 install/sync 前会过期，绝不直接编辑它们。

- 修改前先读目标 `SKILL.md` 及其直接引用的 schema、脚本或模板；保留 frontmatter
  `description` 的触发短语、排除项和范围边界。
- 已提交的 `SKILL.md` 不放机器专属事实。机器拓扑应留在 per-machine config，或以
  相对 skill 目录的方式解析；平台事实可以，机器事实不行。
- 采用小而完整的 patch，并让 README 的 skill 表与 `skills/` 目录保持同步。
- 修改后检查目标 diff 并运行最小相关验证；提交信息沿用
  `skill(<name>): …`、`feat(<name>): …` 或 `chore: …`。
- Release 使用 tag，保证 `npx skills add dzshzx/agent-skills` 的安装可复现。

## Agent skills

### Issue tracker

issue 跟踪在 GitHub Issues（`dzshzx/agent-skills`，经 `gh` CLI 读写）。见 `docs/agents/issue-tracker.md`。

### Triage labels

沿用五个默认 triage 标签（`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`）。见 `docs/agents/triage-labels.md`。

### Domain docs

single-context 布局——根目录 `CONTEXT.md` + `docs/adr/`（按需惰性创建）。见 `docs/agents/domain.md`。
