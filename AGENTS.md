# Zima Blue CLI - Agent 工厂车间

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》

**Zima Blue** 是一个个人 Agent 编排平台,让你能够在自己的电脑上运行一个 7x24 小时自主工作的 AI Agent 工厂。你只需与 Agent 对话,第二天早上醒来,Agent 已经帮你实现了多个版本。

> 📚 **文档导航**
> - [愿景和故事](../docs/vision/) — 项目愿景和齐马蓝故事
> - [架构设计](../docs/architecture/) ⭐ **最新设计，以此为准**
> - [历史文档](../docs/history/) — 设计演进过程（仅供参考）
> - [架构决策](../docs/decisions/) — ADR 决策记录
> - [会话历史](./SESSION.md) — 开发会话记录

---

## Session History

📋 **完整会话历史**: [SESSION.md](./SESSION.md)

> 最近 Session 摘要：
> - **Session 7** (2026-03-28): Kimi Agent 集成测试 - 完成真实集成测试（7个测试全部通过），测试报告，清理脚本
> - **Session 6** (2026-03-26): AgentConfig 模型实现 - 支持 kimi/claude/gemini 多类型，参数模板，命令构建，37个单元测试
> - **Session 5** (2026-03-26): 基础设施与测试框架 - 完成 ConfigManager、BaseConfig、测试框架，107个单元测试全部通过
> - **Session 4** (2026-03-26): Zima CLI 接口层设计 - 完成五组配置实体 (agent/workflow/variable/env/pmg) 和完整 CLI 接口设计文档
> - **Session 3** (2026-03-26): 文档整理与同步 - 重写架构文档、简化 README、归档设计草图

## 1. 项目愿景

### 1.1 核心理念

Zima 是一个 **Agent 启动器**，管理 Kimi CLI 的执行参数：

```
你定义 Prompt 模板 → Zima 配置参数 → Kimi 执行 → 返回结果
```

**适用场景**:
- **SOP 任务**: 运维脚本、数据处理、报告生成
- **研发任务**: 测试覆盖、代码重构（通过 Prompt 定义工作流）
- **CI/CD 集成**: 作为构建步骤，返回结构化结果

### 1.2 命名来源

**Zima Blue** 源自 Alastair Reynolds 的科幻短篇《齐马蓝》。故事讲述了一个艺术家机器人不断回归最初的蓝色——一种纯粹、原始、本质的颜色。

这个名字象征着:
- **回归本质**: 剥离复杂的管理系统，回归"配置→执行→结果"的简单模式
- **纯粹执行**: Kimi 专注于执行 Prompt 定义的工作流
- **自我进化**: 从简单开始，逐步完善 Prompt 模板

---

## 2. 系统架构

### 2.1 单次执行模型

