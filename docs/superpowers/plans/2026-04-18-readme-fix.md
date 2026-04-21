# README Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all issues documented in #20 — create MIT LICENSE, replace static badges with real ones, translate README to full English, restore vision statement, add Windows cleanup reference.

**Architecture:** Direct file edits — one new file (`LICENSE`) and one full rewrite (`README.md`). No code logic changes, purely documentation.

**Tech Stack:** Markdown, GitHub Actions badges, MIT License template

---

### Task 1: Create MIT LICENSE File

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Write LICENSE file**

Use standard MIT License template:

```
MIT License

Copyright (c) 2026 zhuxixi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Stage LICENSE**

```bash
git add LICENSE
```

---

### Task 2: Rewrite README.md in Full English

**Files:**
- Modify: `README.md` (full rewrite)

- [ ] **Step 1: Write new README.md**

Replace entire content with:

```markdown
# Zima Blue CLI

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/zhuxixi/zima-blue-cli/workflows/CI/badge.svg)](https://github.com/zhuxixi/zima-blue-cli/actions)

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

- **🤖 Multi-Agent Support** — Supports Kimi, Claude, Gemini, and other AI executors
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
# Unix / Linux / macOS
./cleanup.sh --auto

# Windows
cleanup.bat --auto
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
```

- [ ] **Step 2: Verify badge URLs are correct**

Check:
- `LICENSE` link → relative path, valid after Task 1
- `CI` badge → `https://github.com/zhuxixi/zima-blue-cli/workflows/CI/badge.svg`
- `Python` badge → `https://www.python.org/`

- [ ] **Step 3: Stage README.md**

```bash
git add README.md
```

---

### Task 3: Commit and Verify

- [ ] **Step 1: Commit changes**

```bash
git commit -m "docs: fix README.md review issues (#20)

- Create MIT LICENSE file
- Replace static badges with dynamic shields.io and GitHub Actions badges
- Translate entire README to English
- Restore vision statement: 7x24 autonomous AI Agent factory
- Add cleanup.bat reference for Windows users
- Consistently use ASCII 7x24 instead of Unicode 7×24"
```

- [ ] **Step 2: Final verification checklist**

| Check | How |
|-------|-----|
| LICENSE exists | `ls LICENSE` |
| README is English | Visual scan — no Chinese characters in body |
| License badge valid | Click link in rendered README |
| CI badge valid | Check GitHub Actions page after push |
| cleanup.bat mentioned | Search `cleanup.bat` in README |
| Vision restored | Search `7x24 autonomous` in README |
| Symbol consistent | Search `7×24` (Unicode) — should return 0 results |

---

## Self-Review

**Spec coverage:**
- ✅ Create MIT LICENSE → Task 1
- ✅ Replace Tests badge with real CI badge → Task 2 (CI badge URL)
- ✅ Full English translation → Task 2 (entire README content)
- ✅ Restore vision statement → Task 2 ("7x24 autonomous AI Agent factory")
- ✅ Add cleanup.bat → Task 2 (Cleanup section)
- ✅ Consistent 7x24 symbol → Task 2 (ASCII x used)

**Placeholder scan:**
- ✅ No TBD/TODO
- ✅ No vague instructions
- ✅ Complete code/content in every step

**Type consistency:**
- ✅ N/A — no types/methods in this doc-only change
