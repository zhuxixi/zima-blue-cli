"""PMG (Parameters Group) management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from zima.config.manager import ConfigManager
from zima.models.pmg import PMGConfig, ParameterDef, VALID_PMG_FOR_TYPES, VALID_PARAM_TYPES
from zima.utils import validate_code_with_error

app = typer.Typer(name="pmg", help="PMG (Parameters Group) management commands")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    code: str = typer.Option(..., "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    for_types: List[str] = typer.Option(..., "--for-type", "-t", help="Target agent types (can specify multiple)"),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing PMG"),
):
    """Create a new parameters group"""
    manager = ConfigManager()
    
    # 1. Validate code format
    is_valid, error = validate_code_with_error(code)
    if not is_valid:
        console.print(f"[red]✗[/red] Invalid code: {error}")
        raise typer.Exit(1)
    
    # 2. Check if code already exists
    if manager.config_exists("pmg", code):
        console.print(f"[red]✗[/red] PMG with code '{code}' already exists")
        raise typer.Exit(1)
    
    # 3. Validate for_types
    for ft in for_types:
        if ft not in VALID_PMG_FOR_TYPES:
            console.print(f"[red]✗[/red] Invalid type '{ft}'. Valid: {VALID_PMG_FOR_TYPES}")
            raise typer.Exit(1)
    
    # 4. Handle --from (copy existing)
    if from_code:
        if not manager.config_exists("pmg", from_code):
            console.print(f"[red]✗[/red] Source PMG '{from_code}' not found")
            raise typer.Exit(1)
        
        try:
            manager.copy_config("pmg", from_code, code, name)
            console.print(f"[green]✓[/green] PMG '{code}' created from '{from_code}'")
            console.print(f"   Name: {name}")
            console.print(f"   Types: {', '.join(for_types)}")
            console.print(f"   File: {manager.get_config_path('pmg', code)}")
            return
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to copy: {e}")
            raise typer.Exit(1)
    
    # 5. Create PMG config
    try:
        config = PMGConfig.create(
            code=code,
            name=name,
            for_types=for_types,
            description=description
        )
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    
    # 6. Validate
    errors = config.validate()
    if errors:
        console.print("[red]✗[/red] Validation failed:")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    
    # 7. Save
    try:
        manager.save_config("pmg", code, config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    # 8. Output success
    console.print(f"[green]✓[/green] PMG '{code}' created successfully")
    console.print(f"   Name: {name}")
    console.print(f"   Types: {', '.join(for_types)}")
    console.print(f"   File: {manager.get_config_path('pmg', code)}")


@app.command()
def list(
    for_type: Optional[str] = typer.Option(None, "--for-type", "-t", help="Filter by agent type"),
    output_format: str = typer.Option("table", "--format", help="Output format: table/json"),
):
    """List all parameters groups"""
    manager = ConfigManager()
    
    # Load all PMGs
    configs = manager.list_configs("pmg")
    
    if not configs:
        console.print("[yellow]No PMGs found.[/yellow] Create one with: zima pmg create")
        return
    
    # Filter by type if specified
    if for_type:
        configs = [
            c for c in configs 
            if for_type in c.get("spec", {}).get("forTypes", [])
        ]
    
    if not configs:
        console.print(f"[yellow]No PMGs found for type '{for_type}'[/yellow]")
        return
    
    if output_format == "json":
        import json
        console.print(json.dumps(config, indent=2, ensure_ascii=False))
    else:
        # Table format
        table = Table(title="Parameters Groups")
        table.add_column("Code", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Types", style="yellow")
        table.add_column("Params", style="blue", justify="right")
        table.add_column("Description", style="dim")
        
        for config in configs:
            metadata = config.get("metadata", {})
            spec = config.get("spec", {})
            
            code = metadata.get("code", "-")
            name = metadata.get("name", "-")
            types = ", ".join(spec.get("forTypes", []))
            param_count = len(spec.get("parameters", []))
            desc = metadata.get("description", "")
            
            # Truncate description
            if len(desc) > 40:
                desc = desc[:37] + "..."
            
            table.add_row(code, name, types, str(param_count), desc)
        
        console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="PMG code"),
    output_format: str = typer.Option("yaml", "--format", help="Output format: yaml/json"),
):
    """Show PMG details"""
    manager = ConfigManager()
    
    if not manager.config_exists("pmg", code):
        console.print(f"[red]✗[/red] PMG '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config = manager.load_config("pmg", code)
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
    code: str = typer.Argument(..., help="PMG code"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    raw: Optional[str] = typer.Option(None, "--raw", help="Update raw parameter string"),
):
    """Update PMG configuration"""
    manager = ConfigManager()
    
    if not manager.config_exists("pmg", code):
        console.print(f"[red]✗[/red] PMG '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config = manager.load_config("pmg", code)
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
    
    # Update raw
    if raw is not None:
        old_raw = config.get("spec", {}).get("raw", "")
        config["spec"]["raw"] = raw
        changes.append(f"raw: '{old_raw}' → '{raw}'")
    
    if not changes:
        console.print("[yellow]No changes specified[/yellow]")
        return
    
    # Save
    try:
        manager.save_config("pmg", code, config)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] PMG '{code}' updated")
    for change in changes:
        console.print(f"   {change}")


@app.command()
def delete(
    code: str = typer.Argument(..., help="PMG code"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
):
    """Delete a parameters group"""
    manager = ConfigManager()
    
    if not manager.config_exists("pmg", code):
        console.print(f"[yellow]PMG '{code}' not found[/yellow]")
        return
    
    # Confirm deletion
    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete PMG '{code}'?")
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)
    
    try:
        manager.delete_config("pmg", code)
        console.print(f"[green]✓[/green] PMG '{code}' deleted")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete: {e}")
        raise typer.Exit(1)


@app.command()
def validate(
    code: str = typer.Argument(..., help="PMG code"),
):
    """Validate PMG configuration"""
    manager = ConfigManager()
    
    if not manager.config_exists("pmg", code):
        console.print(f"[red]✗[/red] PMG '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("pmg", code)
        pmg_config = PMGConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    errors = pmg_config.validate()
    
    if errors:
        console.print(f"[red]✗[/red] Validation failed for '{code}':")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]✓[/green] PMG '{code}' is valid")


@app.command()
def add_param(
    code: str = typer.Argument(..., help="PMG code"),
    name: str = typer.Option(..., "--name", help="Parameter name"),
    param_type: str = typer.Option(..., "--type", help=f"Parameter type: {VALID_PARAM_TYPES}"),
    value: Optional[str] = typer.Option(None, "--value", help="Parameter value"),
    values: Optional[str] = typer.Option(None, "--values", help="Multiple values (comma-separated, for repeatable type)"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Whether flag is enabled (for flag type)"),
):
    """Add a parameter to PMG"""
    manager = ConfigManager()
    
    if not manager.config_exists("pmg", code):
        console.print(f"[red]✗[/red] PMG '{code}' not found")
        raise typer.Exit(1)
    
    # Validate type
    if param_type not in VALID_PARAM_TYPES:
        console.print(f"[red]✗[/red] Invalid type '{param_type}'. Valid: {VALID_PARAM_TYPES}")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("pmg", code)
        pmg_config = PMGConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    # Build parameter value
    param_value = None
    param_values = []
    
    if param_type == "flag":
        # Flag uses enabled, not value
        pass
    elif param_type == "repeatable":
        if not values:
            console.print(f"[red]✗[/red] --values is required for repeatable type")
            raise typer.Exit(1)
        param_values = [v.strip() for v in values.split(",")]
    elif param_type == "json":
        if value:
            try:
                import json
                param_value = json.loads(value)
            except json.JSONDecodeError:
                param_value = value
        else:
            console.print(f"[red]✗[/red] --value is required for {param_type} type")
            raise typer.Exit(1)
    elif param_type == "key-value":
        if value:
            # Parse key=value pairs
            kv = {}
            for pair in value.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    kv[k.strip()] = v.strip()
            param_value = kv
        else:
            console.print(f"[red]✗[/red] --value is required for {param_type} type")
            raise typer.Exit(1)
    else:
        # long, short, positional
        if value is None:
            console.print(f"[red]✗[/red] --value is required for {param_type} type")
            raise typer.Exit(1)
        # Try to parse as boolean
        if value.lower() == "true":
            param_value = True
        elif value.lower() == "false":
            param_value = False
        else:
            param_value = value
    
    # Create parameter
    try:
        param = ParameterDef(
            name=name,
            type=param_type,
            value=param_value,
            values=param_values,
            enabled=enabled
        )
        
        # Validate
        errors = param.validate()
        if errors:
            console.print("[red]✗[/red] Parameter validation failed:")
            for error in errors:
                console.print(f"   - {error}")
            raise typer.Exit(1)
        
        # Add to PMG
        pmg_config.add_parameter(param)
        
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)
    
    # Save
    try:
        manager.save_config("pmg", code, pmg_config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] Parameter '{name}' added to PMG '{code}'")


@app.command()
def remove_param(
    code: str = typer.Argument(..., help="PMG code"),
    name: str = typer.Option(..., "--name", help="Parameter name to remove"),
):
    """Remove a parameter from PMG"""
    manager = ConfigManager()
    
    if not manager.config_exists("pmg", code):
        console.print(f"[red]✗[/red] PMG '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("pmg", code)
        pmg_config = PMGConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    removed = pmg_config.remove_parameter(name)
    
    if not removed:
        console.print(f"[yellow]Parameter '{name}' not found in PMG '{code}'[/yellow]")
        return
    
    # Save
    try:
        manager.save_config("pmg", code, pmg_config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] Parameter '{name}' removed from PMG '{code}'")


@app.command()
def build(
    code: str = typer.Argument(..., help="PMG code"),
    output_format: str = typer.Option("list", "--format", "-f", help="Output format: list/shell"),
    eval_conditions: bool = typer.Option(True, "--eval-conditions/--no-eval-conditions", help="Evaluate conditions"),
):
    """Build command-line arguments from PMG"""
    manager = ConfigManager()
    
    if not manager.config_exists("pmg", code):
        console.print(f"[red]✗[/red] PMG '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("pmg", code)
        pmg_config = PMGConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    # Build command
    args = pmg_config.build_command(eval_conditions=eval_conditions)
    
    if output_format == "shell":
        console.print(" ".join(args))
    else:
        # list format
        import json
        console.print(json.dumps(args))
