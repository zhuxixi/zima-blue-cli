"""Integration tests for PJobExecutor postExec actions."""

import os
import sys
from unittest.mock import MagicMock

import pytest

from tests.base import TestIsolator
from zima.execution.executor import _DISCOVERED_TEXT_MAX_BYTES, PJobExecutor
from zima.models.actions import ActionsConfig, PostExecAction
from zima.models.pjob import PJobConfig


class TestExecutorActions(TestIsolator):
    @pytest.fixture
    def mock_configs(self, isolated_zima_home, config_manager, sample_agent_dict):
        """Set up agent and workflow configs for testing."""
        from zima.models.workflow import WorkflowConfig

        agent_data = sample_agent_dict.copy()
        agent_data["metadata"]["code"] = "test-agent"
        agent_data["spec"]["parameters"]["mockCommand"] = ["echo", "mock output"]
        config_manager.save_config("agent", "test-agent", agent_data)

        wf = WorkflowConfig.create(
            code="test-wf",
            name="Test Workflow",
            template="Hello {{name}}",
            variables=[{"name": "name", "type": "string", "required": True}],
        )
        config_manager.save_config("workflow", "test-wf", wf.to_dict())

        from zima.models.variable import VariableConfig

        var = VariableConfig.create(
            code="test-var", name="Test Variables", values={"name": "World"}
        )
        config_manager.save_config("variable", "test-var", var.to_dict())

        return agent_data, wf.to_dict(), var.to_dict()

    def test_executor_runs_success_actions(self, mock_configs, isolated_zima_home):
        """Test executor runs postExec success actions after agent exits."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        pjob = PJobConfig.create(
            code="test-pjob-actions",
            name="Test PJob with Actions",
            agent="test-agent",
            workflow="test-wf",
            variable="test-var",
        )
        pjob.spec.actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["zima:test-passed"],
                    remove_labels=["zima:test-pending"],
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        manager.save_config("pjob", "test-pjob-actions", pjob.to_dict())

        executor = PJobExecutor()
        mock_ops = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_ops
        executor._actions_runner._registry = mock_registry
        result = executor.execute("test-pjob-actions")

        assert result.status.value == "success"
        mock_ops.add_label.assert_called_once_with("owner/repo", "42", "zima:test-passed")
        mock_ops.remove_label.assert_called_once_with("owner/repo", "42", "zima:test-pending")

    def test_executor_skips_failure_actions_on_success(self, mock_configs, isolated_zima_home):
        """Test failure actions are not run when agent succeeds."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        pjob = PJobConfig.create(
            code="test-pjob-skip",
            name="Test Skip",
            agent="test-agent",
            workflow="test-wf",
            variable="test-var",
        )
        pjob.spec.actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_comment",
                    body="This should not run",
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        manager.save_config("pjob", "test-pjob-skip", pjob.to_dict())

        executor = PJobExecutor()
        mock_ops = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_ops
        executor._actions_runner._registry = mock_registry
        result = executor.execute("test-pjob-skip")

        assert result.status.value == "success"
        mock_ops.post_comment.assert_not_called()


class TestReviewerEndToEnd(TestIsolator):
    @pytest.fixture
    def reviewer_configs(self, isolated_zima_home, config_manager):
        """Set up complete reviewer agent + workflow + pjob configs."""
        from zima.models.variable import VariableConfig
        from zima.models.workflow import WorkflowConfig

        # Agent with mockCommand that outputs approved review XML
        agent_data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "reviewer-agent", "name": "Reviewer Agent"},
            "spec": {
                "type": "kimi",
                "parameters": {
                    "mockCommand": [
                        "echo",
                        "Review complete.\n<zima-review>\n  <verdict>approved</verdict>\n  <summary>LGTM</summary>\n</zima-review>",
                    ]
                },
            },
        }
        config_manager.save_config("agent", "reviewer-agent", agent_data)

        # Workflow
        wf = WorkflowConfig.create(
            code="reviewer-wf",
            name="Reviewer Workflow",
            template="Review PR {{pr_number}}: {{pr_diff}}",
            variables=[
                {"name": "pr_number", "type": "string", "required": True},
                {"name": "pr_diff", "type": "string", "required": True},
            ],
        )
        config_manager.save_config("workflow", "reviewer-wf", wf.to_dict())

        # Variable
        var = VariableConfig.create(
            code="reviewer-var",
            name="Reviewer Vars",
            values={"pr_number": "42", "pr_diff": "+code"},
        )
        config_manager.save_config("variable", "reviewer-var", var.to_dict())

        return agent_data, wf.to_dict(), var.to_dict()

    def test_reviewer_approved_triggers_label(self, reviewer_configs, isolated_zima_home):
        """Full flow: reviewer agent outputs approved -> label transition triggered."""
        from zima.config.manager import ConfigManager
        from zima.models.actions import ActionsConfig, PostExecAction
        from zima.models.pjob import PJobConfig

        manager = ConfigManager()

        pjob = PJobConfig.create(
            code="reviewer-e2e",
            name="Reviewer E2E",
            agent="reviewer-agent",
            workflow="reviewer-wf",
            variable="reviewer-var",
        )
        pjob.metadata.labels = ["reviewer"]
        pjob.spec.actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["zima:approved"],
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="42",
                )
            ]
        )
        manager.save_config("pjob", "reviewer-e2e", pjob.to_dict())

        executor = PJobExecutor()
        mock_ops = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_ops
        executor._actions_runner._registry = mock_registry

        result = executor.execute("reviewer-e2e")

        assert result.status.value == "success"
        assert "approved" in result.stdout
        mock_ops.add_label.assert_called_once_with("owner/repo", "42", "zima:approved")
        mock_ops.remove_label.assert_called_once_with("owner/repo", "42", "zima:needs-review")


