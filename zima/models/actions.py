"""Post-execution action models for PJob automation."""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_ACTION_CONDITIONS = {"success", "failure", "always"}
VALID_ACTION_TYPES = {"github_label", "github_comment"}


@dataclass
class PostExecAction:
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

    condition: str = "always"
    type: str = "github_label"
    add_labels: list[str] = field(default_factory=list)
    remove_labels: list[str] = field(default_factory=list)
    repo: str = ""
    issue: str = ""
    body: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "condition": self.condition,
            "type": self.type,
        }
        if self.add_labels:
            result["addLabels"] = self.add_labels
        if self.remove_labels:
            result["removeLabels"] = self.remove_labels
        if self.repo:
            result["repo"] = self.repo
        if self.issue:
            result["issue"] = self.issue
        if self.body:
            result["body"] = self.body
        return result

    @classmethod
    def from_dict(cls, data: dict) -> PostExecAction:
        """Create from dictionary and validate."""
        action = cls(
            condition=data.get("condition", "always"),
            type=data.get("type", "github_label"),
            add_labels=data.get("addLabels", []),
            remove_labels=data.get("removeLabels", []),
            repo=data.get("repo", ""),
            issue=str(data.get("issue", "")),
            body=data.get("body", ""),
        )
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
class ActionsConfig:
    """Collection of actions for a PJob."""

    post_exec: list[PostExecAction] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {"postExec": [a.to_dict() for a in self.post_exec]}

    @classmethod
    def from_dict(cls, data: dict) -> ActionsConfig:
        """Create from dictionary and validate."""
        actions = []
        for action_data in data.get("postExec", []):
            actions.append(PostExecAction.from_dict(action_data))
        config = cls(post_exec=actions)
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
