# Zima Blue CLI

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》

**Zima Blue CLI** 是一个个人 Agent 编排平台，让你能够在自己的电脑上运行一个 7×24 小时自主工作的 AI Agent 工厂。

你只需定义 Prompt 模板和配置参数，Zima 就会自动唤起 Kimi CLI 执行明确的 SOP 任务，并返回结构化结果。

```
定义 Prompt 模板 → 配置参数 → 执行 → 获取结果
```

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [CLI Commands](#cli-commands)
- [Documentation](#documentation)
- [Development](#development)
- [License](#license)

---

## Features

- **🤖 Multi-Agent Support** — 支持 Kimi、Claude、Gemini 等多种 AI 执行器
- **📋 Configuration Entities** — 分层配置设计：Agent + Workflow + Variable + Env + PMG
- **🚀 PJob Execution Layer** — 声明式任务配置，一键组合并执行
- **📝 Jinja2 Templates** — 灵活的 Prompt 模板与变量替换
- **🔒 Secret Management** — 支持环境变量、文件、Vault 等多种密钥来源
- **🧪 Full Test Coverage** — 单元测试 + 集成测试（含真实 Kimi 调用测试）
- **🧹 Auto Cleanup** — 内置清理脚本，管理临时文件与缓存

---

## Architecture

### Configuration Entities

Zima 采用分层配置设计，通过组合不同实体实现灵活的任务执行：

| Entity | Purpose | Example |
|--------|---------|---------|
| **Agent** | AI executor config (kimi/claude/gemini) | `code-reviewer` |
| **Workflow** | Prompt template (Jinja2) | `code-review-template` |
| **Variable** | Template variable values | `review-vars` |
| **Env** | Environment variables and secrets | `prod-env` |
| **PMG** | Dynamic parameter groups | `build-params` |
| **PJob** | Execution config (composes all above) | `daily-review-task` |

### Directory Structure

```
~/.zima/
├── configs/
│   ├── agents/           # Agent configurations
│   ├── workflows/        # Workflow templates
│   ├── variables/        # Variable configurations
│   ├── envs/             # Environment configurations
│   ├── pmgs/             # Parameter groups
│   └── pjobs/            # Execution task configurations
└── agents/               # Agent runtime directories
    └── <agent-code>/
        ├── logs/         # Execution logs
        ├── prompts/      # Runtime prompts
        └── workspace/    # Working directory
```

### Execution Flow

```bash
# Quick execution (shorthand)
zima run my-agent

# Composed execution (recommended)
zima pjob run my-task    # Combines Agent + Workflow + Variable + Env
```

> **Important**
> This project adopts an iterative design approach. Always refer to `docs/architecture/` for the latest design, and use `AGENTS.md` at the repository root as the final authority for implementation.

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/zhuxixi/zima-blue-cli.git
cd zima-blue-cli

# Install dependencies
pip install -e "."
```

### Basic Usage

```bash
# Create an Agent
zima create my-agent

# Run the Agent
zima run my-agent

# View logs
zima logs my-agent
```

### Advanced Usage: Composed Configuration

```bash
# 1. Create an Agent
zima agent create --name "Code Reviewer" --code reviewer --type kimi

# 2. Create a Workflow template
zima workflow create --name "Review Template" --code review \
  --template "# Review: {{ task_name }}\n\n{{ description }}"

# 3. Create Variable configuration
zima variable create --name "Review Vars" --code review-vars
zima variable set review-vars task_name "Bug Fix Review"
zima variable set review-vars description "Check for memory leaks"

# 4. Create a PJob composition
zima pjob create --name "Code Review Task" --code review-task \
  --agent reviewer --workflow review --variable review-vars

# 5. Run the task
zima pjob run review-task

# 6. View execution history
zima pjob history review-task
```

### Cleanup

```bash
./cleanup.sh --auto      # Clean cache and temporary files
```

---

## CLI Commands

### Shorthand Commands

```bash
zima create <name>          # Create an Agent
zima run <name>             # Execute once
zima list                   # List all Agents
zima show <name>            # Show configuration
zima logs <name>            # View logs
```

### Full Command Groups

```bash
# Agent management (supports kimi/claude/gemini)
zima agent create --name "My Agent" --code my-agent --type kimi
zima agent list --type kimi
zima agent show my-agent
zima agent test my-agent      # Preview generated CLI command
zima agent validate my-agent

# Workflow template management
zima workflow create --name "Review" --code review --template "# {{ title }}"
zima workflow render review --var my-vars

# Variable management
zima variable create --name "My Vars" --code my-vars
zima variable set my-vars key value

# Environment configuration
zima env create --name "Prod" --code prod-env
zima env set-secret prod-env API_KEY --source env

# PMG parameter group management
zima pmg create --name "Build Params" --code build-params

# PJob execution (composes Agent + Workflow + Variable + Env)
zima pjob create --name "Daily Task" --code daily \
  --agent my-agent --workflow review --variable my-vars
zima pjob run daily           # Execute task
zima pjob render daily        # Preview rendered output
zima pjob history daily       # View history
```

See [`docs/API-INTERFACE.md`](docs/API-INTERFACE.md) for the complete interface documentation.

---

## Documentation

```
docs/
├── vision/           # Project vision and story
├── architecture/     # Latest architecture design ⭐ authoritative
├── history/          # Historical designs (reference only)
└── decisions/        # Architecture Decision Records (ADR)
    ├── 001-use-subprocess.md
    ├── 002-15min-cycle.md (deprecated)
    ├── 003-early-completion.md (deprecated)
    └── 004-single-execution.md ⭐ current
```

### Use Cases

- **SOP Tasks**: DevOps scripts, data processing, report generation
- **R&D Tasks**: Test coverage, code refactoring (workflow-driven via Prompt)
- **CI/CD Integration**: Build steps that return structured results
- **Scheduled Tasks**: Periodic automation via cron

---

## Development

See [`AGENTS.md`](AGENTS.md) for development conventions, coding style, and design principles.

### Naming Origin

**Zima Blue** is inspired by Alastair Reynolds' science fiction short story *Zima Blue*.

> The story follows an artist-robot who, after millennia of upgrades and evolution, ultimately returns to its original form as a simple pool-cleaning robot — symbolizing **returning to essence and self-evolution**.

---

## License

This project is licensed under the [MIT License](LICENSE).
