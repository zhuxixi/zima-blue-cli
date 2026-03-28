# Zima Blue CLI

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》

**Zima Blue CLI** 是一个 Agent 启动器，管理 Kimi CLI 的执行参数，让 AI 执行明确的 SOP 任务。

```
定义 Prompt 模板 → 配置参数 → 执行 → 获取结果
```

---

## ⚠️ 重要声明

> **本项目采用迭代式设计**
> 
> - `docs/history/` 中的早期文档仅供参考，记录了设计演进过程
> - **请以 `docs/architecture/` 中的最新设计为准**
> - 实现时以本仓库根目录的 `AGENTS.md` 和最新架构文档为最终依据

---

## 核心概念

### 配置实体 (Configuration Entities)

Zima 采用分层配置设计，通过组合不同实体实现灵活的任务执行：

| 实体 | 用途 | 示例 |
|------|------|------|
| **Agent** | AI 执行器配置 (kimi/claude/gemini) | `code-reviewer` |
| **Workflow** | Prompt 模板 (Jinja2) | `code-review-template` |
| **Variable** | 模板变量值 | `review-vars` |
| **Env** | 环境变量和密钥 | `prod-env` |
| **PMG** | 动态参数组 | `build-params` |
| **PJob** | 执行配置 (组合以上所有) | `daily-review-task` |

### 目录结构

```
~/.zima/
├── configs/
│   ├── agents/           # Agent 配置
│   ├── workflows/        # Workflow 模板
│   ├── variables/        # 变量配置
│   ├── envs/             # 环境配置
│   ├── pmgs/             # 参数组
│   └── pjobs/            # 执行任务配置
└── agents/               # Agent 运行时目录
    └── <agent-code>/
        ├── logs/         # 执行日志
        ├── prompts/      # 运行时 Prompt
        └── workspace/    # 工作目录
```

### 执行流程

```bash
# 方式 1：快速执行（简写）
zima run my-agent

# 方式 2：PJob 组合执行（推荐）
zima pjob run my-task    # 组合 Agent + Workflow + Variable + Env

# Kimi 执行 Prompt 定义的工作流
# 完成后返回结构化结果
```

---

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/zhuxixi/zima-blue-cli.git
cd zima-blue-cli

# 安装依赖
pip install -e "."

# ===== 基础使用 =====

# 创建 Agent
zima create my-agent

# 运行 Agent
zima run my-agent

# 查看日志
zima logs my-agent

# ===== 高级使用：配置实体组合 =====

# 1. 创建带参数的 Agent
zima agent create --name "Code Reviewer" --code reviewer --type kimi

# 2. 创建 Workflow 模板
zima workflow create --name "Review Template" --code review \
  --template "# Review: {{ task_name }}\n\n{{ description }}"

# 3. 创建 Variable 配置
zima variable create --name "Review Vars" --code review-vars
zima variable set review-vars task_name "Bug Fix Review"
zima variable set review-vars description "Check for memory leaks"

# 4. 创建 PJob 组合配置
zima pjob create --name "Code Review Task" --code review-task \
  --agent reviewer --workflow review --variable review-vars

# 5. 执行任务
zima pjob run review-task

# 6. 查看历史
zima pjob history review-task

# ===== 清理临时文件 =====
./cleanup.sh --auto              # 清理缓存和临时文件
```

---

## CLI 命令

### 简写命令

```bash
zima create <name>          # 创建 Agent
zima run <name>             # 单次执行
zima list                   # 列出所有 Agent
zima show <name>            # 查看配置
zima logs <name>            # 查看日志
```

### 完整命令组

```bash
# Agent 管理 (支持 kimi/claude/gemini)
zima agent create --name "My Agent" --code my-agent --type kimi
zima agent list --type kimi
zima agent show my-agent
zima agent test my-agent      # 预览 CLI 命令
zima agent validate my-agent

# Workflow 模板管理
zima workflow create --name "Review" --code review --template "# {{ title }}"
zima workflow render review --var my-vars

# Variable 变量管理
zima variable create --name "My Vars" --code my-vars
zima variable set my-vars key value

# Environment 环境配置
zima env create --name "Prod" --code prod-env
zima env set-secret prod-env API_KEY --source env

# PMG 参数组管理
zima pmg create --name "Build Params" --code build-params

# PJob 任务执行 (组合 Agent + Workflow + Variable + Env)
zima pjob create --name "Daily Task" --code daily \
  --agent my-agent --workflow review --variable my-vars
zima pjob run daily           # 执行任务
zima pjob render daily        # 预览渲染
zima pjob history daily       # 查看历史
```

详见 [API-INTERFACE.md](docs/API-INTERFACE.md) 获取完整接口文档。

---

## 文档结构

```
docs/
├── vision/           # 项目愿景和故事
├── architecture/     # 最新架构设计 ⭐ 以此为准
├── history/          # 历史设计（仅供参考）
└── decisions/        # 架构决策记录 (ADR)
    ├── 001-use-subprocess.md
    ├── 002-15min-cycle.md (已废弃)
    ├── 003-early-completion.md (已废弃)
    └── 004-single-execution.md ⭐ 当前架构
```

---

## 特性

- 🤖 **多 Agent 类型支持** - Kimi / Claude / Gemini
- 📋 **配置实体系统** - Agent + Workflow + Variable + Env + PMG 组合
- 🚀 **PJob 执行层** - 声明式任务配置，一键执行
- 📝 **Jinja2 模板** - 灵活的 Prompt 模板和变量替换
- 🔒 **密钥管理** - 支持环境变量、文件、Vault 多种来源
- 🧪 **完整测试** - 单元测试 + 集成测试（含真实 Kimi 调用测试）
- 🧹 **自动清理** - 内置清理脚本，管理临时文件

## 适用场景

- **SOP 任务**：运维脚本、数据处理、报告生成
- **研发任务**：测试覆盖、代码重构（通过 Prompt 定义工作流）
- **CI/CD 集成**：作为构建步骤，返回结构化结果
- **定时任务**：结合 cron 实现周期性自动化

---

## 命名来源

**Zima Blue** 源自 Alastair Reynolds 的科幻短篇《齐马蓝》。

> 故事讲述了一个艺术家机器人历经万年升级进化，最终回归最初简单的泳池清洁机器人状态——象征着**回归本质、自我进化**。

---

## 开发

详见 [AGENTS.md](AGENTS.md) 了解开发规范和设计原则。

---

## License

MIT
