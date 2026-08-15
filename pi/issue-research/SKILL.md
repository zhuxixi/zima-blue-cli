---
name: issue-research
description: Use when an issue's description is unclear or you need evidence on how to handle it — searching the JFox knowledge base, git history, past issues and PR comments. Use BEFORE brainstorming or systematic-debugging an issue.
---

# Issue Research

issue 描述常不清晰。从多数据源挖依据，搞清"这 issue 到底要怎么处理"。多轮，每轮一个主题，每轮结论评论到 issue。是 github-issue-driven 流程的步 3。

## 数据源（三个都查）
1. **JFox 知识库**（核心）：`jfox search "<关键词>" --type permanent` / `jfox show <id>` —— permanent + session 笔记，整个事件里 JFox 就是知识库角色。
2. **项目 git**：`git log --oneline -30` / 相关 commit message / `gh issue view <N>`（过往相关 issue）。
3. **过往 PR 评论**：`gh pr view <N> --json comments,reviews`（尤其 CR 讨论 / 决策上下文）。

## 多轮调研
每轮一个主题（如"这功能以前有没有实现过"、"这 bug 的根因是什么"）。**每轮结论评论到 issue**，留轨迹：
```bash
gh issue comment <N> --body "## 调研：<主题>
<结论 + 依据来源>"
```

## 调研文件布局（不进项目目录！）
临时调研产物（摘录、对比表、草稿）放全局约定目录，**绝不放项目目录**（会被误 commit 污染）：
```
~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/research/<主题>.md
```
全局集中、跨 session/项目可复用。该目录 pi 与 Claude Code 会话共用（跨 harness 可互读调研结论）。

## 何时停
信息够回答"这 issue 要怎么处理"→ 进路由（详见 github-issue-driven 步 4）：bug → `systematic-debugging`；新需求 → `brainstorming`（均为 superpowers 包技能）。

## 常见坑
- 调研文件放项目目录 → 被 `git add -A` 误 commit。**一定放 `~/.claude/...`**。
- 只读 issue 正文 → 漏掉过往 issue/PR 里的上下文。三个源都扫。
- 调研不留痕 → 下次/别人重踩。结论评论回 issue。
