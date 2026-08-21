"""Unit tests for execution-layer duplicate-review dedup (#181)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zima.execution.executor import ExecutionStatus, PJobExecutor
from zima.execution.history import ExecutionHistory
from zima.models.actions import ActionsConfig, PreExecAction
from zima.models.agent import AgentConfig
from zima.models.pjob import Overrides, PJobConfig
from zima.models.workflow import WorkflowConfig


@pytest.fixture
def mock_pjob_with_scan(isolated_zima_home):
    """Create a PJob with a scan_pr preExec action and save its configs."""
    from zima.config.manager import ConfigManager

    manager = ConfigManager()
    agent = AgentConfig.create(
        code="test-agent",
        name="Test Agent",
        agent_type="kimi",
        parameters={"mockCommand": "echo hello"},
    )
    manager.save_config("agent", "test-agent", agent.to_dict())
    workflow = WorkflowConfig.create(code="test-workflow", name="Test Workflow", template="Hello")
    manager.save_config("workflow", "test-workflow", workflow.to_dict())
    pjob = PJobConfig.create(
        code="test-pjob", name="Test PJob", agent="test-agent", workflow="test-workflow"
    )
    pjob.spec.actions = ActionsConfig(
        provider="github",
        pre_exec=[PreExecAction(type="scan_pr", repo="owner/repo", label="ready-for-review")],
    )
    manager.save_config("pjob", "test-pjob", pjob.to_dict())
    return pjob


class TestScanResultPersistence:
    def test_head_sha_persisted_from_runtime_override(self, mock_pjob_with_scan):
        executor = PJobExecutor()
        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command", return_value=(0, "", "", 12345)),
        ):
            result = executor.execute(
                "test-pjob",
                overrides=Overrides(variable_values={"head_sha": "ABCDEF1234567890"}),
            )
        assert result.status == ExecutionStatus.SUCCESS
        state = executor._history.get_runtime_state("test-pjob", result.execution_id)
        assert state is not None
        assert state["scan_pr_result"]["head_sha"] == "abcdef1234567890"

    def test_scan_result_persisted_before_agent_runs(self, mock_pjob_with_scan):
        """The scan target must be on disk BEFORE the agent command runs,
        so a concurrent stream can see it while this one is still running."""
        executor = PJobExecutor()
        observed = {}

        def _run_command(command, env, work_dir, timeout, stdin_file):
            # At this point scan_pr_result must already be persisted.
            states = executor._history.list_executions("test-pjob")
            observed["count"] = len(states)
            observed["scan_pr_result"] = states[0].get("scan_pr_result")
            return (0, "", "", 12345)

        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command", side_effect=_run_command),
        ):
            result = executor.execute("test-pjob")
        assert result.status == ExecutionStatus.SUCCESS
        assert observed["count"] == 1
        assert observed["scan_pr_result"] == {"repo": "owner/repo", "pr_number": "42"}

    def test_dry_run_does_not_write_state(self, mock_pjob_with_scan):
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ):
            result = executor.execute("test-pjob", dry_run=True)
        assert result.status == ExecutionStatus.SUCCESS
        states = executor._history.list_executions("test-pjob")
        assert all(s.get("execution_id") != result.execution_id for s in states)

    def test_cli_provided_execution_id_persists_into_existing_state(self, mock_pjob_with_scan):
        """Simulate the production CLI→background_runner path: the CLI already
        wrote a status=running state file under a known id; execute() with that
        id must write scan_pr_result into the SAME file and create no orphan."""
        history = ExecutionHistory()
        history.write_runtime_state(
            "test-pjob",
            "cli00001",
            {
                "execution_id": "cli00001",
                "pjob_code": "test-pjob",
                "status": "running",
                "pid": None,
                "started_at": "2026-08-22T00:00:00+00:00",
            },
        )
        executor = PJobExecutor()
        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command", return_value=(0, "", "", 12345)),
        ):
            result = executor.execute("test-pjob", execution_id="cli00001")
        assert result.status == ExecutionStatus.SUCCESS
        assert result.execution_id == "cli00001"
        state = history.get_runtime_state("test-pjob", "cli00001")
        assert state is not None
        assert state["status"] == "running"
        assert state["scan_pr_result"] == {"repo": "owner/repo", "pr_number": "42"}
        # No orphan file: the pjob dir must contain exactly one record.
        assert len(history.list_executions("test-pjob")) == 1


class TestDedupGuard:
    def _seed_duplicate(self, status, head_sha="", started_minutes_ago=0):
        from datetime import datetime, timedelta, timezone

        history = ExecutionHistory()
        started = (datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)).isoformat()
        spr = {"repo": "owner/repo", "pr_number": "42"}
        if head_sha:
            spr["head_sha"] = head_sha
        history.write_runtime_state(
            "test-pjob",
            "dup00001",
            {
                "execution_id": "dup00001",
                "pjob_code": "test-pjob",
                "status": status,
                "pid": None,
                "started_at": started,
                "scan_pr_result": spr,
            },
        )

    def test_duplicate_running_stream_skips(self, mock_pjob_with_scan):
        self._seed_duplicate("running", started_minutes_ago=1)
        executor = PJobExecutor()
        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command") as mock_run,
        ):
            result = executor.execute("test-pjob")
        assert result.status == ExecutionStatus.SKIPPED
        assert "dedup" in result.stderr
        assert "dup00001" in result.stderr
        mock_run.assert_not_called()

    def test_recent_success_same_head_skips(self, mock_pjob_with_scan):
        self._seed_duplicate("success", head_sha="abc123", started_minutes_ago=5)
        executor = PJobExecutor()
        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command") as mock_run,
        ):
            result = executor.execute(
                "test-pjob",
                overrides=Overrides(variable_values={"head_sha": "abc123"}),
            )
        assert result.status == ExecutionStatus.SKIPPED
        mock_run.assert_not_called()

    def test_new_head_sha_allows(self, mock_pjob_with_scan):
        self._seed_duplicate("success", head_sha="abc123", started_minutes_ago=5)
        executor = PJobExecutor()
        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command", return_value=(0, "", "", 12345)) as mock_run,
        ):
            result = executor.execute(
                "test-pjob",
                overrides=Overrides(variable_values={"head_sha": "def456"}),
            )
        assert result.status == ExecutionStatus.SUCCESS
        mock_run.assert_called_once()

    def test_dedup_off_bypasses(self, mock_pjob_with_scan):
        self._seed_duplicate("running", started_minutes_ago=1)
        executor = PJobExecutor()
        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command", return_value=(0, "", "", 12345)) as mock_run,
        ):
            result = executor.execute("test-pjob", dedup_off=True)
        assert result.status == ExecutionStatus.SUCCESS
        mock_run.assert_called_once()

    def test_failed_duplicate_allows(self, mock_pjob_with_scan):
        self._seed_duplicate("failed", started_minutes_ago=1)
        executor = PJobExecutor()
        with (
            patch.object(
                executor._actions_runner,
                "run_pre",
                return_value={"repo": "owner/repo", "pr_number": "42"},
            ),
            patch.object(executor, "_run_command", return_value=(0, "", "", 12345)) as mock_run,
        ):
            result = executor.execute("test-pjob")
        assert result.status == ExecutionStatus.SUCCESS
        mock_run.assert_called_once()
