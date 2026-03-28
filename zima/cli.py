"""ZimaBlue CLI - v2 Simplified"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from zima.models import AgentConfig, RunResult
from zima.core import AgentRunner
from zima.commands import agent as agent_cmd
from zima.commands import workflow as workflow_cmd
from zima.commands import variable as variable_cmd
from zima.commands import env as env_cmd
from zima.commands import pmg as pmg_cmd
from zima.commands import pjob as pjob_cmd

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
console = Console()


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
    workspace: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace directory"
    ),
    prompt: Optional[Path] = typer.Option(
        None, "--prompt", "-p", help="Prompt file"
    ),
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
    agent_yaml.write_text(f"""metadata:
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
""", encoding="utf-8")
    
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
    console.print(f"\n[bold]Result:[/bold]")
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
            desc = config.description[:50] + "..." if len(config.description) > 50 else config.description
        except:
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
        lines = content.split('\n')
        for line in lines[-n:]:
            console.print(line)
    except Exception as e:
        console.print(f"[red]Error reading log: {e}[/red]")


if __name__ == "__main__":
    app()
