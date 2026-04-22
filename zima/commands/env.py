"""Environment configuration management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from zima.config.manager import ConfigManager
from zima.models.env import VALID_ENV_FOR_TYPES, EnvConfig
from zima.utils import validate_code_with_error

app = typer.Typer(name="env", help="Environment configuration management commands")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name"),
    for_type: Optional[str] = typer.Option(
        None, "--for-type", "-t", help="Target agent type: kimi/claude/gemini"
    ),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing env config"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if env config already exists"
    ),
):
    """Create a new environment configuration"""
    if example:
        from zima.templates.examples import EXAMPLES

        print(list(EXAMPLES["env"].values())[0])
        raise typer.Exit(0)

    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)
    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)
    if not for_type:
        console.print("[red]✗[/red] --for-type is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # 1. Validate code format
    is_valid, error = validate_code_with_error(code)
    if not is_valid:
        console.print(f"[red]✗[/red] Invalid code: {error}")
        raise typer.Exit(1)

    # 2. Check if code already exists
    if manager.config_exists("env", code):
        if force:
            try:
                manager.delete_config("env", code)
                console.print(f"[yellow]⚠[/yellow] Overwriting existing env config '{code}'")
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to overwrite: {e}")
                raise typer.Exit(1)
        else:
            console.print(f"[red]✗[/red] Env config with code '{code}' already exists")
            console.print(
                f"   Use [bold]--force[/bold] to overwrite, or [bold]zima env update {code}[/bold] to modify"
            )
            raise typer.Exit(1)

    # 3. Validate for_type
    if for_type not in VALID_ENV_FOR_TYPES:
        console.print(f"[red]✗[/red] Invalid type '{for_type}'. Valid: {VALID_ENV_FOR_TYPES}")
        raise typer.Exit(1)

    # 4. Handle --from (copy existing)
    if from_code:
        if not manager.config_exists("env", from_code):
            console.print(f"[red]✗[/red] Source env config '{from_code}' not found")
            raise typer.Exit(1)

        try:
            manager.copy_config("env", from_code, code, name)
            console.print(f"[green]✓[/green] Env config '{code}' created from '{from_code}'")
            console.print(f"   Name: {name}")
            console.print(f"   Type: {for_type}")
            console.print(f"   File: {manager.get_config_path('env', code)}")
            return
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to copy: {e}")
            raise typer.Exit(1)

    # 5. Create env config
    try:
        config = EnvConfig.create(code=code, name=name, for_type=for_type, description=description)
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
        manager.save_config("env", code, config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    # 8. Output success
    console.print(f"[green]✓[/green] Env config '{code}' created successfully")
    console.print(f"   Name: {name}")
    console.print(f"   Type: {for_type}")
    console.print(f"   File: {manager.get_config_path('env', code)}")


@app.command()
def list(
    for_type: Optional[str] = typer.Option(None, "--for-type", "-t", help="Filter by agent type"),
    output_format: str = typer.Option("table", "--format", help="Output format: table/json"),
):
    """List all environment configurations"""
    manager = ConfigManager()

    # Load all env configs
    configs = manager.list_configs("env")

    if not configs:
        console.print("[yellow]No env configs found.[/yellow] Create one with: zima env create")
        return

    # Filter by type if specified
    if for_type:
        configs = [c for c in configs if c.get("spec", {}).get("forType") == for_type]

    if not configs:
        console.print(f"[yellow]No env configs found with type '{for_type}'[/yellow]")
        return

    if output_format == "json":
        import json

        # Mask secrets in JSON output
        for config in configs:
            spec = config.get("spec", {})
            secrets = spec.get("secrets", [])
            for secret in secrets:
                secret["value"] = f"<secret:{secret.get('source', 'unknown')}>"
        console.print(json.dumps(configs, indent=2, ensure_ascii=False))
    else:
        # Table format
        table = Table(title="Environment Configurations")
        table.add_column("Code", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Vars", style="blue", justify="right")
        table.add_column("Secrets", style="magenta", justify="right")
        table.add_column("Description", style="dim")

        for config in configs:
            metadata = config.get("metadata", {})
            spec = config.get("spec", {})

            code = metadata.get("code", "-")
            name = metadata.get("name", "-")
            agent_type = spec.get("forType", "-")
            var_count = len(spec.get("variables", {}))
            secret_count = len(spec.get("secrets", []))
            desc = metadata.get("description", "")

            # Truncate description
            if len(desc) > 40:
                desc = desc[:37] + "..."

            table.add_row(code, name, agent_type, str(var_count), str(secret_count), desc)

        console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="Env config code"),
    output_format: str = typer.Option("yaml", "--format", help="Output format: yaml/json"),
    resolve_secrets: bool = typer.Option(
        False, "--resolve-secrets", help="Resolve and show secret values (use with caution)"
    ),
):
    """Show environment configuration details"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[red]✗[/red] Env config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("env", code)

        # Mask secrets if not resolving
        if not resolve_secrets and output_format == "yaml":
            spec = config_data.get("spec", {})
            secrets = spec.get("secrets", [])
            for secret in secrets:
                # Add masked value for display (won't be saved)
                secret["_display"] = f"<secret:{secret.get('source', 'unknown')}>"

    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    if output_format == "json":
        import json

        # Always mask secrets in JSON unless explicitly resolved
        if not resolve_secrets:
            spec = config_data.get("spec", {})
            secrets = spec.get("secrets", [])
            for secret in secrets:
                secret["value"] = f"<secret:{secret.get('source', 'unknown')}>"
        console.print(json.dumps(config_data, indent=2, ensure_ascii=False))
    else:
        # YAML format with syntax highlighting
        import yaml

        yaml_content = yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True)
        console.print(Syntax(yaml_content, "yaml"))


