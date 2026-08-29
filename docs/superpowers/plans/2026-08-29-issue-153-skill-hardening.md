# Issue-153 Skill Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 #153 调研结论落进 `pi/github-issue-driven/SKILL.md`——执行模型取舍、subagent cwd 参数、push gate + 降级、清理清单补全。

**Architecture:** 纯文档改动，4 处编辑全部落在 `pi/github-issue-driven/SKILL.md` 的步 5/7/9/10。不碰 zima 代码、不碰 pi 上游、不实现 pi-cwd fork 增强。

**Tech Stack:** Markdown。验证用 `uv run pytest tests/unit/test_cr_batch_contracts.py`（该测试断言 zima-pr-monitor / github-code-review-batch 的 SKILL.md 内容，本改动不触碰，应保持通过）。

## Global Constraints

- 所有编辑在 worktree `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-153-skill-hardening` 内进行（绝对路径编辑，session cwd 不切换）
- 中文表述，与 SKILL.md 现有风格一致（粗体强调、`code` 引用、→ 箭头）
- 不删除任何现有步骤编号与结构，只替换/扩充对应 bullet
- `git add <file>` 按文件 stage，不用 `git add -A`

---

### Task 1: 步 5 执行模型取舍 + ignore 自检

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（步 5 的"首选/兜底"两个 bullet + "自检" bullet）

**Interfaces:**
- Consumes: 无
- Produces: 步 5 的两种执行模型（A/B）命名，步 7 引用"模型 B"概念

- [ ] **Step 1: 替换步 5 的"首选/兜底"两个 bullet**

将：

```markdown
   - **首选（pi）**：调原生 `git_worktree` 工具 `action: "open"`，`path: "./.pi/worktrees/issue-<N>-<shortslug>"`，`branch: "issue-<N>-<shortslug>"` → 工具在 `<repo>/.pi/worktrees/` 创建 worktree，并**开一个新 Pi session**（cwd 落在 worktree 内）继续后续步骤。pi 的 session cwd 固定，不能用切目录的方式进 worktree。
   - **兜底（无 `git_worktree` 工具）**：`git worktree add <repo>/.pi/worktrees/issue-<N>-<shortslug> -b issue-<N>-<shortslug>`，再 `cd <path> && pi` 开新 session。
```

替换为：

```markdown
   - **模型 A（默认 · 开新 session）**：调原生 `git_worktree` 工具 `action: "open"`，`path: "./.pi/worktrees/issue-<N>-<shortslug>"`，`branch: "issue-<N>-<shortslug>"` → 工具在 `<repo>/.pi/worktrees/` 创建 worktree，并**开一个新 Pi session**（cwd 落在 worktree 内）继续后续步骤。**取舍**：机制强制（session cwd 就在 worktree），但流程状态（spec gate、ledger、SDD 进度）跨 session 传递靠文档，新 session 需先读 spec/plan 再继续。
   - **模型 B（同 session · 绝对路径作业）**：`git_worktree` `action: "add"`（或 `git worktree add <repo>/.pi/worktrees/issue-<N>-<shortslug> -b issue-<N>-<shortslug>`）建 worktree，**当前 session 不切目录**，后续所有 read/edit/bash 用 worktree 绝对路径作业。**取舍**：流程状态全程可控，但"在 worktree 里作业"靠纪律，无机制强制。**用户要求当前 session 继续时选 B。**
   - pi 的 session cwd 固定，不能用切目录的方式进 worktree——模型 B 下**禁止** `cd` 进 worktree 后误以为 session 已切换。
```

- [ ] **Step 2: 替换步 5 的"自检" bullet**

将：

```markdown
   - **自检**：`pwd` 在 `<repo>/.pi/worktrees/` 下（或 `git rev-parse --git-dir` 指向 linked worktree），否则停下先建。
```

替换为：

```markdown
   - **自检**：模型 A 下 `pwd` 在 `<repo>/.pi/worktrees/` 下（或 `git rev-parse --git-dir` 指向 linked worktree）；模型 B 下确认所有编辑路径指向 worktree 绝对路径。**ignore 自检**：确认目标仓已 ignore worktree 容器目录（`.gitignore` 含 `.pi/worktrees/`，或写入 `.git/info/exclude`）——否则主 checkout 手滑 `git add -A` 会把 worktree 当 embedded repo 吸入暂存区。
```

- [ ] **Step 3: 验证渲染**

Run: `sed -n '15,30p' pi/github-issue-driven/SKILL.md`
Expected: 步 5 下出现"模型 A""模型 B"两个 bullet + 禁止 cd 说明 + 自检含 ignore 自检

