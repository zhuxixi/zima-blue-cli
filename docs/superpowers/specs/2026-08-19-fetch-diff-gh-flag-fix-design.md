# Spec: fetch_diff 修复（gh pr view --patch → gh pr diff）

日期：2026-08-19
Issue：#164
分支：`issue-164-fix-fetch-diff-gh-flag`

## 目标

修复 `GitHubProvider.fetch_diff` 使用不存在的 gh flag 导致 pinned CR 路径必 skip 的 bug：命令从 `gh pr view <n> --repo <repo> --patch` 改为 `gh pr diff <n> --repo <repo>`，同步修正固化坏行为的测试断言。0.7.1 首次真实 webhook CR 触发暴露（PR #162 现场）。

## 范围决策表

| 项 | 决策 | 依据 |
|---|---|---|
| 实现 | `zima/providers/github.py` `fetch_diff` 命令参数 1 行改动 | #164 Root Cause |
| 测试 | `test_fetch_diff` 断言改 `["gh", "pr", "diff", "123", "--repo", "owner/repo"]`；failure 测试保留 | 调研 1：坏断言固化 |
| 行为变化 | rescan 路径 `pr_diff` 恒空 → 真实值；示例模板 `{{pr_diff}}` 开始渲染内容；1MB cap 不触发 | 调研 2：这是模板本意，非回归 |
| 不做 | 不动 pinned/rescan 分支的重试与 SkipAction 逻辑；不动 #163（smee 心跳）；不动 0.7.1 其他代码 | 单点修复 |

## 验证

1. `uv run pytest tests/unit/test_providers_github.py -v` 全绿
2. 全量 `uv run pytest tests/ -q`
3. 手工验证命令真实性：`gh pr diff 162 --repo zhuxixi/zima-blue-cli` 返回 patch（已知 47306 字节）
4. 合并后 release → 本机真实 webhook CR 端到端跑通（pinned 不再 skip）
