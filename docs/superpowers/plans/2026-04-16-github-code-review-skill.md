# GitHub Code Review Skill 升级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 `github-code-review` skill 升级为完整复刻 Claude 官方 `code-review` 插件的工作流，扩展支持 CLAUDE.md + AGENTS.md 审查，使用 `gh` CLI 发布 PR 评论。

**Architecture:** 纯 `SKILL.md` 指令驱动，不引入任何脚本或资源文件。整个工作流通过 Markdown 中的指令引导 Kimi 使用 `Shell` 执行 `gh` 命令，使用 `Agent` 启动并行 subagent 进行审查和 issue 验证。

**Tech Stack:** Markdown, GitHub CLI (`gh`), Kimi `Agent` / `Shell` tools

---

### Task 1: 备份现有 SKILL.md

**Files:**
- Read: `~/.config/agents/skills/github-code-review/SKILL.md`
- Create: `~/.config/agents/skills/github-code-review/SKILL.md.bak`

- [ ] **Step 1: 备份原文件**

  将现有 skill 文件复制为备份，防止升级过程中丢失内容：

  ```powershell
  Copy-Item -Path "$env:USERPROFILE\.config\agents\skills\github-code-review\SKILL.md" -Destination "$env:USERPROFILE\.config\agents\skills\github-code-review\SKILL.md.bak" -Force
  ```

- [ ] **Step 2: 确认备份成功**

  检查备份文件是否存在：

  ```powershell
  Test-Path "$env:USERPROFILE\.config\agents\skills\github-code-review\SKILL.md.bak"
  ```

  Expected: `True`

---

### Task 2: 重写 SKILL.md — Frontmatter 与概述

**Files:**
- Modify: `~/.config/agents/skills/github-code-review/SKILL.md`

- [ ] **Step 1: 编写新的 YAML frontmatter**

  新的 `SKILL.md` 开头必须是以下 frontmatter：

  ```yaml
  ---
  name: github-code-review
  description: |
    GitHub Pull Request 自动化代码审查工具。
    复刻 Claude Code 官方 code-review 插件工作流，使用多 Agent 并行审查 PR 变更，
    通过 issue 验证机制过滤误报，支持 CLAUDE.md 和 AGENTS.md 双重规范检查。
    使用 gh CLI 发布 PR 评论，无需额外 MCP 配置。
    
    触发词: "review pr", "审查 pr", "pr review", "github review", "review pull request"
  ---
  ```

- [ ] **Step 2: 编写概述与前置要求**

  在 frontmatter 后立即写入：

  ```markdown
  # GitHub Code Review Skill

  GitHub Pull Request 自动化代码审查工具。完整复刻 Claude Code 官方 `code-review` 插件工作流，适配 Kimi CLI 工具环境。

  ## 使用方式

  在 Git 仓库目录中，使用以下方式触发：

  ```
  review pr
  审查 pr #123
  pr review
  github review
  review pull request
  ```

  ## 前置要求

  1. **GitHub CLI (gh)** 已安装并认证：
     ```bash
     gh auth login
     ```
  2. 当前目录在 Git 仓库中，且有 GitHub remote

  ## 核心原则

  - **HIGH SIGNAL ONLY**: 只报告编译错误、确定性的逻辑错误、明确违反 CLAUDE.md 或 AGENTS.md 的规则
  - **不报告**: 代码风格、主观建议、 linter 会捕获的问题、预存在问题
  ```

---

### Task 3: 重写 SKILL.md — 核心 9 步工作流指令

**Files:**
- Modify: `~/.config/agents/skills/github-code-review/SKILL.md`

