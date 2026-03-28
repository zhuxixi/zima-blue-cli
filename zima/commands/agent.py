"""Agent management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

from zima.config.manager import ConfigManager
from zima.models.agent import AgentConfig
from zima.utils import validate_code_with_error, get_valid_agent_types

app = typer.Typer(name="agent", help="Agent management commands")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    code: str = typer.Option(..., "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"),
    agent_type: str = typer.Option("kimi", "--type", "-t", help="Agent type: kimi/claude/gemini"),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing agent"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name"),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", "-w", help="Working directory"),
):
    """Create a new agent"""
    manager = ConfigManager()
    
    # 1. Validate code format
    is_valid, error = validate_code_with_error(code)
    if not is_valid:
        console.print(f"[red]✗[/red] Invalid code: {error}")
        raise typer.Exit(1)
    
    # 2. Check if code already exists
    if manager.config_exists("agent", code):
        console.print(f"[red]✗[/red] Agent with code '{code}' already exists")
        raise typer.Exit(1)
    
    # 3. Handle --from (copy existing)
    if from_code:
        if not manager.config_exists("agent", from_code):
            console.print(f"[red]✗[/red] Source agent '{from_code}' not found")
            raise typer.Exit(1)
        
        try:
            manager.copy_config("agent", from_code, code, name)
            console.print(f"[green]✓[/green] Agent '{code}' created from '{from_code}'")
            console.print(f"   Name: {name}")
            console.print(f"   File: {manager.get_config_path('agent', code)}")
            return
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to copy: {e}")
            raise typer.Exit(1)
    
    # 4. Validate agent type
    valid_types = get_valid_agent_types()
    if agent_type not in valid_types:
        console.print(f"[red]✗[/red] Invalid type '{agent_type}'. Valid: {valid_types}")
        raise typer.Exit(1)
    
    # 5. Build parameters
    params = {}
    if model:
        params["model"] = model
    if work_dir:
        params["workDir"] = work_dir
    
    # 6. Create agent config
    try:
        config = AgentConfig.create(
            code=code,
            name=name,
            agent_type=agent_type,
            description=description,
            parameters=params
        )
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    
    # 7. Validate
    errors = config.validate()
    if errors:
        console.print("[red]✗[/red] Validation failed:")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    
    # 8. Save
    try:
        manager.save_config("agent", code, config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    # 9. Output success
    console.print(f"[green]✓[/green] Agent '{code}' created successfully")
    console.print(f"   Name: {name}")
    console.print(f"   Type: {agent_type}")
    console.print(f"   File: {manager.get_config_path('agent', code)}")


@app.command()
def list(
    agent_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    output_format: str = typer.Option("table", "--format", help="Output format: table/json"),
):
    """List all agents"""
    manager = ConfigManager()
    
    # Load all agents
    configs = manager.list_configs("agent")
    
    if not configs:
        console.print("[yellow]No agents found.[/yellow] Create one with: zima agent create")
        return
    
    # Filter by type if specified
    if agent_type:
        configs = [c for c in configs if c.get("spec", {}).get("type") == agent_type]
    
    if not configs:
        console.print(f"[yellow]No agents found with type '{agent_type}'[/yellow]")
        return
    
    if output_format == "json":
        import json
        console.print(json.dumps(configs, indent=2, ensure_ascii=False))
    else:
        # Table format
        table = Table(title="Agents")
        table.add_column("Code", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Description", style="dim")
        
        for config in configs:
            metadata = config.get("metadata", {})
            spec = config.get("spec", {})
            
            code = metadata.get("code", "-")
            name = metadata.get("name", "-")
            agent_type = spec.get("type", "-")
            desc = metadata.get("description", "")
            
            # Truncate description
            if len(desc) > 40:
                desc = desc[:37] + "..."
            
            table.add_row(code, name, agent_type, desc)
        
        console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="Agent code"),
    output_format: str = typer.Option("yaml", "--format", help="Output format: yaml/json"),
):
    """Show agent details"""
    manager = ConfigManager()
    
    if not manager.config_exists("agent", code):
        console.print(f"[red]✗[/red] Agent '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config = manager.load_config("agent", code)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    if output_format == "json":
        import json
        console.print(json.dumps(config, indent=2, ensure_ascii=False))
    else:
        # YAML format with syntax highlighting
        import yaml
        yaml_content = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
        console.print(Syntax(yaml_content, "yaml"))


@app.command()
def update(
    code: str = typer.Argument(..., help="Agent code"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    set_param: Optional[List[str]] = typer.Option(None, "--set-param", "-p", help="Set parameter (key=value)"),
):
    """Update agent configuration"""
    manager = ConfigManager()
    
    if not manager.config_exists("agent", code):
        console.print(f"[red]✗[/red] Agent '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config = manager.load_config("agent", code)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    # Track if any changes were made
    changes = []
    
    # Update name
    if name:
        old_name = config.get("metadata", {}).get("name", "")
        config["metadata"]["name"] = name
        changes.append(f"name: {old_name} → {name}")
    
    # Update description
    if description:
        config["metadata"]["description"] = description
        changes.append("description updated")
    
    # Update parameters
    if set_param:
        for param in set_param:
            if "=" not in param:
                console.print(f"[red]✗[/red] Invalid parameter format: {param} (expected key=value)")
                raise typer.Exit(1)
            
            key, value = param.split("=", 1)
            
            # Try to parse as number or boolean
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            else:
                try:
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass  # Keep as string
            
            old_value = config.get("spec", {}).get("parameters", {}).get(key)
            config["spec"]["parameters"][key] = value
            changes.append(f"param {key}: {old_value} → {value}")
    
    if not changes:
        console.print("[yellow]No changes specified[/yellow]")
        return
    
    # Save
    try:
        manager.save_config("agent", code, config)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] Agent '{code}' updated")
    for change in changes:
        console.print(f"   {change}")


@app.command()
def delete(
    code: str = typer.Argument(..., help="Agent code"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
):
    """Delete an agent"""
    manager = ConfigManager()
    
    if not manager.config_exists("agent", code):
        console.print(f"[yellow]Agent '{code}' not found[/yellow]")
        return
    
    # Confirm deletion
    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete agent '{code}'?")
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)
    
    try:
        manager.delete_config("agent", code)
        console.print(f"[green]✓[/green] Agent '{code}' deleted")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete: {e}")
        raise typer.Exit(1)


@app.command()
def validate(
    code: str = typer.Argument(..., help="Agent code"),
):
    """Validate agent configuration"""
    manager = ConfigManager()
    
    if not manager.config_exists("agent", code):
        console.print(f"[red]✗[/red] Agent '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("agent", code)
        config = AgentConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    errors = config.validate()
    
    if errors:
        console.print(f"[red]✗[/red] Validation failed for '{code}':")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]✓[/green] Agent '{code}' is valid")


@app.command()
def test(
    code: str = typer.Argument(..., help="Agent code"),
    workflow: Optional[str] = typer.Option(None, "--workflow", "-w", help="Workflow code"),
    variable: Optional[str] = typer.Option(None, "--variable", "-v", help="Variable code"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Env code"),
    pmg: Optional[str] = typer.Option(None, "--pmg", "-p", help="PMG code"),
):
    """Test agent - preview CLI command without executing"""
    manager = ConfigManager()
    
    if not manager.config_exists("agent", code):
        console.print(f"[red]✗[/red] Agent '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("agent", code)
        config = AgentConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    # Validate first
    errors = config.validate()
    if errors:
        console.print(f"[red]✗[/red] Validation failed:")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    
    # Build command
    cmd = config.build_command(
        prompt_file="/path/to/prompt.md" if not workflow else f"<workflow:{workflow}>",
        work_dir=Path(config.parameters.get("workDir", "./workspace"))
    )
    
    # Display preview
    console.print(Panel(
        f"[bold cyan]Agent:[/bold cyan] {config.metadata.name} ({code})\n"
        f"[bold cyan]Type:[/bold cyan] {config.type}\n"
        f"[bold cyan]Model:[/bold cyan] {config.parameters.get('model', 'default')}",
        title="Agent Info"
    ))
    
    console.print("\n[bold]Generated Command:[/bold]")
    console.print(Syntax(" ".join(cmd), "bash"))
    
    # Show parameters
    console.print("\n[bold]Parameters:[/bold]")
    for key, value in config.parameters.items():
        console.print(f"   {key}: {value}")
    
    # Show defaults if any
    if config.defaults:
        console.print("\n[bold]Default References:[/bold]")
        for key, value in config.defaults.items():
            console.print(f"   {key}: {value}")