@app.command()
def update(
    code: str = typer.Argument(..., help="Env config code"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    override_existing: Optional[bool] = typer.Option(
        None, "--override-existing", help="Update override existing setting"
    ),
):
    """Update environment configuration"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[red]✗[/red] Env config '{code}' not found")
        raise typer.Exit(1)

    try:
        config = manager.load_config("env", code)
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

    # Update override_existing
    if override_existing is not None:
        old_val = config.get("spec", {}).get("overrideExisting", False)
        config["spec"]["overrideExisting"] = override_existing
        changes.append(f"overrideExisting: {old_val} → {override_existing}")

    if not changes:
        console.print("[yellow]No changes specified[/yellow]")
        return

    # Save
    try:
        manager.save_config("env", code, config)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Env config '{code}' updated")
    for change in changes:
        console.print(f"   {change}")


@app.command()
def delete(
    code: str = typer.Argument(..., help="Env config code"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
):
    """Delete an environment configuration"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[yellow]Env config '{code}' not found[/yellow]")
        return

    # Confirm deletion
    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete env config '{code}'?")
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)

    try:
        manager.delete_config("env", code)
        console.print(f"[green]✓[/green] Env config '{code}' deleted")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete: {e}")
        raise typer.Exit(1)


@app.command()
def validate(
    code: str = typer.Argument(..., help="Env config code"),
):
    """Validate environment configuration"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[red]✗[/red] Env config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("env", code)
        env_config = EnvConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    errors = env_config.validate()

    if errors:
        console.print(f"[red]✗[/red] Validation failed for '{code}':")
        for error in errors:
            console.print(f"   - {error}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]✓[/green] Env config '{code}' is valid")


@app.command()
def set(
    code: str = typer.Argument(..., help="Env config code"),
    key: str = typer.Option(..., "--key", "-k", help="Variable name"),
    value: Optional[str] = typer.Option(
        None, "--value", "-v", help="Variable value (not needed for secrets)"
    ),
    secret: bool = typer.Option(
        False, "--secret", "-s", help="Store as secret (don't save value directly)"
    ),
    source: str = typer.Option("env", "--source", help="Secret source: env/file/cmd"),
    source_key: Optional[str] = typer.Option(
        None, "--source-key", help="Source key (for env source)"
    ),
    source_path: Optional[str] = typer.Option(
        None, "--source-path", help="Source path (for file source)"
    ),
    source_cmd: Optional[str] = typer.Option(
        None, "--source-cmd", help="Source command (for cmd source)"
    ),
):
    """Set an environment variable"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[red]✗[/red] Env config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("env", code)
        env_config = EnvConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    try:
        if secret:
            # Validate source
            if source not in ("env", "file", "cmd"):
                console.print(f"[red]✗[/red] Invalid source '{source}'. Valid: env, file, cmd")
                raise typer.Exit(1)

            # For env source, use value as the source key if not specified
            if source == "env":
                if not source_key and not value:
                    console.print("[red]✗[/red] --source-key or --value is required for env source")
                    raise typer.Exit(1)
                if not source_key:
                    source_key = value

            if source == "file" and not source_path:
                console.print("[red]✗[/red] --source-path is required for file source")
                raise typer.Exit(1)

            if source == "cmd" and not source_cmd:
                console.print("[red]✗[/red] --source-cmd is required for cmd source")
                raise typer.Exit(1)

            env_config.set_secret(
                name=key, source=source, key=source_key, path=source_path, command=source_cmd
            )
            console.print(f"[green]✓[/green] Secret '{key}' set in '{code}'")
            console.print(f"   Source: {source}")
        else:
            # Set plain variable - value is required
            if value is None:
                console.print("[red]✗[/red] --value is required for plain variables")
                raise typer.Exit(1)

            env_config.set_variable(key, value)
            console.print(f"[green]✓[/green] Variable '{key}' set in '{code}'")
            console.print(f"   Value: {value}")
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)

    # Save
    try:
        manager.save_config("env", code, env_config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)


