"""Actions runner for executing preExec and postExec actions around agent execution."""

from __future__ import annotations

from typing import Optional

from zima.actions.base import ActionProvider
from zima.actions.exceptions import ProviderNotFoundError
from zima.actions.registry import ProviderRegistry, get_default_registry
from zima.models.actions import ActionsConfig, PostExecAction


class SkipAction(Exception):
    """Raised when a preExec action indicates the PJob should be skipped."""

    pass


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
    """Executes preExec and postExec actions around agent execution.

    Handles condition matching, environment variable substitution,
    and action dispatch to the configured provider.
    """

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        history=None,
        pjob_code: Optional[str] = None,
    ):
        self._registry = registry or get_default_registry()
        self._history = history
        self._pjob_code = pjob_code

    def run(
        self,
        actions: ActionsConfig,
        returncode: int,
        env: dict[str, str],
    ) -> list[str]:
        """Execute all matching postExec actions.

        Args:
            actions: Actions configuration from PJob.
            returncode: Agent process exit code.
            env: Environment variables for {{VAR}} substitution.

        Returns:
            List of error messages from failed actions.
        """
        try:
            provider = self._registry.get(actions.provider)
        except ProviderNotFoundError as e:
            print(f"Warning: {e}")
            return [str(e)]

        errors: list[str] = []
        for action in actions.post_exec:
            if not _matches_condition(action.condition, returncode):
                continue

            processed = self._substitute_env(action, env)
            errors.extend(self._execute_action(processed, provider))

        return errors

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

    def _execute_action(self, action: PostExecAction, provider: ActionProvider) -> list[str]:
        """Execute a single action, collecting failures.

        Returns:
            List of error messages from failed operations.
        """
        if not action.repo or not action.issue:
            return []

        errors: list[str] = []

        if action.type == "add_label":
            for label in action.add_labels:
                try:
                    provider.add_label(action.repo, action.issue, label)
                except Exception as e:
                    msg = f"Failed to add label '{label}': {e}"
                    errors.append(msg)
                    print(f"Warning: {msg}")
            for label in action.remove_labels:
                try:
                    provider.remove_label(action.repo, action.issue, label)
                except Exception as e:
                    msg = f"Failed to remove label '{label}': {e}"
                    errors.append(msg)
                    print(f"Warning: {msg}")

        elif action.type == "add_comment":
            if action.body:
                try:
                    provider.post_comment(action.repo, action.issue, action.body)
                except Exception as e:
                    msg = f"Failed to post comment: {e}"
                    errors.append(msg)
                    print(f"Warning: {msg}")

        return errors

    def _substitute_env_str(self, value: str, env: dict[str, str]) -> str:
        """Replace {{VAR}} placeholders with env values."""
        for key, val in env.items():
            value = value.replace(f"{{{{{key}}}}}", str(val))
        return value

    def _select_pr(self, prs: list[dict], repo: str) -> dict:
        """Select the next eligible PR, skipping recently-failed ones.

        Falls back to prs[0] when no history is configured.
        """
        if not self._history or not self._pjob_code:
            return prs[0]

        failures = self._history.get_recent_scan_pr_failures(self._pjob_code, 90)
        skip_set = set()
        for rec in failures:
            spr = rec.get("scan_pr_result")
            if spr:
                skip_set.add((spr.get("repo") or "", spr.get("pr_number") or ""))

        for pr in prs:
            pr_num = str(pr.get("number") or "")
            if (repo, pr_num) not in skip_set:
                return pr

        raise SkipAction(f"All {len(prs)} PR(s) recently attempted, skipping")

    def run_pre(self, actions: ActionsConfig, env: dict[str, str]) -> dict[str, str]:
        """Execute all preExec actions, return discovered variables.

        Args:
            actions: Actions configuration from PJob.
            env: Environment dict for {{VAR}} substitution in action fields.

        Returns:
            Dictionary of discovered variables (e.g., pr_number, pr_url, pr_diff).

        Raises:
            SkipAction: If a preExec action indicates no work to do.
        """
        discovered: dict[str, str] = {}
        try:
            provider = self._registry.get(actions.provider)
        except ProviderNotFoundError as e:
            print(f"Warning: {e}")
            return discovered

        for action in actions.pre_exec:
            if action.type == "scan_pr":
                repo = self._substitute_env_str(action.repo, env)
                label = self._substitute_env_str(action.label, env)
                prs = provider.scan_prs(repo, label)
                if not prs:
                    raise SkipAction(f"No PRs found with label '{label}' in {repo}")
                pr = self._select_pr(prs, repo)
                discovered["repo"] = repo
                discovered["pr_number"] = str(pr.get("number") or "")
                discovered["pr_title"] = pr.get("title") or ""
                discovered["pr_url"] = pr.get("url") or ""
                discovered["pr_diff"] = provider.fetch_diff(repo, discovered["pr_number"])
            else:
                print(f"Warning: Unknown preExec action type '{action.type}', skipping")

        return discovered
