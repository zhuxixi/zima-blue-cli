"""Integration tests for PJob lifecycle."""

import pytest
from typer.testing import CliRunner

from zima.cli import app
from zima.config.manager import ConfigManager
from zima.models.agent import AgentConfig
from zima.models.env import EnvConfig
from zima.models.pmg import PMGConfig
from zima.models.variable import VariableConfig
from zima.models.workflow import WorkflowConfig

runner = CliRunner()


class TestPJobLifecycle:
    """Test PJob complete lifecycle."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment."""
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()

        # Create required directories
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def create_test_agent(self, code="test-agent"):
        """Helper to create test agent."""
        config = AgentConfig.create(
            code=code,
            name="Test Agent",
            agent_type="kimi",
            defaults={"variable": "default-var", "env": "default-env"},
        )
        self.manager.save_config("agent", code, config.to_dict())
        return config

    def create_test_workflow(self, code="test-workflow"):
        """Helper to create test workflow."""
        config = WorkflowConfig.create(
            code=code,
            name="Test Workflow",
            template="# Hello {{ name }}",
        )
        self.manager.save_config("workflow", code, config.to_dict())
        return config

    def create_test_variable(self, code="test-var"):
        """Helper to create test variable."""
        config = VariableConfig.create(
            code=code,
            name="Test Variable",
            values={"name": "World"},
        )
        self.manager.save_config("variable", code, config.to_dict())
        return config

    def create_test_env(self, code="test-env"):
        """Helper to create test env."""
        config = EnvConfig.create(
            code=code,
            name="Test Env",
            for_type="kimi",
            variables={"DEBUG": "false"},
        )
        self.manager.save_config("env", code, config.to_dict())
        return config

    def create_test_pmg(self, code="test-pmg"):
        """Helper to create test pmg."""
        config = PMGConfig.create(
            code=code,
            name="Test PMG",
            for_types=["kimi"],
        )
        self.manager.save_config("pmg", code, config.to_dict())
        return config

    def test_create_pjob(self):
        """Test creating PJob."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        result = runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "test-pjob" in result.output

    def test_create_pjob_missing_agent_fails(self):
        """Test creating PJob with missing agent fails."""
        self.create_test_workflow()

        result = runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "missing-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_list_pjobs(self):
        """Test listing PJobs."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        # Create a PJob
        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
                "--label",
                "test",
                "--label",
                "auto",
            ],
        )

        result = runner.invoke(app, ["pjob", "list"])

        assert result.exit_code == 0
        assert "test-pjob" in result.output
        assert "Test PJob" in result.output

    def test_list_pjobs_with_label_filter(self):
        """Test listing PJobs with label filter."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        # Create PJobs with different labels
        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "PJob A",
                "--code",
                "pjob-a",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
                "--label",
                "group-a",
            ],
        )
        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "PJob B",
                "--code",
                "pjob-b",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
                "--label",
                "group-b",
            ],
        )

        result = runner.invoke(app, ["pjob", "list", "--label", "group-a"])

        assert result.exit_code == 0
        assert "pjob-a" in result.output
        assert "pjob-b" not in result.output

    def test_show_pjob(self):
        """Test showing PJob details."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(app, ["pjob", "show", "test-pjob"])

        assert result.exit_code == 0
        assert "Test PJob" in result.output
        assert "test-agent" in result.output
        assert "test-workflow" in result.output

    def test_update_pjob(self):
        """Test updating PJob."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()
        self.create_test_env()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(
            app,
            [
                "pjob",
                "update",
                "test-pjob",
                "--env",
                "test-env",
                "--timeout",
                "1200",
            ],
        )

        assert result.exit_code == 0
        assert "updated successfully" in result.output

        # Verify update
        show_result = runner.invoke(app, ["pjob", "show", "test-pjob"])
        assert "test-env" in show_result.output

    def test_delete_pjob(self):
        """Test deleting PJob."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(app, ["pjob", "delete", "test-pjob", "--force"])

        assert result.exit_code == 0
        assert "deleted" in result.output

        # Verify deletion
        show_result = runner.invoke(app, ["pjob", "show", "test-pjob"])
        assert show_result.exit_code != 0

    def test_copy_pjob(self):
        """Test copying PJob."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Source PJob",
                "--code",
                "source-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(
            app,
            [
                "pjob",
                "copy",
                "source-pjob",
                "target-pjob",
                "--name",
                "Target PJob",
            ],
        )

        assert result.exit_code == 0
        assert "copied" in result.output

        # Verify copy exists
        show_result = runner.invoke(app, ["pjob", "show", "target-pjob"])
        assert show_result.exit_code == 0
        assert "Target PJob" in show_result.output

    def test_validate_pjob(self):
        """Test validating PJob."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(app, ["pjob", "validate", "test-pjob"])

        assert result.exit_code == 0
        assert "is valid" in result.output

    def test_validate_pjob_strict(self):
        """Test strict validation of PJob."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(app, ["pjob", "validate", "test-pjob", "--strict"])

        assert result.exit_code == 0
        assert "is valid" in result.output
        assert "All referenced configs exist" in result.output

    def test_render_pjob(self):
        """Test rendering PJob template."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()
        self.create_test_variable()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
                "--variable",
                "test-var",
            ],
        )

        result = runner.invoke(app, ["pjob", "render", "test-pjob"])

        assert result.exit_code == 0
        assert "Hello World" in result.output  # Template rendered with variable

    def test_render_pjob_show_command(self):
        """Test rendering PJob with command display."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(app, ["pjob", "render", "test-pjob", "--show-command"])

        assert result.exit_code == 0
        assert "kimi" in result.output  # Command contains kimi

    def test_run_pjob_dry_run(self):
        """Test dry-run of PJob."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(app, ["pjob", "run", "test-pjob", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "kimi" in result.output

    def test_run_pjob_with_overrides(self):
        """Test running PJob with overrides."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(
            app,
            [
                "pjob",
                "run",
                "test-pjob",
                "--dry-run",
                "--set-param",
                "model=kimi-k1.5",
                "--set-env",
                "DEBUG=true",
            ],
        )

        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_history_empty(self):
        """Test history for PJob with no history."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Test PJob",
                "--code",
                "test-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(app, ["pjob", "history", "test-pjob"])

        assert result.exit_code == 0
        assert "No execution history" in result.output

    def test_create_from_existing(self):
        """Test creating PJob from existing."""
        # Create dependencies
        self.create_test_agent()
        self.create_test_workflow()

        runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Source PJob",
                "--code",
                "source-pjob",
                "--agent",
                "test-agent",
                "--workflow",
                "test-workflow",
            ],
        )

        result = runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Copied PJob",
                "--code",
                "copied-pjob",
                "--from-code",
                "source-pjob",
            ],
        )

        assert result.exit_code == 0
        assert "created from" in result.output


