from unittest.mock import MagicMock, patch

import pytest

from zima.actions.exceptions import ProviderNotFoundError
from zima.execution.actions_runner import ActionsRunner, SkipAction, _matches_condition
from zima.models.actions import ActionsConfig, PostExecAction


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
        from zima.models.actions import PreExecAction

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
        from zima.models.actions import PreExecAction

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
        from zima.models.actions import PreExecAction

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
        from zima.models.actions import PreExecAction

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


class TestActionsRunnerPreExecSkipLogic:
    def _make_actions(self, repo="owner/repo", label="zima:needs-review"):
        from zima.models.actions import PreExecAction

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
