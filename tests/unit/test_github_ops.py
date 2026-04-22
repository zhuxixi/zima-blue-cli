from unittest.mock import MagicMock, patch

import pytest

from zima.github.ops import GitHubOps


class TestGitHubOps:
    def test_add_label(self):
        """Test adding a label to an issue/PR."""
        ops = GitHubOps()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ops.add_label("owner/repo", 123, "zima:needs-fix")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "gh" in args
            assert "issue" in args
            assert "edit" in args
            assert "123" in args
            assert "--add-label" in args
            assert "zima:needs-fix" in args
            assert "--repo" in args
            assert "owner/repo" in args

    def test_remove_label(self):
        """Test removing a label from an issue/PR."""
        ops = GitHubOps()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ops.remove_label("owner/repo", 123, "zima:needs-review")
            args = mock_run.call_args[0][0]
            assert "--remove-label" in args
            assert "zima:needs-review" in args

    def test_post_comment(self):
        """Test posting a comment on an issue/PR."""
        ops = GitHubOps()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ops.post_comment("owner/repo", 123, "Review done")
            args = mock_run.call_args[0][0]
            assert "comment" in args
            assert "--body" in args
            assert "Review done" in args

    def test_post_comment_multiline(self):
        """Test posting a multiline comment uses --body flag."""
        ops = GitHubOps()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ops.post_comment("owner/repo", 123, "Line 1\nLine 2")
            args = mock_run.call_args[0][0]
            assert "--body" in args

    def test_add_label_failure_raises(self):
        """Test that gh CLI failure raises RuntimeError."""
        ops = GitHubOps()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="label not found"
            )
            with pytest.raises(RuntimeError, match="GitHub CLI failed"):
                ops.add_label("owner/repo", 123, "bad-label")

    def test_fetch_pr_diff(self):
        """Test fetching PR diff via gh pr view --patch."""
        ops = GitHubOps()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="diff --git a/foo.py b/foo.py", stderr=""
            )
            diff = ops.fetch_pr_diff("owner/repo", 123)
            assert diff == "diff --git a/foo.py b/foo.py"
            args = mock_run.call_args[0][0]
            assert "pr" in args
            assert "view" in args
            assert "--patch" in args
            assert "123" in args
