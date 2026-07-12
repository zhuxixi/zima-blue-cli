"""Integration tests for zima webhook-server command."""

import subprocess
import sys

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

    def test_smee_url_requires_secret(self):
        """--smee-url without --secret is rejected (fail-closed: smee is public)."""
        result = runner.invoke(
            app, ["webhook-server", "--smee-url", "https://smee.io/x", "--pjob", "cr"]
        )
        clean = strip_ansi(result.output)
        assert result.exit_code == 1
        assert "--secret" in clean
        assert "required" in clean

    def test_python_dash_m_zima_is_invocable(self):
        """`python -m zima` works — the webhook trigger spawns it as a subprocess.

        Without zima/__main__.py this fails with "No module named zima.__main__"
        and the webhook trigger silently no-ops.
        """
        result = subprocess.run(
            [sys.executable, "-m", "zima", "--help"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout or "Usage" in result.stderr