```
┌─────────────────────────────────────────────────────────────────┐
│                     Zima Agent Runner                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   1️⃣ 配置阶段                                                    │
│   ├── 读取 agent.yaml（元数据 + prompt + 执行参数）               │
│   └── 渲染 Prompt 模板（注入变量）                                │
│                                                                 │
│   2️⃣ 执行阶段                                                    │
│   ├── 生成 Kimi CLI 命令                                         │
│   ├── 唤起 kimi --print --prompt ...                             │
│   └── 捕获 stdout 到日志文件                                     │
│                                                                 │
│   3️⃣ 结果阶段                                                    │
│   ├── 解析输出（提取 JSON 结果）                                  │
│   └── 返回 RunResult（状态、摘要、日志路径）                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

> 💡 **与循环架构的区别**: 见 [ADR 004](../docs/decisions/004-single-execution.md)
>
> - 删除了 15 分钟循环、守护进程、状态同步
> - 简化为单次执行，由用户/脚本决定何时运行

### 2.2 三层记忆架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent 个人知识库                          │
│              (agent: zima-blue-dev-001)                     │
├─────────────────────────────────────────────────────────────┤
│ 🧠 Session 记忆（短期）                                      │
│    - 上一轮做了什么                                          │
│    - 学到了什么经验                                          │
│    - 犯的错误                                                │
│                                                              │
│ 📚 累积经验（中期）                                          │
│    - 多次 session 的模式总结                                 │
│    - 对特定技术的熟练度                                      │
│    - 个人的代码风格偏好                                      │
│                                                              │
│ 🎯 元认知（长期）                                            │
│    - 自己在项目中的角色定位                                  │
│    - 与人类的协作模式                                        │
│    - 自我改进的目标                                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 每次苏醒时读取 / 结束时写入
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    项目知识库（共享，只读）                   │
│                    (kb: zima-blue)                          │
├─────────────────────────────────────────────────────────────┤
│ 📋 项目长期记忆                                              │
│    - 架构决策 (ADR)                                          │
│    - 里程碑                                                  │
│    - 技术方案                                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 读取
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Issue（执行状态）                  │
├─────────────────────────────────────────────────────────────┤
│ 📝 当前任务状态                                              │
│    - 本次要执行的具体任务                                    │
│    - 代码进度检查点                                          │
│    - 读写在每个周期                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 安全边界 (信任等级)

| 等级 | 操作类型 | 夜间自动 | 说明 |
|------|---------|---------|------|
| 🟢 L1 | 只读/分析 | ✅ 自动 | 读取知识库、分析代码、生成方案 |
| 🟡 L2 | 本地修改 | ✅ 自动 | 编写代码、本地测试、生成文档 |
| 🟠 L3 | 本地提交 | ✅ 自动 | `git commit` 到 feature 分支 |
| 🔴 L4 | 远程操作 | ❌ 禁止 | `git push`、合并 PR、部署生产 |

**原则**: Agent 只能执行 L1-L3, L4 必须人工审查后执行。

---

## 3. 项目结构

```
zima-blue-cli/
│
├── AGENTS.md                   # 本文件: Agent 开发指南
├── README.md                   # 项目介绍(面向人类)
├── docs/                       # 项目文档
│   ├── API-INTERFACE.md        # CLI 接口文档
│   ├── guides/                 # 指南与模板
│   ├── reports/                # 测试报告
│   └── ...
│
├── zima/                       # CLI 源码 (包名)
│   ├── __init__.py
│   ├── cli.py                  # 主 CLI 入口 (Typer)
│   ├── commands/               # CLI 子命令
│   │   ├── __init__.py
│   │   ├── agent.py            # `zima agent *`
│   │   ├── workflow.py         # `zima workflow *`
│   │   ├── variable.py         # `zima variable *`
│   │   ├── env.py              # `zima env *`
│   │   ├── pmg.py              # `zima pmg *`
│   │   └── pjob.py             # `zima pjob *`
│   │
│   ├── config/                 # 配置管理
│   │   ├── __init__.py
│   │   └── manager.py          # ConfigManager - 统一配置管理
│   │
│   ├── core/                   # 核心逻辑
│   │   ├── __init__.py
│   │   ├── runner.py           # AgentRunner (单次执行)
│   │   ├── kimi_runner.py      # KimiRunner (周期执行)
│   │   ├── scheduler.py        # CycleScheduler
│   │   ├── state_manager.py    # 状态管理
│   │   └── daemon.py           # 守护进程
│   │
│   ├── execution/              # 执行层
│   │   ├── __init__.py
│   │   ├── executor.py         # PJob 执行器
│   │   └── history.py          # 执行历史
│   │
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   ├── base.py             # BaseConfig, Metadata
│   │   ├── agent.py            # AgentConfig, AgentState, RunResult, CycleResult
│   │   ├── workflow.py         # WorkflowConfig, VariableDef
│   │   ├── variable.py         # VariableConfig
│   │   ├── env.py              # EnvConfig, SecretDef
│   │   ├── pmg.py              # PMGConfig, ParameterDef, ConditionDef
│   │   ├── pjob.py             # PJobConfig, PJobSpec, ExecutionOptions
│   │   └── config_bundle.py    # ConfigBundle
│   │
│   └── utils.py                # 工具函数
│
├── tests/                      # 测试
│   ├── __init__.py
│   ├── conftest.py             # pytest 配置
│   ├── base.py                 # TestIsolator 基类
│   ├── unit/                   # 单元测试
│   │   ├── test_models_*.py
│   │   └── test_config_manager.py
│   └── integration/            # 集成测试
│       ├── test_kimi_agent_integration.py    # Mock 测试
│       ├── test_kimi_agent_real.py           # 真实 Kimi 测试
│       └── test_*_commands.py
│
├── scripts/                    # 维护脚本
│   ├── cleanup.py              # 清理临时文件脚本
│   └── README.md
│
├── agents/                     # Agent 运行时目录 (gitignored)
│   └── example-agent/
│       ├── agent.yaml
│       ├── prompts/
│       ├── logs/
│       └── workspace/
│
├── logs/                       # 日志目录 (gitignored)
├── workspace/                  # 工作目录 (gitignored)
│
├── pyproject.toml              # Python 项目配置
├── requirements.txt            # 依赖
├── cleanup.bat                 # Windows 清理快捷命令
└── cleanup.sh                  # Unix 清理快捷命令
```

---

## 4. Agent 身份与命名

### 4.1 命名规范

每个 Agent 拥有全局唯一身份标识:

```
格式: {project}-{role}-{instance}

