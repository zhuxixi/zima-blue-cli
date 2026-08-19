# Spec: pi 适配 github-code-review-batch skill

日期：2026-08-19
Issue：#161
分支：`issue-161-pi-cr-batch-adapter`

## 目标

把 `pi/github-code-review-batch/` 从 Claude Code 端 skill 适配为本机 pi-coding-agent 可直接触发的 skill：工具调用 pi 化、subagent 派发 pi 化、metadata 契约独立化（`pi-cr-meta`）、双 bot 表述单 bot 化。评审规则、输出契约、状态报告三态、Verdict 派生、scripts 的确定性逻辑**全部保持不变**。

## 范围决策表

| 项 | 决策 | 依据 |
|---|---|---|
| 工具名 | `Bash`→`bash`、`Read`→`read`、`Agent` 派发段改写 | 轮 1 盘点 |
| subagent 派发 | builtin `reviewer` + subagent 工具 workflowScript `runs.all` 并行；prompt 模板保留 | 轮 2；workflow 工具需用户 opt-in 不适合 |
| metadata 标签 | `cc-cr-meta` → `pi-cr-meta`；标记 "Generated with Claude Code" → "Generated with pi-coding-agent" | 轮 3：zima 核心不消费 cr-meta，改动全在 pi/ 内 |
| 双 bot 表述 | 删 kimi 交叉验证（L19、Step 0.2a 过滤规则），改单 bot（cc）表述 | 顺带覆盖 #154 对本 skill 的要求 |
| monitor 配套 | `pi/zima-pr-monitor/SKILL.md` 认 `pi-cr-meta`（最小改动）；kimi 清理留给 #154 | 收敛判定不失效 |
| scripts | 7 个全保留；build_review_body.py / parse_metadata.py 的 CC 常量改为 pi；apply_suppressions.py 的 `.claude/cr-suppressions.json` → `.pi/cr-suppressions.json`（保留 `.claude` fallback） | 轮 1 |
| frontmatter | description 去 "Claude Code 端" 表述，触发词原文保留（外部调度契约） | 触发契约不破 |
| CLAUDE.md checker 命名 | 保留（检查的是仓库 CLAUDE.md 规范文件，与跑在哪个 harness 无关） | 契约稳定性 |

## 非目标

- 不改评审规则、severity 口径、issue 验证机制、状态报告格式
- 不改 zima 核心代码（webhook/executor/daemon）
- 不做 zima-pr-monitor 的 kimi 清理（#154 的范围）
- 不动 CC 版 skill 的部署（本机 ~/.claude 或旧版副本）

## 验证

1. `grep` 无残留：`Bash`/`Read`/`Agent` 工具名、`cc-cr-meta`、`Generated with Claude Code`、`kimi-cr-meta`（历史说明段除外）
2. scripts 单测跑过（现有 tests/ 里若有覆盖）
3. 手动冒烟：pi 会话内触发 `batch review pr <某PR>` 走通 Step 0-10 骨架（发布评论用 `--dry-run` 变体或先只跑到 Step 8）
4. build_review_body.py / parse_metadata.py 往返一致：build 产出的评论能被 parse 正确读回
