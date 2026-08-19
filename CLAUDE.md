# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zima Blue CLI** is a Python-based AI Agent orchestration platform. It manages execution of AI agents (Kimi, Claude) through composable YAML configurations and Jinja2 prompt templates. Named after the sci-fi story about returning to simplicity.

The repo also ships a pi-coding-agent skills package (GitHub issue-driven dev loop): root `package.json` is its pi package manifest (not npm), skills live under `pi/` (`github-issue-driven` / `issue-research` / `zima-pr-monitor` / `github-code-review-batch`), installed locally via `pi install <repo path>`; pi worktrees use `.pi/worktrees/` (gitignored).

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

# Architecture dependency-direction contracts (layers + framework-free models)
uv run lint-imports

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
| Agent | `AgentConfig` | AI executor config (kimi/claude/pi), builds CLI commands |
| Workflow | `WorkflowConfig` | Jinja2 prompt templates with typed variable definitions |
| Variable | `VariableConfig` | Key-value data for template rendering |
| Env | `EnvConfig` | Secrets and env vars (env/file/cmd/vault sources) |
| PMG | `PMGConfig` | Dynamic CLI parameter groups with conditions |
| **PJob** | `PJobConfig` | **Execution layer** — composes all above into a runnable job |
| **Schedule** | `ScheduleConfig` | **Daemon scheduling** — 32-cycle PJob scheduling with stages |

**Resolution precedence** (highest to lowest): PJob runtime overrides → PJob explicit refs → Agent defaults → System defaults.

### Key Layers

