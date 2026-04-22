"""Actions runner for executing postExec actions after agent process exits."""

from __future__ import annotations

from typing import Optional

from zima.github.ops import GitHubOps
from zima.models.actions import ActionsConfig, PostExecAction
from zima.review.parser import ReviewResult


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
    and GitHub label/comment operations.
    """

    def __init__(self, ops: Optional[GitHubOps] = None):
        self._ops = ops or GitHubOps()

    def run(
        self,
        actions: ActionsConfig,
        returncode: int,
        env: dict[str, str],
        review_result: Optional[ReviewResult] = None,
    ) -> None:
        """Execute all matching postExec actions.

        Args:
            actions: Actions configuration from PJob.
            returncode: Agent process exit code.
            env: Environment variables for {{VAR}} substitution.
            review_result: Parsed review result (optional, for reviewer PJobs).
        """
        for action in actions.post_exec:
            if not _matches_condition(action.condition, returncode):
                continue

            processed = self._substitute_env(action, env)
            self._execute_action(processed)

    def _substitute_env(self, action: PostExecAction, env: dict[str, str]) -> PostExecAction:
        """Replace {{VAR}} placeholders with env values."""

        def sub(value: str) -> str:
            for key, val in env.items():
                value = value.replace(f"{{{key}}}", str(val))
            return value

        return PostExecAction(
            condition=action.condition,
            type=action.type,
            add_labels=[sub(l) for l in action.add_labels],
            remove_labels=[sub(l) for l in action.remove_labels],
            repo=sub(action.repo),
            issue=sub(action.issue),
            body=sub(action.body),
        )

    def _execute_action(self, action: PostExecAction) -> None:
        """Execute a single action."""
        if not action.repo or not action.issue:
            return

        try:
            issue_num = int(action.issue)
        except ValueError:
            return

        if action.type == "github_label":
            for label in action.add_labels:
                self._ops.add_label(action.repo, issue_num, label)
            for label in action.remove_labels:
                self._ops.remove_label(action.repo, issue_num, label)

        elif action.type == "github_comment":
            if action.body:
                self._ops.post_comment(action.repo, issue_num, action.body)
