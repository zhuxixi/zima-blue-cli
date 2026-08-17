"""Unit tests for PJobExecutor preExec integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zima.execution.actions_runner import SkipAction
from zima.execution.executor import ExecutionStatus, PJobExecutor
from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction
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
            return_value={"repo": "preexec/repo", "extra": "preexec-value"},
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
            return_value={"repo": "preexec/repo"},
        ):
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                result = executor.execute("test-pjob")

        assert result.status == ExecutionStatus.SUCCESS
        # preExec "preexec/repo" should override static "static-repo"
        assert result.env.get("repo") == "preexec/repo"

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
        # Runtime env override (non-pr key; pr keys have scan semantics, #158)
        pjob.spec.overrides = Overrides(env_vars={"review_target": "OVERRIDE"})
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"review_target": "PREEXEC", "repo": "x/y"},
        ):
            with patch.object(executor, "_run_command") as mock_run:
                mock_run.return_value = (0, "done", "", 12345)
                result = executor.execute("test-pjob")

        # Runtime override should win over preExec in env_vars
        # (uses a non-pr key: pr/pr_number keys have scan-specific semantics,
        # see #158 — the actually-scanned PR wins there)
        assert result.env.get("review_target") == "OVERRIDE"

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


class TestPinnedPrFlow:
    """Executor-level flow for webhook-pinned PR (#158): overrides carry
    pr_number from --set-var; scan_pr short-circuits; template renders the
    constructed pr_url."""

    def _setup_configs(self, manager, static_pr_number=""):
        from zima.models.variable import VariableConfig

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
            template="batch review pr {{ pr_url }}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"repo": "owner/repo", "pr_url": "", "pr_number": static_pr_number},
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
            pre_exec=[PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

    def test_pinned_pr_number_flows_to_template(self, isolated_zima_home):
        """Webhook-style run: overrides pin pr_number=11; scan_pr short-circuits
        (no provider calls) and the rendered prompt contains the canonical URL."""
        from zima.config.manager import ConfigManager
        from zima.execution.executor import Overrides

        manager = ConfigManager()
        self._setup_configs(manager)

        executor = PJobExecutor()
        overrides = Overrides(
            variable_values={
                "repo": "owner/repo",
                "pr_number": "11",
                "head_sha": "abc123",
            }
        )

        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+patch"

        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            sf = kwargs.get("stdin_file")
            if sf:
                text += "\n" + Path(sf).read_text()
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob", overrides=overrides)

        assert result.status == ExecutionStatus.SUCCESS
        assert "https://github.com/owner/repo/pull/11" in captured["text"]

    def test_pinned_pr_number_beats_static_config(self, isolated_zima_home):
        """Pinned pr_number (override) wins over stale static variable value."""
        from zima.config.manager import ConfigManager
        from zima.execution.executor import Overrides

        manager = ConfigManager()
        self._setup_configs(manager, static_pr_number="999")

        executor = PJobExecutor()
        overrides = Overrides(variable_values={"repo": "owner/repo", "pr_number": "11"})

        mock_provider = MagicMock()
        mock_provider.fetch_diff.return_value = "+patch"

        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            sf = kwargs.get("stdin_file")
            if sf:
                text += "\n" + Path(sf).read_text()
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob", overrides=overrides)

        assert result.status == ExecutionStatus.SUCCESS
        assert "pull/11" in captured["text"]
        assert "pull/999" not in captured["text"]


class TestStaleOverrideCleanup:
    """#158 R6: a stale static pr/pr_number override must not pin rendering or
    postExec to a different PR than the one the scan actually found."""

    def _setup(self, manager):
        from zima.models.variable import VariableConfig

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
            template="review {{ pr_url }} #{{ pr_number }}",
        )
        manager.save_config("workflow", "test-workflow", workflow.to_dict())

        var = VariableConfig.create(
            code="test-var",
            name="Test Vars",
            values={"repo": "owner/repo", "pr_url": "", "pr_number": ""},
        )
        manager.save_config("variable", "test-var", var.to_dict())

        pjob = PJobConfig.create(
            code="test-pjob",
            name="Test PJob",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
            overrides={"variableValues": {"pr_number": "999"}},
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review")],
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    remove_labels=["zima:needs-review"],
                    repo="{{repo}}",
                    issue="{{pr_number}}",
                )
            ],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

    def test_stale_static_override_loses_to_scanned_pr(self, isolated_zima_home, capsys):
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        self._setup(manager)

        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/owner/repo/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "+diff"

        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob")  # no runtime overrides

        assert result.status == ExecutionStatus.SUCCESS
        # Prompt renders the SCANNED PR, not the stale static override
        assert "#42" in captured["text"]
        assert "999" not in captured["text"]
        # postExec also sees the scanned value (remove_label on success path)
        mock_provider.remove_label.assert_called_once_with("owner/repo", "42", "zima:needs-review")
        # Warning emitted (stale key detected)
        assert "stale/empty override" in capsys.readouterr().out


class TestStaleOverrideCleanupCliPath(TestStaleOverrideCleanup):
    """Same scenario as TestStaleOverrideCleanup but through the REAL caller
    paths: commands/pjob.py and background_runner always pass an Overrides()
    object (possibly empty / partially filled), never None (#158 R6)."""

    def test_empty_runtime_overrides_object(self, isolated_zima_home):
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        self._setup(manager)

        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/owner/repo/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "+diff"

        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                # CLI path: always constructs Overrides() even with no --set-var
                result = executor.execute("test-pjob", overrides=Overrides())

        assert result.status == ExecutionStatus.SUCCESS
        assert "#42" in captured["text"]
        assert "999" not in captured["text"]

    def test_partial_runtime_overrides_static_merged_into_values(self, isolated_zima_home):
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        self._setup(manager)

        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/owner/repo/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "+diff"

        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                # Runtime carries an unrelated set-var; the static pr_number=999
                # was deep-merged into variable.values by apply_overrides
                result = executor.execute(
                    "test-pjob",
                    overrides=Overrides(variable_values={"repo": "owner/repo"}),
                )

        assert result.status == ExecutionStatus.SUCCESS
        assert "#42" in captured["text"]
        assert "999" not in captured["text"]


class TestPrAliasRenderChannel:
    """#158 R7: the {{pr}} alias channel and the envVars channel must render
    the scanned PR, and empty defaults must not fire stale warnings."""

    def _setup(self, manager, template, pjob_overrides):
        from zima.models.variable import VariableConfig

        agent = AgentConfig.create(
            code="test-agent",
            name="Test Agent",
            agent_type="kimi",
            parameters={"mockCommand": "echo hello"},
        )
        manager.save_config("agent", "test-agent", agent.to_dict())
        workflow = WorkflowConfig.create(code="test-workflow", name="W", template=template)
        manager.save_config("workflow", "test-workflow", workflow.to_dict())
        var = VariableConfig.create(
            code="test-var",
            name="V",
            values={"repo": "owner/repo", "pr_url": "", "pr_number": "", "pr": ""},
        )
        manager.save_config("variable", "test-var", var.to_dict())
        pjob = PJobConfig.create(
            code="test-pjob",
            name="P",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
            overrides=pjob_overrides,
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

    def _run(self, capsys):
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        self._setup(
            manager,
            template="review {{ pr_url }} #{{ pr_number }} pr={{ pr }}",
            pjob_overrides={"variableValues": {"pr": "999"}},
        )
        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/owner/repo/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "+diff"
        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob", overrides=Overrides())
        out = capsys.readouterr().out
        return result, captured["text"], out

    def test_pr_alias_renders_scanned_pr(self, isolated_zima_home, capsys):
        result, text, out = self._run(capsys)
        assert result.status == ExecutionStatus.SUCCESS
        assert "#42" in text
        assert "pr=42" in text  # alias channel renders the scanned PR (#158 R7)
        assert "999" not in text
        assert "stale/empty" in out

    def test_empty_defaults_do_not_warn(self, isolated_zima_home, capsys, monkeypatch):
        # Ambient env (e.g. a CR harness exporting pr_number) must not turn
        # empty defaults into stale-warning triggers (#158 R17)
        monkeypatch.delenv("pr_number", raising=False)
        monkeypatch.delenv("pr", raising=False)
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        self._setup(
            manager,
            template="review {{ pr_url }}",
            pjob_overrides={"variableValues": {}},
        )
        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "42", "title": "Fix", "url": "https://github.com/owner/repo/pull/42"}
        ]
        mock_provider.fetch_diff.return_value = "+diff"

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", return_value=(0, "done", "", 12345)):
                result = executor.execute("test-pjob", overrides=Overrides())
        assert result.status == ExecutionStatus.SUCCESS
        assert "stale/empty" not in capsys.readouterr().out


class TestPrRewriteEdgeCases:
    """#158 R8: rewrite-channel edge cases."""

    def _base_run(self, manager, template, pjob_overrides, scan_result, action_repo="{{repo}}"):
        from zima.models.variable import VariableConfig

        agent = AgentConfig.create(
            code="test-agent",
            name="A",
            agent_type="kimi",
            parameters={"mockCommand": "echo hello"},
        )
        manager.save_config("agent", "test-agent", agent.to_dict())
        workflow = WorkflowConfig.create(code="test-workflow", name="W", template=template)
        manager.save_config("workflow", "test-workflow", workflow.to_dict())
        var = VariableConfig.create(
            code="test-var",
            name="V",
            values={"repo": "owner/repo", "pr_url": "", "pr_number": ""},
        )
        manager.save_config("variable", "test-var", var.to_dict())
        pjob = PJobConfig.create(
            code="test-pjob",
            name="P",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
            overrides=pjob_overrides,
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo=action_repo, label="zima:needs-review")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = scan_result
        mock_provider.fetch_diff.return_value = "+diff"
        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob", overrides=Overrides())
        return result, captured.get("text", "")

    def test_hash_format_same_pr_rewritten_silently(self, isolated_zima_home, capsys, monkeypatch):
        monkeypatch.delenv("pr_number", raising=False)
        monkeypatch.delenv("pr", raising=False)
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, text = self._base_run(
            manager,
            template="#{{ pr_number }}",
            pjob_overrides={"variableValues": {"pr_number": "#42"}},
            scan_result=[{"number": "42", "title": "T", "url": "u"}],
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert "#42" in text and "##42" not in text  # canonical form, no '#'
        out = capsys.readouterr().out
        assert "stale/empty" not in out  # same PR, format-only: silent rewrite

    def test_non_numeric_scan_output_skips_rewrite(self, isolated_zima_home, capsys):
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, text = self._base_run(
            manager,
            template="#{{ pr_number }}",
            pjob_overrides={"variableValues": {"pr_number": "999"}},
            scan_result=[{"number": "abc", "title": "T", "url": "u"}],  # bad provider
        )
        assert result.status == ExecutionStatus.SUCCESS
        out = capsys.readouterr().out
        assert "invalid pr_number" in out
        assert "stale/empty" not in out  # rewrite skipped entirely
        # Holder value preserved (not overwritten with garbage)
        assert "999" in text

    def test_stale_repo_rewritten_to_scanned(self, isolated_zima_home, capsys):
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, text = self._base_run(
            manager,
            template="repo={{ repo }} #{{ pr_number }}",
            pjob_overrides={"variableValues": {"repo": "old/legacy"}},
            scan_result=[{"number": "42", "title": "T", "url": "u"}],
            action_repo="owner/repo",  # scan targeted the correct repo while
            # the static override still carries a stale one
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert "repo=owner/repo" in text
        assert "old/legacy" not in text
        out = capsys.readouterr().out
        assert "'repo'" in out  # repo listed among rewritten keys


class TestRewriteRound9:
    """#158 R9 regression tests."""

    def _base_run(self, manager, template, pjob_overrides, scan_result, action_repo="{{repo}}"):
        from zima.models.variable import VariableConfig

        agent = AgentConfig.create(
            code="test-agent",
            name="A",
            agent_type="kimi",
            parameters={"mockCommand": "echo hello"},
        )
        manager.save_config("agent", "test-agent", agent.to_dict())
        workflow = WorkflowConfig.create(code="test-workflow", name="W", template=template)
        manager.save_config("workflow", "test-workflow", workflow.to_dict())
        var = VariableConfig.create(
            code="test-var",
            name="V",
            values={"repo": "owner/repo", "pr_url": "", "pr_number": ""},
        )
        manager.save_config("variable", "test-var", var.to_dict())
        pjob = PJobConfig.create(
            code="test-pjob",
            name="P",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
            overrides=pjob_overrides,
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo=action_repo, label="zima:needs-review")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = scan_result
        mock_provider.fetch_diff.return_value = "+diff"
        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob", overrides=Overrides())
        return result, captured.get("text", "")

    def test_raw_scan_form_canonicalized_end_to_end(self, isolated_zima_home, capsys):
        """Provider returns '#42': rewrite canonicalizes holders AND the scan
        value itself — inject cannot reintroduce the raw form (#158 R9)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, text = self._base_run(
            manager,
            template="PR={{ pr_number }}",
            pjob_overrides={"variableValues": {"pr_number": "999"}},
            scan_result=[{"number": "#42", "title": "T", "url": "u"}],
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert "PR=42" in text
        assert "PR=#42" not in text
        assert "999" not in text

    def test_padded_same_pr_canonicalized(self, isolated_zima_home, capsys):
        """Holder '  42  ' is rewritten (exact-equality skip), rendering and
        postExec receive the canonical number (#158 R9)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, text = self._base_run(
            manager,
            template="PR={{ pr_number }}",
            pjob_overrides={"variableValues": {"pr_number": "  42  "}},
            scan_result=[{"number": "42", "title": "T", "url": "u"}],
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert "PR=42" in text
        assert "  42  " not in text

    def test_case_variant_repo_not_flagged(self, isolated_zima_home, capsys):
        """Same repo with different case: no rewrite, no stale warning (#158 R9)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, text = self._base_run(
            manager,
            template="repo={{ repo }}",
            pjob_overrides={"variableValues": {"repo": "Owner/Repo"}},
            scan_result=[{"number": "42", "title": "T", "url": "u"}],
            action_repo="owner/repo",
        )
        assert result.status == ExecutionStatus.SUCCESS
        out = capsys.readouterr().out
        assert "'repo'" not in out  # no stale-repo warning for case variants


class TestInvalidScanDiscardedEntirely:
    """#158 R13 simplification: an invalid scan is discarded entirely —
    nothing from it reaches rendering, env, postExec or history."""

    def _base_run(self, manager, template, scan_result, action_repo="{{repo}}"):
        from zima.models.variable import VariableConfig

        agent = AgentConfig.create(
            code="test-agent",
            name="A",
            agent_type="kimi",
            parameters={"mockCommand": "echo hello"},
        )
        manager.save_config("agent", "test-agent", agent.to_dict())
        workflow = WorkflowConfig.create(code="test-workflow", name="W", template=template)
        manager.save_config("workflow", "test-workflow", workflow.to_dict())
        var = VariableConfig.create(
            code="test-var",
            name="V",
            values={"repo": "owner/repo", "pr_url": "", "pr_number": ""},
        )
        manager.save_config("variable", "test-var", var.to_dict())
        pjob = PJobConfig.create(
            code="test-pjob",
            name="P",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo=action_repo, label="zima:needs-review")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = scan_result
        mock_provider.fetch_diff.return_value = "+diff"
        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob", overrides=Overrides())
        return result, captured.get("text", "")

    def test_invalid_scan_persists_nothing(self, isolated_zima_home, capsys):
        """Garbage pr_number ('12\\n34') -> no scan_pr_result at all; the
        sanitized-passthrough hole cannot exist (#158 R13)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, _ = self._base_run(
            manager,
            template="PR={{ pr_number }}",
            scan_result=[{"number": "12\n34", "title": "T", "url": "u"}],
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.scan_pr_result is None  # nothing persisted
        assert "discarding the scan result entirely" in capsys.readouterr().out

    def test_malformed_repo_keeps_configured_value(self, isolated_zima_home, capsys):
        """Valid pr_number + MALFORMED scanned repo (control chars, fails
        _REPO_FORMAT) -> the key is dropped; {{repo}} renders the configured
        value, not the garbage and not an empty string (#158 R12/R13/R14)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, text = self._base_run(
            manager,
            template="repo={{ repo }} #{{ pr_number }}",
            scan_result=[{"number": "42", "title": "T", "url": "u"}],
            action_repo="garbage\u0000repo/x",  # malformed: control char
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert "repo=owner/repo" in text  # configured default survives
        assert "garbage" not in text

    def test_whitespace_repo_fails_fast(self, isolated_zima_home):
        """A whitespace-only action repo never reaches the rewrite logic —
        the pre-existing empty-repo guard in ActionsRunner fires first
        (SkipAction, label untouched). Guards ordering locked (#158 R14)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, _ = self._base_run(
            manager,
            template="repo=[{{ repo }}]",
            scan_result=[{"number": "42", "title": "T", "url": "u"}],
            action_repo="   ",  # whitespace-only resolved repo
        )
        assert result.status == ExecutionStatus.SKIPPED
        assert "repo resolved to empty" in str(result.stderr)

    def test_overlong_valid_scan_discarded(self, isolated_zima_home, capsys):
        """A >64-digit pr_number passes [0-9]+ but fails the length gate ->
        discarded entirely, no persisted copy diverging from in-memory
        values (#158 R14)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        overlong = "1" * 65
        result, _ = self._base_run(
            manager,
            template="PR={{ pr_number }}",
            scan_result=[{"number": overlong, "title": "T", "url": "u"}],
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.scan_pr_result is None
        assert "discarding the scan result entirely" in capsys.readouterr().out

    def test_valid_scan_persists_capped_values(self, isolated_zima_home):
        """Valid scans persist the discovered values as-is: overlong values
        are rejected upstream by the validity gates (invalid-scan discard),
        so persistence itself never truncates (#158 R14)."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result, _ = self._base_run(
            manager,
            template="PR={{ pr_number }}",
            scan_result=[{"number": "42", "title": "T", "url": "u"}],
            action_repo="owner/repo",
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.scan_pr_result is not None
        assert len(result.scan_pr_result["pr_number"]) <= 64
        assert len(result.scan_pr_result["repo"]) <= 256


class TestOverlongRepoDiscarded:
    """#158 R15: repo-side length gate coverage."""

    def _run_with_action_repo(self, isolated_zima_home, action_repo, pr_number_in_result=True):
        from zima.config.manager import ConfigManager
        from zima.models.variable import VariableConfig

        manager = ConfigManager()
        agent = AgentConfig.create(
            code="test-agent",
            name="A",
            agent_type="kimi",
            parameters={"mockCommand": "echo hello"},
        )
        manager.save_config("agent", "test-agent", agent.to_dict())
        workflow = WorkflowConfig.create(code="test-workflow", name="W", template="repo={{ repo }}")
        manager.save_config("workflow", "test-workflow", workflow.to_dict())
        var = VariableConfig.create(code="test-var", name="V", values={"repo": "owner/repo"})
        manager.save_config("variable", "test-var", var.to_dict())
        pjob = PJobConfig.create(
            code="test-pjob",
            name="P",
            agent="test-agent",
            workflow="test-workflow",
            variable="test-var",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[PreExecAction(type="scan_pr", repo=action_repo, label="zima:needs-review")],
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())

        executor = PJobExecutor()
        mock_provider = MagicMock()
        pr_dict = {"title": "T", "url": "u"}
        if pr_number_in_result:
            pr_dict["number"] = "42"
        mock_provider.scan_prs.return_value = [pr_dict]
        mock_provider.fetch_diff.return_value = "+diff"
        captured: dict = {}

        def fake_run(**kwargs):
            cmd = kwargs["command"]
            text = " ".join(cmd)
            if "--prompt" in cmd:
                text += "\n" + Path(cmd[cmd.index("--prompt") + 1]).read_text()
            captured["text"] = text
            return (0, "done", "", 12345)

        with patch.object(executor._actions_runner._registry, "get", return_value=mock_provider):
            with patch.object(executor, "_run_command", side_effect=fake_run):
                result = executor.execute("test-pjob", overrides=Overrides())
        return result, captured.get("text", "")

    def test_overlong_repo_renders_configured_value(self, isolated_zima_home):
        """action_repo over 256 chars (format-valid but overlong) -> discovered
        repo dropped; configured value renders (#158 R14/R15)."""
        overlong_repo = "a" * 300 + "/b"
        result, text = self._run_with_action_repo(isolated_zima_home, overlong_repo)
        assert result.status == ExecutionStatus.SUCCESS
        assert "repo=owner/repo" in text
        assert "aaaa" not in text
        # scan_pr_result persisted only when the repo gate passed; here repo
        # was dropped, pr_number still valid -> persisted pr only
        assert result.scan_pr_result is not None
        assert result.scan_pr_result["pr_number"] == "42"

    def test_repo_only_invalid_repo_no_crash(self, isolated_zima_home, capsys):
        """Provider returns a PR dict without a number: run_pre emits
        pr_number="" (key present, empty) -> the scan is INVALID and dropped
        entirely, repo included; the configured repo renders (#158 R15/R18)."""
        result, text = self._run_with_action_repo(
            isolated_zima_home, "not a repo", pr_number_in_result=False
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert "repo=owner/repo" in text
        assert result.scan_pr_result is None  # invalid scan persists nothing
        assert "invalid pr_number" in capsys.readouterr().out
