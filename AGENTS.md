# Agent Rules

完整开发指南（布局、编写规则、工作流）在 `CLAUDE.md`；建议会话开始时读一次 @CLAUDE.md，同一会话内不必重读。
通用行为契约与机器事实由全局指令层承载；本文件只记非 Claude agent 需额外知道的项目事实。

## 项目边界

- 本仓是每个 skill 的唯一真源。agent runtime 目录下的安装拷贝（`~/.claude/skills`、`~/.agents/skills`）在编辑后即过期——重新 install/sync；绝不直接编辑 runtime 拷贝。
- 已提交的 `SKILL.md` 内不放机器专属事实：机器拓扑属于 per-machine config（模式见 `skills/sync-agents-instructions/references/config-example.toml`）；平台事实可以，机器事实不行。
- frontmatter `description` 同时充当路由逻辑——编辑时保留触发短语、排除项与范围边界。
- 提交约定：`skill(<name>): …` / `feat(<name>): …` / `chore: …`；保持 README 的 skill 表与 `skills/` 同步。
- Release 打 tag，使 `npx skills add dzshzx/agent-skills` 的安装保持可复现。
