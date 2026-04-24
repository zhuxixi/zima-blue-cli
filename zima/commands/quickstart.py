"""Quickstart wizard command - creates all configs from scratch."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import typer
from rich.console import Console

from zima.config.manager import ConfigManager
from zima.scenes import QUICKSTART_SCENES
from zima.utils import CODE_MAX_LENGTH

console = Console(legacy_windows=False, force_terminal=True)

AGENT_CHOICES: dict[str, str] = {
    "kimi": "kimi-code-cli (月之暗面)",
    "claude": "claude-code (Anthropic)",
}


_SUBPROCESS_TIMEOUT = 10  # seconds


def _detect_git_repo() -> Optional[str]:
    """Detect if current directory is a git repo. Returns repo root path or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _scan_github_prs(label: str = "need-review") -> list[dict]:
    """Scan GitHub for open PRs with given label. Returns display-only results."""
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--label",
                label,
                "--json",
                "number,title,url",
            ],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except Exception:
        return []


def _sanitize_git_url(url: str) -> str:
    """Remove credentials from git URL before displaying."""
    parsed = urlparse(url.strip())
    if parsed.username or parsed.password:
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc += f":{parsed.port}"
        parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)
    return url


def _sanitize_base_name(name: str) -> str:
    """Convert user input to a valid code-safe base name."""
    sanitized = re.sub(r"[\s_]+", "-", name.lower())
    sanitized = re.sub(r"[^a-z0-9-]", "", sanitized)
    sanitized = re.sub(r"-+", "-", sanitized)
    sanitized = sanitized.strip("-")
    if not sanitized:
        return "zima"
    if sanitized[0].isdigit():
        sanitized = "a-" + sanitized.lstrip("0123456789")
        sanitized = sanitized.strip("-")
    # Leave room for longest suffix ("-workflow" = 9) + unique suffix ("-999" = 4)
    max_base = CODE_MAX_LENGTH - 13
    return sanitized[:max_base] or "zima"


def _generate_unique_code(base: str, manager: ConfigManager, kind: str) -> str:
    """Generate a unique config code, appending -N if needed."""
    code = base
    suffix = 2
    max_attempts = 1000
    attempts = 0
    while manager.config_exists(kind, code) and attempts < max_attempts:
        code = f"{base}-{suffix}"
        suffix += 1
        attempts += 1
        if len(code) > CODE_MAX_LENGTH:
            # Truncate base to make room for suffix
            code = base[: CODE_MAX_LENGTH - len(f"-{suffix}")] + f"-{suffix}"
    return code


def _create_all_configs(
    base_name: str,
    scene_key: str,
    agent_type: str,
    work_dir: str,
    env_code: Optional[str],
    manager: ConfigManager,
) -> dict[str, str]:
    """Create all 5 configurations. Returns dict of created codes."""
    from zima.models.agent import AgentConfig
    from zima.models.pjob import PJobConfig
    from zima.models.variable import VariableConfig
    from zima.models.workflow import VariableDef, WorkflowConfig

    scene = QUICKSTART_SCENES[scene_key]

    # Generate unique codes
    agent_code = _generate_unique_code(f"{base_name}-agent", manager, "agent")
    wf_code = _generate_unique_code(f"{base_name}-workflow", manager, "workflow")
    var_code = _generate_unique_code(f"{base_name}-vars", manager, "variable")
    job_code = _generate_unique_code(f"{base_name}-job", manager, "pjob")

    # 1. Create Agent
    agent = AgentConfig.create(
        code=agent_code,
        name=f"{base_name.title()} Agent",
        agent_type=agent_type,
        parameters={"workDir": work_dir},
    )
    manager.save_config("agent", agent_code, agent.to_dict())

    # 2. Create Workflow
    wf = WorkflowConfig.create(
        code=wf_code,
        name=f"{base_name.title()} Workflow",
        template=scene["workflow_template"],
    )
    for var_name in scene.get("variables", {}):
        wf.add_variable(VariableDef(name=var_name, type="string", required=True))
    manager.save_config("workflow", wf_code, wf.to_dict())

    # 3. Create Variable
    var = VariableConfig.create(
        code=var_code,
        name=f"{base_name.title()} Variables",
        for_workflow=wf_code,
        values=scene.get("variables", {}).copy(),
    )
    manager.save_config("variable", var_code, var.to_dict())

    # 4. Create PJob
    job = PJobConfig.create(
        code=job_code,
        name=f"{base_name.title()} Job",
        agent=agent_code,
        workflow=wf_code,
        variable=var_code,
        env=env_code or "",
    )
    manager.save_config("pjob", job_code, job.to_dict())

    return {
        "agent": agent_code,
        "workflow": wf_code,
        "variable": var_code,
        "env": env_code or "",
        "pjob": job_code,
    }


def _select_scene(preselected: Optional[str] = None) -> str:
    """Interactive scene selection. Returns scene key."""
    if preselected:
        if preselected not in QUICKSTART_SCENES:
            console.print(f"[red]Invalid scene: {preselected}[/red]")
            raise typer.Exit(1)
        return preselected

    console.print("\n[bold]Choose a task template:[/bold]")
    scenes = list(QUICKSTART_SCENES.items())
    for i, (key, scene_def) in enumerate(scenes, 1):
        marker = " <- default" if i == 1 else ""
        console.print(f"  [{i}] {scene_def['name']} — {scene_def['description']}{marker}")

    choice = typer.prompt("Enter choice", default="1")
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(scenes):
            raise ValueError
        return scenes[idx][0]
    except ValueError:
        console.print("[red]Invalid choice[/red]")
        raise typer.Exit(1)


