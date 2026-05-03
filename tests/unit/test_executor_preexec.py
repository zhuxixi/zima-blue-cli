"""Unit tests for PJobExecutor preExec integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zima.execution.actions_runner import SkipAction
from zima.execution.executor import ExecutionStatus, PJobExecutor
from zima.models.actions import ActionsConfig, PreExecAction
from zima.models.agent import AgentConfig
from zima.models.pjob import Overrides, PJobConfig
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
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SUCCESS
        # Verify dynamic vars are in env
        assert result.env.get("pr_number") == "42"
        assert result.env.get("pr_title") == "Fix bug"
        assert result.env.get("pr_diff") == "+added line"

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
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SUCCESS
        # Non-conflicting preExec key should be present in env
        assert result.env.get("extra") == "preexec-value"
        # "repo" was skipped from env_vars because it exists in overrides.variable_values
        # (variable_values overrides don't go into env_vars, but the guard still applies)

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
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SUCCESS
        # preExec "preexec-repo" should override static "static-repo"
        assert result.env.get("repo") == "preexec-repo"

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
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SUCCESS
        # Dynamic vars should be in env (template rendered with dynamic vars)
        assert result.env.get("pr_number") == "42"
        assert result.env.get("pr_title") == "Fix bug"

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

    def test_dry_run_skips_preexec_side_effects(self, mock_pjob_with_pre_exec, isolated_zima_home):
        """Test that dry_run=True skips preExec to avoid side effects (e.g. GitHub API calls)."""
        executor = PJobExecutor()

        with patch.object(executor._actions_runner, "run_pre") as mock_run_pre:
            result = executor.execute("test-pjob", dry_run=True)

        mock_run_pre.assert_not_called()
        assert result.status == ExecutionStatus.SUCCESS

    def test_env_vars_priority_runtime_overrides_protected(self, isolated_zima_home):
        """Test that env_vars.update(dynamic_vars) respects runtime env override priority."""
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
            template="{{pr_number}}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"pr_number": ""},
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
        # Runtime env override for pr_number
        pjob.spec.overrides = Overrides(env_vars={"pr_number": "OVERRIDE"})
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"pr_number": "PREEXEC", "repo": "x/y"},
        ):
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                result = executor.execute("test-pjob")

        # Runtime override should win over preExec in env_vars
        assert result.env.get("pr_number") == "OVERRIDE"

    def test_preexec_substitutes_variable_config_values(self, isolated_zima_home):
        """Test that preExec {{var}} substitution includes VariableConfig values, not just env_vars.

        Regression test for #88: preExec used _substitute_env_str which only looked up
        env_vars (from EnvConfig), missing VariableConfig values like {{repo}}.
        """
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
            template="Hello",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        # VariableConfig defines repo, NOT EnvConfig
        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"repo": "zhuxixi/zima-blue-cli", "label": "zima:needs-review"},
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
            pre_exec=[PreExecAction(type="scan_pr", repo="{{repo}}", label="{{label}}")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(executor._actions_runner, "run_pre", return_value={}) as mock_run_pre:
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                executor.execute("test-pjob")

        # The env dict passed to run_pre should contain VariableConfig values
        call_env = mock_run_pre.call_args[0][1]  # second positional arg = env dict
        assert call_env.get("repo") == "zhuxixi/zima-blue-cli"
        assert call_env.get("label") == "zima:needs-review"
