from unittest.mock import MagicMock, patch

import pytest

from zima.actions.exceptions import ProviderNotFoundError
from zima.execution.actions_runner import ActionsRunner, SkipAction, _matches_condition
from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction


class TestMatchesCondition:
    def test_success_with_zero_returncode(self):
        """Test success condition matches zero returncode."""
        assert _matches_condition("success", returncode=0) is True

    def test_success_with_nonzero_returncode(self):
        """Test success condition does not match non-zero returncode."""
        assert _matches_condition("success", returncode=1) is False

    def test_failure_with_nonzero_returncode(self):
        """Test failure condition matches non-zero returncode."""
        assert _matches_condition("failure", returncode=1) is True

    def test_failure_with_zero_returncode(self):
        """Test failure condition does not match zero returncode."""
        assert _matches_condition("failure", returncode=0) is False

    def test_always_matches(self):
        """Test always condition matches any returncode."""
        assert _matches_condition("always", returncode=0) is True
        assert _matches_condition("always", returncode=1) is True


class TestActionsRunner:
    def test_run_no_actions(self):
        """Test runner with no actions does nothing."""
        runner = ActionsRunner()
        runner.run(ActionsConfig(), returncode=0, env={})
        # Should not raise

    def test_run_success_action(self):
        """Test running success-conditioned label actions."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.add_label.assert_called_once_with("owner/repo", "123", "zima:needs-fix")
            mock_provider.remove_label.assert_called_once_with(
                "owner/repo", "123", "zima:needs-review"
            )

    def test_run_failure_action_not_triggered_on_success(self):
        """Test failure actions are skipped on success."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_comment",
                    body="Failed",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.post_comment.assert_not_called()

    def test_run_comment_action(self):
        """Test running comment action."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_comment",
                    body="Review complete: approved",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.post_comment.assert_called_once_with(
                "owner/repo", "123", "Review complete: approved"
            )

    def test_run_env_variable_substitution(self):
        """Test environment variable substitution in action fields."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_comment",
                    body="Repo: {{REPO}} Issue: {{ISSUE}}",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(
                actions,
                returncode=0,
                env={"REPO": "my-org/my-repo", "ISSUE": "42"},
            )
            called_body = mock_provider.post_comment.call_args[0][2]
            assert "my-org/my-repo" in called_body
            assert "42" in called_body

    def test_run_failure_condition(self):
        """Test runner matches failure condition with non-zero returncode."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_comment",
                    body="Failed",
                    repo="o/r",
                    issue="1",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=1, env={})
            mock_provider.post_comment.assert_called_once_with("o/r", "1", "Failed")

    def test_run_skips_without_repo_or_issue(self):
        """Test actions without repo/issue are silently skipped."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["x"],
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.add_label.assert_not_called()

    def test_run_custom_provider(self):
        """Test runner resolves a custom provider from the registry."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            provider="gitlab",
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["bug"],
                    repo="owner/repo",
                    issue="42",
                )
            ],
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider) as mock_get:
            runner.run(actions, returncode=0, env={})
            mock_get.assert_called_once_with("gitlab")
            mock_provider.add_label.assert_called_once_with("owner/repo", "42", "bug")

    def test_run_provider_not_found_warns_and_returns(self, capsys):
        """Test runner warns and returns when provider is not found."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            provider="nonexistent",
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["bug"],
                    repo="owner/repo",
                    issue="42",
                )
            ],
        )
        with patch.object(
            runner._registry,
            "get",
            side_effect=ProviderNotFoundError("Provider 'nonexistent' not found"),
        ):
            errors = runner.run(actions, returncode=0, env={})
            captured = capsys.readouterr()
            assert "Warning" in captured.out
            assert "nonexistent" in captured.out
            assert len(errors) == 1


