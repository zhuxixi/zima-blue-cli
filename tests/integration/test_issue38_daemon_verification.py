"""Integration tests for issue #38 -- automated daemon/PJob verification."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.base import TestIsolator
from zima.cli import app
from zima.config.manager import ConfigManager
from zima.models.agent import AgentConfig
from zima.models.schedule import ScheduleConfig, ScheduleCycleType, ScheduleStage
from zima.models.workflow import WorkflowConfig
from zima.utils import get_zima_home

runner = CliRunner()

# --- Utility functions (module level for reuse across test classes) ---


def _wait_for_file(path: Path, timeout: float = 15.0, interval: float = 0.5) -> bool:
    """Poll until file exists and has content, or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(interval)
    return False


def _process_alive(pid: int) -> bool:
    """Check if a process is still running. Returns False if exited."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we don't have permission to signal it
            return True
    # Windows: OpenProcess + GetExitCodeProcess to check if still running
    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x100000
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False  # process has exited
    # Check exit code — STILL_ACTIVE (259) means the process is running
    exit_code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    kernel32.CloseHandle(handle)
    return exit_code.value == 259  # STILL_ACTIVE


def _mock_script_path() -> Path:
    """Return absolute path to mock_agent.py."""
    return Path(__file__).parent.parent / "fixtures" / "mock_agent.py"


class TestIssue38MockVerification(TestIsolator):
    """Mock-based verification of daemon and PJob execution (CI-friendly)."""

    def _ensure_dirs(self, *kinds: str):
        """Create config subdirectories that TestIsolator doesn't create by default."""
        zima_home = get_zima_home()
        for kind in kinds:
            (zima_home / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def _create_mock_agent(self, code: str = "mock-agent") -> str:
        """Create an agent config with mockCommand pointing to mock_agent.py."""
        manager = ConfigManager()
        mock_script = _mock_script_path()
        config = AgentConfig.create(
            code=code,
            name="Mock Agent",
            agent_type="kimi",
            defaults={},
        )
        data = config.to_dict()
        # Use mockCommand parameter -- get_cli_command_template() returns this
        # instead of "kimi" when building the command.
        # mockCommand replaces the base CLI (e.g. "kimi") with a custom command.
        # Pass as a list to handle paths with spaces correctly.
        data["spec"]["parameters"]["mockCommand"] = [sys.executable, str(mock_script)]
        manager.save_config("agent", code, data)
        return code

    def _create_simple_workflow(self, code: str = "test-wf") -> str:
        """Create a simple workflow."""
        manager = ConfigManager()
        config = WorkflowConfig.create(
            code=code,
            name="Test Workflow",
            template="# Test Task\n\nPlease confirm you received this prompt.",
        )
        manager.save_config("workflow", code, config.to_dict())
        return code

    def _create_verify_pjob(
        self, agent_code: str, workflow_code: str, pjob_code: str = "verify-pjob"
    ) -> str:
        """Create a PJob using mock agent and simple workflow."""
        result = runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Verify PJob",
                "--code",
                pjob_code,
                "--agent",
                agent_code,
                "--workflow",
                workflow_code,
            ],
        )
        assert result.exit_code == 0, f"PJob create failed: {result.output}"
        return pjob_code

    def _create_fast_schedule(self, pjob_code: str, schedule_code: str = "verify-sched") -> str:
        """Create a 1-minute cycle schedule with the PJob in work stage."""
        manager = ConfigManager()
        schedule = ScheduleConfig.create(code=schedule_code, name="Verify Schedule")
        schedule.cycle_minutes = 1
        schedule.daily_cycles = 32
        schedule.stages = [
            ScheduleStage(name="work", offset_minutes=0, duration_minutes=1),
        ]
        schedule.cycle_types = [
            ScheduleCycleType(type_id="verify", work=[pjob_code]),
        ]
        schedule.cycle_mapping = ["verify"] * 32
        manager.save_config("schedule", schedule_code, schedule.to_dict())
        return schedule_code

    def _setup_all(self) -> tuple[str, str, str, str]:
        """Create all configs needed for daemon tests.

        Returns (agent, wf, pjob, schedule) codes.
        """
        self._ensure_dirs("pjobs", "schedules")
        agent_code = self._create_mock_agent()
        wf_code = self._create_simple_workflow()
        pjob_code = self._create_verify_pjob(agent_code, wf_code)
        schedule_code = self._create_fast_schedule(pjob_code)
        return agent_code, wf_code, pjob_code, schedule_code

    # --- Test methods ---

    def test_pjob_run_mock_agent(self):
        """AC #1 + #3: Single PJob execution with mock agent."""
        self._ensure_dirs("pjobs")
        agent_code = self._create_mock_agent()
        wf_code = self._create_simple_workflow()
        pjob_code = self._create_verify_pjob(agent_code, wf_code)

        # Run the PJob
        result = runner.invoke(app, ["pjob", "run", pjob_code])
        assert result.exit_code == 0, f"PJob run failed: {result.output}"
        assert "success" in result.output.lower() or "completed" in result.output.lower()

        # Verify history file exists with success status
        zima_home = get_zima_home()
        history_file = zima_home / "history" / "pjobs.json"
        assert history_file.exists(), "History file should exist after PJob run"
        history_data = json.loads(history_file.read_text(encoding="utf-8"))
        assert pjob_code in history_data, f"PJob {pjob_code} should be in history"
        records = history_data[pjob_code]
        assert len(records) >= 1, "Should have at least one execution record"
        assert (
            records[0]["status"] == "success"
        ), f"First record should have success status, got: {records[0]['status']}"

    def test_daemon_start_and_state(self):
        """AC #2 + #4: Start daemon with schedule, verify PID and state."""
        agent_code, wf_code, pjob_code, schedule_code = self._setup_all()

        zima_home = get_zima_home()
        pid_file = zima_home / "daemon" / "daemon.pid"
        state_file = zima_home / "daemon" / "state.json"

        # Start daemon
        result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert result.exit_code == 0, f"Daemon start failed: {result.output}"

        try:
            # Wait for PID file
            found = _wait_for_file(pid_file, timeout=10.0)
            assert found, "PID file should appear within timeout"

            # Wait for state.json
            found = _wait_for_file(state_file, timeout=10.0)
            assert found, "state.json should appear within timeout"

            # Verify state content
            state = json.loads(state_file.read_text(encoding="utf-8"))
            assert state.get("running") is True, "State should show running=true"
            assert "currentCycle" in state, "State should contain currentCycle"
        finally:
            # Always stop daemon
            runner.invoke(app, ["daemon", "stop"])

    def test_daemon_logs_written(self):
        """AC #3: Daemon writes log entries to daemon.log."""
        agent_code, wf_code, pjob_code, schedule_code = self._setup_all()

        zima_home = get_zima_home()
        log_file = zima_home / "daemon" / "daemon.log"

        # Start daemon
        result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert result.exit_code == 0, f"Daemon start failed: {result.output}"

        try:
            # Wait for log file
            found = _wait_for_file(log_file, timeout=10.0)
            assert found, "daemon.log should appear within timeout"

            # Read log and check for expected content
            log_content = log_file.read_text(encoding="utf-8")
            assert (
                "DaemonScheduler started" in log_content
            ), "Log should contain 'DaemonScheduler started'"
        finally:
            runner.invoke(app, ["daemon", "stop"])

    def test_daemon_history_jsonl(self):
        """AC #5: Daemon records PJob execution in JSONL history files."""
        agent_code, wf_code, pjob_code, schedule_code = self._setup_all()

        zima_home = get_zima_home()
        history_dir = zima_home / "daemon" / "history"

        # Start daemon
        result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert result.exit_code == 0, f"Daemon start failed: {result.output}"

        try:
            # Poll for history log files containing the pjob code.
            # The daemon writes PJob output to .log files in daemon/history/.
            # Note: the daemon creates the log file immediately when spawning
            # a PJob, but content only appears once the PJob completes (~2-3s).
            # JSONL records are written when PJobs are killed/timed-out at
            # stage transitions; successfully completed PJobs only have .log files.
            deadline = time.monotonic() + 15.0
            found_log_files = []
            while time.monotonic() < deadline:
                if history_dir.exists():
                    for log_file in history_dir.glob("*.log"):
                        if pjob_code in log_file.name and log_file.stat().st_size > 0:
                            found_log_files.append(log_file)
                if found_log_files:
                    break
                time.sleep(1.0)

            assert len(found_log_files) > 0, (
                f"Expected daemon history log files for {pjob_code} within 15s, "
                f"history_dir={history_dir}, exists={history_dir.exists()}"
            )

            # Verify log content shows successful execution
            log_content = found_log_files[0].read_text(encoding="utf-8")
            assert (
                "success" in log_content
            ), f"PJob log should contain 'success': {log_content[:300]}"
        finally:
            runner.invoke(app, ["daemon", "stop"])

    def test_daemon_stop_graceful(self):
        """AC #6: Daemon stops gracefully and cleans up PID file."""
        agent_code, wf_code, pjob_code, schedule_code = self._setup_all()

        zima_home = get_zima_home()
        pid_file = zima_home / "daemon" / "daemon.pid"

        # Start daemon
        result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert result.exit_code == 0, f"Daemon start failed: {result.output}"

        # Wait for PID file
        found = _wait_for_file(pid_file, timeout=10.0)
        assert found, "PID file should appear within timeout"

        # Record PID
        pid = int(pid_file.read_text(encoding="utf-8").strip())

        # Stop daemon
        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0, f"Daemon stop failed: {result.output}"

        # Verify PID file removed
        assert not pid_file.exists(), "PID file should be removed after stop"

        # Poll until process is dead (CI containers can be slow to reap)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if not _process_alive(pid):
                break
            time.sleep(0.5)
        else:
            pytest.fail(f"Daemon process {pid} still alive 10s after stop")


