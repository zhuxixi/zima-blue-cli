"""Post-execution action models for PJob automation."""

from __future__ import annotations

from dataclasses import dataclass, field

from zima.models.serialization import YamlSerializable, omit_empty

VALID_ACTION_CONDITIONS = {"success", "failure", "always"}
VALID_ACTION_TYPES = {"github_label", "github_comment"}


@dataclass
class PostExecAction(YamlSerializable):
    """Single post-execution action run after agent exits.

    Attributes:
        condition: When to run - "success", "failure", or "always".
        type: Action type - "github_label" or "github_comment".
        add_labels: Labels to add (for github_label type).
        remove_labels: Labels to remove (for github_label type).
        repo: Repository slug in "owner/repo" format.
        issue: Issue or PR number as string.
        body: Comment body (for github_comment type).
    """

    FIELD_ALIASES = {
        "add_labels": "addLabels",
        "remove_labels": "removeLabels",
    }

    condition: str = "always"
    type: str = "github_label"
    add_labels: list[str] = field(default_factory=list)
    remove_labels: list[str] = field(default_factory=list)
    repo: str = ""
    issue: str = ""
    body: str = ""

    def __post_init__(self):
        if self.issue is None:
            self.issue = ""
        elif not isinstance(self.issue, str):
            if isinstance(self.issue, (int, float)):
                self.issue = str(self.issue)
            else:
                raise TypeError(
                    f"issue must be a string or number, got {type(self.issue).__name__}"
                )

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> PostExecAction:
        """Create from dictionary and validate."""
        action = super().from_dict(data)
        errors = action.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return action

    def validate(self) -> list[str]:
        """Validate action configuration."""
        errors = []
        if self.condition not in VALID_ACTION_CONDITIONS:
            errors.append(f"Invalid condition '{self.condition}'. Valid: {VALID_ACTION_CONDITIONS}")
        if self.type not in VALID_ACTION_TYPES:
            errors.append(f"Invalid type '{self.type}'. Valid: {VALID_ACTION_TYPES}")
        return errors


@dataclass
class ActionsConfig(YamlSerializable):
    """Collection of actions for a PJob."""

    FIELD_ALIASES = {"post_exec": "postExec"}

    post_exec: list[PostExecAction] = field(default_factory=list)

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> ActionsConfig:
        """Create from dictionary and validate."""
        config = super().from_dict(data)
        errors = config.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return config

    def validate(self) -> list[str]:
        """Validate all actions."""
        errors = []
        for i, action in enumerate(self.post_exec):
            action_errors = action.validate()
            errors.extend([f"Action[{i}]: {e}" for e in action_errors])
        return errors
