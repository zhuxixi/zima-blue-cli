"""ZimaBlue CLI - v2 Simplified"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Fix Windows UTF-8 encoding issue
from zima.utils import setup_windows_utf8

setup_windows_utf8()

import typer
from rich.console import Console
from rich.table import Table

from zima.commands import agent as agent_cmd
from zima.commands import env as env_cmd
from zima.commands import pjob as pjob_cmd
from zima.commands import pmg as pmg_cmd
from zima.commands import schedule as schedule_cmd
from zima.commands import variable as variable_cmd
from zima.commands import workflow as workflow_cmd
from zima.config.manager import ConfigManager
from zima.core import AgentRunner
from zima.models import AgentConfig
from zima.models.schedule import ScheduleConfig

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
console = Console(legacy_windows=False, force_terminal=True)


def get_agents_dir() -> Path:
    """Get agents directory - global in ~/.zima/agents"""
    zima_home = os.environ.get("ZIMA_HOME")
    if zima_home:
        agents_dir = Path(zima_home) / "agents"
    else:
        agents_dir = Path.home() / ".zima" / "agents"

    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir


@app.callback()
def main():
    """ZimaBlue CLI - Agent Runner"""
    pass


@app.command()
def create(
    name: str = typer.Argument(..., help="Agent name"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    prompt: Optional[Path] = typer.Option(None, "--prompt", "-p", help="Prompt file"),
):
    """Create a new agent"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name

    if agent_dir.exists():
        console.print(f"[red]✗ Agent '{name}' already exists[/red]")
        raise typer.Exit(1)

    # Create directories
    agent_dir.mkdir(parents=True)
    ws_dir = agent_dir / "workspace"
    ws_dir.mkdir()
    (agent_dir / "logs").mkdir()

    # Create default agent.yaml
    prompt_file = prompt.name if prompt else "prompt.md"
    agent_yaml = agent_dir / "agent.yaml"
    agent_yaml.write_text(
        f"""metadata:
  name: {name}
  description: Auto-generated agent

spec:
  workspace: ./workspace
  prompt:
    file: {prompt_file}
    vars: {{}}
  execution:
    maxTime: 900
    maxStepsPerTurn: 50
    maxRalphIterations: 10
""",
        encoding="utf-8",
    )

    # Copy prompt file if provided
    if prompt and prompt.exists():
        import shutil

        shutil.copy(prompt, agent_dir / prompt_file)
    else:
        # Create default prompt
        (agent_dir / "prompt.md").write_text(f"# {name}\n\nYour task here.\n", encoding="utf-8")

    console.print(f"[green]✓ Created agent '{name}'[/green]")
    console.print(f"  Directory: {agent_dir}")
    console.print(f"  Workspace: {ws_dir}")
    console.print(f"\nEdit {agent_dir / 'agent.yaml'} to configure")


@app.command()
def run(
    name: str = typer.Argument(..., help="Agent name"),
    timeout: Optional[int] = typer.Option(
        None, "--timeout", "-t", help="Max execution time (seconds)"
    ),
):
    """Run an agent once"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name

    if not agent_dir.exists():
        console.print(f"[red]✗ Agent '{name}' not found[/red]")
        raise typer.Exit(1)

    # Load config
    config = AgentConfig.from_yaml(agent_dir / "agent.yaml")

    # Override timeout if provided
    if timeout:
        config.max_execution_time = timeout

    # Run
    runner = AgentRunner(config, agent_dir)
    result = runner.run()

    # Show result
    console.print("\n[bold]Result:[/bold]")
    console.print(f"  Status: {result.status}")
    console.print(f"  Time: {result.elapsed_time:.1f}s")
    console.print(f"  Summary: {result.summary}")

    if result.return_code != 0:
        raise typer.Exit(1)


@app.command()
def list(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List all agents"""
    agents_dir = get_agents_dir()

    if not agents_dir.exists():
        console.print("[yellow]No agents found. Create one with: zima create <name>[/yellow]")
        return

    agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]

    if not agent_dirs:
        console.print("[yellow]No agents found. Create one with: zima create <name>[/yellow]")
        return

    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="green")

    for agent_dir in sorted(agent_dirs):
        name = agent_dir.name
        try:
            config = AgentConfig.from_yaml(agent_dir / "agent.yaml")
            desc = (
                config.description[:50] + "..."
                if len(config.description) > 50
                else config.description
            )
        except Exception:
            desc = "-"

        table.add_row(name, desc)

    console.print(table)


