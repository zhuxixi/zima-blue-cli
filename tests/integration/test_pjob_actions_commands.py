"""Integration tests for PJob actions subcommands."""

import pytest
from typer.testing import CliRunner

from zima.cli import app
from zima.config.manager import ConfigManager
from zima.models.agent import AgentConfig
from zima.models.workflow import WorkflowConfig

runner = CliRunner()


def _create_deps(tmp_path, pjob_code="test-pjob"):
    """Helper: set up ZIMA_HOME, create agent+workflow+pjob."""
    manager = ConfigManager()
    agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
    manager.save_config("agent", "test-agent", agent.to_dict())
    wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
    manager.save_config("workflow", "test-workflow", wf.to_dict())
    result = runner.invoke(
        app,
        [
            "pjob",
            "create",
            "--name",
            "Test PJob",
            "--code",
            pjob_code,
            "--agent",
            "test-agent",
            "--workflow",
            "test-workflow",
        ],
    )
    assert result.exit_code == 0
    return manager


class TestPJobActionsProvider:
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        self.tmp_path = tmp_path
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def test_provider_default(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "provider"])
        assert result.exit_code == 0
        assert "github" in result.output

    def test_provider_set(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "provider", "gitlab"])
        assert result.exit_code == 0
        assert "gitlab" in result.output
        result2 = runner.invoke(app, ["pjob", "actions", "test-pjob", "provider"])
        assert "gitlab" in result2.output

    def test_provider_pjob_not_found(self):
        result = runner.invoke(app, ["pjob", "actions", "missing-pjob", "provider"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestPJobActionsList:
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        self.tmp_path = tmp_path
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def test_list_empty(self):
        _create_deps(self.tmp_path, "t1")
        result = runner.invoke(app, ["pjob", "actions", "t1", "list"])
        assert result.exit_code == 0
        assert "No postExec actions" in result.output

    def test_list_with_actions(self):
        from zima.models.actions import PostExecAction

        _create_deps(self.tmp_path)
        manager = ConfigManager()
        data = manager.load_config("pjob", "test-pjob")
        from zima.models.pjob import PJobConfig

        pjob = PJobConfig.from_dict(data)
        pjob.spec.actions.post_exec.append(
            PostExecAction(
                condition="success",
                type="add_label",
                add_labels=["reviewed"],
                repo="owner/repo",
                issue="{{pr_number}}",
            )
        )
        manager.save_config("pjob", "test-pjob", pjob.to_dict())
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert result.exit_code == 0
        assert "add_label" in result.output
        assert "reviewed" in result.output

    def test_list_pjob_not_found(self):
        result = runner.invoke(app, ["pjob", "actions", "missing", "list"])
        assert result.exit_code != 0


class TestPJobActionsAdd:
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        self.tmp_path = tmp_path
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def test_add_label_action(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "success",
                "--type",
                "add_label",
                "--add-label",
                "reviewed",
                "--remove-label",
                "needs-review",
                "--repo",
                "owner/repo",
                "--issue",
                "{{pr_number}}",
            ],
        )
        assert result.exit_code == 0
        assert "added" in result.output.lower()
        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "add_label" in list_result.output
        assert "reviewed" in list_result.output

    def test_add_comment_action(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "failure",
                "--type",
                "add_comment",
                "--body",
                "Review failed",
                "--repo",
                "owner/repo",
                "--issue",
                "{{pr_number}}",
            ],
        )
        assert result.exit_code == 0

    def test_add_invalid_condition(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "invalid",
                "--type",
                "add_label",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid condition" in result.output

    def test_add_invalid_type(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "success",
                "--type",
                "invalid",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid type" in result.output

    def test_add_missing_condition(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "add", "--type", "add_label"])
        assert result.exit_code != 0

    def test_add_missing_type(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(
            app, ["pjob", "actions", "test-pjob", "add", "--condition", "success"]
        )
        assert result.exit_code != 0

    def test_add_label_warns_no_labels(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "success",
                "--type",
                "add_label",
            ],
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "warn" in output_lower

    def test_add_pjob_not_found(self):
        result = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "missing",
                "add",
                "--condition",
                "success",
                "--type",
                "add_label",
                "--add-label",
                "x",
            ],
        )
        assert result.exit_code != 0

    def test_add_multiple_actions(self):
        _create_deps(self.tmp_path)
        result1 = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "success",
                "--type",
                "add_label",
                "--add-label",
                "a",
            ],
        )
        assert result1.exit_code == 0
        result2 = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "failure",
                "--type",
                "add_comment",
                "--body",
                "fail",
            ],
        )
        assert result2.exit_code == 0
        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "add_label" in list_result.output
        assert "add_comment" in list_result.output

    def test_add_comment_warns_no_body(self):
        _create_deps(self.tmp_path)
        result = runner.invoke(
            app,
            [
                "pjob",
                "actions",
                "test-pjob",
                "add",
                "--condition",
                "failure",
                "--type",
                "add_comment",
            ],
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "warn" in output_lower


class TestPJobActionsRemove:
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        self.tmp_path = tmp_path
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def _create_with_actions(self, pjob_code="test-pjob"):
        _create_deps(self.tmp_path, pjob_code)
        runner.invoke(
            app,
            [
                "pjob",
                "actions",
                pjob_code,
                "add",
                "--condition",
                "success",
                "--type",
                "add_label",
                "--add-label",
                "a",
            ],
        )
        runner.invoke(
            app,
            [
                "pjob",
                "actions",
                pjob_code,
                "add",
                "--condition",
                "failure",
                "--type",
                "add_comment",
                "--body",
                "fail",
            ],
        )

    def test_remove_by_index(self):
        self._create_with_actions()
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "0"])
        assert result.exit_code == 0
        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "add_comment" in list_result.output
        assert "add_label" not in list_result.output

    def test_remove_out_of_range(self):
        self._create_with_actions()
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "99"])
        assert result.exit_code != 0

    def test_remove_pjob_not_found(self):
        result = runner.invoke(app, ["pjob", "actions", "missing", "remove", "--index", "0"])
        assert result.exit_code != 0

    def test_remove_last_action(self):
        self._create_with_actions()
        runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "0"])
        runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "0"])
        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "No postExec actions" in list_result.output
