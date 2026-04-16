# GitHub Code Review Skill 升级设计文档

> 将 Claude Code 官方 `code-review` 插件迁移并升级为 Kimi CLI 的全局 Skill。

## 1. 背景与目标

### 1.1 背景

Claude Code 官方插件市场中有一个 `code-review` 插件，它通过多 Agent 并行审查 Pull Request，并配合 issue 验证机制过滤误报，实现高质量的自动化代码审查。

在 Kimi CLI 生态中，已存在一个 `github-code-review` skill，但其机制与官方插件存在差异：
- 使用置信度评分机制过滤问题
- 依赖假设存在的 MCP 工具发布评论
- 仅支持 AGENTS.md 合规检查

### 1.2 目标

将现有 `github-code-review` skill 升级为**完整复刻** Claude 官方 `code-review` 插件的核心工作流，同时：
- 扩展审查范围至 **CLAUDE.md + AGENTS.md**
- 使用稳定可用的 `gh` CLI 发布 PR 评论
- 确保 PR 评论为**必选项**而非可选项

## 2. 设计概述

### 2.1 Skill 存放位置

```
~/.config/agents/skills/github-code-review/
└── SKILL.md
```

这是一个全局 skill，直接覆盖升级现有的同名 skill。

### 2.2 核心原则

- **纯指令驱动**：不引入额外的脚本或资源文件，所有逻辑通过 `SKILL.md` 中的指令 + Kimi 的 `Agent` / `Shell` 工具完成。
- **纯 `gh` CLI**：所有 GitHub 交互均通过 `gh` 命令执行，不依赖任何 MCP server，保证开箱即用。
- **完整复刻流程**：严格遵循 Claude 插件的 9 步工作流（4 步审查扩展为 5 步）。

## 3. Agent 审查流程

### 3.1 完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: PR 资格审查                                         │
│  - 检查 PR 是否 closed / draft                               │
│  - 检查是否 trivial / automated                              │
│  - 检查是否已被本 bot 评论过                                  │
│  → 任一条件满足，停止并说明原因                               │
├─────────────────────────────────────────────────────────────┤
│  Step 2: 收集项目规范                                        │
│  - 获取修改文件列表 (gh pr diff --name-only)                 │
│  - 收集根目录及各文件所在目录的 CLAUDE.md 和 AGENTS.md        │
├─────────────────────────────────────────────────────────────┤
│  Step 3: PR 变更摘要                                         │
│  - gh pr view 获取标题和描述                                 │
│  - gh pr diff 获取完整 diff                                  │
│  - SubAgent 总结变更内容                                      │
├─────────────────────────────────────────────────────────────┤
│  Step 4: 5 个并行审查 Agent                                  │
│  - Agent 1: CLAUDE.md compliance                             │
│  - Agent 2: CLAUDE.md compliance (并行冗余)                   │
│  - Agent 3: AGENTS.md compliance (新增)                      │
│  - Agent 4: Obvious bugs in diff                             │
│  - Agent 5: Logic / security issues in changed code          │
├─────────────────────────────────────────────────────────────┤
│  Step 5: Issue 验证                                          │
│  - 对每个发现的问题启动独立 SubAgent 验证                      │
│  - 确认问题真实存在，规则确实适用且确实被违反                  │
├─────────────────────────────────────────────────────────────┤
│  Step 6: 过滤与汇总                                          │
│  - 只保留验证通过的 issue                                     │
│  - 汇总为高信号问题列表                                       │
├─────────────────────────────────────────────────────────────┤
│  Step 7: 最终资格审查                                        │
│  - 再次确认 PR 仍然开放                                       │
│  → 若已关闭，作为安全兜底不发布评论，并告知用户               │
├─────────────────────────────────────────────────────────────┤
│  Step 8: 终端输出                                            │
│  - 以 Markdown 格式输出审查结果                               │
├─────────────────────────────────────────────────────────────┤
│  Step 9: 发布 PR 评论（必须）                                 │
│  - 使用 gh pr review --comment -b "<body>" 发布评论          │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 审查 Agent 详细定义

#### Agent 1 & 2: CLAUDE.md Compliance Checker
- **输入**: PR diff, CLAUDE.md 文件列表
- **任务**: 审计变更是否符合 CLAUDE.md 规范
- **注意**: 只考虑与变更文件共享路径或父目录的 CLAUDE.md
- **输出**: 问题列表 `[{description, reason, file, lines, suggestion}]`

#### Agent 3: AGENTS.md Compliance Checker
- **输入**: PR diff, AGENTS.md 文件列表
- **任务**: 审计变更是否符合 AGENTS.md 规范
- **注意**: 区分适用于代码审查的规则 vs 仅适用于编码执行的规则
- **输出**: 问题列表 `[{description, reason, file, lines, suggestion}]`

#### Agent 4: Obvious Bug Scanner
- **输入**: PR diff
- **任务**: 仅关注变更本身，不读取额外上下文
- **范围**: 扫描明显的逻辑错误、空值处理、竞态条件、语法错误、缺失导入等
- **原则**: 只报告严重 Bug，忽略小问题、风格问题和可能的误报
- **输出**: 问题列表 `[{description, reason, file, lines, suggestion}]`

