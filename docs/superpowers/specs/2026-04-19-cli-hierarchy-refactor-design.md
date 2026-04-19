# CLI Command Hierarchy Refactor — Design Spec

> Issue: #27
> Date: 2026-04-19
> Status: Approved

## Problem

`zima` CLI has 9 top-level commands that break the `zima <entity> <action>` design principle:

1. `create`, `run`, `list`, `show`, `logs` — operate on agents but lack entity prefix
2. `daemon-start`, `daemon-stop`, `daemon-status`, `daemon-logs` — kebab-case instead of subcommand group

The top-level `create`/`list`/`show` use a **different implementation** (direct directory manipulation) than `zima agent create`/`list`/`show` (ConfigManager). The top-level `run` uses `AgentRunner` (v1 approach) while `zima pjob run` uses `PJobExecutor` (v2 approach).

No tests cover these 9 commands. All tests already use the subcommand forms.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| `zima run` | Retire entirely | PJob is the execution entity; use `zima pjob run` |
| `zima create/list/show` | Remove entirely | `zima agent create/list/show` provides same+better functionality |
| `zima logs` | Remove entirely | Use `zima pjob history <code>` for execution logs |
| `zima daemon-*` | Refactor to `zima daemon start/stop/status/logs` | Consistent subcommand group pattern |
| `AgentRunner` | Remove `core/runner.py` | Only used by removed `zima run` command |
| Implementation strategy | Clean break (single PR) | Pre-release project, no external users |
| Top-level aliases | None | Clean mental model, no shortcuts |

## Target Command Surface

```
zima agent      create/list/show/update/delete/validate/test/types
zima workflow   create/list/show/update/delete/validate/render/add-var
zima variable   create/list/show/update/delete/set/get/validate/merge
zima env        create/list/show/update/delete/set/set-secret/unset/validate
zima pmg        create/list/show/update/delete/add-param/remove-param/validate
zima pjob       create/list/show/update/delete/copy/run/render/validate/history
zima schedule   create/list/show/update/delete/validate/set-type/set-mapping
zima daemon     start/stop/status/logs
```

All operations follow `zima <entity> <action>`. No top-level action commands.

## Code Changes

### `zima/cli.py` — Major cleanup (~470 lines → ~50 lines)

**Remove:**
- `get_agents_dir()` function
- Top-level commands: `create()`, `run()`, `list()`, `show()`, `logs()`
- Daemon commands: `daemon_start()`, `daemon_stop()`, `daemon_status()`, `daemon_logs()`
- Unused imports: `os`, `subprocess`, `AgentRunner`, `AgentConfig`, `ScheduleConfig`

**Add:**
- `from zima.commands import daemon as daemon_cmd`
- `app.add_typer(daemon_cmd.app, name="daemon")`

### New `zima/commands/daemon.py`

Typer subcommand group with 4 commands. Logic is a direct extraction from `cli.py` — no behavior changes:

```python
app = typer.Typer(name="daemon", help="Daemon management commands")

@app.command()
def start(schedule: str = typer.Option(..., "--schedule", "-s")): ...

@app.command()
def stop(): ...

@app.command()
def status(): ...

@app.command()
def logs(tail: int = typer.Option(20, "--tail", "-n")): ...
```

Preserved behaviors:
- `start`: PID file check, schedule config validation via ConfigManager, detached subprocess spawn, Windows/Linux platform handling
- `stop`: Graceful then forced shutdown, Windows `taskkill /T` for process tree
- `status`: PID liveness check (Windows `ctypes.windll.kernel32` / Unix `os.kill`), state.json display
- `logs`: Tail daemon.log

### `zima/core/runner.py` — Delete

`AgentRunner` is only used by the removed `zima run` command. Safe to delete.

### `zima/core/__init__.py` — Update

Remove `AgentRunner` from imports and `__all__`.

### `zima/models/agent.py` — No changes

`AgentConfig.from_yaml_file()` remains in the model layer (it's a general utility). Only the CLI callers are removed.

### Tests — No changes needed

No tests reference the removed commands. All tests already use subcommand forms.

### `docs/API-INTERFACE.md` — Update

- Remove Section 1.1 (top-level commands) and the "简写命令详解" subsection
- Add `zima daemon` section (start/stop/status/logs)

## Verification

1. **Existing tests pass**: `pytest` — all subcommand tests unaffected
2. **New daemon tests**: Add integration tests for `zima daemon start/stop/status/logs` using CliRunner
3. **Manual check**: `zima --help` shows only entity groups, no action commands
4. **Lint/format**: `ruff check` + `black --check`

## Out of Scope

- No deprecation warnings or migration guide (clean break)
- No changes to remaining subcommand groups (agent, workflow, variable, env, pmg, pjob, schedule)
- No changes to models, ConfigManager, or execution logic
- No new features — pure restructuring