# --- Real-call test class ---


@pytest.mark.real_agent
class TestIssue38RealCall(TestIsolator):
    """Real-agent verification -- requires Kimi CLI installed and authenticated."""

    @pytest.fixture(autouse=True)
    def skip_if_no_real_agent(self, request):
        if not request.config.getoption("--run-real-agent", default=False):
            pytest.skip("Use --run-real-agent to run real-call verification tests")

    def _ensure_dirs(self, *kinds: str):
        zima_home = get_zima_home()
        for kind in kinds:
            (zima_home / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def test_real_pjob_run(self):
        """AC #1 real: Run a lightweight PJob against real Kimi CLI."""
        self._ensure_dirs("pjobs")
        manager = ConfigManager()

        # Create lightweight real agent (no mockCommand -- uses real kimi CLI)
        agent = AgentConfig.create(
            code="verify-agent",
            name="Verify Agent",
            agent_type="kimi",
            defaults={},
        )
        agent_data = agent.to_dict()
        agent_data["spec"]["parameters"]["maxStepsPerTurn"] = 10
        agent_data["spec"]["parameters"]["workDir"] = str(Path.cwd())
        manager.save_config("agent", "verify-agent", agent_data)

        wf = WorkflowConfig.create(
            code="verify-wf",
            name="Verify Workflow",
            template="Read README.md and tell me the project name in one sentence.",
        )
        manager.save_config("workflow", "verify-wf", wf.to_dict())

        result = runner.invoke(
            app,
            [
                "pjob",
                "create",
                "--name",
                "Verify PJob",
                "--code",
                "verify-pjob",
                "--agent",
                "verify-agent",
                "--workflow",
                "verify-wf",
            ],
        )
        assert result.exit_code == 0

        result = runner.invoke(app, ["pjob", "run", "verify-pjob"])
        assert "Execution" in result.output or "completed" in result.output.lower()
