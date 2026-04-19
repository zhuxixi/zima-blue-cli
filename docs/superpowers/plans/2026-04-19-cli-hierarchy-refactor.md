# CLI Command Hierarchy Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove 9 top-level CLI commands and refactor daemon commands into a proper subcommand group, establishing a clean `zima <entity> <action>` pattern.

**Architecture:** Extract daemon commands from `cli.py` into a new `zima/commands/daemon.py` Typer subcommand group. Remove all other top-level commands (`create`, `run`, `list`, `show`, `logs`) and the `AgentRunner` class they depended on. Update docs to match.

**Tech Stack:** Python 3.10+, Typer, Rich, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `zima/commands/daemon.py` | **Create** | Typer subcommand group: `zima daemon start/stop/status/logs` |
| `zima/cli.py` | **Modify** | Remove 9 commands, add daemon subcommand registration |
| `zima/core/runner.py` | **Delete** | `AgentRunner` class — only used by removed `zima run` |
| `zima/core/__init__.py` | **Modify** | Remove `AgentRunner` export |
| `zima/models/__init__.py` | **Modify** | Remove `RunResult` export (only `runner.py` used it) |
| `docs/API-INTERFACE.md` | **Modify** | Remove top-level command docs, add daemon section |
| `tests/integration/test_daemon_commands.py` | **Create** | Integration tests for daemon CLI commands |

---

### Task 1: Create daemon subcommand group

**Files:**
- Create: `zima/commands/daemon.py`

This task creates the new `daemon.py` command module by extracting logic from `cli.py` lines 272-467. No behavior changes — direct extraction.

- [ ] **Step 1: Create `zima/commands/daemon.py`**

```python
"""Daemon management commands."""

from __future__ import annotations

import subprocess
import sys
import time

import typer
from rich.console import Console

from zima.config.manager import ConfigManager
from zima.models.schedule import ScheduleConfig
from zima.utils import get_zima_home

app = typer.Typer(name="daemon", help="Daemon management commands")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def start(
    schedule: str = typer.Option(..., "--schedule", "-s", help="Schedule code"),
):
    """Start the global daemon"""
    daemon_dir = get_zima_home() / "daemon"
    pid_file = daemon_dir / "daemon.pid"

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            # Check if process is alive
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                console.print(f"[yellow]⚠[/yellow] Daemon already running (PID {pid})")
                raise typer.Exit(1)
        except Exception:
            pass
        pid_file.unlink(missing_ok=True)

    manager = ConfigManager()
    if not manager.config_exists("schedule", schedule):
        console.print(f"[red]✗[/red] Schedule '{schedule}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", schedule)
    cfg = ScheduleConfig.from_dict(data)
    errors = cfg.validate(resolve_refs=True)
    if errors:
        console.print("[red]✗[/red] Schedule validation failed:")
        for e in errors:
            console.print(f"   [red]•[/red] {e}")
        raise typer.Exit(1)

    log_file = daemon_dir / "daemon.log"
    daemon_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "zima.daemon_runner",
        "--schedule",
        schedule,
    ]

    log_fh = open(log_file, "w", encoding="utf-8")
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
    except Exception as e:
        log_fh.close()
        console.print(f"[red]✗[/red] Failed to start daemon: {e}")
        raise typer.Exit(1)
    # Detach file handle — daemon process owns it now
    log_fh.close()

    # Brief check that child didn't exit immediately (e.g. validation failure)
    time.sleep(0.5)
    if proc.poll() is not None:
        pid_file.unlink(missing_ok=True)
        console.print(f"[red]✗[/red] Daemon exited immediately (code {proc.returncode})")
        console.print(f"   Check log: {log_file}")
        raise typer.Exit(1)

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    console.print(f"[green]✓[/green] Daemon started (PID {proc.pid})")
    console.print(f"   Schedule: {schedule}")
    console.print(f"   Log: {log_file}")


@app.command()
def stop():
    """Stop the global daemon"""
    daemon_dir = get_zima_home() / "daemon"
    pid_file = daemon_dir / "daemon.pid"

    if not pid_file.exists():
        console.print("[yellow]⚠[/yellow] Daemon is not running")
        raise typer.Exit(0)

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if sys.platform == "win32":
            # Try graceful shutdown first, then force after 5s
            # /T kills the entire process tree (PJobs spawned with CREATE_NEW_PROCESS_GROUP)
            subprocess.run(["taskkill", "/PID", str(pid), "/T"], check=False)

            time.sleep(5)
            # Force kill if still alive
            try:
                import ctypes

                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
            except Exception:
                pass
        else:
            import os
            import signal

            os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        console.print(f"[green]✓[/green] Daemon stopped (PID {pid})")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to stop daemon: {e}")
        raise typer.Exit(1)


@app.command()
def status():
    """Show daemon status"""
    daemon_dir = get_zima_home() / "daemon"
    pid_file = daemon_dir / "daemon.pid"
    state_file = daemon_dir / "state.json"

    if not pid_file.exists():
        console.print("[yellow]Daemon is not running[/yellow]")
        raise typer.Exit(0)

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        console.print("[red]Invalid PID file[/red]")
        raise typer.Exit(1)

    # Check if alive
    alive = False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(1, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            alive = True
    else:
        import os

        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            pass

    if not alive:
        console.print(f"[yellow]Daemon PID {pid} is not alive[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Daemon is running[/green] (PID {pid})")

    if state_file.exists():
        import json

        state = json.loads(state_file.read_text(encoding="utf-8"))
        console.print(f"   Current cycle: {state.get('currentCycle', 'unknown')}")
        console.print(f"   Current stage: {state.get('currentStage', 'unknown')}")
        console.print(f"   Active PJobs: {state.get('activePjobs', [])}")


@app.command()
def logs(
    tail: int = typer.Option(20, "--tail", "-n", help="Number of lines"),
):
    """Show daemon logs"""
    log_file = get_zima_home() / "daemon" / "daemon.log"
    if not log_file.exists():
        console.print("[yellow]No daemon logs found[/yellow]")
        raise typer.Exit(0)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    for line in lines[-tail:]:
        console.print(line)
```

