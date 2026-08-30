---
name: github-issue-driven
description: Use when starting work on a GitHub issue — scanning or claiming an open issue, or when the path from issue to merged PR isn't clear. Use BEFORE diving into implementation of an issue.
---

# GitHub Issue Driven

处理 GitHub issue 的标准研发闭环：issue → 调研 → 设计 → 实现 → CR → 合并。JFox 知识库是调研中枢，superpowers 处理设计与实现，Zima 单 Bot CR 把关合并（cc/pi 版共存，按 review meta 前缀区分；kimi 已移除，见 [[Zima CR 体系单 bot 化]]）。

## When to use
- 会话开始要找事做（扫 open issue）
- 认领了一个 issue，要从头走到合并
- 不确定某个 issue 该走什么流程

## 10 步流程（每步指向对应 skill / 命令）

1. **扫 issue**：`gh issue list --repo <owner>/<repo> --state open --json number,title,labels,body`
2. **认领**：`gh issue edit <N> --add-assignee @me`（评论说明开始处理）
3. **纯调研** → **REQUIRED SUB-SKILL: Use issue-research**（JFox KB + git + 过往 issue/PR；多轮，每轮一主题，结论评论到 issue；调研文件放 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/research/`）
4. **路由**：bug → `systematic-debugging`；新需求/功能 → `brainstorming`（均为 superpowers 包技能）。产 **spec / 根因报告**，draft 在 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/spec.md`（和 research 一样**不进 main**）。**⏸ spec 完成后暂停，等用户确认设计再继续。**
   - **验收方式分层（必答）**：对本次改动的每个功能点建立验收矩阵，标记为 `自动化验证` 或 `用户实测`，并为每项分配稳定 ID（如 `A1`、`U1`）。自动化验证必须注明具体层级（`unit`、`integration`、`static`、`build`、`automated E2E` 等）、验证命令和通过标准；用户实测必须注明操作步骤、观察结果和通过标准。
   - 自动化验证优先选择足以证明行为的最低成本层级：能用 `unit` 验证的不要升级为 `integration`；必须跨组件时使用 `integration`；类型、格式或依赖约束使用 `static`/`build`；能稳定脚本化的完整流程使用 `automated E2E`。`用户实测` 不是自动化验证暂时没写出来时的兜底分类。
   - 若某项无法或不适合自动化，spec 必须说明原因，并写出实测步骤、观察结果、通过标准和可执行时机。

   spec 中可使用以下矩阵结构（不要求每个 issue 同时包含两类条目）：

   | ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
   |----|--------|----------|----------|----------|
   | A1 | 配置解析行为 | 自动化验证（unit） | `uv run pytest ...` | 相关测试通过 |
   | A2 | CLI 跨组件行为 | 自动化验证（integration） | `uv run pytest ...` | 命令返回码和输出符合预期 |
   | U1 | 真实外部服务交互 | 用户实测 | 按步骤执行并观察结果 | 外部服务产生预期效果 |
5. **进 worktree（spec 批准后 · 强制）**：写代码前的隔离关卡——两种执行模型，**默认 B，需要机制强制隔离时选 A**：
   - **模型 B（默认 · 同 session 绝对路径作业）**：`git_worktree` `action: "add"`（或 `git worktree add <repo>/.pi/worktrees/issue-<N>-<shortslug> -b issue-<N>-<shortslug>`）建 worktree，**当前 session 不切目录**，后续所有 read/edit/bash 用 worktree 绝对路径作业。**取舍**：流程状态全程可控、无上下文损失；但"在 worktree 里作业"靠纪律，无机制强制。**安全约定**：worktree 根路径记作 `WT=<repo>/.pi/worktrees/issue-<N>-<shortslug>`，所有编辑路径以 `$WT` 开头，git 操作用 `git -C $WT`——把"靠纪律"变成"一个变量可查"。
   - **模型 A（开新 session）**：调原生 `git_worktree` 工具 `action: "open"`，`path: "./.pi/worktrees/issue-<N>-<shortslug>"`，`branch: "issue-<N>-<shortslug>"` → 工具在 `<repo>/.pi/worktrees/` 创建 worktree，并**开一个新 Pi session**（cwd 落在 worktree 内）继续后续步骤。**取舍**：机制强制（session cwd 就在 worktree），但流程状态（spec gate、ledger、SDD 进度）跨 session 传递靠文档，新 session 需先读 spec/plan 再继续。**需要机制强制隔离时选 A。**
   - pi 的 session cwd 固定，不能用切目录的方式进 worktree——模型 B 下**禁止** `cd` 进 worktree 后误以为 session 已切换。
   - **把 spec 落进 worktree 的 `docs/superpowers/specs/<YYYY-MM-DD>-<slug>-design.md`，作为首个 commit。**（spec draft 在 `~/.claude`，main 从无该文件 → 零搬运。）
   - **命名**：`issue-<N>-<shortslug>`，shortslug 取 issue 标题转小写 kebab-case（只留字母数字与 `-`）；**总长 ≤64 字符**；**无 `feat/`/`fix/` 前缀、无 `/`**。例：issue #309「gem-synth dedup incremental merge」→ `issue-309-gem-synth-dedup-incremental-merge`。
   - **🚫 禁止** `git checkout -b` / `git switch -c` / `git branch <name>`（只是在当前 checkout 切分支，不是 worktree）。
   - **自检**：模型 A 下 `pwd` 在 `<repo>/.pi/worktrees/` 下（或 `git rev-parse --git-dir` 指向 linked worktree）；模型 B 下确认所有编辑路径以 `$WT` 开头。**ignore 自检**：确认目标仓已 ignore worktree 容器目录（`.gitignore` 含 `.pi/worktrees/`，或写入 `.git/info/exclude`）——否则主 checkout 手滑 `git add -A` 会把 worktree 当 embedded repo 吸入暂存区。
