# 项目契约

- 本仓拥有公开 skill 源码 `skills/<name>/`；修改安装副本不会更新源码。机器拓扑放 per-machine config，SKILL.md 只保留可移植的平台约定。
- description 是调用路由：保留自然触发语、排除项与范围边界。README skill 表与源码目录保持一致。
- 文档和路由修改运行 `scripts/verify.sh --no-live`；脚本或命令契约变化再运行对应离线检查。每个 skill 的 `evals/live-check.sh` 会真实调用、计费，按任务需要及已有授权执行；保留其入口，结果只证明脚本中的断言。
- 提交格式为 `type(scope): subject` 或 `chore: subject`，由 `scripts/check-commit-subjects.sh` 检查。
- 改动经 `scripts/candidate.sh` 推成 `candidate/**`，CI 全绿后 promote 自动快进 master，不直推 master；发布再在该 master 提交上推匹配的 annotated `vX.Y.Z` tag；远端 tag 不移动或复用，修复使用下个 patch。
- 跟踪任务时见 `docs/agents/issue-tracker.md`；设计与验证入口见 README。
