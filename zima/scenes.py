"""Quickstart scene template definitions."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Optional

import yaml

from zima.models.actions import ActionsConfig, PostExecAction
from zima.utils import get_zima_home


@dataclass
class Scene:
    """A quickstart scene template with rendering variables and provider config.

    Attributes:
        name: Display name for the scene.
        description: Short description shown in the quickstart wizard.
        workflow_template: Jinja2 template string rendered into the agent prompt.
        variables: Default variable values for the template.
        provider: Action provider name (default ``"github"``).
        scan_command: Optional CLI command to scan for items (e.g. PRs/MRs).
        default_actions: Optional default actions (postExec label transitions, etc.).
    """

    name: str
    description: str
    workflow_template: str
    variables: dict[str, str]
    provider: str = "github"
    scan_command: Optional[list[str]] = None
    default_actions: Optional[ActionsConfig] = None


BUILTIN_SCENES: dict[str, Scene] = {
    "code-review": Scene(
        name="Code Review",
        description="Review PRs/MRs with AI agent",
        workflow_template="review pr {{ pr_url }}",
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
        default_actions=ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    remove_labels=["zima:needs-review"],
                    repo="{{repo}}",
                    issue="{{pr_number}}",
                ),
                PostExecAction(
                    condition="failure",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="{{repo}}",
                    issue="{{pr_number}}",
                ),
            ],
        ),
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
    scenes = {k: copy.deepcopy(v) for k, v in BUILTIN_SCENES.items()}
    user_path = get_zima_home() / "scenes.yaml"
    if user_path.exists():
        try:
            data = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            print(f"Warning: Failed to parse scenes.yaml: {e}")
            return scenes
        for key, spec in data.get("scenes", {}).items():
            try:
                scenes[key] = Scene(**spec)
            except TypeError as e:
                print(f"Warning: Invalid scene config '{key}': {e}")
    return scenes
