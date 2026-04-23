"""Integration tests for quickstart wizard."""

from unittest.mock import patch

from tests.base import TestIsolator


class TestQuickstartCommand(TestIsolator):
    """Test quickstart CLI command."""

    def test_quickstart_code_review_non_interactive(self):
        """Test quickstart with pre-selected options (minimal interaction)."""
        from typer.testing import CliRunner

        from zima.cli import app

        runner = CliRunner()

        # Mock interactive inputs: agent=1, confirm=True, confirm=True
        with patch("zima.commands.quickstart._detect_git_repo", return_value="/tmp/workspace"):
            with patch("zima.commands.quickstart._scan_github_prs", return_value=[]):
                with patch("zima.commands.quickstart.typer.prompt", side_effect=["1", "1"]):
                    with patch("zima.commands.quickstart.typer.confirm", return_value=True):
                        result = runner.invoke(
                            app,
                            [
                                "quickstart",
                                "--scene",
                                "code-review",
                                "--name",
                                "testqs",
                                "--work-dir",
                                "/tmp/workspace",
                            ],
                        )

        assert result.exit_code == 0, result.output
        assert "Created" in result.output or "created" in result.output
        assert "testqs-job" in result.output
        assert "zima pjob run" in result.output
        assert "--dry-run" in result.output
