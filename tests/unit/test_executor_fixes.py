"""Unit tests for executor bug fixes (#11, #13, #15, #16)."""

from zima.execution.executor import PJobExecutor, _friendly_error


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
        """OSError should fall through to default branch."""
        exc = OSError("disk full")
        result = _friendly_error(exc)
        assert result == "OSError: disk full"


class TestFixShellCommand:
    """Test PJobExecutor._fix_shell_command() for issue #13."""

    def test_simple_and_and(self):
        result = PJobExecutor._fix_shell_command("cd /tmp && ls")
        assert result == "cd /tmp ; ls"

    def test_multiple_and_and(self):
        result = PJobExecutor._fix_shell_command("a && b && c")
        assert result == "a ; b ; c"

    def test_and_and_inside_double_quotes_preserved(self):
        result = PJobExecutor._fix_shell_command('echo "a && b"')
        assert result == 'echo "a && b"'

    def test_and_and_inside_single_quotes_preserved(self):
        result = PJobExecutor._fix_shell_command("echo 'a && b'")
        assert result == "echo 'a && b'"

    def test_mixed_quoted_and_unquoted(self):
        result = PJobExecutor._fix_shell_command('echo "a && b" && echo c')
        assert result == 'echo "a && b" ; echo c'

    def test_no_and_and(self):
        result = PJobExecutor._fix_shell_command("echo hello")
        assert result == "echo hello"

    def test_empty_string(self):
        result = PJobExecutor._fix_shell_command("")
        assert result == ""

    def test_non_windows_passthrough(self, monkeypatch):
        """On non-Windows, command should pass through unchanged."""
        import os

        monkeypatch.setattr(os, "name", "posix")
        result = PJobExecutor._fix_shell_command("cd /tmp && ls")
        assert result == "cd /tmp && ls"
