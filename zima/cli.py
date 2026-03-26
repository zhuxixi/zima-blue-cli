"""ZimaBlue CLI - Main entry point"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from zima.models import AgentConfig
from zima.core import KimiRunner, CycleScheduler, StateManager
from zima.core.daemon import start_daemon, stop_daemon, is_daemon_running
from zima.utils import safe_print, icon

app = typer.Typer(
    name="zima",
    help="Zima Blue CLI - Personal Agent Orchestration Platform",
    add_completion=False,
)
console = Console()

# Global scheduler for signal handling
_current_scheduler: Optional[CycleScheduler] = None


def get_agents_dir() -> Path:
    """Get agents directory - global in ~/.zima/agents
    
    Priority:
    1. ZIMA_HOME environment variable
    2. ~/.zima/agents (default)
    """
    # Check ZIMA_HOME environment variable
    zima_home = os.environ.get("ZIMA_HOME")
    if zima_home:
        agents_dir = Path(zima_home) / "agents"
    else:
        # Default to ~/.zima/agents
        agents_dir = Path.home() / ".zima" / "agents"
    
    # Ensure directory exists
    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir


def _signal_handler(sig, frame):
    """Handle interrupt signals"""
    global _current_scheduler
    if _current_scheduler:
        safe_print("\n[WARNING] Received interrupt, stopping agent...")
        _current_scheduler.stop()
    else:
        sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


@app.callback()
def main():
    """Zima Blue CLI - Personal Agent Orchestration Platform"""
    pass


@app.command()
def init(
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        "-p",
        help="Initialize path (default: current directory)"
    )
):
    """Initialize ZimaBlue in current directory"""
    target_path = path or Path.cwd()
    
    # Create directory structure
    (target_path / "agents").mkdir(exist_ok=True)
    
    console.print(f"[green]{icon('check')} Initialized ZimaBlue at {target_path}[/green]")
    console.print(f"  Created: agents/")


@app.command()
def create(
    name: str = typer.Argument(..., help="Agent name"),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace directory (default: agents/{name}/workspace)"
    ),
    task: str = typer.Option(
        "default",
        "--task",
        "-t",
        help="Initial task type"
    ),
):
    """Create a new agent"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name
    
    if agent_dir.exists():
        console.print(f"[red]{icon('cross')} Agent '{name}' already exists[/red]")
        raise typer.Exit(1)
    
    # Create directories
    agent_dir.mkdir(parents=True)
    (agent_dir / "workspace").mkdir()
    (agent_dir / "prompts").mkdir()
    (agent_dir / "logs").mkdir()
    (agent_dir / "sessions").mkdir()
    
    # Create default config
    config = AgentConfig(
        name=name,
        description=f"Agent {name} for automated task execution",
        workspace=workspace or (agent_dir / "workspace"),
        initial_task={
            "type": task,
            "description": f"Execute {task} task",
        },
        pipeline=[
            {
                "name": "analyze",
                "description": "Analyze the current state and requirements",
            },
            {
                "name": "execute",
                "description": "Execute the main task",
            },
            {
                "name": "verify",
                "description": "Verify the results",
            },
        ]
    )
    
    config.to_yaml(agent_dir / "agent.yaml")
    
    console.print(f"[green]{icon('check')} Created agent: {name}[/green]")
    console.print(f"  Location: {agent_dir}")
    console.print(f"  Config: {agent_dir / 'agent.yaml'}")
    console.print(f"\nTo start the agent:")
    console.print(f"  zima start {name}")


