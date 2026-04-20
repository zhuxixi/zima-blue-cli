"""Daemon management commands."""

from __future__ import annotations

import json
import subprocess
import sys
import time

import typer
from rich.console import Console

from zima.config.manager import ConfigManager
from zima.models.schedule import ScheduleConfig
from zima.utils import get_zima_home


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive.

    Uses PROCESS_QUERY_LIMITED_INFORMATION on Windows (more reliable
    than PROCESS_TERMINATE for cross-privilege checks) and os.kill
    with signal 0 on Unix.

    Args:
        pid: Process ID to check.

    Returns:
        True if the process is alive, False otherwise.
    """
    try:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            import os

            os.kill(pid, 0)
            return True
    except PermissionError:
        # Process exists but we lack permission to signal it
        return True
    except (ProcessLookupError, OSError):
        return False


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
            if _is_process_alive(pid):
                console.print(f"[yellow]⚠[/yellow] Daemon already running (PID {pid})")
                raise typer.Exit(1)
            # Process not alive — clean up stale PID file
            pid_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            # Corrupted or unreadable PID file — clean up
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
                stdin=subprocess.DEVNULL,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
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
                if _is_process_alive(pid):
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
            except Exception:
                pass
        else:
            import os
            import signal

            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # Process already dead (stale PID)
            else:
                time.sleep(2)
                if _is_process_alive(pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # Process died between check and kill
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
    except (ValueError, OSError):
        console.print("[red]Cannot read PID file[/red]")
        raise typer.Exit(1)

    # Check if alive
    alive = _is_process_alive(pid)

    if not alive:
        pid_file.unlink(missing_ok=True)
        console.print(f"[yellow]Daemon PID {pid} is not alive[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Daemon is running[/green] (PID {pid})")

    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("state.json is not a JSON object")
            console.print(f"   Current cycle: {state.get('currentCycle', 'unknown')}")
            console.print(f"   Current stage: {state.get('currentStage', 'unknown')}")
            console.print(f"   Active PJobs: {state.get('activePjobs', [])}")
        except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
            console.print("[yellow]   Corrupted state file[/yellow]")


@app.command()
def logs(
    tail: int = typer.Option(20, "--tail", "-n", help="Number of lines"),
):
    """Show daemon logs"""
    log_file = get_zima_home() / "daemon" / "daemon.log"
    if not log_file.exists():
        console.print("[yellow]No daemon logs found[/yellow]")
        raise typer.Exit(0)

    try:
        lines = log_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        console.print(f"[red]✗[/red] Cannot read log file: {e}")
        raise typer.Exit(1)
    for line in lines[-tail:]:
        console.print(line)
