"""Integration tests for zima webhook-server command."""

from typer.testing import CliRunner

from tests.conftest import strip_ansi
from zima.cli import app

runner = CliRunner()


class TestWebhookServerCommand:
    """Tests for 'zima webhook-server'."""

    def test_help_shows_options(self):
        """Help text includes required options."""
        result = runner.invoke(app, ["webhook-server", "--help"])
        clean = strip_ansi(result.output)
        assert result.exit_code == 0
        assert "--smee-url" in clean
        assert "--pjob" in clean
        assert "--port" in clean
        assert "--secret" in clean

    def test_missing_pjob_fails(self):
        """Running without --pjob fails."""
        result = runner.invoke(app, ["webhook-server", "--port", "8765"])
        clean = strip_ansi(result.output)
        assert result.exit_code != 0
        assert "--pjob" in clean

    def test_command_runs_without_subcommand(self):
        """webhook-server without subcommand enters server mode."""
        # We cannot actually start the server in a test, but we can verify
        # the callback is invoked and fails validation before blocking.
        result = runner.invoke(app, ["webhook-server", "--port", "8765"])
        clean = strip_ansi(result.output)
        assert result.exit_code != 0
        assert "At least one --pjob is required" in clean
