# Issue-157 Acceptance Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `github-issue-driven` skill 的 Step 4、Step 6、Step 8–9 中加入“自动化验证 vs 用户实测”的验收分层与端到端追溯规则。

**Architecture:** 这是纯 Markdown skill 文档改动。保留现有 10 步流程结构，只在 Step 4 增加验收矩阵定义，在 Step 6 增加 task↔验收 ID 追溯，在 Step 8–9 增加最终逐项对账；不新增独立模板、解析器或测试代码。

**Tech Stack:** Markdown、shell 文本审计、git diff 检查。

## Global Constraints

- 所有仓库改动在 worktree `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-157-acceptance-layering` 内完成，禁止修改 main。
- 只修改 `pi/github-issue-driven/SKILL.md`；spec 和 plan 文档已在 worktree 内作为流程记录提交。
- 保留当前单 Bot CR、模型 B、subagent `cwd`、push gate、worktree 清理等既有规则，不恢复旧双 Bot 或旧 worktree 文案。
- 顶层验收分类使用“自动化验证”和“用户实测”；自动化验证必须注明具体层级，不能把 integration/static/build/automated E2E 统称为 unit。
- 不新增独立 spec 模板、自动 spec 解析器、`pi/issue-research/SKILL.md` 改动或仓库外 Claude Code skill 同步。
- 代码注释和 commit message 如有新增内容使用英文；skill 正文沿用当前中文风格。

---

### Task 1: 为 Step 4 增加验收方式分层与矩阵要求

**验收 ID:** A1

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（当前 Step 4）

**Interfaces:**
- Consumes: 已有的 issue 路由、spec 产出和 spec gate 规则。
- Produces: 后续 Step 6 可引用的验收 ID 约定，以及可直接复制的验收矩阵字段定义。

- [x] **Step 1: 替换 Step 4 文案，保留原路由和 spec gate**

在当前 Step 4 的“路由”说明之后增加以下要求，不删除原有的 bug/feature 路由、spec draft 路径和“spec 完成后暂停等待用户确认”规则：

```markdown
   - **验收方式分层（必答）**：对本次改动的每个功能点建立验收矩阵，标记为 `自动化验证` 或 `用户实测`，并为每项分配稳定 ID（如 `A1`、`U1`）。自动化验证必须注明具体层级（`unit`、`integration`、`static`、`build`、`automated E2E` 等）、验证命令和通过标准；用户实测必须注明操作步骤、观察结果和通过标准。
   - 自动化验证优先选择足以证明行为的最低成本层级：能用 `unit` 验证的不要升级为 `integration`；必须跨组件时使用 `integration`；类型、格式或依赖约束使用 `static`/`build`；能稳定脚本化的完整流程使用 `automated E2E`。`用户实测` 不是自动化验证暂时没写出来时的兜底分类。
   - 若某项无法或不适合自动化，spec 必须说明原因，并写出实测步骤、观察结果、通过标准和可执行时机。

   spec 中可使用以下矩阵结构（不要求每个 issue 同时包含两类条目）：

   | ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
   |----|--------|----------|----------|----------|
   | A1 | 配置解析行为 | 自动化验证（unit） | `uv run pytest ...` | 相关测试通过 |
   | A2 | CLI 跨组件行为 | 自动化验证（integration） | `uv run pytest ...` | 命令返回码和输出符合预期 |
   | U1 | 真实外部服务交互 | 用户实测 | 按步骤执行并观察结果 | 外部服务产生预期效果 |
```

- [x] **Step 2: 检查 Step 4 仍保留设计 gate**

Run:

```bash
grep -n -A 12 -B 2 '4\. \*\*路由\*\*' pi/github-issue-driven/SKILL.md
```

Expected: 同时看到原有路由、`验收方式分层（必答）`、矩阵字段、`用户实测` 非兜底说明，以及 `spec 完成后暂停`。

- [x] **Step 3: Commit Task 1**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): require acceptance matrix in spec step"
```

---

### Task 2: 为 Step 6 增加 plan 双向追溯要求

**验收 ID:** A2

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（当前 Step 6）

**Interfaces:**
- Consumes: Task 1 产生的 `A1`/`U1` 等验收 ID 和验收矩阵。
- Produces: plan 对实现 task、自动化验证和用户实测项的追溯约束，供 Step 7 实现时执行。

- [x] **Step 1: 在 Step 6 后追加追溯规则**

在当前 Step 6 的 writing-plans 要求之后追加：

```markdown
   - plan 的每个实现 task 必须引用一个或多个 spec 验收 ID；自动化验收项必须落到具体测试、检查或构建命令，用户实测项必须落到实测步骤，或单独建立 post-implementation manual verification task。
   - 不允许出现没有验收归属的实现 task，也不允许出现 spec 验收矩阵中没有对应 plan task 的验收项；不强制使用某一种表格格式，但必须能按验收 ID 双向追溯。
