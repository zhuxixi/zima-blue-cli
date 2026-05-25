# Zima Blue CLI

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/zhuxixi/zima-blue-cli/actions/workflows/integration-test.yml/badge.svg)](https://github.com/zhuxixi/zima-blue-cli/actions/workflows/integration-test.yml)

> "I chose blue. That intense blue." — *Zima Blue*

**Zima Blue CLI** is a personal Agent orchestration platform that lets you run a 7x24 autonomous AI Agent factory on your own computer.

Simply define Prompt templates and configuration parameters, and Zima will automatically invoke Kimi CLI to execute tasks and return structured results.

```
Define Prompt Template → Configure Parameters → Execute → Get Results
```

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [CLI Commands](#cli-commands)
- [Documentation](#documentation)
- [Development](#development)
- [Naming Origin](#naming-origin)
- [License](#license)

---

## Features

- **🤖 Multi-Agent Support** — Pluggable AI executors (currently Kimi and Claude)
- **📋 Configuration Entities** — Layered config design: Agent + Workflow + Variable + Env + PMG
- **🚀 PJob Execution Layer** — Declarative task configuration, one-command composition and execution
- **📝 Jinja2 Templates** — Flexible Prompt templates with variable substitution
- **🔒 Secret Management** — Supports environment variables, files, Vault, and other secret sources
- **🧪 Full Test Coverage** — Unit tests + integration tests (including real Kimi invocation tests)
- **🧹 Auto Cleanup** — Built-in cleanup scripts for cache and temporary files

---

## Architecture

### Configuration Entities

Zima uses a layered configuration design, enabling flexible task execution through composition:

| Entity | Purpose | Example |
|--------|---------|---------|
| **Agent** | AI executor config (kimi/claude) | `code-reviewer` |
| **Workflow** | Prompt template (Jinja2) | `code-review-template` |
| **Variable** | Template variable values | `review-vars` |
| **Env** | Environment variables and secrets | `prod-env` |
| **PMG** | Dynamic parameter groups | `build-params` |
| **PJob** | Execution config (composes all above) | `daily-review-task` |
| **Schedule** | Daemon scheduling (32-cycle stages) | `weekday-review` |

### Directory Structure

```
~/.zima/
├── configs/
│   ├── agents/           # Agent configurations
│   ├── workflows/        # Workflow templates
│   ├── variables/        # Variable configurations
│   ├── envs/             # Environment configurations
│   ├── pmgs/             # Parameter groups
│   ├── pjobs/            # Execution task configurations
│   └── schedules/        # Daemon scheduling configurations
├── daemon/               # Daemon runtime (PID, state, logs, JSONL history)
├── temp/pjobs/           # Ephemeral PJob working directories
├── history/pjobs.json    # Per-PJob execution history (max 100 each)
├── logs/                 # Execution logs
└── scenes.yaml           # Optional user-defined quickstart scenes
```

### Execution Flow

```bash
# Composed execution
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
uv sync
```

### Basic Usage

```bash
# Create an Agent
zima agent create --name "My Agent" --code my-agent --type kimi

# Run a PJob (after composing one)
zima pjob run <pjob-code>

# Inspect execution history
zima pjob history <pjob-code>
```

### Quickstart Wizard

The fastest way to get started. One command creates all configs interactively:

```bash
zima quickstart
```

The wizard walks you through picking a task template, naming your setup, selecting an AI agent (Kimi / Claude), and auto-detects your git repo.

When done, run the generated PJob:

```bash
zima pjob run <generated-code> --dry-run  # preview
zima pjob run <generated-code>            # execute
```

### Advanced Usage: Composed Configuration

> **Tip:** `zima quickstart` is the recommended entry point. The steps below are the manual config-by-config approach for power users.

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
# Cleanup temp and history (cross-platform)
uv run python scripts/cleanup.py --auto
```

---

## CLI Commands

### Command Groups

```bash
# Agent management (supports kimi/claude)
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
├── design/           # Feature design documents (PJob, API interface, etc.)
├── guides/           # User-facing guides
├── history/          # Historical designs (reference only)
├── decisions/        # Architecture Decision Records (ADR; 004-single-execution ⭐ current)
├── reports/          # Generated reports
└── API-INTERFACE.md  # Complete CLI interface reference
```

### Use Cases

- **SOP Tasks**: DevOps scripts, data processing, report generation
- **R&D Tasks**: Test coverage, code refactoring (workflow-driven via Prompt)
- **CI/CD Integration**: Build steps that return structured results
- **Scheduled Tasks**: Periodic automation via cron

---

## AI Coding Pipeline

Zima automates the issue-driven AI coding pipeline — from code review through deployment — using configurable PJob compositions.

### Pipeline Stages

```
issue → brainstorm/spec → plan → impl → create-PR → CR → post-fix → post-merge → integration-test → deploy-prod
```

### Automation Coverage

| Stage | Status | PJob |
|-------|--------|------|
| brainstorm/spec | ❌ Manual (by design) | — |
| plan | ❌ Not implemented | — |
| impl | ❌ Not implemented | — |
| create-PR | ❌ Not implemented | — |
| CR | ⚠️ Partial | `jfox-kc-code-review-job`, `jfox-zc-code-review-job` |
| post-fix | ❌ Not implemented | — |
| post-merge | ❌ Not implemented | — |
| integration-test | ❌ Not implemented | — |
| deploy-prod | ❌ Not implemented | — |

### Supported PJobs

| PJob Code | Description | Stage |
|-----------|-------------|-------|
| `jfox-kc-code-review-job` | Code review via Kimi CLI | CR |
| `jfox-zc-code-review-job` | Code review via Zhipu-driven Claude Code | CR |

---

## Development

See [`AGENTS.md`](AGENTS.md) for development conventions, coding style, and design principles.

### Naming Origin

**Zima Blue** is inspired by Alastair Reynolds' science fiction short story *Zima Blue*.

> The story follows an artist-robot who, after millennia of upgrades and evolution, ultimately returns to its original form as a simple pool-cleaning robot — symbolizing **returning to essence and self-evolution**.

---

## License

This project is licensed under the [MIT License](LICENSE).