示例:
- zima-blue-dev-001      (Zima Blue 项目开发 Agent #1)
- zima-blue-test-001     (Zima Blue 项目测试 Agent #1)
- boktionary-dev-001     (Boktionary 项目开发 Agent #1)
```

### 4.2 知识库存储

```
~/.zettelkasten-agent-{agent_name}/
├── notes/
│   ├── session/           # 每轮周期的 Session 记忆
│   │   ├── 20260325-0015.md
│   │   └── ...
│   │
│   ├── experience/        # 累积经验
│   │   ├── patterns.md
│   │   ├── mistakes.md
│   │   └── skills.md
│   │
│   └── meta/              # 元认知
│       ├── identity.md
│       └── goals.md
│
└── .zk/                   # 向量索引
```

---

## 5. 开发规范

### 5.1 Python 代码风格

- **格式化**: Black (line-length: 100)
- **类型检查**: mypy (strict mode)
- **代码质量**: ruff
- **文档**: Google docstring style

### 5.2 提交规范

```
类型(模块): 简短描述

详细描述(可选)

类型:
- feat: 新功能
- fix: Bug 修复
- docs: 文档更新
- test: 测试相关
- refactor: 重构
- chore: 构建/工具
```

### 5.3 Agent 参与项目的准则

当 Agent 在这个项目上工作时:

1. **优先读取 AGENTS.md**: 每次开始工作前确认当前规范
2. **保持知识库同步**: 
   - 读取个人记忆了解之前的进展
   - 更新 skills.md 记录新掌握的技能
   - 更新 mistakes.md 记录犯的错误
3. **小步快跑**:
   - 每个周期完成一个可验证的小任务
   - 如果任务太大,主动提出拆分
4. **记录 Session**:
   - 每个周期结束时创建 session 笔记
   - 包含:做了什么、学到了什么、遇到了什么问题

---

## 6. 命令设计

### 6.1 命令概览

```bash
# 简写命令 (快捷方式)
zima create <name>                  # 快速创建 Agent
zima run <name>                     # 执行 Agent
zima list                           # 列出 Agent
zima show <name>                    # 查看 Agent
zima logs <name>                    # 查看日志

# 完整命令组
zima agent *                        # Agent 管理 (create/list/show/update/delete/validate/test)
zima workflow *                     # Workflow 管理 (create/list/show/update/delete/validate/render/add-var)
zima variable *                     # Variable 管理 (create/list/show/update/delete/set/get/validate/merge)
zima env *                          # Environment 管理 (create/list/show/update/delete/set/set-secret/unset/validate)
zima pmg *                          # PMG 参数组管理 (create/list/show/update/delete/add-param/remove-param/validate)
zima pjob *                         # PJob 执行管理 (create/list/show/update/delete/run/render/validate/copy/history)
```

### 6.2 使用示例

```bash
# ===== Agent 管理 =====
# 创建不同类型的 Agent
zima agent create --name "Code Reviewer" --code code-reviewer --type kimi
zima agent create --name "Doc Writer" --code doc-writer --type claude --model claude-sonnet-4-6

# 查看和测试
zima agent show code-reviewer
zima agent test code-reviewer       # 预览生成的 CLI 命令
zima agent validate code-reviewer

# ===== Workflow 管理 =====
# 创建带模板的 Workflow
zima workflow create --name "Code Review" --code code-review --template "# Review: {{ task_name }}"

# 渲染模板
zima workflow render code-review --var review-vars

# ===== Variable 管理 =====
# 创建变量配置
zima variable create --name "Review Vars" --code review-vars
zima variable set review-vars task_name "Bug Fix"
zima variable set review-vars priority "high"

# ===== Env 管理 =====
# 创建环境配置
zima env create --name "Prod Env" --code prod-env
zima env set-secret prod-env API_KEY --source env

# ===== PJob 执行 =====
# 创建 PJob (组合所有配置)
zima pjob create \
  --name "Daily Code Review" \
  --code daily-review \
  --agent code-reviewer \
  --workflow code-review \
  --variable review-vars \
  --env prod-env \
  --label automated

# 渲染预览
zima pjob render daily-review --show-command

# 执行
zima pjob run daily-review

# 查看历史
zima pjob history daily-review

# 清理
./cleanup.sh --auto                   # 清理缓存和临时文件
```

### 6.2 Agent 配置 (agent.yaml)

```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  name: zima-blue-dev-001
  displayName: "Zima Blue 开发 Agent"
  organization: personal
  team: default
  labels:
    role: backend
    specialty: cli

spec:
  # 知识库配置
  knowledgeBases:
    personal:
      type: zettelkasten
      path: "~/.zettelkasten-agent-zima-blue-dev-001"
    project:
      type: zettelkasten
      path: "./docs/knowledge-base"
      access: read-only

  # 运行时配置
  runtime:
    cycleInterval: 900           # 15 分钟
    maxExecutionTime: 840        # 14 分钟
    yolo: true
    workspace: "./workspace"
    logs: "./logs"

  # 能力配置
  capabilities:
    skills:
      - ralph-executor
    tools:
      - file/read
      - file/write
      - shell/bash

  # 身份配置
  identity:
    role: "Python CLI 开发工程师"
    specialties:
      - "Typer CLI 框架"
      - "Python 异步编程"
    level: "intermediate"

  # 任务配置
  tasks:
    sources:
      - type: github
        repo: "user/zima-blue-cli"
        labels: ["confirmed", "in-progress"]
```

---

## 7. 开发任务分解

### Phase 1: 基础 CLI (当前)

- [x] 项目初始化与架构设计
- [ ] CLI 框架搭建 (Typer)
- [ ] 配置管理模块
- [ ] Agent 元数据管理

### Phase 2: 核心调度

- [ ] Agent 调度器实现
- [ ] Prompt 生成器
- [ ] Kimi CLI 集成
- [ ] 状态管理

### Phase 3: 知识库集成

- [ ] zk 知识库管理
- [ ] Agent 个人知识库初始化
- [ ] Session 记忆读写

### Phase 4: Web 仪表盘

- [ ] Agent 状态可视化
- [ ] 日志查看器
- [ ] 任务队列管理

---

## 8. 参考资源

- [RALPH-LOOP-DESIGN.md](./RALPH-LOOP-DESIGN.md) - Ralph Loop 完整设计
- [KIMIWORLD-DESIGN.md](./KIMIWORLD-DESIGN.md) - KimiWorld 编排平台设计
- [AGENT-CYCLE-TIMELINE.md](./AGENT-CYCLE-TIMELINE.md) - 15分钟周期时间表

---

> "蓝色从来不是为了寻找答案,蓝色本身就是答案。"
