# Issue-198 Default Model B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `pi/github-issue-driven/SKILL.md` 步 5 的默认执行模型从 A（开新 session）换为 B（同 session 绝对路径作业），并给模型 B 加 `$WT` 变量安全约定。

**Architecture:** 纯文档改动，落在 `pi/github-issue-driven/SKILL.md` 步 5 的两个 bullet + 自检 bullet。

**Tech Stack:** Markdown。验证用 `uv run pytest tests/unit/ -q`。

## Global Constraints

- 所有编辑在 worktree `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-198-default-model-b` 内进行（模型 B：绝对路径编辑，session cwd 不切换）
- 中文表述，与 SKILL.md 现有风格一致
- 不删除模型 A 内容，只对调顺序与默认表述

---

### Task 1: 步 5 默认模型对调 + WT 约定

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（步 5 两个 bullet + 自检 bullet）

- [ ] **Step 1: 替换步 5 的两个模型 bullet**

将：

```markdown
   - **模型 A（默认 · 开新 session）**：调原生 `git_worktree` 工具 `action: "open"`，`path: "./.pi/worktrees/issue-<N>-<shortslug>"`，`branch: "issue-<N>-<shortslug>"` → 工具在 `<repo>/.pi/worktrees/` 创建 worktree，并**开一个新 Pi session**（cwd 落在 worktree 内）继续后续步骤。**取舍**：机制强制（session cwd 就在 worktree），但流程状态（spec gate、ledger、SDD 进度）跨 session 传递靠文档，新 session 需先读 spec/plan 再继续。
   - **模型 B（同 session · 绝对路径作业）**：`git_worktree` `action: "add"`（或 `git worktree add <repo>/.pi/worktrees/issue-<N>-<shortslug> -b issue-<N>-<shortslug>`）建 worktree，**当前 session 不切目录**，后续所有 read/edit/bash 用 worktree 绝对路径作业。**取舍**：流程状态全程可控，但"在 worktree 里作业"靠纪律，无机制强制。**用户要求当前 session 继续时选 B。**
```

替换为：

```markdown
   - **模型 B（默认 · 同 session 绝对路径作业）**：`git_worktree` `action: "add"`（或 `git worktree add <repo>/.pi/worktrees/issue-<N>-<shortslug> -b issue-<N>-<shortslug>`）建 worktree，**当前 session 不切目录**，后续所有 read/edit/bash 用 worktree 绝对路径作业。**取舍**：流程状态全程可控、无上下文损失；但"在 worktree 里作业"靠纪律，无机制强制。**安全约定**：worktree 根路径记作 `WT=<repo>/.pi/worktrees/issue-<N>-<shortslug>`，所有编辑路径以 `$WT` 开头，git 操作用 `git -C $WT`——把"靠纪律"变成"一个变量可查"。
   - **模型 A（开新 session）**：调原生 `git_worktree` 工具 `action: "open"`，`path: "./.pi/worktrees/issue-<N>-<shortslug>"`，`branch: "issue-<N>-<shortslug>"` → 工具在 `<repo>/.pi/worktrees/` 创建 worktree，并**开一个新 Pi session**（cwd 落在 worktree 内）继续后续步骤。**取舍**：机制强制（session cwd 就在 worktree），但流程状态（spec gate、ledger、SDD 进度）跨 session 传递靠文档，新 session 需先读 spec/plan 再继续。**需要机制强制隔离时选 A。**
```

- [ ] **Step 2: 替换步 5 开头句**

将：

```markdown
5. **进 worktree（spec 批准后 · 强制）**：写代码前的隔离关卡——两种执行模型，**默认 A，用户要求当前 session 继续时用 B**：
```

替换为：

```markdown
5. **进 worktree（spec 批准后 · 强制）**：写代码前的隔离关卡——两种执行模型，**默认 B，需要机制强制隔离时选 A**：
```

- [ ] **Step 3: 替换自检 bullet**

将：

```markdown
   - **自检**：模型 A 下 `pwd` 在 `<repo>/.pi/worktrees/` 下（或 `git rev-parse --git-dir` 指向 linked worktree）；模型 B 下确认所有编辑路径指向 worktree 绝对路径。**ignore 自检**：确认目标仓已 ignore worktree 容器目录（`.gitignore` 含 `.pi/worktrees/`，或写入 `.git/info/exclude`）——否则主 checkout 手滑 `git add -A` 会把 worktree 当 embedded repo 吸入暂存区。
```

替换为：

```markdown
   - **自检**：模型 A 下 `pwd` 在 `<repo>/.pi/worktrees/` 下（或 `git rev-parse --git-dir` 指向 linked worktree）；模型 B 下确认所有编辑路径以 `$WT` 开头。**ignore 自检**：确认目标仓已 ignore worktree 容器目录（`.gitignore` 含 `.pi/worktrees/`，或写入 `.git/info/exclude`）——否则主 checkout 手滑 `git add -A` 会把 worktree 当 embedded repo 吸入暂存区。
```

- [ ] **Step 4: 验证渲染**

Run: `grep -n "默认 B\|模型 B（默认\|安全约定\|需要机制强制隔离时选 A" pi/github-issue-driven/SKILL.md`
Expected: 四处均命中

- [ ] **Step 5: Commit**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): step 5 default execution model B (same-session absolute paths) + WT variable convention"
```

---

### Task 2: 全量验证

- [ ] **Step 1: 跑全量单测**

Run: `uv run pytest tests/unit/ -q`
Expected: 全部 PASS

- [ ] **Step 2: 检查 diff**

Run: `git diff main...HEAD --stat`
Expected: 仅 SKILL.md 与 spec 文档
