from unittest.mock import MagicMock, patch

from zima.models.actions import ActionsConfig, PostExecAction
from zima.execution.actions_runner import ActionsRunner, _matches_condition
from zima.review.parser import ReviewResult


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
                    type="github_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        with patch.object(runner, "_ops") as mock_ops:
            runner.run(actions, returncode=0, env={})
            mock_ops.add_label.assert_called_once_with("owner/repo", 123, "zima:needs-fix")
            mock_ops.remove_label.assert_called_once_with("owner/repo", 123, "zima:needs-review")

    def test_run_failure_action_not_triggered_on_success(self):
        """Test failure actions are skipped on success."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="github_comment",
                    body="Failed",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        with patch.object(runner, "_ops") as mock_ops:
            runner.run(actions, returncode=0, env={})
            mock_ops.post_comment.assert_not_called()

    def test_run_comment_action(self):
        """Test running comment action."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="github_comment",
                    body="Review complete: approved",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        with patch.object(runner, "_ops") as mock_ops:
            runner.run(actions, returncode=0, env={})
            mock_ops.post_comment.assert_called_once_with(
                "owner/repo", 123, "Review complete: approved"
            )

    def test_run_env_variable_substitution(self):
        """Test environment variable substitution in action fields."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="github_comment",
                    body="Repo: {{REPO}} Issue: {{ISSUE}}",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        with patch.object(runner, "_ops") as mock_ops:
            runner.run(
                actions,
                returncode=0,
                env={"REPO": "my-org/my-repo", "ISSUE": "42"},
            )
            called_body = mock_ops.post_comment.call_args[0][2]
            assert "my-org/my-repo" in called_body
            assert "42" in called_body

    def test_run_failure_condition(self):
        """Test runner matches failure condition with non-zero returncode."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="github_comment",
                    body="Failed",
                    repo="o/r",
                    issue="1",
                )
            ]
        )
        with patch.object(runner, "_ops") as mock_ops:
            runner.run(actions, returncode=1, env={})
            mock_ops.post_comment.assert_called_once_with("o/r", 1, "Failed")

    def test_run_skips_without_repo_or_issue(self):
        """Test actions without repo/issue are silently skipped."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="github_label",
                    add_labels=["x"],
                )
            ]
        )
        with patch.object(runner, "_ops") as mock_ops:
            runner.run(actions, returncode=0, env={})
            mock_ops.add_label.assert_not_called()