class TestActionsRunnerErrorPropagation:
    """Regression tests for #92: postExec action failures must propagate."""

    def test_add_label_failure_returns_error(self, capsys):
        """Failed add_label returns error message instead of swallowing."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["zima:reviewed"],
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        mock_provider = MagicMock()
        mock_provider.add_label.side_effect = PermissionError("token lacks scope")
        with patch.object(runner._registry, "get", return_value=mock_provider):
            errors = runner.run(actions, returncode=0, env={})
        assert len(errors) == 1
        assert "Failed to add label" in errors[0]
        assert "token lacks scope" in errors[0]
        captured = capsys.readouterr()
        assert "Warning" in captured.out

    def test_remove_label_failure_returns_error(self, capsys):
        """Failed remove_label returns error message."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        mock_provider = MagicMock()
        mock_provider.remove_label.side_effect = PermissionError("insufficient permissions")
        with patch.object(runner._registry, "get", return_value=mock_provider):
            errors = runner.run(actions, returncode=0, env={})
        assert len(errors) == 1
        assert "Failed to remove label" in errors[0]
        assert "insufficient permissions" in errors[0]

    def test_post_comment_failure_returns_error(self, capsys):
        """Failed post_comment returns error message."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_comment",
                    body="Done",
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        mock_provider = MagicMock()
        mock_provider.post_comment.side_effect = ConnectionError("network down")
        with patch.object(runner._registry, "get", return_value=mock_provider):
            errors = runner.run(actions, returncode=0, env={})
        assert len(errors) == 1
        assert "Failed to post comment" in errors[0]
        assert "network down" in errors[0]

    def test_mixed_success_and_failure_collects_all_errors(self):
        """Multiple action failures are all collected."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["ok"],
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        mock_provider = MagicMock()
        mock_provider.add_label.return_value = None  # succeeds
        mock_provider.remove_label.side_effect = PermissionError("nope")
        with patch.object(runner._registry, "get", return_value=mock_provider):
            errors = runner.run(actions, returncode=0, env={})
        assert len(errors) == 1
        assert "Failed to remove label" in errors[0]
        mock_provider.add_label.assert_called_once()

    def test_successful_actions_return_empty_errors(self):
        """No errors returned when all actions succeed."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["ok"],
                    remove_labels=["old"],
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            errors = runner.run(actions, returncode=0, env={})
        assert errors == []


class TestActionsRunnerPreExec:
    def test_run_pre_exec_scan_pr(self):
        """Test running preExec scan_pr action returns discovered variables."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[
                PreExecAction(
                    type="scan_pr",
                    repo="owner/repo",
                    label="zima:needs-review",
                )
            ]
        )
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/o/r/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "diff content"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            env = {}
            result = runner.run_pre(actions, env)
            mock_provider.scan_prs.assert_called_once_with("owner/repo", "zima:needs-review")
            mock_provider.fetch_diff.assert_called_once_with("owner/repo", "42")
            assert result == {
                "repo": "owner/repo",
                "pr_number": "42",
                "pr_title": "Fix",
                "pr_url": "https://github.com/o/r/pull/42",
                "pr_diff": "diff content",
            }
            assert "pr_number" not in env

    def test_run_pre_exec_empty_result(self):
        """Test preExec scan_pr with no results raises SkipAction."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="scan_pr", repo="owner/repo", label="x")]
        )
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = []
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(actions, {})
            assert "no prs found" in str(exc_info.value).lower()

    def test_run_pre_provider_not_found(self, capsys):
        """Test run_pre warns and returns empty dict when provider is not found."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            provider="nonexistent",
            pre_exec=[PreExecAction(type="scan_pr", repo="owner/repo", label="x")],
        )
        with patch.object(
            runner._registry,
            "get",
            side_effect=ProviderNotFoundError("Provider 'nonexistent' not found"),
        ):
            env = {"existing": "value"}
            result = runner.run_pre(actions, env)
            captured = capsys.readouterr()
            assert "Warning" in captured.out
            assert "nonexistent" in captured.out
            assert result == {}
            assert env == {"existing": "value"}

    def test_run_pre_exec_env_substitution(self):
        """Test env variable substitution in run_pre before calling scan_prs."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[
                PreExecAction(
                    type="scan_pr",
                    repo="{{repo}}",
                    label="{{label}}",
                )
            ]
        )
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "7", "title": "Test", "url": "https://github.com/o/r/pull/7"}
        ]
        mock_provider.fetch_diff.return_value = "diff data"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            env = {"repo": "my-org/my-repo", "label": "needs-review"}
            result = runner.run_pre(actions, env)
            mock_provider.scan_prs.assert_called_once_with("my-org/my-repo", "needs-review")
            mock_provider.fetch_diff.assert_called_once_with("my-org/my-repo", "7")
            assert result["repo"] == "my-org/my-repo"
            assert result["pr_number"] == "7"
            assert result["pr_diff"] == "diff data"

    def test_git_pull_success(self):
        """Test git_pull runs git pull in workdir and returns empty dict."""
        import subprocess as _subprocess

        runner = ActionsRunner()
        actions = ActionsConfig(pre_exec=[PreExecAction(type="git_pull")])
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = runner.run_pre(actions, {}, workdir="/path/to/repo")
        mock_run.assert_called_once_with(
            ["git", "pull", "--no-verify"],
            cwd="/path/to/repo",
            stdin=_subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
        assert result == {}

    def test_git_pull_failure_continues(self, capsys):
        """Test git_pull with non-zero returncode logs warning without stderr."""
        runner = ActionsRunner()
        actions = ActionsConfig(pre_exec=[PreExecAction(type="git_pull")])
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="merge conflict")
                result = runner.run_pre(actions, {}, workdir="/path/to/repo")
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "rc=1" in captured.out
        assert "merge conflict" not in captured.out
        assert result == {}

    def test_git_pull_timeout(self, capsys):
        """Test git_pull timeout logs warning and continues."""
        import subprocess as _subprocess

        runner = ActionsRunner()
        actions = ActionsConfig(pre_exec=[PreExecAction(type="git_pull")])
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                mock_run.side_effect = _subprocess.TimeoutExpired(cmd="git pull", timeout=60)
                result = runner.run_pre(actions, {}, workdir="/path/to/repo")
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "timed out" in captured.out
        assert result == {}

    def test_git_pull_no_workdir(self, capsys):
        """Test git_pull skipped with warning when no workdir configured."""
        runner = ActionsRunner()
        actions = ActionsConfig(pre_exec=[PreExecAction(type="git_pull")])
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                result = runner.run_pre(actions, {})
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "no workdir" in captured.out
        mock_run.assert_not_called()
        assert result == {}

    def test_git_pull_file_not_found(self, capsys):
        """Test git_pull with FileNotFoundError (git not on PATH) logs warning."""
        runner = ActionsRunner()
        actions = ActionsConfig(pre_exec=[PreExecAction(type="git_pull")])
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("git not found")
                result = runner.run_pre(actions, {}, workdir="/path/to/repo")
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "git not found" in captured.out
        assert result == {}


class TestRunPrePinnedPr:
    """Pinned-PR short-circuit (#158): env pr_number/pr set by the webhook
    spawn or manual --set-var means the exact PR is known — skip the label
    rescan (GitHub search index lags the just-delivered label event)."""

    def _make_actions(self, repo="owner/repo"):
        return ActionsConfig(
            pre_exec=[PreExecAction(type="scan_pr", repo=repo, label="zima:needs-review")]
        )

    def test_pinned_pr_number_skips_rescan(self):
        """env pr_number pinned -> provider.scan_prs NOT called, values constructed."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": "11"})
            mock_provider.scan_prs.assert_not_called()
            # pr_diff contract is kept (direct gh pr view, no search-index race)
            mock_provider.fetch_diff.assert_called_once_with("owner/repo", "11")
            assert result == {
                "repo": "owner/repo",
                "pr_number": "11",
                "pr_title": "",
                "pr_url": "https://github.com/owner/repo/pull/11",
                "pr_diff": "+diff",
            }

    def test_pinned_fetch_diff_raising_raises_skip(self):
        """fetch_diff raising during a pinned run -> SkipAction (label stays
        for a re-run; no hollow review)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.side_effect = RuntimeError("gh down")
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": "11"})
            assert "fetch_diff raised" in str(exc_info.value)

    def test_pinned_fetch_diff_empty_raises_skip(self):
        """fetch_diff returning an empty string (gh check=False silent fail)
        -> SkipAction; never review an empty diff (#158 R2)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = ""
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": "11"})
            assert "empty diff" in str(exc_info.value)

    def test_pin_env_is_the_only_pin_source_when_provided(self):
        """With pin_env provided (executor path), a pr_number that exists only
        in the merged env (static Variable config) must NOT pin (#158 R2)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/o/r/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "d"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(
                self._make_actions(),
                env={"pr_number": "11"},  # static config value in merged env
                pin_env={},  # nothing runtime-injected
            )
            # No pin: the label rescan ran and discovered PR 42
            mock_provider.scan_prs.assert_called_once_with("owner/repo", "zima:needs-review")
            assert result["pr_number"] == "42"

    def test_pin_env_pins_even_when_env_lacks_it(self):
        """With pin_env provided, a runtime-only pr_number pins even though the
        merged env does not carry it."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(
                self._make_actions(),
                env={},
                pin_env={"pr_number": "11"},
            )
            mock_provider.scan_prs.assert_not_called()
            assert result["pr_number"] == "11"
            assert result["pr_diff"] == "+diff"

    def test_pinned_mixed_exception_then_empty_reports_last_mode(self):
        """Mixed retry sequence (raise, then empty) reports the LAST failure
        mode (empty diff), not the expired exception (#158 R22)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.side_effect = [RuntimeError("gh down"), "", ""]
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.time.sleep"):
                with pytest.raises(SkipAction) as exc_info:
                    runner.run_pre(self._make_actions(), {"pr_number": "11"})
            msg = str(exc_info.value)
            assert "empty diff" in msg
            assert "gh down" not in msg  # expired exception not reported
            assert "re-label to retry" in msg

    def test_pinned_hash_prefix_normalized(self):
        """ "#11" (common copy-paste form) normalizes to 11 and pins (#158 R3)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+d"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": "#11"})
            mock_provider.scan_prs.assert_not_called()
            assert result["pr_number"] == "11"
            assert result["pr_url"].endswith("/pull/11")

    def test_pinned_fetch_diff_retries_then_raises_skip(self):
        """fetch_diff raising twice then succeeding still completes (#158 R3)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.side_effect = [
            RuntimeError("gh down"),
            RuntimeError("gh down"),
            "+diff",
        ]
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.time.sleep") as mock_sleep:
                result = runner.run_pre(self._make_actions(), {"pr_number": "11"})
            assert mock_sleep.call_count == 2
            assert result["pr_diff"] == "+diff"

    def test_pin_env_not_provided_reads_env(self):
        """Legacy direct callers (pin_env=None) still read merged env —
        backwards compatibility for library use."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+d"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": "11"})
            assert result["pr_number"] == "11"

    def test_whitespace_pr_number_does_not_shadow_alias(self):
        """pr_number=' ' (manual typo) is treated as absent; a valid legacy
        pr value still pins (#158 R6)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+d"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": " ", "pr": "11"})
            mock_provider.scan_prs.assert_not_called()
            assert result["pr_number"] == "11"

    def test_hash_only_pr_number_falls_through_to_alias(self):
        """(pr_number='#', pr='11'): the '#'-only candidate does not block the
        valid alias — pins 11 (#158 R7)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+d"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": "#", "pr": "11"})
            mock_provider.scan_prs.assert_not_called()
            assert result["pr_number"] == "11"

    def test_all_invalid_pin_candidates_raise_skip(self):
        """(pr_number=' ', pr='#'): no valid candidate and one malformed ->
        SkipAction (#158 R7)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": " ", "pr": "#"})
            mock_provider.scan_prs.assert_not_called()
            assert "'#' prefix" in str(exc_info.value)

    def test_pinned_hash_only_raises_skip(self):
        """ "#" with no digits fails fast instead of silently unpinning (#158 R4)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": "#"})
            mock_provider.scan_prs.assert_not_called()
            assert "'#' prefix" in str(exc_info.value)

    def test_pinned_empty_diff_retries_then_skips(self):
        """Empty diff results also retry (gh check=False silent fail) and end
        in SkipAction, never a hollow review (#158 R4)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = ""
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.time.sleep") as mock_sleep:
                with pytest.raises(SkipAction) as exc_info:
                    runner.run_pre(self._make_actions(), {"pr_number": "11"})
            assert mock_provider.fetch_diff.call_count == 3
            assert mock_sleep.call_count == 2
            assert "empty diff" in str(exc_info.value)

    def test_malformed_pinned_raises_skip(self):
        """Non-numeric pinned value fails fast via SkipAction (no rescan, no
        mixed state, raw value not echoed — only its length)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": "abc"})
            mock_provider.scan_prs.assert_not_called()
            msg = str(exc_info.value)
            assert "not a valid number" in msg
            assert "abc" not in msg  # raw value never echoed
            assert "len=3" in msg

    def test_pinned_pr_legacy_name(self):
        """env pr (legacy webhook name) also pins."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr": "11"})
            mock_provider.scan_prs.assert_not_called()
            assert result["pr_number"] == "11"

    def test_pinned_pr_number_wins_over_legacy(self):
        """Both set -> pr_number takes precedence."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": "11", "pr": "22"})
            assert result["pr_number"] == "11"

    def test_pinned_pr_number_stripped(self):
        """Whitespace-only padding around the pinned value is stripped."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": " 11 "})
            assert result["pr_number"] == "11"

    def test_empty_pinned_falls_back_to_rescan(self):
        """pr_number set but empty -> original rescan path (with results)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/o/r/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "diff content"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": ""})
            mock_provider.scan_prs.assert_called_once_with("owner/repo", "zima:needs-review")
            assert result["pr_number"] == "42"

    def test_no_pinned_calls_scan_prs(self):
        """No pinned vars at all -> scan_prs called (regression lock)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/o/r/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "d"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run_pre(self._make_actions(), {})
            mock_provider.scan_prs.assert_called_once()

    def test_pinned_with_empty_repo_still_skips(self):
        """Guard order: empty-repo guard precedes the pinned branch."""
        runner = ActionsRunner()
        actions = self._make_actions(repo="")
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(actions, {"pr_number": "11"})
            assert "repo resolved to empty" in str(exc_info.value)

    def test_pinned_wins_over_empty_rescan(self):
        """The #158 bug itself: pinned set + rescan would return [] -> no SkipAction."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = []
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": "11"})
            mock_provider.scan_prs.assert_not_called()
            assert result["pr_number"] == "11"


class TestActionsRunnerPreExecSkipLogic:
    def _make_actions(self, repo="owner/repo", label="zima:needs-review"):
        return ActionsConfig(pre_exec=[PreExecAction(type="scan_pr", repo=repo, label=label)])

    def test_no_history_falls_back_to_first_pr(self):
        """Without history, picks the first PR (prs[0] behavior)."""
        runner = ActionsRunner()
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
            {"number": "20", "title": "PR 20", "url": "url20"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "10"

    def test_skips_recently_failed_pr(self):
        """Skips a PR that failed within the time window."""
        mock_history = MagicMock()
        mock_history.get_recent_scan_pr_failures.return_value = [
            {"scan_pr_result": {"repo": "owner/repo", "pr_number": "10"}}
        ]
        runner = ActionsRunner(history=mock_history, pjob_code="reviewer")
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
            {"number": "20", "title": "PR 20", "url": "url20"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "20"
        mock_history.get_recent_scan_pr_failures.assert_called_once_with("reviewer", 90)

    def test_skips_all_raises_skip_action(self):
        """Raises SkipAction when all PRs were recently attempted."""
        mock_history = MagicMock()
        mock_history.get_recent_scan_pr_failures.return_value = [
            {"scan_pr_result": {"repo": "owner/repo", "pr_number": "10"}},
            {"scan_pr_result": {"repo": "owner/repo", "pr_number": "20"}},
        ]
        runner = ActionsRunner(history=mock_history, pjob_code="reviewer")
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
            {"number": "20", "title": "PR 20", "url": "url20"},
        ]
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(actions, {})
            assert "recently attempted" in str(exc_info.value).lower()

    def test_no_history_param_skips_query(self):
        """When history is None, no query is made and first PR is picked."""
        runner = ActionsRunner(history=None, pjob_code="reviewer")
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "10"

    def test_empty_repo_raises_skip_action(self):
        """Empty repo after substitution raises SkipAction instead of crashing."""
        runner = ActionsRunner(pjob_code="my-reviewer")
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review")]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(actions, {"repo": ""})
            mock_provider.scan_prs.assert_not_called()
            assert "repo resolved to empty" in str(exc_info.value)
            assert "my-reviewer" in str(exc_info.value)

    def test_whitespace_repo_raises_skip_action(self):
        """Whitespace-only repo raises SkipAction."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review")]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(actions, {"repo": "   "})
            mock_provider.scan_prs.assert_not_called()
            assert "repo resolved to empty" in str(exc_info.value)

    def test_empty_label_raises_skip_action(self):
        """Empty label after substitution raises SkipAction."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="scan_pr", repo="owner/repo", label="{{label}}")]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(actions, {"label": ""})
            mock_provider.scan_prs.assert_not_called()
            assert "label resolved to empty" in str(exc_info.value)

    def test_different_repo_not_skipped(self):
        """A failed PR on a different repo does not cause skipping."""
        mock_history = MagicMock()
        mock_history.get_recent_scan_pr_failures.return_value = [
            {"scan_pr_result": {"repo": "other/repo", "pr_number": "10"}},
        ]
        runner = ActionsRunner(history=mock_history, pjob_code="reviewer")
        actions = self._make_actions(repo="owner/repo")
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "10"

    def test_overlong_pinned_fails_fast(self):
        """A >64-digit pinned pr_number fails the length part of validity
        (#158 R15, aligned with the executor scan gate)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": "1" * 65})
            mock_provider.scan_prs.assert_not_called()
            assert "non-numeric or overlong" in str(exc_info.value)


class TestPinnedLabelRecheck:
    """#158 R22 security: the pinned fast path re-verifies the trigger label
    via a direct API call before trusting an injected pin."""

    def _make_actions(self, repo="owner/repo"):
        return ActionsConfig(
            pre_exec=[PreExecAction(type="scan_pr", repo=repo, label="zima:needs-review")]
        )

    def test_pinned_label_absent_raises_skip(self):
        """A pin whose PR does NOT carry the label (forged event) is
        rejected — no review, no postExec (#158 R22)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.verify_pr_label.return_value = False
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": "11"})
            mock_provider.verify_pr_label.assert_called_once_with(
                "owner/repo", "11", "zima:needs-review"
            )
            mock_provider.fetch_diff.assert_not_called()
            assert "does not carry label" in str(exc_info.value)

    def test_pinned_label_present_proceeds(self):
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.verify_pr_label.return_value = True
        mock_provider.fetch_diff.return_value = "+d"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(self._make_actions(), {"pr_number": "11"})
            assert result["pr_number"] == "11"

    def test_pin_consumed_after_first_scan_action(self):
        """Multi-action PJob: the second scan_pr action must NOT re-apply the
        consumed pin against its own repo (#158 R22)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.verify_pr_label.return_value = True
        mock_provider.fetch_diff.return_value = "+d"
        mock_provider.scan_prs.return_value = [{"number": "42", "title": "T", "url": "u"}]
        actions = ActionsConfig(
            pre_exec=[
                PreExecAction(type="scan_pr", repo="owner/one", label="zima:needs-review"),
                PreExecAction(type="scan_pr", repo="owner/two", label="zima:needs-review"),
            ]
        )
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, env={}, pin_env={"pr_number": "11"})
            # First action pinned; second action fell back to its own label scan
            mock_provider.verify_pr_label.assert_called_once()
            assert mock_provider.scan_prs.call_count == 1
            assert result["pr_number"] == "42"  # second action's scan won

    def test_pinned_verify_raising_fails_closed(self):
        """verify_pr_label raising (gh timeout/missing) must fail closed via
        SkipAction, never propagate into the preExec path (#158 R23)."""
        runner = ActionsRunner()
        mock_provider = MagicMock()
        mock_provider.verify_pr_label.side_effect = RuntimeError("gh gone")
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(self._make_actions(), {"pr_number": "11"})
            mock_provider.fetch_diff.assert_not_called()
            assert "does not carry label" in str(exc_info.value)