class TestBackgroundRunnerState:
    """Test background runner writes state files correctly."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)
        from zima.execution.history import ExecutionHistory
        self.history = ExecutionHistory()

    def create_deps(self):
        agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
        self.manager.save_config("agent", "test-agent", agent.to_dict())
        wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
        self.manager.save_config("workflow", "test-workflow", wf.to_dict())

        from typer.testing import CliRunner
        from zima.cli import app
        runner = CliRunner()
        result = runner.invoke(app, [
            "pjob", "create",
            "--name", "Test PJob", "--code", "test-pjob",
            "--agent", "test-agent", "--workflow", "test-workflow",
        ])
        assert result.exit_code == 0

    def test_background_runner_state_file_lifecycle(self):
        """State file is written at start and updated on completion."""
        self.create_deps()
        from datetime import datetime, timezone

        execution_id = "test0001"
        started_at = datetime.now(timezone.utc).astimezone().isoformat()

        # Simulate CLI writing initial state file
        self.history.write_runtime_state("test-pjob", execution_id, {
            "execution_id": execution_id,
            "pjob_code": "test-pjob",
            "status": "running",
            "pid": 99999,
            "command": ["echo", "test"],
            "started_at": started_at,
            "finished_at": None,
            "duration_seconds": None,
            "returncode": None,
            "stdout_preview": "",
            "stderr_preview": "",
            "error_detail": "",
            "log_path": str(self.temp_dir / "logs" / "background" / f"test-pjob-{execution_id}.log"),
            "agent": "kimi",
            "workflow": "test-workflow",
        })

        # Verify state file exists with running status
        state = self.history.get_runtime_state("test-pjob", execution_id)
        assert state is not None
        assert state["status"] == "running"
        assert state["pjob_code"] == "test-pjob"

        # Simulate background_runner completing
        self.history.update_runtime_state(
            "test-pjob", execution_id,
            status="success",
            returncode=0,
            duration_seconds=5.0,
            stdout_preview="test output",
        )

        updated = self.history.get_runtime_state("test-pjob", execution_id)
        assert updated["status"] == "success"
        assert updated["returncode"] == 0
        assert updated["duration_seconds"] == 5.0


class TestPJobRuntimeCommands:
    """Integration tests for status, ps, cancel, and list runtime indicators."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)
        from zima.execution.history import ExecutionHistory
        self.history = ExecutionHistory()

    def create_deps(self):
        from zima.models.agent import AgentConfig
        from zima.models.workflow import WorkflowConfig
        agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
        self.manager.save_config("agent", "test-agent", agent.to_dict())
        wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
        self.manager.save_config("workflow", "test-workflow", wf.to_dict())
        from typer.testing import CliRunner
        from zima.cli import app
        runner = CliRunner()
        result = runner.invoke(app, [
            "pjob", "create",
            "--name", "Test PJob", "--code", "test-pjob",
            "--agent", "test-agent", "--workflow", "test-workflow",
        ])
        assert result.exit_code == 0

    def test_status_no_history(self):
        """status shows message when no history exists."""
        self.create_deps()
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "status", "test-pjob"])
        assert result.exit_code == 0
        assert "No execution history" in result.output

    def test_status_shows_running(self):
        """status command shows running execution."""
        self.create_deps()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).astimezone().isoformat()
        self.history.write_runtime_state("test-pjob", "run001", {
            "execution_id": "run001",
            "pjob_code": "test-pjob",
            "status": "running",
            "pid": 99999,
            "started_at": now,
            "log_path": str(self.temp_dir / "logs" / "background" / "test-pjob-run001.log"),
            "agent": "kimi",
            "workflow": "test-workflow",
        })
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "status", "test-pjob"])
        assert result.exit_code == 0
        assert "run001" in result.output

    def test_status_shows_mixed(self):
        """status shows both running and completed executions."""
        self.create_deps()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).astimezone().isoformat()
        self.history.write_runtime_state("test-pjob", "run001", {
            "execution_id": "run001", "pjob_code": "test-pjob",
            "status": "running", "pid": 99999, "started_at": now,
        })
        self.history.write_runtime_state("test-pjob", "run002", {
            "execution_id": "run002", "pjob_code": "test-pjob",
            "status": "success", "pid": 10000, "started_at": now,
            "duration_seconds": 10.0, "returncode": 0,
        })
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "status", "test-pjob"])
        assert result.exit_code == 0
        assert "run001" in result.output
        assert "run002" in result.output

    def test_ps_empty(self):
        """ps command shows message when nothing is running."""
        self.create_deps()
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "ps"])
        assert result.exit_code == 0
        assert "No running" in result.output

    def test_cancel_not_found(self):
        """cancel with non-existent execution ID."""
        self.create_deps()
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "cancel", "test-pjob", "--id", "nonexistent"])
        assert result.exit_code == 1

    def test_cancel_marks_dead_pid(self):
        """cancel marks dead PID as dead status."""
        self.create_deps()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).astimezone().isoformat()
        self.history.write_runtime_state("test-pjob", "run001", {
            "execution_id": "run001", "pjob_code": "test-pjob",
            "status": "running", "pid": 99999999, "started_at": now,
        })
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "cancel", "test-pjob", "--id", "run001"])
        assert result.exit_code == 0
        state = self.history.get_runtime_state("test-pjob", "run001")
        assert state["status"] in ("cancelled", "dead")

    def test_list_shows_running_indicator(self):
        """pjob list shows running indicator for pjobs with active executions."""
        self.create_deps()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).astimezone().isoformat()
        self.history.write_runtime_state("test-pjob", "run001", {
            "execution_id": "run001", "pjob_code": "test-pjob",
            "status": "running", "pid": 99999, "started_at": now,
        })
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "list"])
        assert result.exit_code == 0
        assert "test-pjob" in result.output

    def test_history_shows_running_status(self):
        """history command shows running records with appropriate status."""
        self.create_deps()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).astimezone().isoformat()
        self.history.write_runtime_state("test-pjob", "run001", {
            "execution_id": "run001", "pjob_code": "test-pjob",
            "status": "running", "pid": 99999, "started_at": now,
        })
        from typer.testing import CliRunner
        from zima.cli import app
        result = CliRunner().invoke(app, ["pjob", "history", "test-pjob"])
        assert result.exit_code == 0
        assert "run001" in result.output