@app.command()
def unset(
    code: str = typer.Argument(..., help="Env config code"),
    key: str = typer.Option(..., "--key", "-k", help="Variable name to remove"),
):
    """Remove an environment variable"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[red]✗[/red] Env config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("env", code)
        env_config = EnvConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    # Try to remove from variables first
    removed = env_config.unset_variable(key)

    # If not found, try secrets
    if not removed:
        removed = env_config.unset_secret(key)

    if not removed:
        console.print(f"[yellow]Variable '{key}' not found in '{code}'[/yellow]")
        return

    # Save
    try:
        manager.save_config("env", code, env_config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Variable '{key}' removed from '{code}'")


@app.command()
def get(
    code: str = typer.Argument(..., help="Env config code"),
    key: str = typer.Option(..., "--key", "-k", help="Variable name"),
    resolve: bool = typer.Option(False, "--resolve", help="Resolve secret value"),
):
    """Get an environment variable value"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[red]✗[/red] Env config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("env", code)
        env_config = EnvConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    # Try plain variable first
    value = env_config.get_variable(key)
    if value is not None:
        console.print(value)
        return

    # Try secret
    secret = env_config.get_secret(key)
    if secret:
        if resolve:
            try:
                from zima.models.env import SecretResolver

                value = SecretResolver.resolve(secret)
                console.print(value)
            except ValueError as e:
                console.print(f"[red]✗[/red] Failed to resolve secret: {e}")
                raise typer.Exit(1)
        else:
            console.print(secret.get_masked_value())
        return

    console.print(f"[yellow]Variable '{key}' not found in '{code}'[/yellow]")
    raise typer.Exit(1)


@app.command()
def export(
    code: str = typer.Argument(..., help="Env config code"),
    format: str = typer.Option("dotenv", "--format", "-f", help="Export format: dotenv/shell/json"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    resolve_secrets: bool = typer.Option(
        False, "--resolve-secrets", help="Resolve secret values (use with caution)"
    ),
):
    """Export environment configuration"""
    manager = ConfigManager()

    if not manager.config_exists("env", code):
        console.print(f"[red]✗[/red] Env config '{code}' not found")
        raise typer.Exit(1)

    try:
        config_data = manager.load_config("env", code)
        env_config = EnvConfig.from_dict(config_data)
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load: {e}")
        raise typer.Exit(1)

    # Generate export content
    if format == "dotenv":
        content = env_config.export_dotenv(resolve_secrets=resolve_secrets)
    elif format == "shell":
        content = env_config.export_shell(resolve_secrets=resolve_secrets)
    elif format == "json":
        content = env_config.export_json(resolve_secrets=resolve_secrets)
    else:
        console.print(f"[red]✗[/red] Invalid format '{format}'. Valid: dotenv, shell, json")
        raise typer.Exit(1)

    # Output
    if output:
        Path(output).write_text(content, encoding="utf-8")
        console.print(f"[green]✓[/green] Exported to: {output}")
    else:
        console.print(content)