#### Agent 5: Logic / Security Analyzer
- **输入**: PR diff
- **任务**: 在引入的代码中寻找深层问题
- **范围**: 安全问题、不正确逻辑、资源泄漏、边界条件处理不当等
- **原则**: 只关注变更代码范围内的问题
- **输出**: 问题列表 `[{description, reason, file, lines, suggestion}]`

### 3.3 Issue 验证机制

每个在 Step 4 中发现的问题都必须经过独立验证：

- **验证 Agent 输入**: 单个问题描述、PR diff、相关规范文件列表
- **验证 Agent 任务**:
  1. 验证问题是否真实存在
  2. 对于规范问题：双重检查规范文件是否明确提到该规则，且该规则确实适用于被审查文件
  3. 对于 Bug：验证代码逻辑是否确实如报告所述存在问题
- **验证 Agent 输出**: `{valid: boolean, explanation: string}`

只有 `valid: true` 的问题才会进入最终报告。

### 3.4 高信号原则（Critical: HIGH SIGNAL ONLY）

只标记以下类型的问题：
- 代码将无法编译或解析（语法错误、类型错误、缺失导入、未解析引用）
- 代码无论输入如何都会产生错误结果（明显逻辑错误）
- 清晰、无歧义的 CLAUDE.md 或 AGENTS.md 违规，且能引用具体规则

**不标记**：
- 代码风格或质量问题
- 依赖特定输入或状态才可能发生的问题
- 主观建议或改进意见
- 预存在问题（非 PR 引入）
- Linter 会捕获的问题
- 被 lint ignore 注释明确忽略的规则

## 4. 输出与评论格式

### 4.1 终端输出格式

发现问题的示例：

```markdown
### Code Review

Found 3 issues:

1. Missing error handling for OAuth callback (CLAUDE.md says "Always handle OAuth errors")

https://github.com/owner/repo/blob/abc123.../src/auth.ts#L67-L72

2. Memory leak: OAuth state not cleaned up (bug due to missing cleanup in finally block)

https://github.com/owner/repo/blob/abc123.../src/auth.ts#L88-L95

3. Inconsistent naming pattern (AGENTS.md says "Use camelCase for functions")

https://github.com/owner/repo/blob/abc123.../src/utils.ts#L23-L28
```

无问题的示例：

```markdown
### Code Review

No issues found. Checked for bugs, CLAUDE.md and AGENTS.md compliance.
```

### 4.2 代码链接格式要求

必须严格遵循以下格式，否则 GitHub Markdown 无法正确渲染：

```
https://github.com/owner/repo/blob/[full-sha]/path/file.ext#L[start]-L[end]
```

要求：
- 使用完整 SHA（不是缩写）
- `#L` 表示行号
- 行范围格式：`L[start]-L[end]`
- 至少包含 1 行上下文（评论行前后各至少 1 行）

### 4.3 PR 评论发布

**每次执行必须发布评论**，使用命令：

```bash
gh pr review --comment -b "<review_body>"
```

评论内容与终端最终输出的 Markdown 报告完全一致（不包含审查过程的中间信息）。

## 5. 工具与错误处理

### 5.1 使用的 Kimi 工具

| 工具 | 用途 |
|------|------|
| `Shell` | 执行 `gh pr view`, `gh pr diff`, `gh pr review` 等命令 |
| `Agent` | 启动并行 subagent 进行审查、总结和 issue 验证 |

### 5.2 常见错误处理

| 场景 | 处理方式 |
|------|---------|
| `gh` 未安装或未认证 | 提示用户安装并运行 `gh auth login` |
| 当前目录不是 Git 仓库 | 提示用户切换到 Git 仓库目录 |
| 仓库无 GitHub remote | 提示用户配置 GitHub remote |
| PR 不存在 | 提示用户检查 PR 编号或当前分支 |
| PR 在审查过程中关闭 | Step 7 最终检查捕获，不发布评论并告知用户 |
| 无 CLAUDE.md / AGENTS.md | 跳过对应合规检查，仅进行 Bug 扫描 |

## 6. 与现有 skill 的升级对比

| 维度 | 现有 `github-code-review` | 新版设计 |
|------|--------------------------|---------|
| **并行审查 Agent** | 4-5 个（compliance + bug + history + pr-comment + code-comment） | **5 个（2x CLAUDE.md + 1x AGENTS.md + 2x bug）** |
| **问题过滤机制** | 置信度评分（阈值 80） | **Issue 验证机制（验证通过才保留）** |
| **规范检查范围** | 仅 AGENTS.md | **CLAUDE.md + AGENTS.md** |
| **评论发布方式** | 假设 MCP `add_issue_comment` | **纯 `gh pr review --comment`** |
| **PR 评论可选性** | 可选（需 `--comment`） | **必须** |
| **历史分析** | 有（git blame + 相关 PR 评论） | **移除**（聚焦 diff 本身，降低噪音） |
| **开箱即用性** | 依赖 MCP 配置 | **仅需 `gh` CLI 即可** |

## 7. 实现范围

本次升级只涉及重写 `~/.config/agents/skills/github-code-review/SKILL.md` 文件，不引入任何脚本、配置文件或额外资源。
