# Codex Skill Editing Contract

本仓是每个 skill 的唯一真源。只编辑 `skills/<name>/` 下的源码；agent runtime
目录中的安装拷贝在重新 install/sync 前会过期，绝不直接编辑它们。

- 修改前先读目标 `SKILL.md` 及其直接引用的 schema、脚本或模板；保留 frontmatter
  `description` 的触发短语、排除项和范围边界。
- 已提交的 `SKILL.md` 不放机器专属事实。机器拓扑应留在 per-machine config，或以
  相对 skill 目录的方式解析；平台事实可以，机器事实不行。
- 采用小而完整的 patch，并让 README 的 skill 表与 `skills/` 目录保持同步。
- 修改后检查目标 diff，push 前跑 `scripts/verify.sh`：先机械门（与 CI 同一组），再对
  相对 `origin/master` 有改动的 skill 跑各自的 `skills/<name>/evals/live-check.sh`（真调用、
  计费、需本机 CLI 与凭证，只在本地跑；`--all` 全跑）。每个 skill 必须有 live-check
  （`validate_repository.py` 强制），断言写在脚本头部，绿只证明断言的行为。**SKILL.md 里出现的
  每条命令行都要被真正执行过一次，不能只让 agent 复述它打算跑什么**——复述能通过的无效 flag
  会一路穿过验证。不引入评分表、多轮爬山或 grader 子代理；`evals/evals.json` 只是参考题库。
  提交信息为 `type(scope): subject` 形态——`skill(<name>): …`、`feat(<name>): …` 或 `chore: …`；
  裸 `<name>: …` 不算，`scripts/check-commit-subjects.sh` 在 verify 与 CI 校验。
- Release 候选先合入 `master`，等待该同一 SHA 的 CI 通过，再创建匹配的带
  注解 `vX.Y.Z` tag，保证 `npx skills add dzshzx/agent-skills` 的安装可复现。
  远端发布 tag 不移动、不复用；失败修复使用下一个 patch 版本。

## Agent skills

### Issue tracker

issue 跟踪在 GitHub Issues（`dzshzx/agent-skills`，经 `gh` CLI 读写）。见 `docs/agents/issue-tracker.md`。