- [ ] **Step 1: 写入主执行流程指令**

  在 `SKILL.md` 中追加完整的工作流指令：

  ```markdown
  ## 执行流程

  当用户触发此 Skill 时，严格按以下步骤执行：

  ### Step 1: PR 资格审查

  使用 `Shell` 执行：
  - `gh pr view <PR> --json state,isDraft,title,body`
  - `gh pr view <PR> --comments`

  检查以下任一条件，如满足则停止并说明原因：
  - PR 状态为 `CLOSED`
  - PR 是 `draft`
  - PR 是 trivial / automated（如描述包含 "automated", "bump version", 仅依赖更新等）
  - 本 bot 已在此 PR 下留过评论（评论作者匹配当前环境）

  > 例外：Claude / Kimi 生成的 PR 仍然审查。

  ### Step 2: 收集项目规范

  1. 使用 `Shell` 执行 `gh pr diff <PR> --name-only` 获取修改文件列表
  2. 检查并读取以下文件（如存在）：
     - 根目录 `CLAUDE.md`
     - 根目录 `AGENTS.md`
     - 各修改文件所在目录的 `CLAUDE.md`
     - 各修改文件所在目录的 `AGENTS.md`

  ### Step 3: 获取 PR 摘要

  1. `gh pr view <PR>` 获取标题、描述、作者
  2. `gh pr diff <PR>` 获取完整 diff
  3. 启动一个轻量 subagent，输入 diff + 标题 + 描述，输出变更摘要（1-3 句话）

  ### Step 4: 5 个并行审查 Agent

  启动 5 个并行 `Agent` 审查变更。每个 Agent 接收：PR diff、变更摘要、PR 标题和描述、相关规范文件。

  **Agent 1: CLAUDE.md compliance checker**
  - 审计变更是否符合 CLAUDE.md 规范
  - 只考虑与变更文件共享路径或父目录的 CLAUDE.md

  **Agent 2: CLAUDE.md compliance checker (冗余并行)**
  - 同 Agent 1，独立执行以增加召回率

  **Agent 3: AGENTS.md compliance checker**
  - 审计变更是否符合 AGENTS.md 规范
  - 注意区分适用于代码审查的规则 vs 仅适用于编码执行的规则

  **Agent 4: Obvious bug scanner**
  - 仅关注 diff 本身，不读取额外上下文
  - 扫描明显的逻辑错误、空值处理、竞态条件、语法错误、缺失导入
  - 只报告严重 Bug，忽略小问题、风格问题和可能的误报

  **Agent 5: Logic / security analyzer**
  - 在引入的代码中寻找深层问题：安全问题、不正确逻辑、资源泄漏、边界条件
  - 只关注变更代码范围内的问题

  **每个 Agent 输出格式**：
  ```json
  [
    {
      "description": "问题描述",
      "reason": "原因（CLAUDE.md / AGENTS.md / bug / logic）",
      "file": "文件路径",
      "lines": "行号范围",
      "suggestion": "修复建议（如有）"
    }
  ]
  ```

  ### Step 5: Issue 验证

  对 Step 4 中收集到的所有 issue，**逐个启动并行 subagent 验证**。

  **验证 Agent 输入**：单个 issue + PR diff + 相关规范文件内容
  **验证 Agent 任务**：
  1. 该问题是否真实存在？
  2. 对于规范问题：规范文件是否明确提到该规则，且规则确实适用于该文件？
  3. 对于 Bug：代码逻辑是否确实如报告所述存在问题？

  **验证 Agent 输出**：
  ```json
  { "valid": true, "explanation": "解释" }
  ```

  只有 `valid: true` 的问题才会进入最终报告。

  ### Step 6: 过滤与汇总

  - 丢弃所有验证未通过的 issue
  - 去重：相同文件、相同行范围、相同原因的问题只保留一条
  - 按 `reason` 分组排序：CLAUDE.md → AGENTS.md → bug → logic

  ### Step 7: 最终资格审查

  再次使用 `Shell` 执行 `gh pr view <PR> --json state`：
  - 若状态已变为 `CLOSED` 或 `MERGED`，停止，不发布评论，告知用户

  ### Step 8: 终端输出

  生成 Markdown 格式的审查报告并输出到终端：

  ```markdown
  ### Code Review

  Found N issues:

  1. {description} ({reason})

  https://github.com/{owner}/{repo}/blob/{full-sha}/{file}#L{start}-L{end}
  ...
  ```

  如果没有问题：
  ```markdown
  ### Code Review

  No issues found. Checked for bugs, CLAUDE.md and AGENTS.md compliance.
  ```

  **代码链接要求**：
  - 使用完整 SHA（通过 `git rev-parse HEAD` 获取）
  - 格式：`https://github.com/owner/repo/blob/[sha]/path#L[start]-L[end]`
  - 至少包含 1 行上下文（评论行前后各至少 1 行）

  ### Step 9: 发布 PR 评论（必须）

  使用 `Shell` 执行：

  ```bash
  gh pr review <PR> --comment -b "<review_body>"
  ```

  `<review_body>` 与终端最终输出的 Markdown 报告完全一致。
  ```

---

### Task 4: 重写 SKILL.md — 高信号原则与错误处理

**Files:**
- Modify: `~/.config/agents/skills/github-code-review/SKILL.md`

- [ ] **Step 1: 写入 HIGH SIGNAL 原则指令**

  追加以下内容：

  ```markdown
  ## HIGH SIGNAL 原则

  只标记以下类型的问题：
  - 代码将无法编译或解析（语法错误、类型错误、缺失导入、未解析引用）
  - 代码无论输入如何都会产生错误结果（明显逻辑错误）
  - 清晰、无歧义的 CLAUDE.md 或 AGENTS.md 违规，且能引用具体规则原文

  **绝不标记**：
  - 代码风格或质量问题
  - 依赖特定输入或状态才可能发生的问题
  - 主观建议或改进意见
  - 预存在问题（非 PR 引入）
  - Linter / TypeChecker 会捕获的问题
  - 被 lint ignore 注释明确忽略的规则
  - 看起来像 bug 但实际上正确的代码

  如果你不确定一个问题是否真实，不要标记它。误报会侵蚀信任并浪费审查者时间。
  ```

- [ ] **Step 2: 写入错误处理与边界情况**

  追加以下内容：

  ```markdown
  ## 边界情况处理

  | 情况 | 处理方式 |
  |------|---------|
  | PR 已关闭 | Step 1 / Step 7 捕获，跳过并说明原因 |
  | PR 是草稿 | Step 1 捕获，跳过 |
  | 本 bot 已评论过 | Step 1 捕获，跳过避免重复 |
  | trivial / automated PR | Step 1 捕获，跳过 |
  | 无 CLAUDE.md | Agent 1 & 2 跳过，仅其他 agent 审查 |
  | 无 AGENTS.md | Agent 3 跳过，仅其他 agent 审查 |
  | 审查过程中 PR 关闭 | Step 7 捕获，不发布评论 |
  | 无问题通过验证 | 输出 "No issues found" 并作为评论发布 |
  ```

---

### Task 5: 验证新 SKILL.md 格式

**Files:**
- Read: `~/.config/agents/skills/github-code-review/SKILL.md`

- [ ] **Step 1: 检查 YAML frontmatter**

  确认文件开头符合：
  ```yaml
  ---
  name: github-code-review
  description: |
    ...
  ---
  ```

  确认 `name` 和 `description` 字段存在且不为空。

- [ ] **Step 2: 检查关键章节完整性**

  确认文件中包含以下章节：
  - `# GitHub Code Review Skill`
  - `## 使用方式`
  - `## 前置要求`
  - `## 执行流程`
  - `## HIGH SIGNAL 原则`
  - `## 边界情况处理`

