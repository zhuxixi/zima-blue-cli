"""Integration tests for zima webhook-server command."""

import importlib

from typer.testing import CliRunner

from tests.conftest import strip_ansi
from zima.cli import app

runner = CliRunner()


class TestWebhookServerCommand:
    """Tests for 'zima webhook-server'."""

    def test_help_shows_options(self):
        """Help text includes required options (--secret is hidden: use env var)."""
        result = runner.invoke(app, ["webhook-server", "--help"])
        clean = strip_ansi(result.output)
        assert result.exit_code == 0
        assert "--smee-url" in clean
        assert "--pjob" in clean
        assert "--repo" in clean
        assert "--port" in clean
        assert "--allow-no-secret" in clean

    def test_missing_pjob_fails(self):
        """Running without --pjob fails (pass --allow-no-secret to reach that check)."""
        result = runner.invoke(app, ["webhook-server", "--port", "8765", "--allow-no-secret"])
        clean = strip_ansi(result.output)
        assert result.exit_code != 0
        assert "--pjob" in clean

    def test_command_runs_without_subcommand(self):
        """webhook-server without subcommand enters server mode."""
        # We cannot actually start the server in a test, but we can verify
        # the callback is invoked and fails validation before blocking.
        result = runner.invoke(app, ["webhook-server", "--port", "8765", "--allow-no-secret"])
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
        assert "requires" in clean

    def test_no_secret_fails_closed_by_default(self):
        """Without a secret and without --allow-no-secret, the server refuses to run."""
        result = runner.invoke(app, ["webhook-server", "--pjob", "cr"])
        clean = strip_ansi(result.output)
        assert result.exit_code == 1
        assert "secret is required" in clean

    def test_smee_url_ssrf_rejected(self):
        """--smee-url must be an https smee.io URL (SSRF guard)."""
        result = runner.invoke(
            app,
            [
                "webhook-server",
                "--smee-url",
                "https://169.254.169.254/latest/meta-data/",
                "--secret",
                "s",
                "--pjob",
                "cr",
            ],
        )
        clean = strip_ansi(result.output)
        assert result.exit_code == 1
        assert "smee.io" in clean

    def test_python_dash_m_zima_module_resolves(self):
        """zima/__main__.py exists so `python -m zima` resolves.

        The webhook trigger spawns ``[sys.executable, "-m", "zima", ...]``;
        without zima/__main__.py that fails with "No module named zima.__main__"
        and the trigger silently no-ops. Verify the module exists and is wired to
        the CLI app. (The actual ``python -m zima`` execution is covered by the
        CliRunner-based tests; we avoid a subprocess here because it hangs under
        CI's captured-stdout/pipe setup.)
        """
        spec = importlib.util.find_spec("zima.__main__")
        assert spec is not None, "zima/__main__.py is missing; `python -m zima` would fail"
        module = importlib.import_module("zima.__main__")
        assert module.app is not None

    def test_repo_paired_with_pjob_accepted(self, monkeypatch):
        """A 1:1 --pjob/--repo pairing reaches run_server with bound routes."""
        captured: dict = {}

        def fake_run_server(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("zima.commands.webhook.run_server", fake_run_server)
        result = runner.invoke(
            app,
            [
                "webhook-server",
                "--allow-no-secret",
                "--port",
                "8765",
                "--pjob",
                "zima-cr",
                "--repo",
                "zhuxixi/zima-blue-cli",
                "--pjob",
                "jfox-cr",
                "--repo",
                "zhuxixi/jfox",
            ],
        )
        assert result.exit_code == 0, result.output
        routes = captured["routes"]
        assert [r.code for r in routes] == ["zima-cr", "jfox-cr"]
        assert [r.repo for r in routes] == ["zhuxixi/zima-blue-cli", "zhuxixi/jfox"]

    def test_broadcast_mode_when_no_repo(self, monkeypatch):
        """Without --repo, routes carry repo=None (legacy broadcast mode)."""
        captured: dict = {}

        def fake_run_server(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("zima.commands.webhook.run_server", fake_run_server)
        result = runner.invoke(
            app,
            ["webhook-server", "--allow-no-secret", "--port", "8765", "--pjob", "cr"],
        )
        assert result.exit_code == 0, result.output
        routes = captured["routes"]
        assert routes == [importlib.import_module("zima.webhook.server").PjobRoute("cr")]
        assert routes[0].repo is None

    def test_repo_count_mismatch_fails(self):
        """Unequal --repo / --pjob counts are rejected."""
        result = runner.invoke(
            app,
            [
                "webhook-server",
                "--allow-no-secret",
                "--pjob",
                "a",
                "--pjob",
                "b",
                "--repo",
                "owner/repo",
            ],
        )
        clean = strip_ansi(result.output)
        assert result.exit_code == 1
        assert "--repo count" in clean

    def test_invalid_repo_value_fails(self):
        """A malformed --repo value is rejected."""
        result = runner.invoke(
            app,
            ["webhook-server", "--allow-no-secret", "--pjob", "a", "--repo", "bad repo"],
        )
        clean = strip_ansi(result.output)
        assert result.exit_code == 1
        assert "Invalid --repo" in clean
