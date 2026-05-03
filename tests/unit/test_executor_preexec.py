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
        # preExec raised SkipAction before command execution

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

    def test_run_pre_exec_vars_in_env(self, mock_pjob_with_pre_exec, isolated_zima_home):
        """Test that preExec returned variables are merged into env vars."""
        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"pr_number": "42", "pr_title": "Test PR"},
        ):
            with patch.object(executor, "_run_command") as mock_run_command:
                mock_run_command.return_value = (0, "hello output", "", 12345)

                result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SUCCESS
        assert result.env.get("pr_number") == "42"
        assert result.env.get("pr_title") == "Test PR"

    def test_run_pre_exec_vars_available_in_template(self, isolated_zima_home):
        """Test that preExec discovered variables are available for Jinja2 rendering."""
        from zima.config.manager import ConfigManager
        from zima.models.variable import VariableConfig

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
            template="Review PR #{{pr_number}}: {{pr_title}}\n{{pr_diff}}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"pr_number": "", "pr_title": "", "pr_diff": ""},
        )
        manager.save_config("variable", "test-var", var.to_dict())

        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[
                PreExecAction(type="scan_pr", repo="owner/repo", label="ready"),
            ],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        dynamic_vars = {
            "repo": "owner/repo",
            "pr_number": "42",
            "pr_title": "Fix bug",
            "pr_url": "https://github.com/owner/repo/pull/42",
            "pr_diff": "+added line",
        }

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value=dynamic_vars,
        ):
            result = executor.execute("test-pjob", dry_run=True)

        assert result.status == ExecutionStatus.SUCCESS
        # Verify dynamic vars are in env
        assert result.env.get("pr_number") == "42"
        assert result.env.get("pr_title") == "Fix bug"
        assert result.env.get("pr_diff") == "+added line"
        # Verify template was rendered with dynamic vars
        assert "42" in result.prompt_content
        assert "Fix bug" in result.prompt_content
        assert "+added line" in result.prompt_content

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

    def test_preexec_priority_runtime_override_wins(self, isolated_zima_home):
        """Test that runtime overrides take priority over preExec dynamic vars."""
        from zima.config.manager import ConfigManager
        from zima.models.variable import VariableConfig

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
            template="repo={{repo}}, extra={{extra}}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"repo": "", "extra": ""},
        )
        manager.save_config("variable", "test-var", var.to_dict())

        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
            overrides={"variableValues": {"repo": "override-repo"}},
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo="x/y", label="ready")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "preexec-repo", "extra": "preexec-value"},
        ):
            result = executor.execute("test-pjob", dry_run=True)

        assert result.status == ExecutionStatus.SUCCESS
        # Runtime override "override-repo" should win over preExec "preexec-repo"
        assert "override-repo" in result.prompt_content
        assert "preexec-repo" not in result.prompt_content
        # Non-conflicting preExec key should be present
        assert "preexec-value" in result.prompt_content

    def test_preexec_priority_over_static_config(self, isolated_zima_home):
        """Test that preExec values override static variable config values."""
        from zima.config.manager import ConfigManager
        from zima.models.variable import VariableConfig

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
            template="repo={{repo}}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"repo": "static-repo"},
        )
        manager.save_config("variable", "test-var", var.to_dict())

        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo="x/y", label="ready")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "preexec-repo"},
        ):
            result = executor.execute("test-pjob", dry_run=True)

        assert result.status == ExecutionStatus.SUCCESS
        # preExec "preexec-repo" should override static "static-repo"
        assert "preexec-repo" in result.prompt_content
        assert "static-repo" not in result.prompt_content

    def test_preexec_no_variable_creates_dynamic_var(self, isolated_zima_home):
        """Test that preExec dynamic vars work when PJob has no variable reference."""
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
            template="Review PR #{{pr_number}}: {{pr_title}}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        # PJob with NO variable reference
        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo="x/y", label="ready")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"pr_number": "42", "pr_title": "Fix bug"},
        ):
            result = executor.execute("test-pjob", dry_run=True)

        assert result.status == ExecutionStatus.SUCCESS
        # Dynamic vars should still be available for rendering
        assert "42" in result.prompt_content
        assert "Fix bug" in result.prompt_content

    def test_preexec_empty_dynamic_vars(self, isolated_zima_home):
        """Test that empty dynamic_vars from preExec doesn't crash and runs normally."""
        from zima.config.manager import ConfigManager
        from zima.models.variable import VariableConfig

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
            template="Hello {{name}}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"name": "world"},
        )
        manager.save_config("variable", "test-var", var.to_dict())

        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo="x/y", label="ready")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(executor._actions_runner, "run_pre", return_value={}):
            result = executor.execute("test-pjob", dry_run=True)

        assert result.status == ExecutionStatus.SUCCESS
        # Static variable should still render normally
        assert "world" in result.prompt_content
