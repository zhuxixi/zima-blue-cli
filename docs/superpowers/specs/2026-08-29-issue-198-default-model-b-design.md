# Spec: 步 5 默认执行模型改为 B（issue #198）

**Date**: 2026-08-29
**Issue**: #198
**Scope**: `pi/github-issue-driven/SKILL.md` 步 5

## 背景

#197 落地了步 5 的两种执行模型（A 开新 session / B 同 session 绝对路径），默认设为 A。实战验证（#153 处理即用模型 B 完成）表明：同 session 绝对路径作业流程状态全程可控、无上下文损失，更适合 agent 驱动的 controller 模式。

## 改动

1. 步 5 默认从 A 换为 B：`**默认 B，需要机制强制隔离时选 A**`，两个 bullet 顺序对调。
2. 模型 B 加安全约定：worktree 根路径记作 `WT=<repo>/.pi/worktrees/issue-<N>-<shortslug>`，所有编辑路径以 `$WT` 开头，git 操作用 `git -C $WT`。
3. 自检 bullet 同步：模型 B 下确认所有编辑路径以 `$WT` 开头。

## 非目标

- 不改模型 A 内容（保留为机制强制隔离选项）
- 不引入 pi-cwd 等扩展

## 验收

- SKILL.md 步 5 默认表述为 B，WT 约定落位
- tests/unit 全量通过
- 用户 review 确认