- [ ] **Step 2: Verify the new file has no syntax errors**

Run: `python -c "from zima.commands.daemon import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add zima/commands/daemon.py
git commit -m "feat(daemon): create daemon subcommand group extracted from cli.py"
```

---

### Task 2: Clean up `cli.py` — remove all top-level commands

**Files:**
- Modify: `zima/cli.py`

Replace the entire `cli.py` with the cleaned version. The file shrinks from ~470 lines to ~50 lines.

- [ ] **Step 1: Rewrite `zima/cli.py`**

The new `cli.py` should contain ONLY the app setup, subcommand registrations, and the callback. Remove: `get_agents_dir()`, `create()`, `run()`, `list()`, `show()`, `logs()`, `daemon_start()`, `daemon_stop()`, `daemon_status()`, `daemon_logs()`. Remove unused imports: `os`, `subprocess`, `AgentRunner`, `AgentConfig`, `ScheduleConfig`. Add: `daemon` command import and registration.

```python
"""ZimaBlue CLI - v2 Simplified"""

from __future__ import annotations

from zima.utils import setup_windows_utf8

setup_windows_utf8()

import typer

from zima.commands import agent as agent_cmd
from zima.commands import daemon as daemon_cmd
from zima.commands import env as env_cmd
from zima.commands import pjob as pjob_cmd
from zima.commands import pmg as pmg_cmd
from zima.commands import schedule as schedule_cmd
from zima.commands import variable as variable_cmd
from zima.commands import workflow as workflow_cmd

app = typer.Typer(
    name="zima",
    help="ZimaBlue CLI - Agent Runner",
    add_completion=False,
)

# Register subcommands
app.add_typer(agent_cmd.app, name="agent")
app.add_typer(workflow_cmd.app, name="workflow")
app.add_typer(variable_cmd.app, name="variable")
app.add_typer(env_cmd.app, name="env")
app.add_typer(pmg_cmd.app, name="pmg")
app.add_typer(pjob_cmd.app, name="pjob")
app.add_typer(schedule_cmd.app, name="schedule")
app.add_typer(daemon_cmd.app, name="daemon")


@app.callback()
def main():
    """ZimaBlue CLI - Agent Runner"""
    pass


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Verify CLI loads and shows correct help**

Run: `python -m zima.cli --help`
Expected: Shows only subcommand groups (agent, workflow, variable, env, pmg, pjob, schedule, daemon). No top-level `create`, `run`, `list`, `show`, `logs`, `daemon-start`, etc.

- [ ] **Step 3: Commit**

```bash
git add zima/cli.py
git commit -m "refactor(cli): remove all top-level commands, keep only entity subcommands"
```

---

### Task 3: Remove `AgentRunner` and clean up exports

**Files:**
- Delete: `zima/core/runner.py`
- Modify: `zima/core/__init__.py`
- Modify: `zima/models/__init__.py`

- [ ] **Step 1: Delete `zima/core/runner.py`**

```bash
git rm zima/core/runner.py
```

- [ ] **Step 2: Update `zima/core/__init__.py`**

Remove the `AgentRunner` import and export. The file becomes:

```python
"""Core components for ZimaBlue - v2"""

from .claude_runner import ClaudeRunner
from .daemon_scheduler import DaemonScheduler

__all__ = ["ClaudeRunner", "DaemonScheduler"]
```

- [ ] **Step 3: Update `zima/models/__init__.py`**

Remove `RunResult` from imports and `__all__` (only `runner.py` used it, and that file is deleted). Check the current file first — remove only `RunResult` and leave all other exports intact.

Find the line:
```python
from .agent import AgentConfig, AgentState, CycleResult, RunResult
```
Change to:
```python
from .agent import AgentConfig, AgentState, CycleResult
```

Find the line:
```python
    "RunResult",
