"""PJob management commands - execution layer for Agent tasks."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from zima.config.manager import ConfigManager
from zima.execution.executor import PJobExecutor
from zima.execution.history import ExecutionHistory
from zima.models.pjob import Overrides, PJobConfig
from zima.utils import get_zima_home, validate_code_with_error

app = typer.Typer(name="pjob", help="PJob management - execute Agent tasks")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name"),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent code"),
    workflow: Optional[str] = typer.Option(None, "--workflow", "-w", help="Workflow code"),
    variable: Optional[str] = typer.Option(None, "--variable", "-v", help="Variable code"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Env code"),
    pmg: Optional[str] = typer.Option(None, "--pmg", "-p", help="PMG code"),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    label: Optional[List[str]] = typer.Option(
        None, "--label", "-l", help="Labels (can be used multiple times)"
    ),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", help="Working directory"),
    timeout: int = typer.Option(0, "--timeout", "-t", help="Timeout in seconds (0 = no timeout)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output save path"),
    from_code: Optional[str] = typer.Option(None, "--from-code", help="Copy from existing pjob"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if PJob already exists"
    ),
):
    """Create a new PJob"""
    if example:
        from zima.templates.examples import EXAMPLES

        print(next(iter(EXAMPLES["pjob"].values())))
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
    if manager.config_exists("pjob", code):
        if force:
            try:
                manager.delete_config("pjob", code)
                console.print(f"[yellow]⚠[/yellow] Overwriting existing PJob '{code}'")
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to overwrite: {e}")
                raise typer.Exit(1)
        else:
            console.print(f"[red]✗[/red] PJob with code '{code}' already exists")
            console.print(
                f"   Use [bold]--force[/bold] to overwrite, or [bold]zima pjob update {code}[/bold] to modify"
            )
            raise typer.Exit(1)

    # 3. Validate agent and workflow are provided (unless copying)
    if not from_code:
        if not agent:
            console.print("[red]✗[/red] --agent is required (unless using --from-code)")
            raise typer.Exit(1)
        if not workflow:
            console.print("[red]✗[/red] --workflow is required (unless using --from-code)")
            raise typer.Exit(1)

    # 4. Handle --from (copy existing)
    if from_code:
        if not manager.config_exists("pjob", from_code):
            console.print(f"[red]✗[/red] Source pjob '{from_code}' not found")
            raise typer.Exit(1)

        try:
            source_data = manager.load_config("pjob", from_code)
            source_data["metadata"]["code"] = code
            source_data["metadata"]["name"] = name
            if description:
                source_data["metadata"]["description"] = description

            # Override refs if specified
            if agent:
                source_data["spec"]["agent"] = agent
            if workflow:
                source_data["spec"]["workflow"] = workflow
            if variable:
                source_data["spec"]["variable"] = variable
            if env:
                source_data["spec"]["env"] = env
            if pmg:
                source_data["spec"]["pmg"] = pmg

            manager.save_config("pjob", code, source_data)
            console.print(f"[green]✓[/green] PJob '{code}' created from '{from_code}'")
            console.print(f"   Name: {name}")
            console.print(f"   File: {manager.get_config_path('pjob', code)}")
            return
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to copy: {e}")
            raise typer.Exit(1)

    # 4. Validate required refs exist
    if not manager.config_exists("agent", agent):
        console.print(f"[red]✗[/red] Agent '{agent}' not found")
        raise typer.Exit(1)
    if not manager.config_exists("workflow", workflow):
        console.print(f"[red]✗[/red] Workflow '{workflow}' not found")
        raise typer.Exit(1)

    # 5. Build execution options
    exec_options = {}
    if work_dir:
        exec_options["workDir"] = work_dir
    if timeout != 0:
        exec_options["timeout"] = timeout

    output_options = {}
    if output:
        output_options["saveTo"] = output

    # 6. Create PJob config
    try:
        config = PJobConfig.create(
            code=code,
            name=name,
            agent=agent,
            workflow=workflow,
            description=description,
            variable=variable or "",
            env=env or "",
            pmg=pmg or "",
            labels=list(label) if label else [],
            execution=exec_options if exec_options else None,
            output=output_options if output_options else None,
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
        manager.save_config("pjob", code, config.to_dict())
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to save: {e}")
        raise typer.Exit(1)

    # 9. Output success
    console.print(f"[green]✓[/green] PJob '{code}' created successfully")
    console.print(f"   Name: {name}")
    console.print(f"   Agent: {agent}")
    console.print(f"   Workflow: {workflow}")
    if variable:
        console.print(f"   Variable: {variable}")
    if env:
        console.print(f"   Env: {env}")
    if pmg:
        console.print(f"   PMG: {pmg}")
    console.print(f"   File: {manager.get_config_path('pjob', code)}")


@app.command("list")
def list_pjobs(
    label: Optional[List[str]] = typer.Option(None, "--label", "-l", help="Filter by labels"),
    agent_type: Optional[str] = typer.Option(None, "--agent-type", help="Filter by agent type"),
    output_format: str = typer.Option("table", "--format", help="Output format: table/json"),
):
    """List all PJobs"""
    manager = ConfigManager()

    # Load all PJobs
    configs = manager.list_configs("pjob")

    if not configs:
        console.print("[yellow]No PJobs found.[/yellow] Create one with: zima pjob create")
        return

    # Filter by labels
    if label:
        configs = [
            c
            for c in configs
            if any(lbl in c.get("metadata", {}).get("labels", []) for lbl in label)
        ]

    if not configs:
        console.print("[yellow]No PJobs match the specified filters[/yellow]")
        return

    if output_format == "json":
        import json

        console.print(json.dumps(configs, indent=2, ensure_ascii=False))
    else:
        # Table format
        table = Table(title="PJobs")
        table.add_column("Code", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Agent", style="yellow")
        table.add_column("Workflow", style="blue")
        table.add_column("Labels", style="dim")

        for config in configs:
            metadata = config.get("metadata", {})
            spec = config.get("spec", {})

            code = metadata.get("code", "-")
            name = metadata.get("name", "-")
            labels = metadata.get("labels", [])

            # Get agent workflow names
            agent_code = spec.get("agent", "-")
            workflow_code = spec.get("workflow", "-")

            labels_str = ", ".join(labels) if labels else "-"

            table.add_row(code, name, agent_code, workflow_code, labels_str)

        console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="PJob code"),
    history: bool = typer.Option(False, "--history", help="Show execution history"),
    limit: int = typer.Option(10, "--limit", help="Number of history records"),
    output_format: str = typer.Option("yaml", "--format", help="Output format: yaml/json"),
):
    """Show PJob details"""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    if history:
        # Show execution history
        hist = ExecutionHistory()
        records = hist.get_history(code, limit=limit)

        if not records:
            console.print(f"[yellow]No execution history for '{code}'[/yellow]")
            return

        table = Table(title=f"Execution History: {code}")
        table.add_column("ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Duration", style="yellow")
        table.add_column("Started", style="dim")

        for record in records:
            status_color = {
                "success": "green",
                "failed": "red",
                "timeout": "yellow",
                "cancelled": "dim",
            }.get(record.status, "white")

            table.add_row(
                record.execution_id,
                f"[{status_color}]{record.status}[/{status_color}]",
                f"{record.duration_seconds:.1f}s",
                record.started_at[:19] if record.started_at else "-",
            )

        console.print(table)

        # Show stats
        stats = hist.get_stats(code)
        console.print(
            f"\nStats: {stats['total']} runs, {stats['success']} success ({stats['success_rate']:.0f}%)"
        )
    else:
        # Show config
        data = manager.load_config("pjob", code)
        config = PJobConfig.from_dict(data)

        if output_format == "json":
            import json

            console.print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            # Pretty display
            console.print(Panel(f"[bold]{config.metadata.name}[/bold]", subtitle=f"code: {code}"))

            tree = Tree(f"[bold cyan]PJob: {code}[/bold cyan]")

            # Metadata
            meta_branch = tree.add("[bold]Metadata[/bold]")
            meta_branch.add(f"Name: {config.metadata.name}")
            if config.metadata.description:
                meta_branch.add(f"Description: {config.metadata.description}")
            if config.metadata.labels:
                meta_branch.add(f"Labels: {', '.join(config.metadata.labels)}")

            # Spec
            spec_branch = tree.add("[bold]Configuration[/bold]")
            spec_branch.add(f"Agent: {config.spec.agent}")
            spec_branch.add(f"Workflow: {config.spec.workflow}")
            if config.spec.variable:
                spec_branch.add(f"Variable: {config.spec.variable}")
            if config.spec.env:
                spec_branch.add(f"Env: {config.spec.env}")
            if config.spec.pmg:
                spec_branch.add(f"PMG: {config.spec.pmg}")

            # Execution
            exec_branch = tree.add("[bold]Execution Options[/bold]")
            exec_branch.add(f"Work Dir: {config.spec.execution.work_dir or 'default'}")
            exec_branch.add(f"Timeout: {config.spec.execution.timeout}s")
            exec_branch.add(f"Retries: {config.spec.execution.retries}")

            console.print(tree)
            console.print(f"\n[dim]File: {manager.get_config_path('pjob', code)}[/dim]")


@app.command()
def update(
    code: str = typer.Argument(..., help="PJob code"),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Update agent"),
    workflow: Optional[str] = typer.Option(None, "--workflow", "-w", help="Update workflow"),
    variable: Optional[str] = typer.Option(None, "--variable", "-v", help="Update variable"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Update env"),
    pmg: Optional[str] = typer.Option(None, "--pmg", "-p", help="Update pmg"),
    timeout: Optional[int] = typer.Option(None, "--timeout", "-t", help="Update timeout"),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", help="Update work directory"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Update output path"),
    add_label: Optional[List[str]] = typer.Option(None, "--add-label", help="Add labels"),
    remove_label: Optional[List[str]] = typer.Option(None, "--remove-label", help="Remove labels"),
):
    """Update PJob configuration"""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    try:
        data = manager.load_config("pjob", code)
        config = PJobConfig.from_dict(data)

        # Update refs
        if agent:
            if not manager.config_exists("agent", agent):
                console.print(f"[red]✗[/red] Agent '{agent}' not found")
                raise typer.Exit(1)
            config.spec.agent = agent
        if workflow:
            if not manager.config_exists("workflow", workflow):
                console.print(f"[red]✗[/red] Workflow '{workflow}' not found")
                raise typer.Exit(1)
            config.spec.workflow = workflow
        if variable:
            config.spec.variable = variable
        if env:
            config.spec.env = env
        if pmg:
            config.spec.pmg = pmg

        # Update execution options
        if timeout is not None:
            config.spec.execution.timeout = timeout
        if work_dir:
            config.spec.execution.work_dir = work_dir

        # Update output
        if output:
            config.spec.output.save_to = output

        # Update labels
        if add_label:
            for label in add_label:
                if label not in config.metadata.labels:
                    config.metadata.labels.append(label)
        if remove_label:
            config.metadata.labels = [
                lbl for lbl in config.metadata.labels if lbl not in remove_label
            ]

        # Save
        manager.save_config("pjob", code, config.to_dict())
        console.print(f"[green]✓[/green] PJob '{code}' updated successfully")

    except Exception as e:
        console.print(f"[red]✗[/red] Failed to update: {e}")
        raise typer.Exit(1)


@app.command()
def delete(
    code: str = typer.Argument(..., help="PJob code"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
):
    """Delete a PJob"""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Are you sure you want to delete PJob '{code}'?")
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)

    try:
        manager.delete_config("pjob", code)
        console.print(f"[green]✓[/green] PJob '{code}' deleted")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to delete: {e}")
        raise typer.Exit(1)


@app.command()
def run(
    code: str = typer.Argument(..., help="PJob code"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be executed without running"
    ),
    set_var: Optional[List[str]] = typer.Option(
        None, "--set-var", help="Override variable values (key=value)"
    ),
    set_env: Optional[List[str]] = typer.Option(
        None, "--set-env", help="Override environment variables (key=value)"
    ),
    set_param: Optional[List[str]] = typer.Option(
        None, "--set-param", help="Override agent parameters (key=value)"
    ),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", help="Override working directory"),
    keep_temp: bool = typer.Option(False, "--keep-temp", help="Keep temporary files"),
    timeout: Optional[int] = typer.Option(None, "--timeout", "-t", help="Override timeout"),
    skip_validation: bool = typer.Option(
        False, "--skip-validation", help="Skip pre-execution validation"
    ),
):
    """Execute a PJob (runs in background by default)"""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    # Load config (needed for validation AND for state file metadata)
    data = manager.load_config("pjob", code)
    config = PJobConfig.from_dict(data)

    # Pre-execution validation
    if not skip_validation:
        try:
            validation_errors = []
            if config.spec.agent and not manager.config_exists("agent", config.spec.agent):
                validation_errors.append(f"Agent '{config.spec.agent}' not found")
            if config.spec.workflow and not manager.config_exists("workflow", config.spec.workflow):
                validation_errors.append(f"Workflow '{config.spec.workflow}' not found")
            if config.spec.variable and not manager.config_exists("variable", config.spec.variable):
                validation_errors.append(f"Variable '{config.spec.variable}' not found")
            if config.spec.env and not manager.config_exists("env", config.spec.env):
                validation_errors.append(f"Env '{config.spec.env}' not found")
            if config.spec.pmg and not manager.config_exists("pmg", config.spec.pmg):
                validation_errors.append(f"PMG '{config.spec.pmg}' not found")

            check_dir = work_dir or config.spec.execution.work_dir
            if check_dir:
                wd = Path(check_dir)
                if not wd.exists():
                    console.print(
                        f"[yellow]⚠[/yellow] Work directory '{wd}' does not exist, creating..."
                    )
                    wd.mkdir(parents=True, exist_ok=True)

            if validation_errors:
                console.print("[red]✗[/red] Validation failed:")
                for error in validation_errors:
                    console.print(f"   [red]•[/red] {error}")
                raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Pre-execution validation warning: {e}")

    # Build overrides
    overrides = Overrides()
    if set_var:
        for var in set_var:
            if "=" in var:
                key, value = var.split("=", 1)
                keys = key.split(".")
                target = overrides.variable_values
                for k in keys[:-1]:
                    if k not in target:
                        target[k] = {}
                    target = target[k]
                target[keys[-1]] = value
    if set_env:
        for env in set_env:
            if "=" in env:
                key, value = env.split("=", 1)
                overrides.env_vars[key] = value
    if set_param:
        for param in set_param:
            if "=" in param:
                key, value = param.split("=", 1)
                overrides.agent_params[key] = value

    # ==================================================================
    # Dry-run: render only, no background spawn
    # ==================================================================
    if dry_run:
        executor = PJobExecutor()
        try:
            result = executor.execute(
                pjob_code=code,
                overrides=overrides,
                dry_run=True,
                keep_temp=keep_temp,
            )
            console.print(Panel("[bold yellow]DRY RUN[/bold yellow]"))
            if result.prompt_content:
                console.print(
                    Panel(
                        result.prompt_content,
                        title="[bold]Rendered Workflow[/bold]",
                        border_style="blue",
                    )
                )
            console.print("\nCommand that would be executed:")
            console.print(Syntax(" ".join(result.command), "bash"))
            console.print("\nEnvironment variables:")
            import re

            _SENSITIVE_RE = re.compile(
                r"(TOKEN|SECRET|PASSWORD|CREDENTIAL|PRIVATE_KEY|API_KEY|_PAT\b)",
                re.IGNORECASE,
            )
            _PATH_RE = re.compile(
                r"(^PATH$|_PATH$|C_INCLUDE|EXEPATH|POSH_THEMES)", re.IGNORECASE
            )
            for key, value in result.env.items():
                is_sensitive = bool(_SENSITIVE_RE.search(key)) and not _PATH_RE.search(key)
                if is_sensitive:
                    masked = value[:8] + "***" if len(value) > 8 else "***"
                    console.print(f"  {key}={masked}")
                else:
                    console.print(f"  {key}={value}")
        except Exception as e:
            import traceback

            console.print(f"[red]✗[/red] Dry-run failed: {e}")
            console.print(
                Panel(
                    Syntax(traceback.format_exc(), "python"),
                    title="[red]Stack Trace[/red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1)
        return

    # ==================================================================
    # Background execution (default)
    # ==================================================================
    import json
    import subprocess
    import sys
    import uuid
    from datetime import datetime, timezone

    from zima.execution.history import ExecutionHistory

    execution_id = str(uuid.uuid4())[:8]
    log_dir = get_zima_home() / "logs" / "background"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{code}-{execution_id}.log"
    started_at = datetime.now(timezone.utc).astimezone().isoformat()

    # Build command for dry-run to capture what would execute
    executor = PJobExecutor()
    dry_result = executor.execute(
        pjob_code=code,
        overrides=overrides,
        dry_run=True,
        keep_temp=keep_temp,
    )

    # 1. Write initial state file BEFORE spawning
    history = ExecutionHistory()
    history.write_runtime_state(
        code,
        execution_id,
        {
            "execution_id": execution_id,
            "pjob_code": code,
            "status": "running",
            "pid": None,
            "command": dry_result.command,
            "started_at": started_at,
            "finished_at": None,
            "duration_seconds": None,
            "returncode": None,
            "stdout_preview": "",
            "stderr_preview": "",
            "error_detail": "",
            "log_path": str(log_path),
            "agent": config.spec.agent,
            "workflow": config.spec.workflow,
        },
    )

    # 2. Build subprocess command
    overrides_json = (
        json.dumps(overrides.to_dict()) if not overrides.is_empty() else "{}"
    )
    cmd = [
        sys.executable,
        "-m",
        "zima.execution.background_runner",
        code,
        "--execution-id",
        execution_id,
        "--overrides",
        overrides_json,
    ]
    if keep_temp:
        cmd.append("--keep-temp")

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            **kwargs,
        )

    # 3. Update state file with actual PID
    history.update_runtime_state(code, execution_id, pid=process.pid)

    # 4. Print summary
    console.print(f"\n[green]✓[/green] PJob '{code}' started")
    console.print(f"   Execution ID: {execution_id}")
    console.print(f"   PID: {process.pid}")
    console.print(f"   Log: {log_path}")
    console.print(f"   Status: [bold]zima pjob status {code}[/bold]")


@app.command()
def render(
    code: str = typer.Argument(..., help="PJob code"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Save rendered prompt to file"
    ),
    show_command: bool = typer.Option(
        False, "--show-command", help="Show the command that would be executed"
    ),
    show_env: bool = typer.Option(False, "--show-env", help="Show environment variables"),
):
    """Render the workflow template without executing"""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    executor = PJobExecutor()

    try:
        # Render prompt
        rendered = executor.render_prompt(code)

        if output:
            Path(output).write_text(rendered, encoding="utf-8")
            console.print(f"[green]✓[/green] Rendered prompt saved to: {output}")
        else:
            console.print(Panel("[bold]Rendered Prompt[/bold]"))
            console.print(Syntax(rendered, "markdown"))

        # Show command if requested
        if show_command:
            command, prompt_file, env_vars = executor.build_command(code)
            console.print(Panel("[bold]Command[/bold]"))
            console.print(Syntax(" ".join(command), "bash"))
            console.print(f"\n[dim]Prompt file: {prompt_file}[/dim]")

        # Show env if requested
        if show_env:
            _, _, env_vars = executor.build_command(code)
            console.print(Panel("[bold]Environment Variables[/bold]"))
            for key, value in env_vars.items():
                if not key.lower().endswith("key") and not key.startswith("_"):
                    console.print(f"  {key}={value}")

    except Exception as e:
        console.print(f"[red]✗[/red] Failed to render: {e}")
        raise typer.Exit(1)


@app.command()
def validate(
    code: str = typer.Argument(..., help="PJob code"),
    strict: bool = typer.Option(
        True, "--strict/--no-strict", help="Validate all referenced configs exist (default: True)"
    ),
    check_render: bool = typer.Option(
        False, "--check-render", help="Check if template renders successfully"
    ),
    check_workdir: bool = typer.Option(
        True,
        "--check-workdir/--no-check-workdir",
        help="Check if work directory exists (default: True)",
    ),
):
    """Validate PJob configuration"""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    try:
        data = manager.load_config("pjob", code)
        config = PJobConfig.from_dict(data)

        all_errors = []
        warnings = []

        # Basic validation
        errors = config.validate()
        all_errors.extend(errors)

        # Strict validation (check refs exist) - now default
        if strict:
            # Check agent exists
            if config.spec.agent and not manager.config_exists("agent", config.spec.agent):
                all_errors.append(f"Agent '{config.spec.agent}' not found")

            # Check workflow exists
            if config.spec.workflow and not manager.config_exists("workflow", config.spec.workflow):
                all_errors.append(f"Workflow '{config.spec.workflow}' not found")

            # Check variable exists (if specified)
            if config.spec.variable and not manager.config_exists("variable", config.spec.variable):
                all_errors.append(f"Variable '{config.spec.variable}' not found")

            # Check env exists (if specified)
            if config.spec.env and not manager.config_exists("env", config.spec.env):
                all_errors.append(f"Env '{config.spec.env}' not found")

            # Check pmg exists (if specified)
            if config.spec.pmg and not manager.config_exists("pmg", config.spec.pmg):
                all_errors.append(f"PMG '{config.spec.pmg}' not found")

        # Check work directory exists
        if check_workdir and config.spec.execution.work_dir:
            work_dir = Path(config.spec.execution.work_dir)
            if not work_dir.exists():
                warnings.append(
                    f"Work directory '{work_dir}' does not exist (will be created on run)"
                )

        # Check template render
        if check_render:
            try:
                executor = PJobExecutor()
                rendered = executor.render_prompt(code)
                # Try to detect undefined variables
                if "<!-- Template render error:" in rendered:
                    all_errors.append(
                        f"Template render error: {rendered.split('<!-- Template render error:')[1].split('-->')[0].strip()}"
                    )
            except Exception as e:
                all_errors.append(f"Template render failed: {e}")

        # Output results
        if all_errors:
            console.print(f"[red]✗[/red] Validation failed for PJob '{code}':")
            for error in all_errors:
                console.print(f"   [red]•[/red] {error}")
            raise typer.Exit(1)

        # Show success
        console.print(f"[green]✓[/green] PJob '{code}' is valid")

        if strict:
            console.print("   [green]•[/green] All referenced configs exist")
        if check_render:
            console.print("   [green]•[/green] Template renders successfully")
        if not warnings:
            console.print("   [green]•[/green] Ready to execute")

        # Show warnings if any
        for warning in warnings:
            console.print(f"   [yellow]⚠[/yellow] {warning}")

    except Exception as e:
        console.print(f"[red]✗[/red] Validation error: {e}")
        raise typer.Exit(1)


@app.command()
def copy(
    source: str = typer.Argument(..., help="Source PJob code"),
    target: str = typer.Argument(..., help="Target PJob code"),
    name: str = typer.Option(..., "--name", "-n", help="New display name"),
):
    """Copy a PJob"""
    manager = ConfigManager()

    if not manager.config_exists("pjob", source):
        console.print(f"[red]✗[/red] Source PJob '{source}' not found")
        raise typer.Exit(1)

    if manager.config_exists("pjob", target):
        console.print(f"[red]✗[/red] Target PJob '{target}' already exists")
        raise typer.Exit(1)

    try:
        data = manager.load_config("pjob", source)
        data["metadata"]["code"] = target
        data["metadata"]["name"] = name

        manager.save_config("pjob", target, data)
        console.print(f"[green]✓[/green] PJob '{source}' copied to '{target}'")
        console.print(f"   Name: {name}")

    except Exception as e:
        console.print(f"[red]✗[/red] Failed to copy: {e}")
        raise typer.Exit(1)


@app.command("history")
def show_history(
    code: str = typer.Argument(..., help="PJob code"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    clear: bool = typer.Option(False, "--clear", help="Clear history"),
    detail: Optional[str] = typer.Option(
        None, "--detail", help="Show detailed info for execution ID"
    ),
):
    """Show or clear execution history"""
    history = ExecutionHistory()

    if clear:
        if history.clear_history(code):
            console.print(f"[green]✓[/green] History for '{code}' cleared")
        else:
            console.print(f"[yellow]No history to clear for '{code}'[/yellow]")
        return

    # Show detailed view for a specific execution
    if detail:
        record = history.get_record(code, detail)
        if not record:
            console.print(f"[red]✗[/red] Execution '{detail}' not found for '{code}'")
            raise typer.Exit(1)

        console.print(Panel(f"[bold]Execution Detail: {detail}[/bold]", subtitle=f"PJob: {code}"))

        status_color = {
            "success": "green",
            "failed": "red",
            "timeout": "yellow",
            "cancelled": "dim",
        }.get(record.status, "white")

        console.print(f"Status: [{status_color}]{record.status}[/{status_color}]")
        console.print(f"Return Code: {record.returncode}")
        if record.pid:
            console.print(f"PID: {record.pid}")
        console.print(f"Duration: {record.duration_seconds:.1f}s")
        console.print(f"Started: {record.started_at}")
        console.print(f"Finished: {record.finished_at}")
        console.print(f"Command: {' '.join(record.command)}")

        if record.stderr_preview:
            console.print(
                Panel(record.stderr_preview, title="[red]stderr[/red]", border_style="red")
            )

        if record.error_detail:
            console.print(
                Panel(
                    record.error_detail,
                    title="[red]Error Detail[/red]",
                    border_style="red",
                )
            )
        return

    records = history.get_history(code, limit=limit, status=status)

    if not records:
        console.print(f"[yellow]No execution history for '{code}'[/yellow]")
        return

    table = Table(title=f"Execution History: {code}")
    table.add_column("ID", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Return", style="yellow")
    table.add_column("PID", style="magenta")
    table.add_column("Duration", style="blue")
    table.add_column("Started", style="dim")

    for record in records:
        status_color = {
            "success": "green",
            "failed": "red",
            "timeout": "yellow",
            "cancelled": "dim",
        }.get(record.status, "white")

        table.add_row(
            record.execution_id,
            f"[{status_color}]{record.status}[/{status_color}]",
            str(record.returncode),
            str(record.pid) if record.pid else "-",
            f"{record.duration_seconds:.1f}s",
            record.started_at[:19] if record.started_at else "-",
        )

    console.print(table)

    # Show stats
    stats = history.get_stats(code)
    console.print(
        f"\nStats: {stats['total']} runs, "
        f"{stats['success']} success ({stats['success_rate']:.0f}%), "
        f"avg {stats['avg_duration']:.1f}s"
    )
    console.print(f"\nUse [dim]zima pjob history {code} --detail <ID>[/dim] to see error details")
