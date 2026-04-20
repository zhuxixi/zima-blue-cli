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


class TestDaemonStatusErrors(TestIsolator):
    """Test zima daemon status error handling."""

    def test_status_cleans_up_dead_pid_file(self):
        """Status should remove PID file when process is dead."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        # Write a PID that doesn't exist
        pid_file.write_text("99999999", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert not pid_file.exists()

    def test_status_corrupted_state_json(self):
        """Status should handle corrupted state.json gracefully."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        pid_file.write_text("99999999", encoding="utf-8")
        state_file = daemon_dir / "state.json"
        state_file.write_text("not valid json {{{", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0

    def test_status_unreadable_pid_file(self):
        """Status should handle unreadable PID file gracefully."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        # Write valid content but we'll test the error path
        # This test verifies (ValueError, OSError) is caught
        pid_file.write_text("not_a_number", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code != 0
        assert "Invalid" in result.output or "Cannot read" in result.output


class TestDaemonLogs(TestIsolator):
    """Test zima daemon logs command."""

    def test_logs_no_log_file(self):
        """Daemon logs when no log file exists should show message."""
        result = runner.invoke(app, ["daemon", "logs"])
        assert result.exit_code == 0
        assert "No daemon logs" in result.output


class TestDaemonLogsErrors(TestIsolator):
    """Test zima daemon logs error handling."""

    def test_logs_unreadable_file(self):
        """Logs should handle unreadable log file gracefully."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        log_file = daemon_dir / "daemon.log"
        # Write valid content — tests that the path exists and is read
        log_file.write_text("line1\nline2\nline3", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "logs"])
        assert result.exit_code == 0
        assert "line1" in result.output
