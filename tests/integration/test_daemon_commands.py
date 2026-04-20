"""Integration tests for daemon CLI commands."""

from typer.testing import CliRunner

from tests.base import TestIsolator
from zima.cli import app

runner = CliRunner()


class TestDaemonStart(TestIsolator):
    """Test zima daemon start command."""

    def test_start_no_schedule(self):
        """Daemon start without --schedule should fail."""
        result = runner.invoke(app, ["daemon", "start"])
        assert result.exit_code != 0

    def test_start_nonexistent_schedule(self):
        """Daemon start with nonexistent schedule should fail."""
        result = runner.invoke(app, ["daemon", "start", "--schedule", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestDaemonStop(TestIsolator):
    """Test zima daemon stop command."""

    def test_stop_not_running(self):
        """Daemon stop when not running should show warning."""
        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        assert "not running" in result.output


class TestDaemonStatus(TestIsolator):
    """Test zima daemon status command."""

    def test_status_not_running(self):
        """Daemon status when not running should show message."""
        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert "not running" in result.output


class TestDaemonStopCleanup(TestIsolator):
    """Test zima daemon stop PID cleanup behavior."""

    def test_stop_removes_stale_pid_file(self):
        """Daemon stop should remove PID file even for nonexistent process."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        # Write a PID that doesn't exist
        pid_file.write_text("99999999", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        assert not pid_file.exists()


class TestDaemonLogs(TestIsolator):
    """Test zima daemon logs command."""

    def test_logs_no_log_file(self):
        """Daemon logs when no log file exists should show message."""
        result = runner.invoke(app, ["daemon", "logs"])
        assert result.exit_code == 0
        assert "No daemon logs" in result.output
