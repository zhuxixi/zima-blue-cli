"""Schedule management commands for daemon-mode cycle configuration."""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from zima.config.manager import ConfigManager
from zima.models.schedule import ScheduleConfig, ScheduleCycleType
from zima.utils import validate_code_with_error

app = typer.Typer(name="schedule", help="Schedule management - daemon cycle configuration")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name"),
    code: Optional[str] = typer.Option(None, "--code", "-c", help="Unique code"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if exists"),
):
    """Create a new Schedule"""
    if example:
        from zima.templates.examples import EXAMPLES

        print(list(EXAMPLES["schedule"].values())[0])
        raise typer.Exit(0)

    if not name or not code:
        console.print("[red]✗[/red] --name and --code are required")
        raise typer.Exit(1)

    is_valid, error = validate_code_with_error(code)
    if not is_valid:
        console.print(f"[red]✗[/red] Invalid code: {error}")
        raise typer.Exit(1)

    manager = ConfigManager()
    if manager.config_exists("schedule", code):
        if force:
            manager.delete_config("schedule", code)
            console.print(f"[yellow]⚠[/yellow] Overwriting existing schedule '{code}'")
        else:
            console.print(f"[red]✗[/red] Schedule '{code}' already exists")
            raise typer.Exit(1)

    config = ScheduleConfig.create(code=code, name=name)
    manager.save_config("schedule", code, config.to_dict())
    console.print(f"[green]✓[/green] Schedule '{code}' created")
    console.print(f"   File: {manager.get_config_path('schedule', code)}")


@app.command("list")
def list_schedules():
    """List all Schedules"""
    manager = ConfigManager()
    configs = manager.list_configs("schedule")

    if not configs:
        console.print("[yellow]No schedules found.[/yellow]")
        return

    table = Table(title="Schedules")
    table.add_column("Code", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Cycles", style="yellow")
    table.add_column("Types", style="blue")

    for data in configs:
        cfg = ScheduleConfig.from_dict(data)
        type_count = len(cfg.cycle_types)
        table.add_row(cfg.metadata.code, cfg.metadata.name, str(cfg.daily_cycles), str(type_count))

    console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="Schedule code"),
):
    """Show Schedule details"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)

    tree = Tree(f"[bold cyan]Schedule: {code}[/bold cyan]")
    meta = tree.add("[bold]Metadata[/bold]")
    meta.add(f"Name: {cfg.metadata.name}")
    if cfg.metadata.description:
        meta.add(f"Description: {cfg.metadata.description}")

    spec = tree.add("[bold]Spec[/bold]")
    spec.add(f"Cycle: {cfg.cycle_minutes} minutes")
    spec.add(f"Daily cycles: {cfg.daily_cycles}")

    stages = tree.add("[bold]Stages[/bold]")
    for s in cfg.stages:
        stages.add(f"{s.name}: +{s.offset_minutes}m ({s.duration_minutes}m)")

    types = tree.add("[bold]Cycle Types[/bold]")
    for ct in cfg.cycle_types:
        types.add(f"{ct.type_id}: work={ct.work}, rest={ct.rest}, dream={ct.dream}")

    mapping = tree.add("[bold]Cycle Mapping (first 16)[/bold]")
    mapping.add(str(cfg.cycle_mapping[:16]))

    console.print(tree)


@app.command()
def update(
    code: str = typer.Argument(..., help="Schedule code"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
):
    """Update Schedule metadata"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)
    if name:
        cfg.metadata.name = name
    if description is not None:
        cfg.metadata.description = description

    manager.save_config("schedule", code, cfg.to_dict())
    console.print(f"[green]✓[/green] Schedule '{code}' updated")


@app.command()
def delete(
    code: str = typer.Argument(..., help="Schedule code"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a Schedule"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    if not force:
        if not typer.confirm(f"Delete schedule '{code}'?"):
            console.print("Cancelled")
            raise typer.Exit(0)

    manager.delete_config("schedule", code)
    console.print(f"[green]✓[/green] Schedule '{code}' deleted")


@app.command()
def validate(
    code: str = typer.Argument(..., help="Schedule code"),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Check PJob refs exist"),
):
    """Validate a Schedule"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)
    errors = cfg.validate(resolve_refs=strict)

    if errors:
        console.print("[red]✗[/red] Validation failed:")
        for e in errors:
            console.print(f"   [red]•[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Schedule '{code}' is valid")


@app.command()
def set_type(
    code: str = typer.Argument(..., help="Schedule code"),
    type_id: str = typer.Option(..., "--typeId", help="Cycle type ID (e.g., A)"),
    stage: str = typer.Option(..., "--stage", help="Stage name: work/rest/dream"),
    pjobs: List[str] = typer.Option(..., "--pjobs", help="PJob codes"),
):
    """Set PJobs for a cycle type and stage"""
    valid_stages = {"work", "rest", "dream"}
    if stage not in valid_stages:
        console.print(f"[red]✗[/red] stage must be one of {valid_stages}")
        raise typer.Exit(1)

    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)

    # Find or create cycle type
    ct = cfg.get_cycle_type(type_id)
    if ct is None:
        ct = ScheduleCycleType(type_id=type_id)
        cfg.cycle_types.append(ct)

    setattr(ct, stage, list(pjobs))
    manager.save_config("schedule", code, cfg.to_dict())
    console.print(f"[green]✓[/green] Set {code}/{type_id}/{stage} = {list(pjobs)}")


@app.command()
def set_mapping(
    code: str = typer.Argument(..., help="Schedule code"),
    index: int = typer.Option(..., "--index", help="Cycle index 0-31"),
    type_id: str = typer.Option(..., "--type", help="Type ID or 'idle'"),
):
    """Set cycle mapping at a specific index"""
    if not (0 <= index <= 31):
        console.print("[red]✗[/red] index must be 0-31")
        raise typer.Exit(1)

    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)

    # Validate type_id against defined cycle types
    if type_id != "idle":
        valid_type_ids = {ct.type_id for ct in cfg.cycle_types}
        if type_id not in valid_type_ids:
            console.print(
                f"[red]✗[/red] Unknown typeId '{type_id}'. Valid: {sorted(valid_type_ids) or '(none defined)'}"
            )
            raise typer.Exit(1)

    cfg.cycle_mapping[index] = type_id
    manager.save_config("schedule", code, cfg.to_dict())
    console.print(f"[green]✓[/green] Set cycleMapping[{index}] = '{type_id}'")
