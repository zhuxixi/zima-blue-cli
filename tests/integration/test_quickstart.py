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

        with patch("zima.commands.quickstart._detect_git_repo", return_value="/tmp/workspace"):
            with patch("zima.commands.quickstart._scan_with_command", return_value=[]):
                with patch("zima.commands.quickstart.typer.prompt", return_value="1"):
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

    def test_quickstart_custom_scene_non_interactive(self):
        """Test quickstart with custom scene."""
        from typer.testing import CliRunner

        from zima.cli import app

        runner = CliRunner()

        with patch("zima.commands.quickstart._detect_git_repo", return_value="/tmp/workspace"):
            with patch("zima.commands.quickstart.typer.prompt", return_value="1"):
                with patch("zima.commands.quickstart.typer.confirm", return_value=True):
                    result = runner.invoke(
                        app,
                        [
                            "quickstart",
                            "--scene",
                            "custom",
                            "--name",
                            "testcustom",
                            "--work-dir",
                            "/tmp/workspace",
                        ],
                    )

        assert result.exit_code == 0, result.output
        assert "testcustom-job" in result.output
        assert "zima pjob run" in result.output

    def test_quickstart_invalid_scene(self):
        """Test quickstart with invalid scene exits with error."""
        from typer.testing import CliRunner

        from zima.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["quickstart", "--scene", "nonexistent"])

        assert result.exit_code == 1
        assert "Invalid scene" in result.output

    def test_quickstart_cancelled(self):
        """Test quickstart when user cancels at summary."""
        from typer.testing import CliRunner

        from zima.cli import app

        runner = CliRunner()

        with patch("zima.commands.quickstart._detect_git_repo", return_value="/tmp/workspace"):
            with patch("zima.commands.quickstart.typer.prompt", return_value="1"):
                with patch("zima.commands.quickstart.typer.confirm", return_value=False):
                    result = runner.invoke(
                        app,
                        [
                            "quickstart",
                            "--scene",
                            "code-review",
                            "--name",
                            "testcancel",
                            "--work-dir",
                            "/tmp/workspace",
                        ],
                    )

        assert result.exit_code == 0
        assert "Cancelled" in result.output