@app.command()
def start(
    name: str = typer.Argument(..., help="Agent name"),
    cycle: Optional[int] = typer.Option(
        None,
        "--cycle",
        "-c",
        help="Start from specific cycle (for debugging)"
    ),
    detach: bool = typer.Option(
        False,
        "--detach",
        "-d",
        help="Run agent in background (daemon mode)"
    ),
):
    """Start an agent"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name
    
    if not agent_dir.exists():
        console.print(f"[red]{icon('cross')} Agent '{name}' not found[/red]")
        raise typer.Exit(1)
    
    config_path = agent_dir / "agent.yaml"
    if not config_path.exists():
        console.print(f"[red]{icon('cross')} Agent config not found: {config_path}[/red]")
        raise typer.Exit(1)
    
    # Check if already running
    if is_daemon_running(agent_dir):
        console.print(f"[yellow]{icon('warning')} Agent '{name}' is already running[/yellow]")
        console.print(f"  Use 'zima logs {name} -f' to view logs")
        raise typer.Exit(1)
    
    if detach:
        # Start as daemon (background process)
        pid = start_daemon(agent_dir)
        console.print(f"[green]{icon('check')} Agent '{name}' started in background[/green]")
        console.print(f"  PID: {pid}")
        console.print(f"  Logs: {agent_dir / 'daemon.log'}")
        console.print(f"\nTo view logs:")
        console.print(f"  zima logs {name} -f")
        console.print(f"\nTo stop:")
        console.print(f"  zima stop {name}")
    else:
        # Run in foreground (blocking)
        console.print(f"[green]{icon('check')} Starting agent '{name}' in foreground[/green]")
        console.print(f"  Press Ctrl+C to stop\n")
        
        # Load config
        config = AgentConfig.from_yaml(config_path)
        
        # Initialize components
        runner = KimiRunner(config, agent_dir)
        state_manager = StateManager(agent_dir)
        scheduler = CycleScheduler(config, runner, state_manager)
        
        # Set cycle if specified
        if cycle:
            state = state_manager.load_state()
            state.current_cycle = cycle - 1
            state_manager.save_state(state)
            console.print(f"[yellow]Starting from cycle {cycle}[/yellow]")
        
        # Set global scheduler for signal handling
        global _current_scheduler
        _current_scheduler = scheduler
        
        try:
            scheduler.run()
        except KeyboardInterrupt:
            safe_print("\n[WARNING] Stopped by user")
        finally:
            _current_scheduler = None


@app.command()
def status(
    name: str = typer.Argument(..., help="Agent name"),
):
    """Show agent status"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name
    
    if not agent_dir.exists():
        console.print(f"[red]{icon('cross')} Agent '{name}' not found[/red]")
        raise typer.Exit(1)
    
    state_manager = StateManager(agent_dir)
    state = state_manager.load_state()
    
    # Check daemon status
    daemon_running = is_daemon_running(agent_dir)
    
    # Build status table
    table = Table(title=f"Agent: {name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    # Show combined status
    if daemon_running:
        display_status = f"{state.status} (daemon running)"
    else:
        display_status = state.status
    
    table.add_row("Status", display_status)
    table.add_row("Daemon Mode", "running" if daemon_running else "stopped")
    table.add_row("Current Cycle", str(state.current_cycle))
    table.add_row("Current Stage", state.current_stage or "not started")
    table.add_row("Started At", state.started_at or "never")
    table.add_row("Updated At", state.updated_at or "never")
    
    if state.async_tasks:
        table.add_row("Async Tasks", str(len(state.async_tasks)))
    
    console.print(table)
    
    # Show daemon info if running
    if daemon_running:
        pid_file = agent_dir / "daemon.pid"
        if pid_file.exists():
            pid = pid_file.read_text().strip()
            console.print(f"\n[bold]Daemon Info:[/bold]")
            console.print(f"  PID: {pid}")
            console.print(f"  Log: {agent_dir / 'daemon.log'}")
    
    # Show recent sessions
    sessions = state_manager.get_recent_sessions(3)
    if sessions:
        console.print(f"\n[bold]Recent Sessions:[/bold]")
        for i, session in enumerate(sessions, 1):
            lines = session.split('\n')
            title = lines[0] if lines else f"Session {i}"
            console.print(f"  {i}. {title}")


@app.command()
def logs(
    name: str = typer.Argument(..., help="Agent name"),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow log output"
    ),
    n: int = typer.Option(
        20,
        "--lines",
        "-n",
        help="Number of lines to show"
    ),
):
    """Show agent logs"""
    import time
    
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name
    logs_dir = agent_dir / "logs"
    
    if not logs_dir.exists():
        console.print(f"[red]✗ No logs found for agent '{name}'[/red]")
        raise typer.Exit(1)
    
    log_files = sorted(logs_dir.glob("cycle_*.log"), reverse=True)
    
    if not log_files:
        console.print(f"[yellow]{icon('warning')} No log files found[/yellow]")
        return
    
    latest_log = log_files[0]
    
    if follow:
        # Follow mode (simple implementation)
        console.print(f"[bold]Following {latest_log.name} (Ctrl+C to exit):[/bold]\n")
        last_size = 0
        try:
            while True:
                if latest_log.exists():
                    content = latest_log.read_text(encoding="utf-8")
                    if len(content) > last_size:
                        new_content = content[last_size:]
                        console.print(new_content, end="")
                        last_size = len(content)
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped[/yellow]")
    else:
        # Show last n lines
        content = latest_log.read_text(encoding="utf-8")
        lines = content.split('\n')
        
        console.print(f"[bold]Latest log ({latest_log.name}):[/bold]\n")
        for line in lines[-n:]:
            console.print(line)


@app.command()
def list(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed information"
    ),
):
    """List all agents"""
    agents_dir = get_agents_dir()
    
    if not agents_dir.exists():
        console.print(f"[yellow]{icon('warning')} No agents found. Create one with: zima create <name>[/yellow]")
        return
    
    agent_dirs = [d for d in agents_dir.iterdir() if d.is_dir()]
    
    if not agent_dirs:
        console.print(f"[yellow]{icon('warning')} No agents found. Create one with: zima create <name>[/yellow]")
        return
    
    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Cycle", style="yellow")
    table.add_column("Stage", style="blue")
    
    for agent_dir in sorted(agent_dirs):
        name = agent_dir.name
        state_manager = StateManager(agent_dir)
        state = state_manager.load_state()
        
        table.add_row(
            name,
            state.status,
            str(state.current_cycle),
            state.current_stage or "-"
        )
    
    console.print(table)


@app.command()
def stop(
    name: str = typer.Argument(..., help="Agent name"),
):
    """Stop a running agent (daemon mode)"""
    agents_dir = get_agents_dir()
    agent_dir = agents_dir / name
    
    if not agent_dir.exists():
        console.print(f"[red]{icon('cross')} Agent '{name}' not found[/red]")
        raise typer.Exit(1)
    
    if not is_daemon_running(agent_dir):
        console.print(f"[yellow]{icon('warning')} Agent '{name}' is not running in daemon mode[/yellow]")
        console.print(f"  If running in foreground, press Ctrl+C in that terminal")
        raise typer.Exit(1)
    
    if stop_daemon(agent_dir):
        console.print(f"[green]{icon('check')} Agent '{name}' stopped[/green]")
    else:
        console.print(f"[red]{icon('cross')} Failed to stop agent '{name}'[/red]")


if __name__ == "__main__":
    app()
