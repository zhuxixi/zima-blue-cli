# Issue #38 Automated Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-layer automated verification suite (mock tests for CI + real-call tests for manual verification) that replaces the manual steps in issue #38.

**Architecture:** Mock tests use a `mockCommand` parameter in `AgentConfig.get_cli_command_template()` (3-line production change) to redirect execution to a Python shim script (`tests/fixtures/mock_agent.py`). This avoids adding a new agent type or modifying the executor. Real-call tests are gated behind a `--real-agent` pytest flag. A checklist script provides filesystem-level verification for manual runs.

**Tech Stack:** pytest, Python 3.10+, Typer CliRunner, subprocess, jinja2 (existing)

> ⚠️ **Outdated Reference (Issue #43)**: This plan assumes a per-agent log directory (`~/.zima/agents/*/logs/`). The actual implementation uses the system temp directory (`zima-pjobs/`) and stores history centrally in `~/.zima/history/pjobs.json`. See [AGENTS.md](../../../AGENTS.md) for the accurate data layout.

---

## File Structure

| Path | Responsibility |
|------|---------------|
| `zima/models/agent.py` | **Modified:** Add `mockCommand` check to `get_cli_command_template()` (3 lines) |
| `tests/fixtures/mock_agent.py` | Mock Kimi CLI shim — parses all kimi flags, sleeps 2s, prints JSON result |
| `tests/integration/test_issue38_daemon_verification.py` | Main test suite — 5 mock tests + 1 real-call test, all using `TestIsolator` |
| `scripts/verify_issue38_checklist.py` | Filesystem checklist — inspects `~/.zima` and prints pass/fail for all 6 AC |
| `scripts/verify-issue38.sh` | Convenience wrapper — runs mock tests by default, passes `--real-agent` through |
| `pyproject.toml` | Add `real_agent` pytest marker |

---

## Task 1: Add `mockCommand` support + `real_agent` pytest marker

**Files:**
- Modify: `zima/models/agent.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `mockCommand` check to `get_cli_command_template()`**

In `zima/models/agent.py`, modify `get_cli_command_template()` (around line 196) to check for `mockCommand` before the hardcoded templates:

```python
def get_cli_command_template(self) -> list[str]:
    """Get base CLI command template for this agent type."""
    # Mock override: if mockCommand is set, use it instead of real CLI
    if self.parameters.get("mockCommand"):
        return [str(self.parameters["mockCommand"])]

    templates = {
        "kimi": ["kimi", "--print", "--yolo"],
        "claude": ["claude", "-p"],
        "gemini": ["gemini", "--yolo"],
    }
    return templates.get(self.type, [])
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/unit/test_models_agent.py -v`

Expected: All existing tests pass (mockCommand is not set in any production config).

- [ ] **Step 3: Add `real_agent` marker to pytest config**

Find the `[tool.pytest.ini_options]` section in `pyproject.toml` and add the `real_agent` marker to the existing `markers` list.

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "real_agent: tests that call the real Kimi/Claude CLI (slow, manual)",
]
```

- [ ] **Step 4: Verify marker is registered**

Run: `pytest --markers | grep real_agent`

Expected output contains: `@pytest.mark.real_agent: tests that call the real Kimi/Claude CLI (slow, manual)`

- [ ] **Step 5: Commit**

```bash
git add zima/models/agent.py pyproject.toml
git commit -m "feat(agent): add mockCommand parameter + real_agent pytest marker for #38"
```

---

## Task 2: Create mock agent fixture

**Files:**
- Create: `tests/fixtures/mock_agent.py`

- [ ] **Step 1: Create the mock agent script**

The script must accept all flags that `_build_kimi_command()` generates (see `zima/models/agent.py` lines 261-282). Flag names use hyphens (e.g., `--max-steps-per-turn`, not `--maxStepsPerTurn`) because `_build_kimi_command` outputs hyphenated flags.

```python
#!/usr/bin/env python3
"""Mock agent for testing. Simulates kimi CLI with minimal delay."""

import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    # Flags matching _build_kimi_command() output
    parser.add_argument("--prompt", required=True, help="Path to prompt file")
    parser.add_argument("--model", default="mock", help="Model name")
    parser.add_argument("--max-steps-per-turn", type=int, default=10, help="Max steps per turn")
    parser.add_argument("--max-ralph-iterations", type=int, default=3)
    parser.add_argument("--max-retries-per-step", type=int, default=1)
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--work-dir", default=".", help="Working directory")
    parser.add_argument("--output-format", default="text")
    # Flags from build_command() prompt/workdir handling
    args = parser.parse_args()

    # Validate prompt file exists
    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        return 1

    # Read and echo back a snippet (proves file was read)
    prompt_content = prompt_path.read_text(encoding="utf-8")
    summary = prompt_content[:200].replace("\n", " ")

    # Simulate work
    time.sleep(2)

    # Output structured result
    result = {
        "status": "success",
        "model": args.model,
        "steps": args.max_steps_per_turn,
        "summary": f"Mock agent completed. Prompt preview: {summary}...",
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make script executable (Unix)**

Run: `chmod +x tests/fixtures/mock_agent.py`

(Windows does not need this step.)

- [ ] **Step 3: Test mock agent standalone**

Run:
```bash
python tests/fixtures/mock_agent.py --prompt README.md --model mock --max-steps-per-turn 5 --yolo
```

Expected: JSON output with `"status": "success"` and a prompt preview from `README.md`.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/mock_agent.py
git commit -m "test(fixtures): add mock agent shim for daemon verification"
```

---

## Task 3: Write mock verification tests

**Files:**
- Create: `tests/integration/test_issue38_daemon_verification.py`

- [ ] **Step 1: Write test file skeleton, imports, and utility functions**

```python
"""Integration tests for issue #38 — automated daemon/PJob verification."""

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
from zima.models.schedule import ScheduleConfig, ScheduleStage, ScheduleCycleType
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
    # Windows: OpenProcess returns NULL (0) if process has exited
    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x100000
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True  # process still alive
    return False  # process has exited


def _mock_script_path() -> Path:
    """Return absolute path to mock_agent.py."""
    return Path(__file__).parent.parent / "fixtures" / "mock_agent.py"
```

- [ ] **Step 2: Write TestIssue38MockVerification class with helper methods**

```python
class TestIssue38MockVerification(TestIsolator):
    """Mock-based verification of daemon and PJob execution (CI-friendly)."""

    def _ensure_dirs(self, *kinds: str):
        """Create config subdirectories that TestIsolator doesn't create by default."""
        zima_home = get_zima_home()
        for kind in kinds:
            (zima_home / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def _create_mock_agent(self, code="mock-agent"):
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
        # Use mockCommand parameter — get_cli_command_template() returns this instead of "kimi"
        data["spec"]["parameters"]["mockCommand"] = f"{sys.executable} {mock_script}"
        manager.save_config("agent", code, data)
        return code

    def _create_simple_workflow(self, code="test-wf"):
        """Create a simple workflow."""
        manager = ConfigManager()
        config = WorkflowConfig.create(
            code=code,
            name="Test Workflow",
            template="# Test Task\n\nPlease confirm you received this prompt.",
        )
        manager.save_config("workflow", code, config.to_dict())
        return code

    def _create_verify_pjob(self, agent_code, workflow_code, pjob_code="verify-pjob"):
        """Create a PJob using mock agent and simple workflow."""
        result = runner.invoke(
            app,
            [
                "pjob", "create",
                "--name", "Verify PJob",
                "--code", pjob_code,
                "--agent", agent_code,
                "--workflow", workflow_code,
            ],
        )
        assert result.exit_code == 0, f"PJob create failed: {result.output}"
        return pjob_code

    def _create_fast_schedule(self, pjob_code, schedule_code="verify-sched"):
        """Create a 1-minute cycle schedule with the PJob in work stage."""
        manager = ConfigManager()
        schedule = ScheduleConfig.create(code=schedule_code, name="Verify Schedule")
        schedule.cycle_minutes = 1
        schedule.daily_cycles = 32
        schedule.stages = [
            ScheduleStage(name="work", offset_minutes=0, duration_minutes=1),
        ]
        schedule.cycle_types = [
            ScheduleCycleType(type_id="verify", work=[pjob_code])
        ]
        schedule.cycle_mapping = ["idle", "verify"] + ["idle"] * 30
        manager.save_config("schedule", schedule_code, schedule.to_dict())
        return schedule_code

    def _setup_all(self):
        """Create all configs needed for daemon tests. Returns (agent, wf, pjob, schedule) codes."""
        self._ensure_dirs("pjobs", "schedules")
        agent_code = self._create_mock_agent()
        wf_code = self._create_simple_workflow()
        pjob_code = self._create_verify_pjob(agent_code, wf_code)
        schedule_code = self._create_fast_schedule(pjob_code)
        return agent_code, wf_code, pjob_code, schedule_code
```

**Key points:**
- Inherits `TestIsolator` which sets `ZIMA_HOME` and creates base config dirs via autouse fixture
- `_ensure_dirs("pjobs", "schedules")` creates only the dirs `TestIsolator` doesn't provide
- `_create_mock_agent` uses `mockCommand` parameter instead of overriding `spec.parameters.command`
- `mockCommand` is set as `f"{sys.executable} {mock_script}"` so `get_cli_command_template()` returns a single string that works as a shell command

- [ ] **Step 3: Write test_pjob_run_mock_agent**

```python
    def test_pjob_run_mock_agent(self):
        """AC #1 + #3: PJob single execution with mock agent writes logs."""
        self._ensure_dirs("pjobs")
        agent_code = self._create_mock_agent()
        wf_code = self._create_simple_workflow()
        pjob_code = self._create_verify_pjob(agent_code, wf_code)

        result = runner.invoke(app, ["pjob", "run", pjob_code])

        assert result.exit_code == 0, f"PJob run failed: {result.output}"
        assert "completed" in result.output.lower() or "success" in result.output.lower()

        # Verify execution history was recorded
        zima_home = get_zima_home()
        history_file = zima_home / "history" / "pjobs.json"
        assert history_file.exists(), "Execution history file not created"
        history_data = json.loads(history_file.read_text(encoding="utf-8"))
        assert pjob_code in history_data
        assert len(history_data[pjob_code]) >= 1
        assert history_data[pjob_code][0]["status"] == "success"
```

- [ ] **Step 4: Write test_daemon_start_and_state**

```python
    def test_daemon_start_and_state(self):
        """AC #2 + #4: Daemon starts, creates PID file and state.json."""
        _, _, pjob_code, schedule_code = self._setup_all()

        # Start daemon
        result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert result.exit_code == 0, f"Daemon start failed: {result.output}"
        assert "started" in result.output.lower()

        zima_home = get_zima_home()

        # Verify PID file
        pid_file = zima_home / "daemon" / "daemon.pid"
        assert _wait_for_file(pid_file, timeout=5), "PID file not created"
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        assert pid > 0

        # Verify state.json
        state_file = zima_home / "daemon" / "state.json"
        assert _wait_for_file(state_file, timeout=5), "State file not created"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state.get("running") is True
        assert "currentCycle" in state

        # Cleanup: stop daemon
        runner.invoke(app, ["daemon", "stop"])
```

- [ ] **Step 5: Write test_daemon_logs_written**

```python
    def test_daemon_logs_written(self):
        """AC #3: Daemon writes logs to daemon.log."""
        _, _, _, schedule_code = self._setup_all()

        # Start daemon
        result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert result.exit_code == 0

        # Poll for log file instead of fixed sleep
        zima_home = get_zima_home()
        log_file = zima_home / "daemon" / "daemon.log"
        assert _wait_for_file(log_file, timeout=10), "Daemon log not created"
        log_content = log_file.read_text(encoding="utf-8")
        assert "DaemonScheduler started" in log_content or "cycle" in log_content.lower()

        # Cleanup
        runner.invoke(app, ["daemon", "stop"])
```

- [ ] **Step 6: Write test_daemon_history_jsonl**

```python
    def test_daemon_history_jsonl(self):
        """AC #5: Daemon records execution history in JSONL."""
        _, _, pjob_code, schedule_code = self._setup_all()

        # Start daemon and let it run briefly
        result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert result.exit_code == 0

        # Give daemon time to trigger work stage (1-min cycle, cycle 1 = verify)
        # Poll for history files instead of fixed sleep
        zima_home = get_zima_home()
        history_dir = zima_home / "daemon" / "history"

        found = False
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not found:
            jsonl_files = list(history_dir.glob("*.jsonl")) if history_dir.exists() else []
            if jsonl_files:
                # Check if any file has content for our pjob
                for f in jsonl_files:
                    content = f.read_text(encoding="utf-8").strip()
                    if pjob_code in content:
                        found = True
                        break
            if not found:
                time.sleep(0.5)

        # Stop daemon (triggers history recording for killed PJobs)
        runner.invoke(app, ["daemon", "stop"])

        assert found, f"No JSONL history records for {pjob_code}"
```

- [ ] **Step 7: Write test_daemon_stop_graceful**

```python
    def test_daemon_stop_graceful(self):
        """AC #6: Daemon stops gracefully, cleans up PID file."""
        _, _, _, schedule_code = self._setup_all()

        # Start daemon
        start_result = runner.invoke(app, ["daemon", "start", "--schedule", schedule_code])
        assert start_result.exit_code == 0

        zima_home = get_zima_home()
        pid_file = zima_home / "daemon" / "daemon.pid"
        assert _wait_for_file(pid_file, timeout=5)
        pid = int(pid_file.read_text(encoding="utf-8").strip())

        # Stop daemon
        stop_result = runner.invoke(app, ["daemon", "stop"])
        assert stop_result.exit_code == 0, f"Daemon stop failed: {stop_result.output}"
        assert "stopped" in stop_result.output.lower()

        # Verify PID file removed
        assert not pid_file.exists(), "PID file not cleaned up after stop"

        # Verify daemon process is gone
        assert not _process_alive(pid), f"Daemon process {pid} still running after stop"
```

- [ ] **Step 8: Write real-call test (skipped by default)**

```python

class TestIssue38RealCall(TestIsolator):
    """Real-agent verification — requires Kimi CLI installed and authenticated."""

    @pytest.fixture(autouse=True)
    def skip_if_no_real_agent(self, pytestconfig):
        if not pytestconfig.getoption("--real-agent", default=False):
            pytest.skip("Use --real-agent to run real-call verification tests")

    def _ensure_dirs(self, *kinds: str):
        """Create config subdirectories that TestIsolator doesn't create by default."""
        zima_home = get_zima_home()
        for kind in kinds:
            (zima_home / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def test_real_pjob_run(self):
        """AC #1 real: Run a lightweight PJob against real Kimi CLI."""
        self._ensure_dirs("pjobs")
        manager = ConfigManager()

        # Create lightweight real agent (no mockCommand — uses real kimi CLI)
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

        # Create simple workflow
        wf = WorkflowConfig.create(
            code="verify-wf",
            name="Verify Workflow",
            template="Read README.md and tell me the project name in one sentence.",
        )
        manager.save_config("workflow", "verify-wf", wf.to_dict())

        # Create PJob
        result = runner.invoke(
            app,
            [
                "pjob", "create",
                "--name", "Verify PJob",
                "--code", "verify-pjob",
                "--agent", "verify-agent",
                "--workflow", "verify-wf",
            ],
        )
        assert result.exit_code == 0

        # Run PJob (this calls real Kimi CLI)
        result = runner.invoke(app, ["pjob", "run", "verify-pjob"])
        # We don't assert exit_code == 0 because Kimi may fail for various reasons
        # Just verify it ran and produced output
        assert "Execution" in result.output or "completed" in result.output.lower()
```

- [ ] **Step 9: Commit**

```bash
git add tests/integration/test_issue38_daemon_verification.py
git commit -m "test(integration): add issue #38 daemon/PJob verification tests"
```

---

## Task 4: Create filesystem checklist script

**Files:**
- Create: `scripts/verify_issue38_checklist.py`

- [ ] **Step 1: Write the checklist script**

```python
#!/usr/bin/env python3
"""Issue #38 verification checklist — inspects ~/.zima filesystem state."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def check_pass(name: str, detail: str = "") -> dict:
    return {"status": "PASS", "name": name, "detail": detail}


def check_fail(name: str, detail: str = "") -> dict:
    return {"status": "FAIL", "name": name, "detail": detail}


def check_file_exists(path: Path, name: str) -> dict:
    if path.exists():
        return check_pass(name, str(path))
    return check_fail(name, f"Not found: {path}")


def main() -> int:
    zima_home = Path.home() / ".zima"
    checks = []

    # AC #1 + #3: PJob execution log
    agent_logs_dir = zima_home / "agents"
    log_files = []
    if agent_logs_dir.exists():
        for agent_dir in agent_logs_dir.iterdir():
            logs_dir = agent_dir / "logs"
            if logs_dir.exists():
                log_files.extend(logs_dir.glob("*.log"))

    if log_files:
        checks.append(check_pass("PJob execution log exists", str(log_files[0])))
    else:
        checks.append(check_fail("PJob execution log exists", "No .log files in ~/.zima/agents/*/logs/"))

    # AC #4: Daemon state file
    state_file = zima_home / "daemon" / "state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            checks.append(check_pass("Daemon state file exists and valid", str(state_file)))
        except json.JSONDecodeError as e:
            checks.append(check_fail("Daemon state file exists and valid", f"Invalid JSON: {e}"))
    else:
        checks.append(check_fail("Daemon state file exists and valid", str(state_file)))

    # AC #5: Execution history JSONL
    history_dir = zima_home / "daemon" / "history"
    jsonl_files = list(history_dir.glob("*.jsonl")) if history_dir.exists() else []
    if jsonl_files:
        checks.append(check_pass("Execution history JSONL exists", str(jsonl_files[0])))
    else:
        checks.append(check_fail("Execution history JSONL exists", "No .jsonl files in ~/.zima/daemon/history/"))

    # AC #6: PID file cleaned up
    pid_file = zima_home / "daemon" / "daemon.pid"
    if pid_file.exists():
        checks.append(check_fail("PID file cleaned up after stop", f"Still exists: {pid_file}"))
    else:
        checks.append(check_pass("PID file cleaned up after stop"))

    # AC #6: No orphaned processes
    if sys.platform == "win32":
        import subprocess

        # Use wmic to find daemon_runner processes by command line
        # tasklist does NOT include command-line arguments, so it's useless here
        result = subprocess.run(
            [
                "wmic", "process", "where",
                "commandline like '%daemon_runner%'",
                "get", "processid",
            ],
            capture_output=True,
            text=True,
        )
        # wmic returns header line + empty lines + PIDs if found
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and l.strip() != "ProcessId"]
        if len(lines) == 0:
            checks.append(check_pass("No orphaned daemon processes"))
        else:
            checks.append(check_fail("No orphaned daemon processes", f"Found PIDs: {', '.join(lines)}"))
    else:
        import subprocess
        result = subprocess.run(
            ["pgrep", "-f", "daemon_runner"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:  # pgrep returns 1 if no match
            checks.append(check_pass("No orphaned daemon processes"))
        else:
            pids = result.stdout.strip()
            checks.append(check_fail("No orphaned daemon processes", f"Found PIDs: {pids}"))

    # Print report
    print("Issue #38 Verification Checklist")
    print("=" * 40)
    passed = sum(1 for c in checks if c["status"] == "PASS")
    for c in checks:
        icon = "[PASS]" if c["status"] == "PASS" else "[FAIL]"
        print(f"{icon} {c['name']}")
        if c["detail"]:
            print(f"       {c['detail']}")

    print()
    print(f"Result: {passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Test checklist script**

Run: `python scripts/verify_issue38_checklist.py`

Expected: Checklist output showing PASS/FAIL for each AC. Since no daemon has run yet, most should show FAIL (which is expected behavior).

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_issue38_checklist.py
git commit -m "feat(scripts): add issue #38 filesystem verification checklist"
```

---

## Task 5: Create convenience wrapper script

**Files:**
- Create: `scripts/verify-issue38.sh`
- Create: `scripts/verify-issue38.bat` (Windows equivalent)

- [ ] **Step 1: Write Unix wrapper script**

```bash
#!/usr/bin/env bash
# Issue #38 verification wrapper
# Usage: ./scripts/verify-issue38.sh [--real-agent]

set -euo pipefail

REAL_AGENT=""
if [[ "${1:-}" == "--real-agent" ]]; then
    REAL_AGENT="--real-agent"
    echo "Running with REAL agent (slow)..."
else
    echo "Running mock verification suite..."
fi

echo ""
echo "=== Running pytest integration tests ==="
pytest tests/integration/test_issue38_daemon_verification.py -v ${REAL_AGENT}

echo ""
echo "=== Running filesystem checklist ==="
python scripts/verify_issue38_checklist.py

echo ""
echo "Verification complete."
```

- [ ] **Step 2: Write Windows wrapper script**

```batch
@echo off
REM Issue #38 verification wrapper
REM Usage: .\scripts\verify-issue38.bat [--real-agent]

set "REAL_AGENT="
if "%~1"=="--real-agent" (
    set "REAL_AGENT=--real-agent"
    echo Running with REAL agent (slow)...
) else (
    echo Running mock verification suite...
)

echo.
echo === Running pytest integration tests ===
pytest tests/integration/test_issue38_daemon_verification.py -v %REAL_AGENT%

echo.
echo === Running filesystem checklist ===
python scripts/verify_issue38_checklist.py

echo.
echo Verification complete.
```

- [ ] **Step 3: Make Unix script executable**

Run: `chmod +x scripts/verify-issue38.sh`

- [ ] **Step 4: Test mock run**

Run: `pytest tests/integration/test_issue38_daemon_verification.py -v`

Expected: 5 mock tests pass, 1 real-call test skipped.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify-issue38.sh scripts/verify-issue38.bat
git commit -m "feat(scripts): add issue #38 verification wrapper scripts"
```

---

## Task 6: Final verification and cleanup

**Files:**
- None (verification only)

- [ ] **Step 1: Run full mock test suite**

Run: `pytest tests/integration/test_issue38_daemon_verification.py -v`

Expected:
- `test_pjob_run_mock_agent` PASS
- `test_daemon_start_and_state` PASS
- `test_daemon_logs_written` PASS
- `test_daemon_history_jsonl` PASS
- `test_daemon_stop_graceful` PASS
- `test_real_pjob_run` SKIPPED

- [ ] **Step 2: Verify checklist against a known clean state**

Run: `python scripts/verify_issue38_checklist.py`

Expected: All FAIL (no daemon has run in real `~/.zima` during tests since tests use tmp_path isolation).

- [ ] **Step 3: Run all existing integration tests to ensure no regressions**

Run: `pytest tests/integration/ -v --tb=short`

Expected: All existing tests still pass.

- [ ] **Step 4: Update issue #38 on GitHub**

After code is merged, update issue #38 body to reference the automated verification:

```bash
gh issue edit 38 --body "$(cat <<'EOF'
## Sub 0: zima CLI 验证 (已完成自动化)

验证 zima CLI 核心功能（daemon 模式、PJob 执行、32 周期调度）的自动化测试套件已实现。

### 快速验证（Mock 层，CI 自动运行）
```bash
pytest tests/integration/test_issue38_daemon_verification.py -v
```

### 真实调用验证（可选，手动触发）
```bash
pytest tests/integration/test_issue38_daemon_verification.py --real-agent -v
# 或
./scripts/verify-issue38.sh --real-agent
```

### 文件系统检查
```bash
python scripts/verify_issue38_checklist.py
```

### 设计文档
- Spec: `docs/superpowers/specs/2026-04-20-issue-38-automated-verification-design.md`
- Plan: `docs/superpowers/plans/2026-04-20-issue-38-automated-verification.md`
EOF
)"
```

- [ ] **Step 5: Final commit**

```bash
git commit --allow-empty -m "test(issue38): complete automated verification suite for #38"
```

---

## Self-Review

### Spec Coverage Check

| Spec Section | Plan Task | Status |
|-------------|-----------|--------|
| `mockCommand` production change | Task 1, Step 1 | ✅ Covered |
| `real_agent` pytest marker | Task 1, Step 3 | ✅ Covered |
| Mock Agent fixture (full kimi flags) | Task 2 | ✅ Covered |
| Mock Test Layer (5 tests, polling) | Task 3, Steps 1-7 | ✅ Covered |
| Real Call Layer | Task 3, Step 8 | ✅ Covered |
| Fast Schedule (1-min cycle, dataclass API) | Task 3, Step 2 helper | ✅ Covered |
| Checklist script (wmic/pgrep) | Task 4 | ✅ Covered |
| Wrapper scripts | Task 5 | ✅ Covered |
| Manual verification steps | Task 3, Step 8 + Task 6, Step 4 | ✅ Covered |

### Placeholder Scan

- [x] No "TBD", "TODO", "implement later"
- [x] No vague "add error handling" without code
- [x] All test code is complete and copy-pasteable
- [x] All file paths are exact

### Type Consistency

- [x] `ScheduleStage` and `ScheduleCycleType` imported as top-level classes from `zima.models.schedule`
- [x] `AgentConfig.create` signature matches existing code (`code`, `name`, `agent_type`)
- [x] `TestIsolator` used consistently — no duplicate `monkeypatch.setenv("ZIMA_HOME")`
- [x] `mockCommand` parameter used instead of overriding `spec.parameters.command`
- [x] `_wait_for_file()` polling used instead of `time.sleep()`
- [x] `_process_alive()` uses `OpenProcess(SYNCHRONIZE)` with correct alive/exited logic
- [x] Mock agent accepts hyphenated flags matching `_build_kimi_command()` output