- [ ] **Step 3: 行数检查**

  确认 `SKILL.md` 总行数在 400-600 行之间。如超过 600 行，考虑精简冗余描述。

---

### Task 6: 提交更改

**Files:**
- `~/.config/agents/skills/github-code-review/SKILL.md`

- [ ] **Step 1: 查看改动差异**

  在 git 仓库（zima-blue-cli）中确认设计/计划文档状态，并检查 skill 文件是否已保存：

  ```powershell
  Get-Content "$env:USERPROFILE\.config\agents\skills\github-code-review\SKILL.md" -Head 20
  ```

- [ ] **Step 2: 清理备份文件（可选）**

  如果新 skill 已验证无误，删除备份：

  ```powershell
  Remove-Item "$env:USERPROFILE\.config\agents\skills\github-code-review\SKILL.md.bak" -Force
  ```

- [ ] **Step 3: 提交设计/计划文档到 git**

  由于 skill 文件位于用户全局配置目录（不在当前 git 仓库内），只需提交已保存的 spec 和 plan：

  ```bash
  git add docs/superpowers/
  git commit -m "docs(plan): add github-code-review skill implementation plan"
  ```

---

## Self-Review Checklist

- [x] **Spec coverage**: 设计文档中的 9 步流程、5 个并行 agent、issue 验证、PR 评论必发、CLAUDE.md+AGENTS.md 双重检查均已覆盖
- [x] **Placeholder scan**: 计划中没有 TBD、TODO、"implement later" 等占位符
- [x] **Type consistency**: N/A（纯 Markdown skill，无代码类型）
