"""Workflow management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

from zima.config.manager import ConfigManager
from zima.models.workflow import WorkflowConfig, VariableDef, VALID_TEMPLATE_FORMATS
from zima.models.variable import VariableConfig
from zima.utils import validate_code_with_error

app = typer.Typer(name="workflow", help="Workflow management commands")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    code: str = typer.Option(..., "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Template content (or @file to load from file)"),
    format: str = typer.Option("jinja2", "--format", "-f", help="Template format: jinja2/mustache/plain"),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing workflow"),
):
    """Create a new workflow"""
    manager = ConfigManager()
    
    # 1. Validate code format
    is_valid, error = validate_code_with_error(code)
    if not is_valid:
        console.print(f"[red]✗[/red] Invalid code: {error}")
        raise typer.Exit(1)
    
    # 2. Check if code already exists
    if manager.config_exists("workflow", code):
        console.print(f"[red]✗[/red] Workflow with code '{code}' already exists")
        raise typer.Exit(1)
    
    # 3. Validate format
    if format not in VALID_TEMPLATE_FORMATS:
        console.print(f"[red]✗[/red] Invalid format '{format}'. Valid: {VALID_TEMPLATE_FORMATS}")
        raise typer.Exit(1)
    
    # 4. Handle --from (copy existing)
    if from_code:
        if not manager.config_exists("workflow", from_code):
            console.print(f"[red]✗[/red] Source workflow '{from_code}' not found")
            raise typer.Exit(1)
        
        try:
            manager.copy_config("workflow", from_code, code, name)
            console.print(f"[green]✓[/green] Workflow '{code}' created from '{from_code}'")
            console.print(f"   Name: {name}")
            console.print(f"   File: {manager.get_config_path('workflow', code)}")
            return
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to copy: {e}")
            raise typer.Exit(1)
    
    # 5. Load template from file if specified
    template_content = ""
    if template:
        if template.startswith("@"):
            template_file = Path(template[1:])
            if not template_file.exists():
                console.print(f"[red]✗[/red] Template file not found: {template_file}")
                raise typer.Exit(1)
            template_content = template_file.read_text(encoding="utf-8")
        else:
            template_content = template
    
    # 6. Create workflow config
    try:
        config = WorkflowConfig.create(
            code=code,
            name=name,
            template=template_content,
            description=description,
            format=format
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
        manager.save_config("workflow", code, config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    # 9. Output success
    console.print(f"[green]✓[/green] Workflow '{code}' created successfully")
    console.print(f"   Name: {name}")
    console.print(f"   Format: {format}")
    console.print(f"   File: {manager.get_config_path('workflow', code)}")


@app.command()
def list(
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
    output_format: str = typer.Option("table", "--format", help="Output format: table/json"),
):
    """List all workflows"""
    manager = ConfigManager()
    
    # Load all workflows
    configs = manager.list_configs("workflow")
    
    if not configs:
        console.print("[yellow]No workflows found.[/yellow] Create one with: zima workflow create")
        return
    
    # Filter by tag if specified
    if tag:
        configs = [
            c for c in configs 
            if tag in c.get("spec", {}).get("tags", [])
        ]
    
    if not configs:
        console.print(f"[yellow]No workflows found with tag '{tag}'[/yellow]")
        return
    
    if output_format == "json":
        import json
        console.print(json.dumps(configs, indent=2, ensure_ascii=False))
    else:
        # Table format
        table = Table(title="Workflows")
        table.add_column("Code", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Version", style="blue")
        table.add_column("Tags", style="yellow")
        table.add_column("Description", style="dim")
        
        for config in configs:
            metadata = config.get("metadata", {})
            spec = config.get("spec", {})
            
            code = metadata.get("code", "-")
            name = metadata.get("name", "-")
            version = spec.get("version", "-")
            tags = spec.get("tags", [])
            desc = metadata.get("description", "")
            
            # Truncate description
            if len(desc) > 40:
                desc = desc[:37] + "..."
            
            table.add_row(code, name, version, ", ".join(tags) if tags else "-", desc)
        
        console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="Workflow code"),
    output_format: str = typer.Option("yaml", "--format", help="Output format: yaml/json"),
):
    """Show workflow details"""
    manager = ConfigManager()
    
    if not manager.config_exists("workflow", code):
        console.print(f"[red]✗[/red] Workflow '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config = manager.load_config("workflow", code)
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
    code: str = typer.Argument(..., help="Workflow code"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="New template content (or @file)"),
    add_tag: Optional[List[str]] = typer.Option(None, "--add-tag", help="Add tag (can be used multiple times)"),
    remove_tag: Optional[List[str]] = typer.Option(None, "--remove-tag", help="Remove tag (can be used multiple times)"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Update version"),
):
    """Update workflow configuration"""
    manager = ConfigManager()
    
    if not manager.config_exists("workflow", code):
        console.print(f"[red]✗[/red] Workflow '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config = manager.load_config("workflow", code)
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
    
    # Update template
    if template:
        if template.startswith("@"):
            template_file = Path(template[1:])
            if not template_file.exists():
                console.print(f"[red]✗[/red] Template file not found: {template_file}")
                raise typer.Exit(1)
            template_content = template_file.read_text(encoding="utf-8")
        else:
            template_content = template
        config["spec"]["template"] = template_content
        changes.append("template updated")
    
    # Add tags
    if add_tag:
        existing_tags = config.get("spec", {}).get("tags", [])
        for tag in add_tag:
            if tag not in existing_tags:
                existing_tags.append(tag)
        config["spec"]["tags"] = existing_tags
        changes.append(f"added tags: {', '.join(add_tag)}")
    
    # Remove tags
    if remove_tag:
        existing_tags = config.get("spec", {}).get("tags", [])
        for tag in remove_tag:
            if tag in existing_tags:
                existing_tags.remove(tag)
        config["spec"]["tags"] = existing_tags
        changes.append(f"removed tags: {', '.join(remove_tag)}")
    
    # Update version
    if version:
        old_version = config.get("spec", {}).get("version", "")
        config["spec"]["version"] = version
        changes.append(f"version: {old_version} → {version}")
    
    if not changes:
        console.print("[yellow]No changes specified[/yellow]")
        return
    
    # Save
    try:
        manager.save_config("workflow", code, config)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] Workflow '{code}' updated")
    for change in changes:
        console.print(f"   {change}")


@app.command()
def delete(
    code: str = typer.Argument(..., help="Workflow code"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
):
    """Delete a workflow"""
    manager = ConfigManager()
    
    if not manager.config_exists("workflow", code):
        console.print(f"[yellow]Workflow '{code}' not found[/yellow]")
        return
    
    # Confirm deletion
    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete workflow '{code}'?")
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)
    
    try:
        manager.delete_config("workflow", code)
        console.print(f"[green]✓[/green] Workflow '{code}' deleted")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete: {e}")
        raise typer.Exit(1)


@app.command()
def validate(
    code: str = typer.Argument(..., help="Workflow code"),
):
    """Validate workflow configuration"""
    manager = ConfigManager()
    
    if not manager.config_exists("workflow", code):
        console.print(f"[red]✗[/red] Workflow '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("workflow", code)
        config = WorkflowConfig.from_dict(config_data)
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
        console.print(f"[green]✓[/green] Workflow '{code}' is valid")


@app.command()
def render(
    code: str = typer.Argument(..., help="Workflow code"),
    variable: Optional[str] = typer.Option(None, "--variable", "-v", help="Variable config code to use for values"),
    var: Optional[List[str]] = typer.Option(None, "--var", help="Variable value (key=value, can be used multiple times)"),
    output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Output to file instead of console"),
):
    """Render workflow template with variables"""
    manager = ConfigManager()
    
    # Load workflow
    if not manager.config_exists("workflow", code):
        console.print(f"[red]✗[/red] Workflow '{code}' not found")
        raise typer.Exit(1)
    
    try:
        workflow_data = manager.load_config("workflow", code)
        workflow = WorkflowConfig.from_dict(workflow_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load workflow: {e}")
        raise typer.Exit(1)
    
    # Collect variable values
    values = {}
    
    # Load from variable config if specified
    if variable:
        if not manager.config_exists("variable", variable):
            console.print(f"[red]✗[/red] Variable config '{variable}' not found")
            raise typer.Exit(1)
        
        try:
            var_data = manager.load_config("variable", variable)
            var_config = VariableConfig.from_dict(var_data)
            values.update(var_config.values)
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to load variable config: {e}")
            raise typer.Exit(1)
    
    # Parse inline variables
    if var:
        for v in var:
            if "=" not in v:
                console.print(f"[red]✗[/red] Invalid variable format: {v} (expected key=value)")
                raise typer.Exit(1)
            key, value = v.split("=", 1)
            # Try to parse as JSON for complex values
            try:
                import json
                value = json.loads(value)
            except json.JSONDecodeError:
                pass  # Keep as string
            values[key] = value
    
    # Validate variables
    validation_errors = workflow.validate_variables(values)
    if validation_errors:
        console.print(f"[red]✗[/red] Variable validation failed:")
        for error in validation_errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    
    # Render template
    try:
        rendered = workflow.render(values)
    except Exception as e:
        console.print(f"[red]✗[/red] Render failed: {e}")
        raise typer.Exit(1)
    
    # Output
    if output_file:
        Path(output_file).write_text(rendered, encoding="utf-8")
        console.print(f"[green]✓[/green] Rendered output saved to: {output_file}")
    else:
        console.print(Panel(
            Syntax(rendered, "markdown"),
            title=f"Rendered: {code}",
            border_style="green"
        ))


@app.command()
def add_var(
    code: str = typer.Argument(..., help="Workflow code"),
    name: str = typer.Option(..., "--name", "-n", help="Variable name (supports dot notation)"),
    var_type: str = typer.Option("string", "--type", "-t", help="Variable type: string/number/boolean/array/object"),
    required: bool = typer.Option(True, "--required/--optional", help="Whether variable is required"),
    default: Optional[str] = typer.Option(None, "--default", "-d", help="Default value (JSON format)"),
    description: str = typer.Option("", "--description", help="Variable description"),
):
    """Add a variable definition to workflow"""
    manager = ConfigManager()
    
    if not manager.config_exists("workflow", code):
        console.print(f"[red]✗[/red] Workflow '{code}' not found")
        raise typer.Exit(1)
    
    try:
        config_data = manager.load_config("workflow", code)
        workflow = WorkflowConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)
    
    # Parse default value if provided
    default_value = None
    if default:
        try:
            import json
            default_value = json.loads(default)
        except json.JSONDecodeError:
            default_value = default  # Keep as string
    
    # Create variable definition
    var_def = VariableDef(
        name=name,
        type=var_type,
        required=required,
        default=default_value,
        description=description
    )
    
    # Validate variable definition
    errors = var_def.validate()
    if errors:
        console.print("[red]✗[/red] Variable validation failed:")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    
    # Add to workflow
    workflow.add_variable(var_def)
    
    # Save
    try:
        manager.save_config("workflow", code, workflow.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)
    
    console.print(f"[green]✓[/green] Variable '{name}' added to workflow '{code}'")
    console.print(f"   Type: {var_type}")
    console.print(f"   Required: {required}")
    if default_value is not None:
        console.print(f"   Default: {default_value}")
