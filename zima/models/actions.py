"""Action models for PJob automation."""

from __future__ import annotations

from dataclasses import dataclass, field

from zima.models.serialization import YamlSerializable, omit_empty

VALID_ACTION_CONDITIONS = {"success", "failure", "always"}
VALID_POST_ACTION_TYPES = {"add_label", "add_comment"}
VALID_PRE_ACTION_TYPES = {"scan_pr", "run_command"}


@dataclass
class PostExecAction(YamlSerializable):
    """Single post-execution action run after agent exits.

    Attributes:
        condition: When to run - "success", "failure", or "always".
        type: Action type - "add_label" or "add_comment".
        add_labels: Labels to add (for add_label type).
        remove_labels: Labels to remove (for add_label type).
        repo: Repository slug in "owner/repo" format.
        issue: Issue or PR number as string.
        body: Comment body (for add_comment type).
    """

    FIELD_ALIASES = {
        "add_labels": "addLabels",
        "remove_labels": "removeLabels",
    }

    condition: str = "always"
    type: str = "add_label"
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
        if self.type not in VALID_POST_ACTION_TYPES:
            errors.append(f"Invalid type '{self.type}'. Valid: {VALID_POST_ACTION_TYPES}")
        return errors


@dataclass
class PreExecAction(YamlSerializable):
    """Single pre-execution action run before agent starts.

    Attributes:
        condition: When to run — "always", "success", or "failure".
        type: Action type — "scan_pr" or "run_command".
        repo: Repository slug in "owner/repo" format (for scan_pr).
        label: Label to scan for (for scan_pr).
        command: Shell command to run (for run_command).
    """

    condition: str = "always"
    type: str = "scan_pr"
    repo: str = ""
    label: str = ""
    command: str = ""

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> PreExecAction:
        """Create from dictionary and validate."""
        action = super().from_dict(data)
        errors = action.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return action

    def validate(self) -> list[str]:
        """Validate pre-execution action configuration."""
        errors = []
        if self.condition not in VALID_ACTION_CONDITIONS:
            errors.append(f"Invalid condition '{self.condition}'. Valid: {VALID_ACTION_CONDITIONS}")
        if self.type not in VALID_PRE_ACTION_TYPES:
            errors.append(f"Invalid type '{self.type}'. Valid: {VALID_PRE_ACTION_TYPES}")
        return errors


@dataclass
class ActionsConfig(YamlSerializable):
    """Collection of actions for a PJob.

    Attributes:
        provider: The action provider to use (default: "github").
        pre_exec: List of PreExecAction instances to run before the agent starts.
        post_exec: List of PostExecAction instances to run after agent exits.
    """

    FIELD_ALIASES = {"pre_exec": "preExec", "post_exec": "postExec"}

    provider: str = "github"
    pre_exec: list[PreExecAction] = field(default_factory=list)
    post_exec: list[PostExecAction] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = omit_empty(super().to_dict())
        if self.provider == "github":
            d.pop("provider", None)
        return d

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
        for i, action in enumerate(self.pre_exec):
            action_errors = action.validate()
            errors.extend([f"PreAction[{i}]: {e}" for e in action_errors])
        for i, action in enumerate(self.post_exec):
            action_errors = action.validate()
            errors.extend([f"Action[{i}]: {e}" for e in action_errors])
        return errors
