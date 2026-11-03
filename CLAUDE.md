# 项目契约

- 本仓拥有公开 skill 源码 `skills/<name>/`；修改安装副本不会更新源码。机器拓扑放 per-machine config，SKILL.md 只保留可移植的平台约定。
- description 是调用路由：保留自然触发语、排除项与范围边界。README skill 表与源码目录保持一致。
- 文档和路由修改运行 `scripts/verify.sh --no-live`；`evals/live-check.sh` 真实调用、计费，结果只证明脚本中的断言。
- 提交标题另允许 `skill` 类型；验证、CI 与发布 tag 规则见 README。票在本仓 GitHub Issues。
