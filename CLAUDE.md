# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zima Blue CLI** is a Python-based AI Agent orchestration platform. It manages execution of AI agents (Kimi, Claude, Gemini) through composable YAML configurations and Jinja2 prompt templates. Named after the sci-fi story about returning to simplicity.

## Development Commands

```bash
# Install (editable mode)
pip install -e "."
pip install -e ".[dev]"          # includes pytest, black, ruff

# Run CLI
zima --help
zima run <agent-name>

# Format
black zima/ tests/ --line-length 100

# Lint
ruff check zima/ tests/

# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run a single test file
pytest tests/unit/test_models_agent.py

# Run a single test
pytest tests/unit/test_models_agent.py::TestAgentConfig::test_from_dict -v

# Cleanup temp files
python scripts/cleanup.py --auto
```

## Architecture

### Configuration Entity System (6 + 1 types)

The core design is composability through seven YAML-based configuration types:

| Entity | Model | Purpose |
|--------|-------|---------|
| Agent | `AgentConfig` | AI executor config (kimi/claude/gemini), builds CLI commands |
| Workflow | `WorkflowConfig` | Jinja2 prompt templates with typed variable definitions |
| Variable | `VariableConfig` | Key-value data for template rendering |
| Env | `EnvConfig` | Secrets and env vars (env/file/cmd/vault sources) |
| PMG | `PMGConfig` | Dynamic CLI parameter groups with conditions |
| **PJob** | `PJobConfig` | **Execution layer** — composes all above into a runnable job |
| **Schedule** | `ScheduleConfig` | **Daemon scheduling** — 32-cycle PJob scheduling with stages |

**Resolution precedence** (highest to lowest): PJob runtime overrides → PJob explicit refs → Agent defaults → System defaults.

### Key Layers

- **`zima/cli.py`** — Typer CLI entry point. Registers subcommand groups. Has Windows UTF-8 fix.
- **`zima/commands/`** — CLI subcommand implementations (agent, workflow, variable, env, pmg, pjob, schedule).
- **`zima/config/manager.py`** — `ConfigManager`: unified CRUD for all config types. Single class handles create/read/update/delete/list for every entity kind via `KINDS` set.
- **`zima/models/`** — Dataclasses for each entity. `BaseConfig` provides common YAML load/save. `Metadata` has code/name/description.
- **`zima/core/runner.py`** — `AgentRunner`: simple single-execution via subprocess. Builds kimi command, captures output, parses JSON result.
- **`zima/execution/executor.py`** — `PJobExecutor`: resolves ConfigBundle (agent+workflow+variable+env+pmg), renders template, builds command, executes subprocess.
- **`zima/models/config_bundle.py`** — `ConfigBundle`: assembled config set ready for execution.
- **`zima/core/kimi_runner.py`** / **`zima/core/claude_runner.py`** — Agent-specific subprocess runners for Kimi and Claude.
- **`zima/execution/background_runner.py`** — Background PJob execution in detached process.
- **`zima/execution/history.py`** — Execution history tracking with PID recording.
- **`zima/daemon_runner.py`** — Entry point for detached daemon process (`python -m zima.daemon_runner`).
- **`zima/core/daemon_scheduler.py`** — `DaemonScheduler`: 32-cycle PJob scheduling with stage timers, PJob spawn/kill, JSONL history.
- **`zima/utils.py`** — Shared utilities (`ensure_dir`, etc.).

### Execution Flow

```
zima pjob run <code>
  → PJobExecutor loads PJobConfig
  → Resolves referenced Agent/Workflow/Variable/Env/PMG
  → Renders Workflow template with Variables
  → Builds CLI command from Agent parameters
  → Executes subprocess (kimi/claude/gemini)
  → Captures output, logs to ~/.zima/agents/<code>/logs/
  → Returns ExecutionResult
```

### Data Layout

```
~/.zima/
├── configs/{agents,workflows,variables,envs,pmgs,pjobs,schedules}/   # YAML configs
├── daemon/                    # Daemon runtime (PID, state, logs, history)
│   ├── daemon.pid
│   ├── daemon.log
│   ├── state.json
│   └── history/*.jsonl
└── agents/<code>/
    ├── workspace/     # Working directory for execution
    ├── prompts/       # Rendered prompt files
    └── logs/          # Execution logs
```

Customizable via `ZIMA_HOME` env var.

### Legacy Components (Unused in v2)

`core/daemon.py`, `core/scheduler.py`, `core/state_manager.py` — retained for reference only. v2 replaced 15-min cycle architecture with single execution (see ADR 004). `core/daemon_scheduler.py` is the new v3 daemon scheduler.

## Code Conventions

- **Python 3.10+**, dataclasses (not pydantic models despite pydantic being a dependency)
- **Build system**: hatchling (configured in `pyproject.toml`)
- **Black** formatting at 100 chars, **ruff** for linting
- **Google-style docstrings**
- **YAML configs** follow Kubernetes-style `apiVersion: zima.io/v1` / `kind: X` / `metadata` / `spec` structure
- **Code identifiers** (`metadata.code`): lowercase letters, numbers, hyphens only, max 64 chars
- **Commit format**: `type(scope): description` (feat/fix/docs/test/refactor/chore)

## Testing

- **`tests/unit/`** — Pure unit tests for models and config manager
- **`tests/integration/`** — CLI command tests using Typer's `CliRunner`, subprocess integration tests
- **`tests/conftest.py`** — Fixtures: `isolated_zima_home` (temp ZIMA_HOME), `config_manager`, `cli_runner`, `unique_code`
- **`tests/base.py`** — `TestIsolator` base class with `setup_isolation` autouse fixture
- Integration tests are auto-marked with `@pytest.mark.integration` via `pytest_collection_modifyitems`
- Tests use `monkeypatch` to set `ZIMA_HOME` to temp directories for isolation
- **Coverage threshold**: 60% (`fail_under = 60` in `pyproject.toml`)
- **Test fixtures**: `tests/fixtures/configs/` — sample YAML configs for integration tests

## CI Pipeline

- **GitHub Actions** on push/PR to `master`
- **Lint job**: `ruff check` + `black --check`
- **Test job**: `pytest --cov=zima --cov-fail-under=60` (Python 3.13)

## Extension Points

To add a new **Agent type** (e.g., a new AI CLI):
1. Add to `VALID_AGENT_TYPES` and parameter template in `zima/models/agent.py`
2. Implement `_build_*_command` method in `AgentConfig`

To add a new **Configuration Entity**:
1. Create model in `zima/models/<entity>.py`
2. Add kind to `ConfigManager.KINDS`
3. Create commands in `zima/commands/<entity>.py`
4. Register Typer subcommand in `zima/cli.py`

## Documentation

- `AGENTS.md` — Agent development guide (identity, naming, knowledge base)
- `docs/architecture/` — **Current architecture** (authoritative)
- `docs/history/` — Deprecated designs (reference only)
- `docs/decisions/` — ADRs; ADR-004 (single execution) is the current model
- `docs/design/` — Feature design documents (PJob design, API interface, etc.)
- `SESSION.md` — Development session history