@app.command()
def show(
    name: str = typer.Argument(..., help="Agent name"),
):
    """Show agent configuration"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name

    if not agent_dir.exists():
        console.print(f"[red]✗ Agent '{name}' not found[/red]")
        raise typer.Exit(1)

    config = AgentConfig.from_yaml(agent_dir / "agent.yaml")

    table = Table(title=f"Agent: {name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Name", config.name)
    table.add_row("Description", config.description)
    table.add_row("Workspace", str(config.workspace))
    table.add_row("Prompt File", config.prompt_file)
    table.add_row("Max Time", f"{config.max_execution_time}s")
    table.add_row("Max Steps/Turn", str(config.max_steps_per_turn))
    table.add_row("Max Ralph Iter", str(config.max_ralph_iterations))

    console.print(table)

    if config.prompt_vars:
        console.print("\n[bold]Prompt Variables:[/bold]")
        for k, v in config.prompt_vars.items():
            console.print(f"  {k}: {v}")


@app.command()
def logs(
    name: str = typer.Argument(..., help="Agent name"),
    n: int = typer.Option(20, "--lines", "-n", help="Number of lines"),
):
    """Show agent logs"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name

    if not agent_dir.exists():
        console.print(f"[red]✗ Agent '{name}' not found[/red]")
        raise typer.Exit(1)

    logs_dir = agent_dir / "logs"
    if not logs_dir.exists():
        console.print("[yellow]No logs found[/yellow]")
        return

    # Get latest log
    log_files = sorted(logs_dir.glob("*.log"), reverse=True)
    if not log_files:
        console.print("[yellow]No logs found[/yellow]")
        return

    latest = log_files[0]
    console.print(f"[bold]Latest log ({latest.name}):[/bold]\n")

    try:
        content = latest.read_text(encoding="utf-8")
        lines = content.split("\n")
        for line in lines[-n:]:
            console.print(line)
    except Exception as e:
        console.print(f"[red]Error reading log: {e}[/red]")


# ---------------------------------------------------------------------------
# Daemon commands
# ---------------------------------------------------------------------------


@app.command()
def daemon_start(
    schedule: str = typer.Option(..., "--schedule", "-s", help="Schedule code"),
):
    """Start the global daemon"""
    daemon_dir = Path.home() / ".zima" / "daemon"
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

    if sys.platform == "win32":
        proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    console.print(f"[green]✓[/green] Daemon started (PID {proc.pid})")
    console.print(f"   Schedule: {schedule}")
    console.print(f"   Log: {log_file}")


@app.command()
def daemon_stop():
    """Stop the global daemon"""
    daemon_dir = Path.home() / ".zima" / "daemon"
    pid_file = daemon_dir / "daemon.pid"

    if not pid_file.exists():
        console.print("[yellow]⚠[/yellow] Daemon is not running")
        raise typer.Exit(0)

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
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
def daemon_status():
    """Show daemon status"""
    daemon_dir = Path.home() / ".zima" / "daemon"
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
def daemon_logs(
    tail: int = typer.Option(20, "--tail", "-n", help="Number of lines"),
):
    """Show daemon logs"""
    log_file = Path.home() / ".zima" / "daemon" / "daemon.log"
    if not log_file.exists():
        console.print("[yellow]No daemon logs found[/yellow]")
        raise typer.Exit(0)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    for line in lines[-tail:]:
        console.print(line)


if __name__ == "__main__":
    app()
