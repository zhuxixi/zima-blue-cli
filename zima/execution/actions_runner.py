"""Actions runner for executing preExec and postExec actions around agent execution."""

from __future__ import annotations

import re
import subprocess
import time
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


# Max accepted length for a pinned PR number: overlong values are INVALID
# (not truncated), keeping the runner and executor validation layers in
# agreement (#158 R15/R17).
PINNED_PR_MAX_LEN = 64


def normalize_pr_number(value: str) -> str:
    """Normalize a user-supplied PR number: strip whitespace and a leading
    ``#`` (common copy-paste form). Returns "" for empty input."""
    v = str(value or "").strip()
    if v.startswith("#"):
        v = v.lstrip("#").strip()
    return v


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

    def run_pre(
        self,
        actions: ActionsConfig,
        env: dict[str, str],
        workdir: Optional[str] = None,
        pin_env: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """Execute all preExec actions, return discovered variables.

        Args:
            actions: Actions configuration from PJob.
            env: Environment dict for {{VAR}} substitution in action fields.
            workdir: Working directory for git_pull action (agent's workDir).
            pin_env: Runtime-injected variable values only (``--set-var`` /
                webhook spawn). When provided, the pinned-PR short-circuit
                trusts only these — static Variable config values in ``env``
                never pin (#158 R2). ``None`` falls back to reading ``env``
                (direct callers / legacy behavior).

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
                if not repo or not repo.strip():
                    raise SkipAction(
                        f"preExec scan_pr skipped — repo resolved to empty "
                        f"(pjob={self._pjob_code or '?'}, original='{action.repo}')"
                    )
                if not label or not label.strip():
                    raise SkipAction(
                        f"preExec scan_pr skipped — label resolved to empty "
                        f"(pjob={self._pjob_code or '?'}, original='{action.label}')"
                    )
                # Caller pinned the exact PR (webhook event / manual --set-var):
                # trust it instead of rescanning the label. GitHub's search index
                # lags a few seconds behind the just-delivered label event, so a
                # rescan at trigger time can miss the PR that caused this very
                # run (#158). No pin -> daemon polling path, behavior unchanged.
                # Only runtime-injected values pin (pin_env from the executor's
                # overrides); static Variable config keys never pin (#158 R2).
                pin_source = pin_env if pin_env is not None else env
                # Normalize the common "#123" copy-paste form (#158 R3).
                # pr_number wins over the legacy pr name; whitespace-only
                # values are treated as absent so they cannot shadow a valid
                # alias value, and '#'-only candidates also fall through to
                # the next name — SkipAction fires only when NO candidate
                # yields a valid number (#158 R6/R7).
                pinned = ""
                _malformed_pin = False
                for _pin_key in ("pr_number", "pr"):
                    _raw = str(pin_source.get(_pin_key) or "").strip()
                    if not _raw:
                        continue
                    _norm = normalize_pr_number(_raw)
                    if _norm:
                        pinned = _norm
                        break
                    _malformed_pin = True
                if _malformed_pin and not pinned:
                    raise SkipAction(
                        "preExec scan_pr skipped — pinned pr value is only a "
                        f"'#' prefix with no digits, pjob={self._pjob_code or '?'}"
                    )
                # Length is part of validity, aligned with the executor's
                # scan validation gate (<=64) so both layers agree (#158 R15)
                if pinned and not (re.fullmatch(r"[0-9]+", pinned) and len(pinned) <= 64):
                    # Malformed manual input (typo in --set-var): fail fast.
                    # Only report the length, never echo the raw value (#158 R2).
                    raise SkipAction(
                        f"preExec scan_pr skipped — pinned pr value is not a "
                        f"valid number (non-numeric or overlong; len={len(pinned)}), "
                        f"pjob={self._pjob_code or '?'}"
                    )
                if pinned:
                    print(
                        f"scan_pr: pinned PR #{pinned} in {repo} "
                        f"(runtime-injected), skipping label rescan"
                    )
                    discovered["repo"] = repo
                    discovered["pr_number"] = pinned
                    discovered["pr_title"] = ""
                    discovered["pr_url"] = f"https://github.com/{repo}/pull/{pinned}"
                    # Keep the pr_diff contract of the scan path: fetch_diff
                    # reads the PR directly (gh pr view), not the search index,
                    # so it does not reintroduce the #158 race. An empty/failed
                    # diff must NOT flow into a hollow review: fail fast with
                    # SkipAction (SKIPPED skips postExec, label stays for a
                    # re-run) instead of "reviewing" an empty diff (#158 R2).
                    # Transient gh failures get a short bounded retry first
                    # (#158 R3/R4): attempts 3x with 1s/2s backoff. An empty
                    # string ALSO retries — GitHubProvider.fetch_diff returns
                    # "" for gh non-zero exit (check=False), so rate-limit /
                    # network blips surface as empty, not raised.
                    diff = ""
                    last_exc: Optional[Exception] = None
                    for attempt in range(3):
                        try:
                            diff = provider.fetch_diff(repo, pinned)
                            if diff:
                                last_exc = None
                                break
                        except Exception as e:  # noqa: BLE001 - retry, then skip
                            last_exc = e
                        if attempt < 2:
                            time.sleep(1.0 * (attempt + 1))
                    if last_exc is not None:
                        raise SkipAction(
                            f"preExec scan_pr skipped — fetch_diff raised for "
                            f"pinned PR #{pinned} after 3 attempts "
                            f"(possibly transient — re-label to retry): {last_exc}"
                        ) from last_exc
                    if not diff:
                        raise SkipAction(
                            f"preExec scan_pr skipped — fetch_diff returned an "
                            f"empty diff for pinned PR #{pinned} (gh failed or "
                            f"no patch); not reviewing without a diff — "
                            f"re-label to retry"
                        )
                    discovered["pr_diff"] = diff
                    continue
                prs = provider.scan_prs(repo, label)
                if not prs:
                    raise SkipAction(f"No PRs found with label '{label}' in {repo}")
                pr = self._select_pr(prs, repo)
                discovered["repo"] = repo
                discovered["pr_number"] = str(pr.get("number") or "")
                discovered["pr_title"] = pr.get("title") or ""
                discovered["pr_url"] = pr.get("url") or ""
                discovered["pr_diff"] = provider.fetch_diff(repo, discovered["pr_number"])
            elif action.type == "git_pull":
                if not workdir:
                    print("Warning: git_pull skipped, no workdir configured")
                else:
                    try:
                        pull_result = subprocess.run(
                            ["git", "pull", "--no-verify"],
                            cwd=workdir,
                            stdin=subprocess.DEVNULL,
                            capture_output=True,
                            text=True,
                            errors="replace",
                            timeout=60,
                        )
                        if pull_result.returncode != 0:
                            print(
                                f"Warning: git pull failed in {workdir} (rc={pull_result.returncode})"
                            )
                    except subprocess.TimeoutExpired:
                        print(f"Warning: git pull timed out in {workdir}")
                    except (FileNotFoundError, OSError) as e:
                        print(f"Warning: git pull failed in {workdir}: {e}")
            else:
                print(f"Warning: Unknown preExec action type '{action.type}', skipping")

        return discovered