class TestPreExecToPostExecFlow(TestIsolator):
    """Integration test: preExec discovers PR → template renders with vars → postExec uses vars."""

    @pytest.fixture
    def full_reviewer_setup(self, isolated_zima_home, config_manager):
        """Set up reviewer configs with preExec scan_pr + postExec label actions."""
        from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction
        from zima.models.variable import VariableConfig
        from zima.models.workflow import WorkflowConfig

        agent_data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "reviewer-agent", "name": "Reviewer Agent"},
            "spec": {
                "type": "kimi",
                "parameters": {
                    "mockCommand": [
                        "echo",
                        "Review done.\n<zima-review>\n  <verdict>approved</verdict>\n"
                        "  <summary>LGTM</summary>\n</zima-review>",
                    ]
                },
            },
        }
        config_manager.save_config("agent", "reviewer-agent", agent_data)

        wf = WorkflowConfig.create(
            code="reviewer-wf",
            name="Reviewer Workflow",
            template="Review PR #{{pr_number}} in {{repo}}\nDiff:\n{{pr_diff}}",
        )
        config_manager.save_config("workflow", "reviewer-wf", wf.to_dict())

        var = VariableConfig.create(
            code="reviewer-var",
            name="Reviewer Vars",
            values={"repo": "owner/repo", "pr_number": "", "pr_title": "", "pr_diff": ""},
        )
        config_manager.save_config("variable", "reviewer-var", var.to_dict())

        pjob = PJobConfig.create(
            code="reviewer-full",
            name="Full Reviewer",
            agent="reviewer-agent",
            workflow="reviewer-wf",
            variable="reviewer-var",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[
                PreExecAction(
                    type="scan_pr",
                    repo="owner/repo",
                    label="zima:needs-review",
                )
            ],
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["zima:approved"],
                    remove_labels=["zima:needs-review"],
                    repo="{{repo}}",
                    issue="{{pr_number}}",
                )
            ],
        )
        config_manager.save_config("pjob", "reviewer-full", pjob.to_dict())

        return pjob

    def test_preexec_vars_flow_to_template_and_postexec(
        self, full_reviewer_setup, isolated_zima_home
    ):
        """preExec scan_pr → dynamic vars in template → postExec label with those vars."""
        from unittest.mock import MagicMock

        executor = PJobExecutor()
        mock_ops = MagicMock()
        mock_ops.scan_prs.return_value = [
            {"number": "99", "title": "Bug fix", "url": "https://github.com/owner/repo/pull/99"}
        ]
        mock_ops.fetch_diff.return_value = "+fixed code"
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_ops
        executor._actions_runner._registry = mock_registry

        result = executor.execute("reviewer-full")

        assert result.status.value == "success"
        # Dynamic vars should be in env
        assert result.env.get("pr_number") == "99"
        assert result.env.get("pr_diff") == "+fixed code"
        # postExec should use the dynamic vars for label action
        mock_ops.add_label.assert_called_once_with("owner/repo", "99", "zima:approved")
        mock_ops.remove_label.assert_called_once_with("owner/repo", "99", "zima:needs-review")


