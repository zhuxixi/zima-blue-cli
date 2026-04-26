"""Actions runner for executing postExec actions after agent process exits."""

from __future__ import annotations

from typing import Optional

from zima.actions.base import ActionProvider
from zima.actions.exceptions import ProviderNotFoundError
from zima.actions.registry import ProviderRegistry, get_default_registry
from zima.models.actions import ActionsConfig, PostExecAction


def _matches_condition(condition: str, returncode: int) -> bool:
    """Check if action condition matches execution result.

    Args:
        condition: Action condition - "success", "failure", or "always".
        returncode: Process exit code.

    Returns:
        True if the condition matches the returncode.
    """
    if condition == "always":
        return True
    if condition == "success":
        return returncode == 0
    if condition == "failure":
        return returncode != 0
    return False


class ActionsRunner:
    """Executes postExec actions after agent process exits.

    Handles condition matching, environment variable substitution,
    and action dispatch to the configured provider.
    """

    def __init__(self, registry: Optional[ProviderRegistry] = None):
        self._registry = registry or get_default_registry()

    def run(
        self,
        actions: ActionsConfig,
        returncode: int,
        env: dict[str, str],
    ) -> None:
        """Execute all matching postExec actions.

        Args:
            actions: Actions configuration from PJob.
            returncode: Agent process exit code.
            env: Environment variables for {{VAR}} substitution.
        """
        try:
            provider = self._registry.get(actions.provider)
        except ProviderNotFoundError as e:
            print(f"Warning: {e}")
            return

        for action in actions.post_exec:
            if not _matches_condition(action.condition, returncode):
                continue

            processed = self._substitute_env(action, env)
            self._execute_action(processed, provider)

    def _substitute_env(self, action: PostExecAction, env: dict[str, str]) -> PostExecAction:
        """Replace {{VAR}} placeholders with env values."""

        def sub(value: str) -> str:
            for key, val in env.items():
                value = value.replace(f"{{{{{key}}}}}", str(val))
            return value

        return PostExecAction(
            condition=action.condition,
            type=action.type,
            add_labels=[sub(label) for label in action.add_labels],
            remove_labels=[sub(label) for label in action.remove_labels],
            repo=sub(action.repo),
            issue=sub(action.issue),
            body=sub(action.body),
        )

    def _execute_action(self, action: PostExecAction, provider: ActionProvider) -> None:
        """Execute a single action, logging individual failures but continuing."""
        if not action.repo or not action.issue:
            return

        if action.type == "add_label":
            for label in action.add_labels:
                try:
                    provider.add_label(action.repo, action.issue, label)
                except RuntimeError as e:
                    print(f"Warning: Failed to add label '{label}': {e}")
            for label in action.remove_labels:
                try:
                    provider.remove_label(action.repo, action.issue, label)
                except RuntimeError as e:
                    print(f"Warning: Failed to remove label '{label}': {e}")

        elif action.type == "add_comment":
            if action.body:
                try:
                    provider.post_comment(action.repo, action.issue, action.body)
                except RuntimeError as e:
                    print(f"Warning: Failed to post comment: {e}")
