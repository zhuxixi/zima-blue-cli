"""Quickstart scene template definitions."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Optional

import yaml

from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction
from zima.providers.defaults import get_default_provider_name
from zima.utils import get_zima_home


@dataclass
class Scene:
    """A quickstart scene template with rendering variables and provider config."""

    name: str
    description: str
    workflow_template: str
    variables: dict[str, str]
    provider: str | None = None
    scan_command: Optional[list[str]] = None
    default_actions: Optional[ActionsConfig] = None

    def __post_init__(self):
        if self.provider is None:
            self.provider = get_default_provider_name()


BUILTIN_SCENES: dict[str, Scene] = {
    "code-review": Scene(
        name="Code Review",
        description="Review PRs/MRs with AI agent",
        workflow_template="review pr {{ pr_url }}",
        variables={"pr_url": "", "repo": "", "pr_number": ""},
        provider="github",
        default_actions=ActionsConfig(
            pre_exec=[
                PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review"),
            ],
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
                if "default_actions" in spec and isinstance(spec["default_actions"], dict):
                    spec["default_actions"] = ActionsConfig.from_dict(spec["default_actions"])
                scenes[key] = Scene(**spec)
            except (TypeError, ValueError) as e:
                print(f"Warning: Invalid scene config '{key}': {e}")
    return scenes
