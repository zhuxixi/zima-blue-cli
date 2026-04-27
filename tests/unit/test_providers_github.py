"""Unit tests for GitHubProvider."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from zima.providers.github import GitHubProvider


class TestGitHubProvider:
    def test_name(self):
        """Verify provider name is 'github'."""
        provider = GitHubProvider()
        assert provider.name == "github"

    def test_add_label(self):
        """Verify correct gh issue edit args for adding a label."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.add_label("owner/repo", "123", "zima:needs-fix")
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
            assert mock_run.call_args[1].get("stdin") == subprocess.DEVNULL

    def test_remove_label(self):
        """Verify correct gh issue edit --remove-label args."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.remove_label("owner/repo", "123", "zima:needs-review")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "--remove-label" in args
            assert "zima:needs-review" in args

    def test_post_comment(self):
        """Verify correct gh issue comment args."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.post_comment("owner/repo", "123", "Review done")
            args = mock_run.call_args[0][0]
            assert "comment" in args
            assert "--body" in args
            assert "Review done" in args

    def test_post_comment_multiline(self):
        """Verify --body flag used for multiline comments."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.post_comment("owner/repo", "123", "Line 1\nLine 2")
            args = mock_run.call_args[0][0]
            assert "--body" in args

    def test_add_label_failure_raises(self):
        """Verify RuntimeError on gh failure."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="label not found")
            with pytest.raises(RuntimeError, match="gh CLI failed"):
                provider.add_label("owner/repo", "123", "bad-label")

    def test_fetch_diff(self):
        """Verify gh pr view --patch args and return value."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="diff --git a/foo.py b/foo.py", stderr=""
            )
            diff = provider.fetch_diff("owner/repo", "123")
            assert diff == "diff --git a/foo.py b/foo.py"
            args = mock_run.call_args[0][0]
            assert "pr" in args
            assert "view" in args
            assert "--patch" in args
            assert "123" in args

    def test_fetch_diff_failure_returns_empty(self):
        """Verify fetch_diff returns empty string on gh failure."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
            diff = provider.fetch_diff("owner/repo", "123")
            assert diff == ""