```

- [x] **Step 2: 检查 Step 6 与 Step 7 gate 未被覆盖**

Run:

```bash
grep -n -A 8 -B 2 '6\. \*\*写计划\*\*' pi/github-issue-driven/SKILL.md
grep -n -A 2 '7\. \*\*实现\*\*' pi/github-issue-driven/SKILL.md
```

Expected: Step 6 同时保留 `REQUIRED SUB-SKILL: Use writing-plans`、worktree 要求、双向追溯规则；Step 7 的 plan gate 原文仍存在。

- [x] **Step 3: Commit Task 2**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): trace plan tasks to acceptance ids"
```

---

### Task 3: 为 Step 8–9 增加最终逐项验收规则

**验收 ID:** A3

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（当前 Step 8、Step 9）

**Interfaces:**
- Consumes: Task 1 的验收矩阵和 Task 2 的 task↔验收 ID 映射。
- Produces: 本地 CR、Zima CR 和合并前检查的逐项验收要求。

- [x] **Step 1: 在 Step 8–9 后增加最终对账段落**

在现有 Step 9 的 CR/合并条件之后、`## 为什么高度可自动化` 之前追加：

```markdown

   **验收逐项对账**：本地 CR 和合并前检查必须按 spec 验收矩阵逐项核对。自动化项记录实际执行的命令及结果；用户实测项按清单实际执行并记录观察结果。单测或其他自动化命令通过，不能替代尚未执行的用户实测；用户实测暂时无法执行时标记为 `pending`，不能宣称全部验收完成。自动化验证失败必须修复或明确记录阻塞原因，用户实测失败或 `pending` 状态必须在最终报告中如实呈现。
```

- [x] **Step 2: 检查最终对账规则与既有 CR 门禁兼容**

Run:

```bash
grep -n -A 8 -B 3 '验收逐项对账' pi/github-issue-driven/SKILL.md
grep -nE '单 Bot|pi-cr-meta|kimi-cr-meta|push/开 PR|模型 B|worktree' pi/github-issue-driven/SKILL.md | head -30
```

Expected:

- 找到自动化命令/结果记录、用户实测记录、`pending` 和“不能替代”规则；
- 既有单 Bot、`pi-cr-meta`、push gate、模型 B 和 worktree 规则仍存在，未出现旧双 Bot/旧工作目录要求。

- [x] **Step 3: Commit Task 3**

```bash
git add pi/github-issue-driven/SKILL.md
git commit -m "docs(skill): require acceptance reconciliation before merge"
```

---

### Task 4: 全文一致性验证与本地 CR 准备

**验收 ID:** A1–A4

**Files:**
- Verify: `pi/github-issue-driven/SKILL.md`
- Verify: `docs/superpowers/specs/2026-08-30-issue-157-acceptance-layering-design.md`
- Verify: `docs/superpowers/plans/2026-08-30-issue-157-acceptance-layering.md`

**Interfaces:**
- Consumes: Tasks 1–3 的文档改动。
- Produces: 可提交给本地 CR 和 Zima CR 的完整变更集，验收项 A1–A4 均有证据。

- [x] **Step 1: 执行 Markdown 和范围检查**

Run:

```bash
git diff --check main...HEAD
printf '%s\n' '--- acceptance terms ---'
grep -nE '验收方式分层|自动化验证|用户实测|最低成本|验收 ID|双向追溯|验收逐项对账|pending' pi/github-issue-driven/SKILL.md
printf '%s\n' '--- forbidden legacy wording ---'
! grep -nE '双 Bot|EnterWorktree|ExitWorktree|\.claude/worktrees' pi/github-issue-driven/SKILL.md
printf '%s\n' '--- changed files ---'
git diff --name-only main...HEAD
```

Expected:

- `git diff --check` 无输出并返回 0；
- 关键验收词全部出现；
- 旧双 Bot、旧 worktree 工具或旧工作目录文案检查返回 0；
- 变更文件只有 spec、plan 和 `pi/github-issue-driven/SKILL.md`。

- [x] **Step 2: 按 spec A1–A4 对账**

逐项确认：

- A1：Step 4 有两类验收定义、矩阵字段、自动化层级和用户实测失败说明；
- A2：Step 6 有 task→验收项和验收项→task 的双向追溯；
- A3：Step 8–9 有命令/结果记录、实测记录、`pending` 和禁止替代规则；
- A4：单 Bot、worktree、push gate 等当前规则仍保留，且没有恢复旧文案。

- [x] **Step 3: 查看最终 diff，准备本地 CR**

Run:

```bash
git diff --stat main...HEAD
git diff main...HEAD -- pi/github-issue-driven/SKILL.md
```

Expected: 只有目标 skill 的三处流程文案变化；没有删除既有流程纪律，也没有引入模板、代码或其他 skill 改动。