def _select_agent_type() -> str:
    """Interactive agent type selection."""
    console.print("\n[bold]Which AI agent do you want to use?[/bold]")
    choices = list(AGENT_CHOICES.items())
    for i, (key, label) in enumerate(choices, 1):
        marker = " <- default" if i == 1 else ""
        console.print(f"  [{i}] {label}{marker}")

    choice = typer.prompt("Enter choice", default="1")
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(choices):
            raise ValueError
        return choices[idx][0]
    except ValueError:
        console.print("[red]Invalid choice[/red]")
        raise typer.Exit(1)


def _resolve_work_dir(preselected: Optional[str] = None) -> str:
    """Resolve working directory, interactive if needed."""
    if preselected:
        return preselected

    git_dir = _detect_git_repo()
    if git_dir:
        console.print("\n[bold]Working directory:[/bold]")
        console.print(f"  Current directory: {git_dir}")
        try:
            remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=_SUBPROCESS_TIMEOUT,
            )
            if remote.returncode == 0 and remote.stdout.strip():
                safe_url = _sanitize_git_url(remote.stdout.strip())
                console.print(f"  Git remote: {safe_url}")
        except Exception:
            pass
        use_current = typer.confirm("Use current directory?", default=True)
        if use_current:
            return git_dir

    return typer.prompt("Enter working directory path", default=str(Path.cwd()))


def _select_env(agent_type: str, manager: ConfigManager) -> Optional[str]:
    """Select or skip env config. Returns env code or None."""
    configs = manager.list_configs("env")
    matching = [c for c in configs if c.get("spec", {}).get("forType") == agent_type]

    if not matching:
        return None

    console.print(f"\n[bold]Select API key for {agent_type}:[/bold]")
    for i, config in enumerate(matching, 1):
        code = config["metadata"]["code"]
        name = config["metadata"]["name"]
        marker = " <- default" if i == 1 else ""
        console.print(f"  [{i}] {name} ({code}){marker}")
    console.print(f"  [{len(matching) + 1}] Skip (configure later)")

    choice = typer.prompt("Enter choice", default="1")
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(matching):
            return None
        return matching[idx]["metadata"]["code"]
    except ValueError:
        return None


def quickstart(
    scene: Optional[str] = typer.Option(
        None, "--scene", "-s", help="Pre-select scene: code-review|custom"
    ),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Base name for all configs"),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", "-w", help="Working directory"),
):
    """Interactive wizard to create a complete PJob from scratch."""
    console.print("\n[bold cyan]Welcome to Zima quickstart![/bold cyan]")
    console.print("This wizard creates a complete PJob configuration from scratch.\n")

    # Step 1: Select scene
    scene_key = _select_scene(preselected=scene)

    # Step 2: Get base name
    raw_name = name or typer.prompt("What would you like to name your setup", default="hello-zima")
    base_name = _sanitize_base_name(raw_name)

    # Step 3: Select agent type
    agent_type = _select_agent_type()

    # Step 4: Resolve workDir
    resolved_work_dir = _resolve_work_dir(preselected=work_dir)

    # Step 5: Show PR scan (display only)
    if scene_key == "code-review":
        console.print("\n[bold]Scanning GitHub for open PRs with 'need-review' label...[/bold]")
        prs = _scan_github_prs("need-review")
        if prs:
            console.print(f"  Found {len(prs)} PR(s) (display only, not saved to config):")
            for pr in prs:
                console.print(f"    PR #{pr['number']}: {pr['title']}", markup=False)
        else:
            console.print("  No matching PRs found. You'll provide the URL when running.")

    # Step 6: Select env
    manager = ConfigManager()
    env_code = _select_env(agent_type, manager)

    # Step 7: Summary & confirm
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Scene:       {scene_key}")
    console.print(f"  Name:        {base_name}")
    console.print(f"  Agent:       {base_name}-agent ({agent_type})")
    console.print(f"  WorkDir:     {resolved_work_dir}")
    console.print(f"  Workflow:    {base_name}-workflow")
    console.print(f"  Variable:    {base_name}-vars")
    if env_code:
        console.print(f"  Env:         {env_code}")
    else:
        console.print("  Env:         (skipped)")
    console.print(f"  PJob:        {base_name}-job")

    if not typer.confirm("\nCreate all configurations?", default=True):
        console.print("Cancelled.")
        raise typer.Exit(0)

    # Step 8: Create all configs
    codes = _create_all_configs(
        base_name=base_name,
        scene_key=scene_key,
        agent_type=agent_type,
        work_dir=resolved_work_dir,
        env_code=env_code,
        manager=manager,
    )

    # Step 9: Print results
    console.print("\n[green]Created configurations:[/green]")
    console.print(f"  Agent:       {codes['agent']}")
    console.print(f"  Workflow:    {codes['workflow']}")
    console.print(f"  Variable:    {codes['variable']}")
    console.print(f"  PJob:        {codes['pjob']}")

    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  Preview:  zima pjob run {codes['pjob']} --dry-run")
    console.print(f"  Execute:  zima pjob run {codes['pjob']} --set-var pr_url=YOUR_PR_URL")