class TestRequireReviewExecutorGate(TestIsolator):
    """requireReview gate wiring: the executor must pass the review-signal
    flag (from agent stdout) through to ActionsRunner.run (#201)."""

    def _run_gate_pjob(self, isolated_zima_home, config_manager, mock_command, post_exec):
        """Build agent+workflow+variable+pjob with the given mock command and
        postExec actions, execute with a mocked provider registry, and return
        (result, mock_ops)."""
        from zima.config.manager import ConfigManager
        from zima.models.variable import VariableConfig
        from zima.models.workflow import WorkflowConfig

        agent_data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "gate-agent", "name": "Gate Agent"},
            "spec": {"type": "kimi", "parameters": {"mockCommand": mock_command}},
        }
        config_manager.save_config("agent", "gate-agent", agent_data)

        wf = WorkflowConfig.create(code="gate-wf", name="Gate Workflow", template="Hello")
        config_manager.save_config("workflow", "gate-wf", wf.to_dict())

        var = VariableConfig.create(code="gate-var", name="Gate Variables", values={})
        config_manager.save_config("variable", "gate-var", var.to_dict())

        pjob = PJobConfig.create(
            code="gate-pjob",
            name="Gate PJob",
            agent="gate-agent",
            workflow="gate-wf",
            variable="gate-var",
        )
        pjob.spec.actions = ActionsConfig(post_exec=post_exec)
        manager = ConfigManager()
        manager.save_config("pjob", "gate-pjob", pjob.to_dict())

        executor = PJobExecutor()
        mock_ops = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_ops
        executor._actions_runner._registry = mock_registry
        result = executor.execute("gate-pjob")
        return result, mock_ops

    def test_startup_failure_skips_require_review_action(self, isolated_zima_home, config_manager):
        """Agent exits 1 with empty stdout (E2BIG-like): the requireReview
        failure action must NOT fire — label stays untouched (#201)."""
        result, mock_ops = self._run_gate_pjob(
            isolated_zima_home,
            config_manager,
            [sys.executable, "-c", "raise SystemExit(1)"],
            [
                PostExecAction(
                    condition="failure",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="42",
                    require_review=True,
                )
            ],
        )
        assert result.status.value == "failed"
        mock_ops.add_label.assert_not_called()
        mock_ops.remove_label.assert_not_called()

    def test_needs_fix_status_line_still_fires_require_review_action(
        self, isolated_zima_home, config_manager
    ):
        """Agent exits 1 but stdout carries 'Status: NEEDS_FIX': action fires.
        No <zima-review> XML — effective_returncode stays 1 (failure condition
        matches) AND the Status line opens the gate (#201)."""
        result, mock_ops = self._run_gate_pjob(
            isolated_zima_home,
            config_manager,
            [sys.executable, "-c", "print('Status: NEEDS_FIX'); raise SystemExit(1)"],
            [
                PostExecAction(
                    condition="failure",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="42",
                    require_review=True,
                )
            ],
        )
        assert result.status.value == "failed"
        mock_ops.add_label.assert_called_once_with("owner/repo", "42", "zima:needs-fix")

    def test_success_without_review_skips_remove_label(self, isolated_zima_home, config_manager):
        """exit 0 但无 review 信号：requireReview 的 success 动作（摘
        needs-review）同样被跳过 —— 无审查不摘待审标签（spec §2.2 连带语义）。"""
        result, mock_ops = self._run_gate_pjob(
            isolated_zima_home,
            config_manager,
            [sys.executable, "-c", "print('finished without a review verdict')"],
            [
                PostExecAction(
                    condition="success",
                    type="add_label",
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="42",
                    require_review=True,
                )
            ],
        )
        assert result.status.value == "success"
        mock_ops.remove_label.assert_not_called()


def test_large_cjk_env_value_does_not_e2big(isolated_zima_home):
    """A 100KB-byte UTF-8 CJK env value must not trigger E2BIG at Popen (#201).

    Per-string budget: MAX_ARG_STRLEN=131072 bytes incl. "KEY=" and NUL;
    the #201 byte cap (100_000) keeps any single envp string under it.
    """
    cjk_value = "汉" * (_DISCOVERED_TEXT_MAX_BYTES // 3)  # 99_999 bytes
    assert len(cjk_value.encode("utf-8")) <= _DISCOVERED_TEXT_MAX_BYTES

    executor = PJobExecutor()
    env = {**os.environ, "pr_diff": cjk_value}
    returncode, stdout, stderr, pid = executor._run_command(
        command=[sys.executable, "-c", "pass"],
        env=env,
        work_dir=str(isolated_zima_home),
        timeout=30,
    )
    assert returncode == 0