```
Remove it from `__all__`.

Note: Do NOT remove `RunResult` from `zima/models/agent.py` itself — it's a data class in the model layer and may be useful later.

- [ ] **Step 4: Verify no broken imports**

Run: `python -c "from zima.core import ClaudeRunner, DaemonScheduler; from zima.models import AgentConfig; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add zima/core/__init__.py zima/models/__init__.py
git commit -m "refactor: remove AgentRunner and RunResult CLI dependency"
```

---

### Task 4: Add daemon command integration tests

**Files:**
- Create: `tests/integration/test_daemon_commands.py`

Test the new `zima daemon` subcommand group using Typer's `CliRunner`. These tests verify the CLI registration works correctly and basic command behavior without an actual daemon process.

- [ ] **Step 1: Create `tests/integration/test_daemon_commands.py`**

```python
"""Integration tests for daemon CLI commands."""

from typer.testing import CliRunner

from tests.base import TestIsolator
from zima.cli import app

runner = CliRunner()


class TestDaemonStart(TestIsolator):
    """Test zima daemon start command."""

    def test_start_no_schedule(self):
        """Daemon start without --schedule should fail."""
        result = runner.invoke(app, ["daemon", "start"])
        assert result.exit_code != 0

    def test_start_nonexistent_schedule(self):
        """Daemon start with nonexistent schedule should fail."""
        result = runner.invoke(app, ["daemon", "start", "--schedule", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestDaemonStop(TestIsolator):
    """Test zima daemon stop command."""

    def test_stop_not_running(self):
        """Daemon stop when not running should show warning."""
        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        assert "not running" in result.output


class TestDaemonStatus(TestIsolator):
    """Test zima daemon status command."""

    def test_status_not_running(self):
        """Daemon status when not running should show message."""
        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert "not running" in result.output


class TestDaemonLogs(TestIsolator):
    """Test zima daemon logs command."""

    def test_logs_no_log_file(self):
        """Daemon logs when no log file exists should show message."""
        result = runner.invoke(app, ["daemon", "logs"])
        assert result.exit_code == 0
        assert "No daemon logs" in result.output
```

- [ ] **Step 2: Run the new tests**

Run: `pytest tests/integration/test_daemon_commands.py -v`
Expected: All 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_daemon_commands.py
git commit -m "test(daemon): add integration tests for daemon CLI commands"
```

---

### Task 5: Update `docs/API-INTERFACE.md`

**Files:**
- Modify: `docs/API-INTERFACE.md`

Remove Section 1.1 (top-level commands) and add a daemon section.

- [ ] **Step 1: Edit the document**

Make the following changes to `docs/API-INTERFACE.md`:

1. **Replace Section 1.1** (lines 28-55, "### 1.1 顶层命令" through "简写命令详解") with a brief note:

```markdown
### 1.1 Daemon 管理

**命令**: `zima daemon <subcommand>`

守护进程管理，用于启动/停止/查看调度器守护进程。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `start` | 启动守护进程 | `zima daemon start --schedule my-schedule` |
| `stop` | 停止守护进程 | `zima daemon stop` |
| `status` | 查看守护进程状态 | `zima daemon status` |
| `logs` | 查看守护进程日志 | `zima daemon logs --tail 50` |
```

2. **Update the 目录** (Table of Contents): Change the `1.1 顶层命令` entry to `1.1 Daemon 管理`.

3. **Update version history**: Add a new entry at the top of the version table:

```markdown
| v2.3 | 2026-04-19 | CLI 命令层级重组：移除顶层命令，新增 daemon 子命令组 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/API-INTERFACE.md
git commit -m "docs(api): update CLI interface doc for command hierarchy refactor"
```

---

### Task 6: Run full verification

This task ensures nothing is broken.

- [ ] **Step 1: Run lint and format checks**

Run: `ruff check zima/ tests/`
Expected: No errors

Run: `black --check zima/ tests/ --line-length 100`
Expected: No errors (all files formatted)

If black reports formatting issues, run: `black zima/ tests/ --line-length 100` and amend the relevant commit.

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests pass. No import errors from removing `runner.py`.

- [ ] **Step 3: Verify CLI help output**

Run: `python -m zima.cli --help`
Expected: Shows exactly these subcommand groups: agent, workflow, variable, env, pmg, pjob, schedule, daemon. No top-level action commands.

Run: `python -m zima.cli daemon --help`
Expected: Shows 4 subcommands: start, stop, status, logs.

- [ ] **Step 4: Verify old commands are gone**

Run: `python -m zima.cli create --help`
Expected: Error: `No such command 'create'`

Run: `python -m zima.cli run --help`
Expected: Error: `No such command 'run'`

Run: `python -m zima.cli daemon-start --help`
Expected: Error: `No such command 'daemon-start'`
