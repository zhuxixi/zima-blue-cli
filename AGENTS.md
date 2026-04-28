# AGENTS.md

This file provides guidance to Kimi Code agents when working with code in this repository.

## Project Overview

**Zima Blue CLI** is a Python-based AI Agent orchestration platform. It manages execution of AI agents (Kimi, Claude) through composable YAML configurations and Jinja2 prompt templates. Named after the sci-fi story about returning to simplicity.

## Development Commands

```bash
# Install (editable mode) — uv sync installs all deps including dev
uv sync

# Run CLI (inside uv-managed venv)
uv run zima --help
uv run zima pjob run <pjob-code>

# Format
uv run black zima/ tests/ --line-length 100

# Lint
uv run ruff check zima/ tests/

# Run all tests
uv run pytest

# Run only unit tests
uv run pytest tests/unit/

# Run only integration tests
uv run pytest tests/integration/

# Run a single test file
uv run pytest tests/unit/test_models_agent.py

# Run a single test
uv run pytest tests/unit/test_models_agent.py::TestAgentConfig::test_from_dict -v

# Cleanup temp files
uv run python scripts/cleanup.py --auto
```

## Architecture

### Configuration Entity System (6 + 1 types)

The core design is composability through seven YAML-based configuration types:

| Entity | Model | Purpose |
|--------|-------|---------|
| Agent | `AgentConfig` | AI executor config (kimi/claude), builds CLI commands |
| Workflow | `WorkflowConfig` | Jinja2 prompt templates with typed variable definitions |
| Variable | `VariableConfig` | Key-value data for template rendering |
| Env | `EnvConfig` | Secrets and env vars (env/file/cmd/vault sources) |
| PMG | `PMGConfig` | Dynamic CLI parameter groups with conditions |
| **PJob** | `PJobConfig` | **Execution layer** — composes all above into a runnable job |
| **Schedule** | `ScheduleConfig` | **Daemon scheduling** — 32-cycle PJob scheduling with stages |

**Resolution precedence** (highest to lowest): PJob runtime overrides → PJob explicit refs → Agent defaults → System defaults.

### Key Layers

- **`zima/cli.py`** — Typer CLI entry point. Registers subcommand groups. Has Windows UTF-8 fix.
- **`zima/commands/`** — CLI subcommand implementations (agent, workflow, variable, env, pmg, pjob, schedule, daemon).
- **`zima/config/manager.py`** — `ConfigManager`: unified CRUD for all config types. Single class handles create/read/update/delete/list for every entity kind via `KINDS` set.
- **`zima/models/`** — Dataclasses for each entity. `BaseConfig` provides common YAML load/save. `Metadata` has code/name/description.
- **`zima/execution/executor.py`** — `PJobExecutor`: resolves ConfigBundle (agent+workflow+variable+env+pmg), renders template, builds command, executes subprocess.
- **`zima/models/config_bundle.py`** — `ConfigBundle`: assembled config set ready for execution.
- **`zima/core/kimi_runner.py`** / **`zima/core/claude_runner.py`** — Agent-specific subprocess runners for Kimi and Claude.
- **`zima/execution/background_runner.py`** — Background PJob execution in detached process.
- **`zima/execution/history.py`** — Execution history tracking with PID recording.
- **`zima/execution/actions_runner.py`** — `ActionsRunner`: executes preExec actions before agent starts and postExec actions after agent exit. Supports `SkipAction` to short-circuit execution when preExec finds no work.
- **`zima/actions/base.py`** — `ActionProvider` ABC — interface all providers implement (add_label, remove_label, post_comment, fetch_diff, scan_prs).
- **`zima/actions/registry.py`** — `ProviderRegistry`: loads built-in + discovers external providers via `importlib.metadata.entry_points`.
- **`zima/actions/exceptions.py`** — `ProviderNotFoundError`, `ProviderError`.
- **`zima/providers/__init__.py`** — `BUILTIN_PROVIDERS` dict.
- **`zima/providers/github.py`** — `GitHubProvider`: wraps `gh` CLI for label/comment/diff/scan_prs operations.
- **`zima/models/actions.py`** — `PreExecAction` / `PostExecAction` / `ActionsConfig`: dataclasses for PJob pre-execution and post-execution automation.
- **`zima/scenes.py`** — `Scene` dataclass, `load_scenes()` merges built-in scenes with user-defined `~/.zima/scenes.yaml`.
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
  → Runs preExec actions (e.g., scan_pr) before agent starts
     → If SkipAction raised, returns ExecutionResult(status=SKIPPED)
  → Executes subprocess (kimi/claude)
  → Runs postExec actions through configured provider (label/comment) in finally block
  → Captures output, stores execution history centrally
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
├── temp/                      # Temporary execution artifacts
│   └── pjobs/                # PJob execution working directories (auto-cleaned)
├── history/
│   └── pjobs.json           # Execution history (per-PJob records, max 100 each)
└── scenes.yaml                # User-defined quickstart scene overrides
```

**Execution artifacts** (ephemeral by default):
- Working directory: `~/.zima/temp/pjobs/<code>-<id>/` (under ZIMA_HOME, not system temp)
- Rendered prompt: `<temp_dir>/prompt.md`
- Temp dir is cleaned up after execution unless `keep_temp` or `save_to` is set
- Full stdout/stderr is returned in-memory; only a 500-char preview is persisted to history

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
- **Lint job**: `uv run ruff check` + `uv run black --check`
- **Test job**: `uv run pytest --cov=zima --cov-fail-under=60` (Python 3.13)

## Extension Points

To add a new **Agent type** (e.g., a new AI CLI):
1. Add to `VALID_AGENT_TYPES` and parameter template in `zima/models/agent.py`
2. Implement `_build_*_command` method in `AgentConfig`

To add a new **Configuration Entity**:
1. Create model in `zima/models/<entity>.py`
2. Add kind to `ConfigManager.KINDS`
3. Create commands in `zima/commands/<entity>.py`
4. Register Typer subcommand in `zima/cli.py`
5. Add example YAML to `zima/templates/examples.py` (`EXAMPLES` dict + `VALID_KINDS`)

## Gotchas

### GitHub PR Code Review Feedback

PR reviews use three independent APIs. Different CR tools submit via different endpoints. To get complete feedback you must check all three:
- Issue comments: `gh api repos/{owner}/{repo}/issues/{n}/comments`
- Reviews: `gh api repos/{owner}/{repo}/pulls/{n}/reviews`
- Inline comments: `gh api repos/{owner}/{repo}/pulls/{n}/comments`

### Daemon / Subprocess Patterns

- Detached subprocess: must set `stdin=subprocess.DEVNULL` to prevent stdin blocking
- Daemon threading lock: use `RLock` not `Lock` (nested call chains will deadlock)
- Windows taskkill: add `/T` to kill entire process tree (PJob child processes don't die with daemon)
- Runtime paths must use `get_zima_home()` not `Path.home() / ".zima"` (respects ZIMA_HOME env var)

## Documentation

- `CLAUDE.md` — Agent context file for Claude Code agents
- `docs/architecture/` — Current architecture (authoritative)
- `docs/history/` — Deprecated designs (reference only)
- `docs/decisions/` — ADRs; ADR-004 (single execution) is the current model
- `docs/design/` — Feature design documents (PJob design, API interface, etc.)
- `SESSION.md` — Development session history