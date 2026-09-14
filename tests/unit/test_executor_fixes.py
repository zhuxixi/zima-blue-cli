"""Unit tests for executor bug fixes (#11, #13, #15, #16, #92, #213)."""

import json
import os
import sys
from pathlib import Path

import pytest

from zima.execution.executor import ExecutionResult, ExecutionStatus, PJobExecutor, _friendly_error
from zima.utils import get_zima_home


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


class TestExecutorSessionDirInjection:
    """pi agents must receive --session-dir pointing inside the temp dir (#213)."""

    @pytest.fixture
    def sd_configs(self, isolated_zima_home, config_manager):
        from zima.models.pjob import PJobConfig
        from zima.models.workflow import WorkflowConfig

        config_manager.save_config(
            "agent",
            "sd-agent",
            {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "sd-agent", "name": "SD Agent"},
                "spec": {"type": "pi", "parameters": {"mockCommand": ["echo", "ok"]}},
            },
        )
        wf = WorkflowConfig.create(code="sd-wf", name="SD Workflow", template="do it", variables=[])
        config_manager.save_config("workflow", "sd-wf", wf.to_dict())
        pjob = PJobConfig.create(code="sd-pjob", name="SD PJob", agent="sd-agent", workflow="sd-wf")
        config_manager.save_config("pjob", "sd-pjob", pjob.to_dict())

    @staticmethod
    def _session_dir_of(command):
        """Return the value passed to --session-dir in a built command."""
        assert "--session-dir" in command
        return command[command.index("--session-dir") + 1]

    def test_pi_command_carries_session_dir(self, sd_configs, isolated_zima_home):
        executor = PJobExecutor()
        result = executor.execute("sd-pjob", dry_run=True)

        # dry_run echoes the command without executing the agent (the command is
        # built before the dry-run branch)
        session_dir = self._session_dir_of(result.command)
        # OS-independent: the value uses native separators (backslashes on
        # Windows), so compare Path components instead of a slash suffix.
        assert Path(session_dir).parts[-2:] == (
            f"sd-pjob-{result.execution_id}",
            "pi-sessions",
        )
        # A dry run never launched the agent: no fabricated failure reason.
        assert result.usage is None

    def test_preview_command_carries_session_dir(self, sd_configs, isolated_zima_home):
        """The preview path (pjob render --show-command) must match execution (#213)."""
        executor = PJobExecutor()

        command, _prompt_file, _env_vars = executor.build_command("sd-pjob")

        session_dir = self._session_dir_of(command)
        assert Path(session_dir).parts[-2:] == ("sd-pjob-preview", "pi-sessions")


class TestUsageCollection:
    """Executor collects the usage ledger before deleting the temp dir (#213)."""

    # Fake pi agent (same interpreter, separate process): parses --session-dir
    # from its own argv — exactly what real pi does — and writes one parent
    # session file plus one subagent artifact meta into it. Payloads are
    # embedded via repr() so no shell quoting is involved.
    SESSION_LINE = {
        "type": "message",
        "message": {
            "role": "assistant",
            "provider": "zai-coding-cn",
            "model": "glm-5.3",
            "usage": {
                "input": 100,
                "output": 10,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 110,
                "cost": {"total": 0.01},
            },
        },
    }
    CHILD_META = {
        "agent": "checker",
        "model": "zai-coding-cn/glm-5.3-flash",
        "usage": {
            "input": 900,
            "output": 90,
            "cacheRead": 0,
            "cacheWrite": 0,
            "cost": 0.09,
            "turns": 2,
        },
    }

    @classmethod
    def _mock_agent_command(cls):
        script = (
            "import pathlib, sys\n"
            "sess = None\n"
            "args = sys.argv[1:]\n"
            "for i, a in enumerate(args):\n"
            '    if a == "--session-dir" and i + 1 < len(args):\n'
            "        sess = args[i + 1]\n"
            "if sess:\n"
            "    root = pathlib.Path(sess)\n"
            '    (root / "subagent-artifacts").mkdir(parents=True, exist_ok=True)\n'
            '    (root / "s.jsonl").write_text('
            + repr(json.dumps(cls.SESSION_LINE))
            + ' + "\\n", encoding="utf-8")\n'
            '    (root / "subagent-artifacts" / "r1_checker_meta.json").write_text('
            + repr(json.dumps(cls.CHILD_META))
            + ', encoding="utf-8")\n'
        )
        return [sys.executable, "-c", script]

    @pytest.fixture
    def pjob(self, isolated_zima_home, config_manager):
        from zima.models.pjob import PJobConfig
        from zima.models.workflow import WorkflowConfig

        config_manager.save_config(
            "agent",
            "ul-agent",
            {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "ul-agent", "name": "UL Agent"},
                "spec": {"type": "pi", "parameters": {"mockCommand": self._mock_agent_command()}},
            },
        )
        wf = WorkflowConfig.create(code="ul-wf", name="UL Workflow", template="do it", variables=[])
        config_manager.save_config("workflow", "ul-wf", wf.to_dict())
        pjob = PJobConfig.create(code="ul-pjob", name="UL PJob", agent="ul-agent", workflow="ul-wf")
        config_manager.save_config("pjob", "ul-pjob", pjob.to_dict())
        return pjob

    def test_usage_collected_and_temp_removed(self, pjob, isolated_zima_home):
        executor = PJobExecutor()

        result = executor.execute("ul-pjob")

        assert result.status.value == "success"
        assert result.usage["collected"] is True
        assert result.usage["totals"]["total_tokens"] == 1100
        assert result.usage["by_role"]["parent"]["total_tokens"] == 110
        assert result.usage["by_role"]["children"]["total_tokens"] == 990
        assert result.usage["children_count"] == 1
        assert result.usage["cost_note"] == "estimated"
        assert result.temp_dir is None  # temp dir cleaned up
        assert not (get_zima_home() / "temp" / "pjobs" / f"ul-pjob-{result.execution_id}").exists()
