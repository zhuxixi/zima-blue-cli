"""Unit tests for PJobExecutor preExec integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zima.execution.actions_runner import SkipAction
from zima.execution.executor import ExecutionStatus, PJobExecutor
from zima.models.actions import ActionsConfig, PreExecAction
from zima.models.agent import AgentConfig
from zima.models.pjob import PJobConfig
from zima.models.workflow import WorkflowConfig


class TestPreExecIntegration:
    """Test preExec action integration in PJobExecutor.execute()."""

    @pytest.fixture
    def mock_pjob_with_pre_exec(self, isolated_zima_home):
        """Create a PJobConfig with pre_exec actions and save required configs."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()

        # Save agent config
        agent = AgentConfig.create(
            code="test-agent",
            name="Test Agent",
            agent_type="kimi",
            parameters={"mockCommand": "echo hello"},
        )
        manager.save_config("agent", "test-agent", agent.to_dict())

        # Save workflow config
        workflow = WorkflowConfig.create(
            code="test-workflow",
            name="Test Workflow",
            template="Hello {{ name }}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        # Create PJob with pre_exec actions
        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[
                PreExecAction(
                    type="scan_pr",
                    repo="owner/repo",
                    label="ready-for-review",
                )
            ],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        return pjob

    def test_run_pre_exec_skipped(self, mock_pjob_with_pre_exec, isolated_zima_home):
        """Test that SkipAction from preExec returns SKIPPED status."""
        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            side_effect=SkipAction("No PRs found with label 'ready-for-review' in owner/repo"),
        ):
            result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SKIPPED
        assert result.returncode == 0
        assert "No PRs found" in result.stderr
        assert result.stdout == ""
        # Command is built before preExec runs; agent subprocess is skipped

    def test_run_pre_exec_success(self, mock_pjob_with_pre_exec, isolated_zima_home):
        """Test that successful preExec allows agent execution to proceed."""
        executor = PJobExecutor()

        with patch.object(executor._actions_runner, "run_pre") as mock_run_pre:
            with patch.object(executor, "_run_command") as mock_run_command:
                mock_run_command.return_value = (0, "hello output", "", 12345)

                result = executor.execute("test-pjob")

        mock_run_pre.assert_called_once()
        mock_run_command.assert_called_once()
        assert result.status == ExecutionStatus.SUCCESS
        assert result.returncode == 0
        assert result.stdout == "hello output"

    def test_run_pre_exec_no_actions(self, isolated_zima_home):
        """Test that PJob without pre_exec actions runs normally."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()

        agent = AgentConfig.create(
            code="test-agent",
            name="Test Agent",
            agent_type="kimi",
            parameters={"mockCommand": "echo hello"},
        )
        manager.save_config("agent", "test-agent", agent.to_dict())

        workflow = WorkflowConfig.create(
            code="test-workflow",
            name="Test Workflow",
            template="Hello world",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(executor._actions_runner, "run_pre") as mock_run_pre:
            with patch.object(executor, "_run_command") as mock_run_command:
                mock_run_command.return_value = (0, "hello output", "", 12345)

                result = executor.execute("test-pjob")

        mock_run_pre.assert_not_called()
        mock_run_command.assert_called_once()
        assert result.status == ExecutionStatus.SUCCESS

    def test_run_pre_exec_mutates_env(self, mock_pjob_with_pre_exec, isolated_zima_home):
        """Test that preExec can mutate env vars (e.g., inject PR info)."""
        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            side_effect=lambda actions, env: env.update({"pr_number": "42", "pr_title": "Test PR"}),
        ):
            with patch.object(executor, "_run_command") as mock_run_command:
                mock_run_command.return_value = (0, "hello output", "", 12345)

                result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SUCCESS
        assert result.env.get("pr_number") == "42"
        assert result.env.get("pr_title") == "Test PR"

    def test_run_pre_exec_failure(self, mock_pjob_with_pre_exec, isolated_zima_home):
        """Test that non-SkipAction exception from preExec returns FAILED status."""
        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            side_effect=RuntimeError("GitHub API rate limit exceeded"),
        ):
            result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.FAILED
        assert result.returncode == 1
        assert "GitHub API rate limit exceeded" in result.stderr
