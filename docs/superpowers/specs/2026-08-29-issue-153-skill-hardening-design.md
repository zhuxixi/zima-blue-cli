# Spec: github-issue-driven skill 层适配（issue #153 剩余动作）

**Date**: 2026-08-29
**Issue**: #153（实战首跑报告剩余动作）
**Scope**: `pi/github-issue-driven/SKILL.md`（主）+ `pi/zima-pr-monitor/SKILL.md`（步 9 关联，视需要）

## 背景

#153 的 5 个建议动作中，动作 1（删旧版 skill 三件套）已完成。剩余 3 个 skill 改动 + pi 工具侧 4 条。调研结论（已评论到 #153）：pi 工具侧 4 条已全部上游修复（pi-subagents 0.51.0~0.59.0），无需上报、无需装 extension；剩余真实工作 = skill 层适配，用上原生能力。

## 改动清单

### 1. 步 5：写明两种执行模型取舍

两种模型：
- **A. `git_worktree open` 开新 session**：新 session cwd 落在 worktree，机制强制，但流程状态（spec gate、ledger、SDD 进度）跨 session 传递靠文档。
- **B. 同 session + 绝对路径作业**：`git_worktree add` 建 worktree，当前 session 用绝对路径编辑 worktree 内文件，全程可控，但靠纪律。

**决策**：skill 主推 A（机制强制），B 作为"用户要求在当前 session 继续"时的兜底，写明取舍与适用条件。

### 2. 步 5/7：派 subagent 显式传 `cwd` 参数

原生 subagent 工具已有 `cwd` 参数（pi-subagents 0.15.0 起）。替代现在的 `Work from:` prompt 纪律：
- 派 implementer/reviewer 时传 `cwd: <worktree 绝对路径>`
- 保留 `Work from:` 作为双保险（prompt 层 + 机制层）
- 删除"subagent 无 cwd 注入"的过时表述

### 3. 步 9：push/PR 人工 gate + zima 缺席降级路径

- **人工 gate**：用户 AGENTS.md 硬规则"不自动 commit/push 除非明确许可"。步 9 在 push/开 PR 前加显式 gate：暂停等用户确认。
- **降级路径**：zima 双 bot 缺席时（个人 fork / 无 bot 仓库），降级为人工 CR 或本地 workflow code-review，写明判定条件。

### 4. 步 5/10：ignore 自检 + 完整清理清单

- **步 5 自检**：worktree 容器目录（`.pi/worktrees/`）必须被目标仓 ignore（`.gitignore` 或 `.git/info/exclude`），防止主 checkout `git add -A` 吸入 embedded repo。
- **步 10 清理清单补全**：远端分支删除（`git push origin --delete <branch>`）、调研目录处置说明（`~/.claude/github-issue-driven/...` 设计为跨 harness 留档，无清理时机，说明即可）。

## 非目标

- 不改 pi 上游（4 条已修复）
- 不实现 pi-cwd fork 增强（原生 cwd 参数替代）
- 不改 zima 代码（纯 skill 文档改动）

## 验收

- SKILL.md 四处改动落位，表述与调研结论一致
- 仓库 skill 扫描测试通过（如有）
- 用户 review 确认
