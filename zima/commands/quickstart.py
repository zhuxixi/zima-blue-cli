"""Quickstart wizard command - creates all configs from scratch."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console

from zima.config.manager import ConfigManager
from zima.scenes import QUICKSTART_SCENES

console = Console(legacy_windows=False, force_terminal=True)

AGENT_CHOICES: dict[str, str] = {
    "kimi": "kimi-code-cli (月之暗面)",
    "claude": "claude-code (Anthropic)",
}


def _detect_git_repo() -> Optional[str]:
    """Detect if current directory is a git repo. Returns path or None."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
        return str(Path.cwd())
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
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except Exception:
        return []


def _generate_unique_code(base: str, manager: ConfigManager, kind: str) -> str:
    """Generate a unique config code, appending -N if needed."""
    code = base
    suffix = 2
    while manager.config_exists(kind, code):
        code = f"{base}-{suffix}"
        suffix += 1
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