- [ ] **Step 4: Commit**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): step 5 execution-model tradeoff (A new-session vs B same-session) + ignore self-check"
```

---

### Task 2: 步 7 subagent 显式传 cwd 参数

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（步 7 末句）

**Interfaces:**
- Consumes: Task 1 的模型 A/B 概念
- Produces: 步 7 的 cwd 参数纪律

- [ ] **Step 1: 替换步 7 末句**

将：

```markdown
7. **实现** → **REQUIRED SUB-SKILL: Use subagent-driven-development**（worktree 内，**禁碰 main**）。**🚪 Gate：Step 6 的 plan 文档必须存在才能开始实现——spec 不算 plan。** 派 implementer 时把 worktree 绝对路径填进 `Work from:`，别让 subagent 回主仓库作业。
```

替换为：

```markdown
7. **实现** → **REQUIRED SUB-SKILL: Use subagent-driven-development**（worktree 内，**禁碰 main**）。**🚪 Gate：Step 6 的 plan 文档必须存在才能开始实现——spec 不算 plan。** 派 implementer/reviewer 时**显式传 `cwd: <worktree 绝对路径>`**（subagent 工具原生参数，机制强制），并在 task 里保留 `Work from: <worktree 绝对路径>` 作双保险——别让 subagent 回主仓库作业。
```

- [ ] **Step 2: 验证渲染**

Run: `grep -n "cwd" pi/github-issue-driven/SKILL.md`
Expected: 步 7 行出现 `cwd: <worktree 绝对路径>`

- [ ] **Step 3: Commit**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): step 7 pass explicit cwd param to subagents (native tool param, replaces prompt-only discipline)"
```

---

### Task 3: 步 9 push gate + 降级路径

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（步 9 整条）

**Interfaces:**
- Consumes: 无
- Produces: 步 9 的 gate 与降级纪律

- [ ] **Step 1: 替换步 9 整条**

将：

```markdown
9. **PR + Zima 单 Bot CR + 前台阻塞等待** → **REQUIRED SUB-SKILL: Use zima-pr-monitor**（开 PR、打 `zima:needs-review`、**同 turn 立即前台阻塞等待 CR job 完成（禁止结束 turn，helper 见 zima-pr-monitor）**、解析 review meta（`cc-cr-meta` / `pi-cr-meta` 前缀区分；`kimi-cr-meta` 忽略）、worktree 修、重打标签、收敛判定、合并）
```

替换为：

```markdown
9. **PR + Zima 单 Bot CR + 前台阻塞等待** → **REQUIRED SUB-SKILL: Use zima-pr-monitor**（**🚪 push/开 PR 前暂停，等用户明确许可**——用户 AGENTS.md 硬规则"不自动 commit/push 除非明确许可"；开 PR、打 `zima:needs-review`、**同 turn 立即前台阻塞等待 CR job 完成（禁止结束 turn，helper 见 zima-pr-monitor）**、解析 review meta（`cc-cr-meta` / `pi-cr-meta` 前缀区分；`kimi-cr-meta` 忽略）、worktree 修、重打标签、收敛判定、合并）。**zima 缺席降级**：个人 fork / 无 bot 仓库（无 zima CR 环境）时，降级为人工 CR 或 pi 原生 `workflow` 工具 `code-review` 模式，并在 issue 评论说明降级原因。
```

- [ ] **Step 2: 验证渲染**

Run: `grep -n "push/开 PR 前暂停\|zima 缺席降级" pi/github-issue-driven/SKILL.md`
Expected: 两处均命中

- [ ] **Step 3: Commit**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): step 9 human gate before push/PR + zima-absent degradation path"
```

---

### Task 4: 步 10 清理清单补全

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（步 10 整条）

**Interfaces:**
- Consumes: 无
- Produces: 步 10 完整清理清单

- [ ] **Step 1: 替换步 10 整条**

将：

```markdown
10. **post-merge**：结束 worktree session（回主仓库 session）→ `git_worktree` `action: "remove"`（或 `git worktree remove <repo>/.pi/worktrees/issue-<N>-<shortslug>`）→ `git worktree prune` → `git checkout main && git pull`（release / 部署 / 配置 = 人工，不在自动化环内）
```

替换为：

```markdown
10. **post-merge**：结束 worktree session（回主仓库 session）→ `git_worktree` `action: "remove"`（或 `git worktree remove <repo>/.pi/worktrees/issue-<N>-<shortslug>`）→ `git worktree prune` → 删远端分支 `git push origin --delete issue-<N>-<shortslug>`（本地分支随 worktree remove 一并清理）→ `git checkout main && git pull`。调研目录 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/` 设计为跨 harness 留档，**不清理**（release / 部署 / 配置 = 人工，不在自动化环内）
```

- [ ] **Step 2: 验证渲染**

Run: `grep -n "push origin --delete\|跨 harness 留档" pi/github-issue-driven/SKILL.md`
Expected: 两处均命中

- [ ] **Step 3: Commit**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): step 10 complete cleanup list (remote branch deletion, research dir retention)"
```

---

### Task 5: 全量验证

**Files:**
- Test: `tests/unit/test_cr_batch_contracts.py`（回归，应保持通过）

- [ ] **Step 1: 跑 skill 相关测试**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py -q`
Expected: 全部 PASS（本改动不触碰 github-code-review-batch / zima-pr-monitor 的 SKILL.md）

- [ ] **Step 2: 跑全量单测**

Run: `uv run pytest tests/unit/ -q`
Expected: 全部 PASS

- [ ] **Step 3: 检查 diff 完整性**

Run: `git diff main...HEAD --stat`
Expected: 仅 `pi/github-issue-driven/SKILL.md` 与 spec/plan 文档

- [ ] **Step 4: 更新 #153 评论**

在 issue #153 评论：4 个 skill 改动已完成，附 commit 列表，等待用户 review。
