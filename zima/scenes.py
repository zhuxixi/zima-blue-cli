"""Quickstart scene template definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import yaml

from zima.utils import get_zima_home


@dataclass
class Scene:
    name: str
    description: str
    workflow_template: str
    variables: dict[str, str]
    provider: str = "github"
    scan_command: Optional[list[str]] = None


BUILTIN_SCENES: dict[str, Scene] = {
    "code-review": Scene(
        name="Code Review",
        description="Review PRs/MRs with AI agent",
        workflow_template="CR {{ pr_url }}",
        variables={"pr_url": ""},
        provider="github",
        scan_command=[
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--label",
            "need-review",
            "--json",
            "number,title,url",
        ],
    ),
    "custom": Scene(
        name="Custom Task",
        description="Write your own prompt template",
        workflow_template="",
        variables={},
    ),
}

QUICKSTART_SCENES = BUILTIN_SCENES  # backward compat alias


def load_scenes() -> dict[str, Scene]:
    """Load built-in scenes merged with user-defined scenes from ~/.zima/scenes.yaml."""
    scenes = BUILTIN_SCENES.copy()
    user_path = get_zima_home() / "scenes.yaml"
    if user_path.exists():
        data = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
        for key, spec in data.get("scenes", {}).items():
            scenes[key] = Scene(**spec)
    return scenes