- **`zima/cli.py`** — Typer CLI entry point. Registers subcommand groups. Has Windows UTF-8 fix.
- **`zima/commands/`** — CLI subcommand implementations (agent, workflow, variable, env, pmg, pjob, schedule, daemon, webhook-server).
- **`zima/config/manager.py`** — `ConfigManager`: unified CRUD for all config types. Single class handles create/read/update/delete/list for every entity kind via `KINDS` set.
- **`zima/models/`** — Dataclasses for each entity. `BaseConfig` provides common YAML load/save. `Metadata` has code/name/description.
- **`zima/execution/executor.py`** — `PJobExecutor`: resolves ConfigBundle (agent+workflow+variable+env+pmg), renders template, builds command, executes subprocess, runs postExec actions.
- **`zima/models/config_bundle.py`** — `ConfigBundle`: assembled config set ready for execution.
- **`zima/core/kimi_runner.py`** / **`zima/core/claude_runner.py`** — Agent-specific subprocess runners for Kimi and Claude. (pi type reuses the executor's generic subprocess + stdin-pipe path, no dedicated runner.)
- **`zima/execution/background_runner.py`** — Background PJob execution in detached process.
- **`zima/execution/history.py`** — Execution history tracking with PID recording.
- **`zima/execution/actions_runner.py`** — `ActionsRunner`: executes postExec actions (GitHub label/comment) after agent exit.
- **`zima/actions/base.py`** — `ActionProvider` ABC: interface providers implement (add_label, remove_label, post_comment, fetch_diff, scan_prs, verify_pr_label — fail-closed by default).
- **`zima/actions/registry.py`** — `ProviderRegistry`: discovers providers (built-in github + external) via the `zima.action_providers` entry-point group (`importlib.metadata.entry_points`).
- **`zima/models/defaults.py`** — Default action-provider name resolution (`ZIMA_GIT_REPO_PROVIDER` env var).
- **`zima/models/ports.py`** — `ConfigStore` Protocol: the port `zima.models` depends on instead of concrete `ConfigManager` (DIP).
- **`zima/execution/secret_resolver.py`** — `SecretResolver` + env export; subprocess/IO moved out of `zima.models`.
- **`zima/execution/template_renderer.py`** — `render_workflow_template` / `validate_template_syntax`; jinja2 moved out of `zima.models`.
- **`zima/review/parser.py`** — `ReviewParser`: parses `<zima-review>` XML blocks from agent stdout into structured review results.
- **`zima/providers/github.py`** — `GitHubProvider`: wraps `gh` CLI for label add/remove, comment post, PR diff fetch.
- **`zima/models/actions.py`** — `PostExecAction` / `ActionsConfig`: dataclasses for PJob post-execution automation.
- **`zima/scenes.py`** — `Scene` dataclass + `load_scenes()`: merges built-in scenes with user-defined `~/.zima/scenes.yaml` for quickstart wizard.
- **`zima/daemon_runner.py`** — Entry point for detached daemon process (`python -m zima.daemon_runner`).
- **`zima/__main__.py`** — Enables `python -m zima`; the webhook server triggers PJobs via `[python, -m, zima, pjob run, ...]`, so without this file triggers silently no-op.
- **`zima/webhook/`** — GitHub webhook receiver (`server.py` HTTP+spawn, `payload.py` PR-labeled parser + HMAC verify, `smee.py` SSE forwarder) behind the `webhook-server` subcommand; auto-triggers CR PJobs on `pull_request labeled zima:needs-review`.
- **`zima/core/daemon_scheduler.py`** — `DaemonScheduler`: 32-cycle PJob scheduling with stage timers, PJob spawn/kill, JSONL history.
- **`zima/utils.py`** — Shared utilities (`ensure_dir`, etc.).

### Execution Flow

```
zima pjob run <code>
  → PJobExecutor loads PJobConfig
  → Resolves referenced Agent/Workflow/Variable/Env/PMG
  → Renders Workflow template with Variables
  → Builds CLI command from Agent parameters
  → Runs preExec actions (e.g., scan_prs); SkipAction → ExecutionResult(status=SKIPPED)
  → Executes subprocess (kimi/claude/pi)
  → Runs postExec actions (e.g. GitHub label transition) in finally block
  → Captures output, stores execution history centrally
  → Returns ExecutionResult
```

**Post-exec actions** run unconditionally in the `finally` block:
- On success (returncode=0): `condition: success` actions fire
- On failure/timeout/cancel: `condition: failure` actions fire, `action_errors` recorded
- Reviewer PJobs: `<zima-review>` XML in stdout is parsed, verdict maps to effective returncode

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
└── history/
    └── pjobs.json           # Execution history (per-PJob records, max 100 each)
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

- **GitHub Actions** on push/PR to `main` (workflow accepts `master` too, see `.github/workflows/integration-test.yml`)
- Lint: `uv run ruff check zima/ tests/` + `uv run black --check zima/ tests/ --line-length 100` + `uv run lint-imports` (architecture contracts; gate on `.importlinter` / `.arch-governance.yml`)
- Test: `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60` (Python 3.10/3.13 matrix)
- Publish: `.github/workflows/publish.yml` triggers on tag push

## Extension Points

To add a new **Agent type** (e.g., a new AI CLI):
1. Add to `VALID_AGENT_TYPES` and parameter template in `zima/models/agent.py`
2. Implement `_build_*_command` method in `AgentConfig`

Note: `pi` type is supported (pi-coding-agent print mode). It uses `--mode` for output format (not `--output-format`), `needs_stdin_pipe=True` (stdin-piped like claude), and relies on `Popen(cwd=)` (pi has no `--work-dir`/`--add-dir` flag, so `addDirs` is unsupported and warned+ignored, unlike kimi/claude).

To add a new **Configuration Entity**:
1. Create model in `zima/models/<entity>.py`
2. Add kind to `ConfigManager.KINDS`
3. Create commands in `zima/commands/<entity>.py`
4. Register Typer subcommand in `zima/cli.py`
5. Add example YAML to `zima/templates/examples.py` (`EXAMPLES` dict + `VALID_KINDS`). `EXAMPLES` is nested: `EXAMPLES[kind][example_name]` → YAML string.

## Gotchas

### Architecture Governance (dependency direction)

- `.arch-governance.yml` 是依赖方向的单一事实源；改它而非 `.importlinter`（后者由前者生成，CI 的 `uv run lint-imports` 读它），详见 ADR-005
- 分层是细粒度线性序（外/IO 层 → 内/领域层：`__main__`→`cli`→`commands`→`daemon_runner|webhook`→`core`→`providers`→`scenes`→`templates`→`execution`→`review`→`config`→`actions`→`models`→`utils`）；外层可 import 内层，反向即违规
- `zima.models` 是框架无关的领域核（最内层）：禁止 import `subprocess`/`jinja2`/`requests`/`typer`/`rich`（`yaml`/`platform` 刻意不禁）
- 框架 IO 走 `zima/execution` 适配层（`secret_resolver.py` 解密钥、`template_renderer.py` 渲染 jinja2）；`models` 经 `models/ports.py` 的 `ConfigStore` Protocol 依赖抽象，不直接依赖具体 `ConfigManager`
- 内置 github provider 走 entry-point（`pyproject.toml` 的 `zima.action_providers`）注册，`actions` 层不 import `providers`

### GitHub PR Code Review Feedback

PR 评论有三个独立 API，不同 CR 工具用不同 API 提交，获取完整反馈必须查所有端点：
- Issue comments: `gh api repos/{owner}/{repo}/issues/{n}/comments`
- Reviews: `gh api repos/{owner}/{repo}/pulls/{n}/reviews`
- Inline comments: `gh api repos/{owner}/{repo}/pulls/{n}/comments`

### Daemon / Subprocess Patterns

- Detached subprocess: 必须设 `stdin=subprocess.DEVNULL` 防止 stdin 阻塞
- 守护进程内 threading lock: 用 `RLock` 而非 `Lock`（嵌套调用链会死锁）
- Windows taskkill: 加 `/T` 杀整个进程树（PJob 子进程不会随 daemon 一起死）
- 新增运行时路径必须用 `get_zima_home()` 而非 `Path.home() / ".zima"`（ZIMA_HOME env var）

### Agent CLIs

- Kimi agent 调用 `kimi`（Kimi Code CLI）二进制（旧名 `kimi-cli` 已废弃，0.5.5 迁移），运行 Kimi PJob 前需确保 `kimi` 在 PATH 中
- pi agent 调用 `pi`（pi-coding-agent）二进制，运行 pi PJob 前需确保 `pi` 在 PATH 中；pi 用 `--mode` 而非 `--output-format` 控制输出格式，`--thinking max` 默认深度思考，prompt 经 stdin pipe 传入（同 claude）
- Kimi 旧参数 `maxStepsPerTurn`/`maxRalphIterations`/`maxRetriesPerStep`/`yolo`/`workDir` 已移除；三个 agent（kimi/claude/pi）的工作目录统一由 subprocess `cwd` 控制，无 `--work-dir` CLI flag

### Webhook Server

- `webhook-server` 默认 fail-closed：必须设 `--secret` 或 `ZIMA_WEBHOOK_SECRET`；`--allow-no-secret` 仅限本地 loopback 调试
- `--secret` 是 hidden option（避免出现在 `ps` / `/proc/<pid>/cmdline`），优先用 `ZIMA_WEBHOOK_SECRET` env var；`--smee-url` 做 SSRF 防护（仅允许 https smee.io），且**强制**要求 secret（smee channel 公开可读、可伪造）
- smee 事件无 rawBody 时转发器会用 secret 对 `json.dumps(body)` 重签再转发（#150）：此时 HMAC 只认证「经本地转发器」而非「GitHub 来源」；smee channel 公开可读，任何知道 channel URL 的人都能注入伪造事件触发 CR PJob（护栏：仅 zima:needs-review 标签事件、repo 白名单、60s 去重、触发自己的 PJob）。要端到端认证 GitHub 来源需用公网直投（GitHub → server，不经 smee）
- 触发的 PJob 经 `zima pjob run`（background_runner）后台执行，fire-and-forget，用 `zima pjob ps` 查看；agent 并发由 daemon 管，webhook 不做并发上限
- repo / head_sha 经严格 allow-list 校验后才传入 PJob `--set-var`（防模板注入）；同一 (event, pjob_code) 在 60s 窗口内去重，部分失败时仅该 code 不标记、可被 GitHub 重投重跑
- 多仓库路由：`--repo`（repeatable）与 `--pjob` 按序 1:1 配对（`--pjob A --repo X --pjob B --repo Y`），事件只触发 `repo` 匹配的 PJob（大小写不敏感），未匹配 repo 的事件忽略且记日志、不广播 → 单实例可服务多仓库（共用一个 smee channel）。完全不传 `--repo` 保留广播模式（向后兼容）；一旦传任何 `--repo`，计数必须等于 `--pjob` 否则报错。路由逻辑在 `server.py::trigger_pjobs` 经 `PjobRoute(code, repo|None)` 实现，`payload.py` 的 `should_trigger_review` 只管事件合法性（不感知 repo 绑定）

## Documentation

- `AGENTS.md` — Agent context file for Kimi Code agents
- `docs/architecture/` — **Current architecture** (authoritative)
- `docs/history/` — Deprecated designs (reference only)
- `docs/decisions/` — ADRs; ADR-004 (single execution) is the current model, ADR-005 (architecture governance) defines the dependency-direction contract
- `docs/design/` — Feature design documents (PJob design, API interface, etc.)
