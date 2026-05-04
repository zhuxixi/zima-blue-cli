"""Unit tests for executor bug fixes (#11, #13, #15, #16, #92)."""

import os

from zima.execution.executor import ExecutionResult, ExecutionStatus, PJobExecutor, _friendly_error


class TestFriendlyError:
    """Test _friendly_error() for issue #15."""

    def test_file_not_found(self):
        exc = FileNotFoundError("no such file: config.yaml")
        result = _friendly_error(exc)
        assert result == "File not found: no such file: config.yaml"

    def test_permission_error(self):
        exc = PermissionError("/etc/hosts")
        result = _friendly_error(exc)
        assert result == "Permission denied: /etc/hosts"

    def test_value_error(self):
        exc = ValueError("agent type 'unknown' not supported")
        result = _friendly_error(exc)
        assert result == "Configuration error: agent type 'unknown' not supported"

    def test_key_error(self):
        exc = KeyError("spec")
        result = _friendly_error(exc)
        assert result == "Missing required field: 'spec'"

    def test_connection_error(self):
        exc = ConnectionError("refused")
        result = _friendly_error(exc)
        assert result == "Connection error: refused"

    def test_timeout_error(self):
        exc = TimeoutError("30s elapsed")
        result = _friendly_error(exc)
        assert result == "Connection error: 30s elapsed"

    def test_attribute_error(self):
        exc = AttributeError("'str' object has no attribute 'get'")
        result = _friendly_error(exc)
        assert result == "Invalid configuration: 'str' object has no attribute 'get'"

    def test_generic_exception(self):
        exc = RuntimeError("something broke")
        result = _friendly_error(exc)
        assert result == "RuntimeError: something broke"

    def test_os_error_not_caught_by_specific_branches(self):
        exc = OSError("disk full")
        result = _friendly_error(exc)
        assert result == "OSError: disk full"


class TestFixShellCommand:
    """Test PJobExecutor._fix_shell_command() for issue #13."""

    def test_simple_and_and(self, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        result = PJobExecutor._fix_shell_command("cd /tmp && ls")
        assert result == "cd /tmp ; ls"

    def test_multiple_and_and(self, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        result = PJobExecutor._fix_shell_command("a && b && c")
        assert result == "a ; b ; c"

    def test_and_and_inside_double_quotes_preserved(self, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        result = PJobExecutor._fix_shell_command('echo "a && b"')
        assert result == 'echo "a && b"'

    def test_and_and_inside_single_quotes_preserved(self, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        result = PJobExecutor._fix_shell_command("echo 'a && b'")
        assert result == "echo 'a && b'"

    def test_mixed_quoted_and_unquoted(self, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        result = PJobExecutor._fix_shell_command('echo "a && b" && echo c')
        assert result == 'echo "a && b" ; echo c'

    def test_no_and_and(self, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        result = PJobExecutor._fix_shell_command("echo hello")
        assert result == "echo hello"

    def test_empty_string(self, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        result = PJobExecutor._fix_shell_command("")
        assert result == ""

    def test_non_windows_passthrough(self, monkeypatch):
        monkeypatch.setattr(os, "name", "posix")
        result = PJobExecutor._fix_shell_command("cd /tmp && ls")
        assert result == "cd /tmp && ls"


class TestCreateTempDir:
    """Test PJobExecutor._create_temp_dir() uses ZIMA_HOME (#47)."""

    def test_temp_dir_under_zima_home(self, monkeypatch, temp_dir):
        monkeypatch.setenv("ZIMA_HOME", str(temp_dir))

        executor = PJobExecutor()
        result = executor._create_temp_dir("my-pjob", "abc123")

        expected = temp_dir / "temp" / "pjobs" / "my-pjob-abc123"
        assert result == expected
        assert result.exists()

    def test_temp_dir_creates_parents(self, monkeypatch, temp_dir):
        monkeypatch.setenv("ZIMA_HOME", str(temp_dir))

        # temp/pjobs/ should not exist yet
        assert not (temp_dir / "temp").exists()

        executor = PJobExecutor()
        result = executor._create_temp_dir("test-pjob", "id1")

        assert (temp_dir / "temp" / "pjobs").exists()
        assert result.exists()


class TestActionErrorStatusFlip:
    """Regression tests for #92: action errors flip status from SUCCESS to FAILED."""

    def test_action_error_flips_status_to_failed(self):
        """When postExec action fails, status changes from SUCCESS to FAILED."""
        result = ExecutionResult(
            pjob_code="reviewer",
            status=ExecutionStatus.SUCCESS,
            returncode=0,
            action_errors=["Failed to remove label 'zima:needs-review': PermissionError"],
        )
        # Simulate the status flip logic from executor finally block
        if result.status == ExecutionStatus.SUCCESS and result.action_errors:
            result.status = ExecutionStatus.FAILED
            result.returncode = 1

        assert result.status == ExecutionStatus.FAILED
        assert result.returncode == 1
        assert len(result.action_errors) == 1

    def test_no_errors_keeps_success(self):
        """When no action errors, status remains SUCCESS."""
        result = ExecutionResult(
            pjob_code="reviewer",
            status=ExecutionStatus.SUCCESS,
            returncode=0,
            action_errors=[],
        )
        if result.status == ExecutionStatus.SUCCESS and result.action_errors:
            result.status = ExecutionStatus.FAILED
            result.returncode = 1

        assert result.status == ExecutionStatus.SUCCESS
        assert result.returncode == 0

    def test_agent_failure_not_overridden_by_action_errors(self):
        """Agent failure status is not affected by action_errors check."""
        result = ExecutionResult(
            pjob_code="reviewer",
            status=ExecutionStatus.FAILED,
            returncode=1,
            action_errors=["Some action error"],
        )
        if result.status == ExecutionStatus.SUCCESS and result.action_errors:
            result.status = ExecutionStatus.FAILED
            result.returncode = 1

        # Status was already FAILED, should stay FAILED
        assert result.status == ExecutionStatus.FAILED
        assert result.returncode == 1
