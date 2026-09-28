// 提交标题规则：全局规则（fleet-state ADR 0047）加本仓扩展类型 deploy、skill。
// CI 与 scripts/check-commit-subjects.sh 经 npx 以固定版本运行 commitlint 读取本文件；
// 用 .mjs 是为了 ignores 函数（YAML 无法表达）。
export default {
  extends: ['@commitlint/config-conventional'],
  // 放行 `git merge`/subtree 生成的 `Merge commit '<sha>'`（含 ` as '<dir>'`）；
  // `Merge branch … into …` 等由 commitlint 默认 ignores 放行。
  ignores: [
    (message) =>
      /^Merge commit '[0-9a-f]{7,40}'( as '[^']+')?\s*$/m.test(
        message.split('\n')[0],
      ),
  ],
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'build',
        'chore',
        'ci',
        'docs',
        'feat',
        'fix',
        'perf',
        'refactor',
        'revert',
        'style',
        'test',
        'deploy',
        'skill',
      ],
    ],
    'scope-case': [2, 'always', 'lower-case'],
    'subject-case': [0],
    'header-max-length': [2, 'always', 100],
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
  },
};
