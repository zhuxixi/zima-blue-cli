"""Variable management commands."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from zima.config.manager import ConfigManager
from zima.models.variable import VariableConfig
from zima.models.workflow import WorkflowConfig
from zima.utils import validate_code_with_error

app = typer.Typer(name="variable", help="Variable management commands")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name"),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    for_workflow: Optional[str] = typer.Option(
        None, "--for-workflow", "-w", help="Target workflow code"
    ),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(
        None, "--from", help="Copy from existing variable config"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if variable config already exists"
    ),
):
    """Create a new variable configuration"""
    if example:
        from zima.templates.examples import EXAMPLES

        print(list(EXAMPLES["variable"].values())[0])
        raise typer.Exit(0)

    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)
    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # 1. Validate code format
    is_valid, error = validate_code_with_error(code)
    if not is_valid:
        console.print(f"[red]✗[/red] Invalid code: {error}")
        raise typer.Exit(1)

    # 2. Check if code already exists
    if manager.config_exists("variable", code):
        if force:
            try:
                manager.delete_config("variable", code)
                console.print(f"[yellow]⚠[/yellow] Overwriting existing variable config '{code}'")
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to overwrite: {e}")
                raise typer.Exit(1)
        else:
            console.print(f"[red]✗[/red] Variable config with code '{code}' already exists")
            console.print(
                f"   Use [bold]--force[/bold] to overwrite, or [bold]zima variable update {code}[/bold] to modify"
            )
            raise typer.Exit(1)

    # 3. Validate target workflow if specified
    if for_workflow and not manager.config_exists("workflow", for_workflow):
        console.print(f"[red]✗[/red] Target workflow '{for_workflow}' not found")
        raise typer.Exit(1)

    # 4. Handle --from (copy existing)
    if from_code:
        if not manager.config_exists("variable", from_code):
            console.print(f"[red]✗[/red] Source variable config '{from_code}' not found")
            raise typer.Exit(1)

        try:
            manager.copy_config("variable", from_code, code, name)
            console.print(f"[green]✓[/green] Variable config '{code}' created from '{from_code}'")
            console.print(f"   Name: {name}")
            console.print(f"   File: {manager.get_config_path('variable', code)}")
            return
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to copy: {e}")
            raise typer.Exit(1)

    # 5. Create variable config
    config = VariableConfig.create(
        code=code, name=name, for_workflow=for_workflow or "", description=description
    )

    # 6. Validate
    errors = config.validate()
    if errors:
        console.print("[red]✗[/red] Validation failed:")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)

    # 7. Save
    try:
        manager.save_config("variable", code, config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    # 8. Output success
    console.print(f"[green]✓[/green] Variable config '{code}' created successfully")
    console.print(f"   Name: {name}")
    if for_workflow:
        console.print(f"   For Workflow: {for_workflow}")
    console.print(f"   File: {manager.get_config_path('variable', code)}")


@app.command()
def list(
    for_workflow: Optional[str] = typer.Option(
        None, "--for-workflow", "-w", help="Filter by workflow code"
    ),
    output_format: str = typer.Option("table", "--format", help="Output format: table/json"),
):
    """List all variable configurations"""
    manager = ConfigManager()

    # Load all variable configs
    configs = manager.list_configs("variable")

    if not configs:
        console.print(
            "[yellow]No variable configs found.[/yellow] Create one with: zima variable create"
        )
        return

    # Filter by workflow if specified
    if for_workflow:
        configs = [c for c in configs if c.get("spec", {}).get("forWorkflow") == for_workflow]

    if not configs:
        console.print(f"[yellow]No variable configs found for workflow '{for_workflow}'[/yellow]")
        return

    if output_format == "json":
        import json

        console.print(json.dumps(configs, indent=2, ensure_ascii=False))
    else:
        # Table format
        table = Table(title="Variable Configurations")
        table.add_column("Code", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("For Workflow", style="blue")
        table.add_column("Description", style="dim")

        for config in configs:
            metadata = config.get("metadata", {})
            spec = config.get("spec", {})

            code = metadata.get("code", "-")
            name = metadata.get("name", "-")
            wf = spec.get("forWorkflow", "-") or "-"
            desc = metadata.get("description", "")

            # Truncate description
            if len(desc) > 40:
                desc = desc[:37] + "..."

            table.add_row(code, name, wf, desc)

        console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="Variable config code"),
    output_format: str = typer.Option("yaml", "--format", help="Output format: yaml/json"),
):
    """Show variable configuration details"""
    manager = ConfigManager()

    if not manager.config_exists("variable", code):
        console.print(f"[red]✗[/red] Variable config '{code}' not found")
        raise typer.Exit(1)

    try:
        config = manager.load_config("variable", code)
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
    code: str = typer.Argument(..., help="Variable config code"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    for_workflow: Optional[str] = typer.Option(
        None, "--for-workflow", "-w", help="Target workflow code"
    ),
):
    """Update variable configuration"""
    manager = ConfigManager()

    if not manager.config_exists("variable", code):
        console.print(f"[red]✗[/red] Variable config '{code}' not found")
        raise typer.Exit(1)

    try:
        config = manager.load_config("variable", code)
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

    # Update target workflow
    if for_workflow is not None:
        # Validate target workflow if not empty
        if for_workflow and not manager.config_exists("workflow", for_workflow):
            console.print(f"[red]✗[/red] Target workflow '{for_workflow}' not found")
            raise typer.Exit(1)

        old_wf = config.get("spec", {}).get("forWorkflow", "")
        config["spec"]["forWorkflow"] = for_workflow
        changes.append(f"forWorkflow: {old_wf or '-'} → {for_workflow or '-'}")

    if not changes:
        console.print("[yellow]No changes specified[/yellow]")
        return

    # Save
    try:
        manager.save_config("variable", code, config)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Variable config '{code}' updated")
    for change in changes:
        console.print(f"   {change}")


@app.command()
def delete(
    code: str = typer.Argument(..., help="Variable config code"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
):
    """Delete a variable configuration"""
    manager = ConfigManager()

    if not manager.config_exists("variable", code):
        console.print(f"[yellow]Variable config '{code}' not found[/yellow]")
        return

    # Confirm deletion
    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete variable config '{code}'?")
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)

    try:
        manager.delete_config("variable", code)
        console.print(f"[green]✓[/green] Variable config '{code}' deleted")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete: {e}")
        raise typer.Exit(1)


@app.command()
def set(
    code: str = typer.Argument(..., help="Variable config code"),
    key: str = typer.Option(
        ..., "--key", "-k", help="Variable key (dot notation supported, e.g., 'task.name')"
    ),
    value: str = typer.Option(
        ..., "--value", "-v", help="Variable value (JSON format for complex values)"
    ),
):
    """Set a variable value"""
    manager = ConfigManager()

    if not manager.config_exists("variable", code):
        console.print(f"[red]✗[/red] Variable config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("variable", code)
        config = VariableConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    # Try to parse value as JSON
    try:
        import json

        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value  # Keep as string

    # Set value
    old_value = config.get_value(key)
    config.set_value(key, parsed_value)

    # Save
    try:
        manager.save_config("variable", code, config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Variable '{key}' set in '{code}'")
    console.print(f"   {old_value} → {parsed_value}")


@app.command()
def get(
    code: str = typer.Argument(..., help="Variable config code"),
    key: str = typer.Argument(..., help="Variable key (dot notation supported)"),
):
    """Get a variable value"""
    manager = ConfigManager()

    if not manager.config_exists("variable", code):
        console.print(f"[red]✗[/red] Variable config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("variable", code)
        config = VariableConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    value = config.get_value(key)

    if value is None:
        console.print(f"[yellow]Variable '{key}' not found in '{code}'[/yellow]")
        raise typer.Exit(1)

    # Output based on type
    value_type = type(value)
    if value_type is dict or value_type is list:
        import json

        console.print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        console.print(value)


@app.command()
def validate(
    code: str = typer.Argument(..., help="Variable config code"),
    check_workflow: bool = typer.Option(
        False, "--check-workflow", help="Validate against target workflow"
    ),
):
    """Validate variable configuration"""
    manager = ConfigManager()

    if not manager.config_exists("variable", code):
        console.print(f"[red]✗[/red] Variable config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("variable", code)
        config = VariableConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    errors = config.validate()

    # Validate against workflow if requested
    if check_workflow and config.for_workflow:
        if not manager.config_exists("workflow", config.for_workflow):
            errors.append(f"Target workflow '{config.for_workflow}' not found")
        else:
            try:
                wf_data = manager.load_config("workflow", config.for_workflow)
                workflow = WorkflowConfig.from_dict(wf_data)

                # Check if variable paths match workflow requirements
                var_paths = config.list_paths()
                wf_vars = workflow.get_variable_names()

                for wf_var in wf_vars:
                    if wf_var not in var_paths:
                        wf_var_def = next((v for v in workflow.variables if v.name == wf_var), None)
                        if wf_var_def and wf_var_def.required:
                            errors.append(f"Required variable '{wf_var}' not provided")
            except Exception as e:
                errors.append(f"Failed to validate against workflow: {e}")

    if errors:
        console.print(f"[red]✗[/red] Validation failed for '{code}':")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]✓[/green] Variable config '{code}' is valid")


@app.command()
def merge(
    code: str = typer.Argument(..., help="Variable config code"),
    source: str = typer.Option(..., "--from", help="Source variable config to merge from"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing values"),
):
    """Merge values from another variable configuration"""
    manager = ConfigManager()

    # Load target
    if not manager.config_exists("variable", code):
        console.print(f"[red]✗[/red] Target variable config '{code}' not found")
        raise typer.Exit(1)

    # Load source
    if not manager.config_exists("variable", source):
        console.print(f"[red]✗[/red] Source variable config '{source}' not found")
        raise typer.Exit(1)

    try:
        target_data = manager.load_config("variable", code)
        target = VariableConfig.from_dict(target_data)

        source_data = manager.load_config("variable", source)
        src = VariableConfig.from_dict(source_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    # Merge values
    if overwrite:
        target.merge_values(src.values)
    else:
        # Only add new keys, preserve existing
        for key, value in src.values.items():
            if key not in target.values:
                target.values[key] = value

    # Save
    try:
        manager.save_config("variable", code, target.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    console.print(f"[green]OK[/green] Merged values from '{source}' into '{code}'")
