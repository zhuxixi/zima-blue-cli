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
            assert args == [
                "gh",
                "issue",
                "edit",
                "123",
                "--add-label",
                "zima:needs-fix",
                "--repo",
                "owner/repo",
            ]
            assert mock_run.call_args[1].get("stdin") == subprocess.DEVNULL

    def test_remove_label(self):
        """Verify correct gh issue edit --remove-label args."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.remove_label("owner/repo", "123", "zima:needs-review")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == [
                "gh",
                "issue",
                "edit",
                "123",
                "--remove-label",
                "zima:needs-review",
                "--repo",
                "owner/repo",
            ]

    def test_post_comment(self):
        """Verify correct gh issue comment args."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.post_comment("owner/repo", "123", "Review done")
            args = mock_run.call_args[0][0]
            assert args == [
                "gh",
                "issue",
                "comment",
                "123",
                "--body",
                "Review done",
                "--repo",
                "owner/repo",
            ]

    def test_post_comment_multiline(self):
        """Verify --body flag used for multiline comments."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.post_comment("owner/repo", "123", "Line 1\nLine 2")
            args = mock_run.call_args[0][0]
            assert args == [
                "gh",
                "issue",
                "comment",
                "123",
                "--body",
                "Line 1\nLine 2",
                "--repo",
                "owner/repo",
            ]

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
            assert args == [
                "gh",
                "pr",
                "view",
                "123",
                "--repo",
                "owner/repo",
                "--patch",
            ]

    def test_fetch_diff_failure_returns_empty(self):
        """Verify fetch_diff returns empty string on gh failure."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
            diff = provider.fetch_diff("owner/repo", "123")
            assert diff == ""

    def test_scan_prs(self):
        """Verify scan_prs calls gh pr list with correct args."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='[{"number":42,"title":"Fix bug","url":"https://github.com/o/r/pull/42"}]',
                stderr="",
            )
            prs = provider.scan_prs("owner/repo", "zima:needs-review")
            assert len(prs) == 1
            assert prs[0]["number"] == 42
            assert prs[0]["url"] == "https://github.com/o/r/pull/42"
            args = mock_run.call_args[0][0]
            assert args == [
                "gh",
                "pr",
                "list",
                "--repo",
                "owner/repo",
                "--label",
                "zima:needs-review",
                "--state",
                "open",
                "--json",
                "number,title,url,headRefName",
            ]

    def test_scan_prs_empty(self):
        """Verify scan_prs returns empty list when no PRs match."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            prs = provider.scan_prs("owner/repo", "zima:needs-review")
            assert prs == []

    def test_scan_prs_failure_raises(self):
        """Verify RuntimeError on gh failure."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="API error")
            with pytest.raises(RuntimeError, match="gh CLI failed"):
                provider.scan_prs("owner/repo", "zima:needs-review")

    def test_scan_prs_invalid_json_raises(self):
        """Verify RuntimeError on invalid JSON output."""
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="not-json", stderr="")
            with pytest.raises(RuntimeError, match="Failed to parse gh pr list output"):
                provider.scan_prs("owner/repo", "zima:needs-review")