6. **写计划** → **REQUIRED SUB-SKILL: Use writing-plans**（**在 worktree 内**）→ `docs/superpowers/plans/<YYYY-MM-DD>-<slug>.md`。
   - plan 的每个实现 task 必须引用一个或多个 spec 验收 ID；自动化验收项必须落到具体测试、检查或构建命令，用户实测项必须落到实测步骤，或单独建立 post-implementation manual verification task。
   - 不允许出现没有验收归属的实现 task，也不允许出现 spec 验收矩阵中没有对应 plan task 的验收项；不强制使用某一种表格格式，但必须能按验收 ID 双向追溯。
7. **实现** → **REQUIRED SUB-SKILL: Use subagent-driven-development**（worktree 内，**禁碰 main**）。**🚪 Gate：Step 6 的 plan 文档必须存在才能开始实现——spec 不算 plan。** 派 implementer/reviewer 时**显式传 `cwd: <worktree 绝对路径>`**（subagent 工具原生参数，机制强制），并在 task 里保留 `Work from: <worktree 绝对路径>` 作双保险——别让 subagent 回主仓库作业。
8. **本地快速 CR** → `requesting-code-review`（superpowers）或 pi 原生 `workflow` 工具的 `code-review` 模式（agent 按问题复杂度自选深度；**必做**，深度自定）
9. **PR + Zima 单 Bot CR + 前台阻塞等待** → **REQUIRED SUB-SKILL: Use zima-pr-monitor**（**🚪 push/开 PR 前暂停，等用户明确许可**——用户 AGENTS.md 硬规则"不自动 commit/push 除非明确许可"；开 PR、打 `zima:needs-review`、**同 turn 立即前台阻塞等待 CR job 完成（禁止结束 turn，helper 见 zima-pr-monitor）**、解析 review meta（`cc-cr-meta` / `pi-cr-meta` 前缀区分；`kimi-cr-meta` 忽略）、worktree 修、重打标签、收敛判定、合并）。**zima 缺席降级**：个人 fork / 无 bot 仓库（无 zima CR 环境）时，降级为人工 CR 或 pi 原生 `workflow` 工具 `code-review` 模式，并在 issue 评论说明降级原因。

   **验收逐项对账**：本地 CR 和合并前检查必须按 spec 验收矩阵逐项核对。自动化项记录实际执行的命令及结果；用户实测项按清单实际执行并记录观察结果。单测或其他自动化命令通过，不能替代尚未执行的用户实测；用户实测暂时无法执行时标记为 `pending`，不能宣称全部验收完成。自动化验证失败必须修复或明确记录阻塞原因，用户实测失败或 `pending` 状态必须在最终报告中如实呈现。

10. **post-merge**：结束 worktree session（回主仓库 session）→ `git_worktree` `action: "remove"`（或 `git worktree remove <repo>/.pi/worktrees/issue-<N>-<shortslug>`）→ `git worktree prune` → 删本地分支 `git branch -D issue-<N>-<shortslug>`（`git worktree remove` 只删目录不删分支，需单独删）→ 删远端分支 `git push origin --delete issue-<N>-<shortslug> || true`（PR merge 时 GitHub 可能已自动删远端分支，`|| true` 容错）→ `git checkout main && git pull`。调研目录 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/` 设计为跨 harness 留档，**不清理**（release / 部署 / 配置 = 人工，不在自动化环内）

## 为什么高度可自动化
调研（步 3）做细 + JFox KB permanent 笔记够厚 → 步 4 brainstorming/system-debugging 基本已有答案（少澄清）→ 步 6-10 近乎自动。**瓶颈是调研质量 + KB 厚度，不是流程本身**——平时往 JFox 沉淀 permanent note = 给未来自动化攒燃料。

## 关键纪律
- **main 永远干净**：所有仓库产物（spec/plan/code）**从 Step 5 起在 worktree 内产生并提交**。Step 4 的 spec draft 在 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/`（同 research 纪律），不落 main。该目录是全局约定目录，pi 与 Claude Code 会话共用同一份调研（跨 harness 可复用）。
- **spec ≠ plan（不可混淆）**：spec = 设计（决策表/数据流/组件契约/降级/非目标）；plan = 任务拆解（有序 task、文件级改动、每步验证）。**spec 再详也不算 plan，Step 6 不可跳。**
- **worktree 命名**：`issue-<N>-<shortslug>`，无 `feat/`/`fix/` 前缀、无 `/`、总长 ≤64 字符；**禁止 `git checkout -b` / `git switch -c` 在主 checkout 切分支**。
- `git add <file>` 按文件 stage，**别用 `git add -A`**（会把 untracked 临时文件 sweep 进 commit）。
- 调研/spec draft **不进项目目录**（会污染 commit），放 `~/.claude/github-issue-driven/...`。
- issue 的调研结论要评论回 issue 区（留轨迹）。
