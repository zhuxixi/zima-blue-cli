# Issue #38 Automated Verification Design

> **Goal:** Replace manual verification steps in issue #38 with an automated, repeatable test suite that validates zima CLI core functionality (daemon mode, PJob execution, 32-cycle scheduling) before borobo development begins.

**Target Issue:** [#38](https://github.com/zhuxixi/zima-blue-cli/issues/38) — Sub 0: zima CLI 手工验证 (borobo 前置条件)

> ⚠️ **Outdated Reference (Issue #43)**: This document references `~/.zima/agents/<code>/logs/` as the log location. The actual implementation uses the system temp directory (`zima-pjobs/`) and stores history centrally in `~/.zima/history/pjobs.json`. See [AGENTS.md](../../../../AGENTS.md) for the accurate data layout.

---

## 1. Background

Issue #38 requires verifying that zima CLI's core execution engine is stable before borobo (the GitHub App bot) can rely on it. The original acceptance criteria are manual steps:

1. `zima pjob run <pjob>` works in single-execution mode
2. `zima daemon start` launches 32-cycle scheduling and PJobs execute per cycle
3. Execution logs are written to `~/.zima/agents/<code>/logs/`
4. Daemon state file (`state.json`) updates correctly
5. Execution history (JSONL) is recorded correctly
6. `zima daemon stop` stops gracefully with no orphaned subprocesses

This design replaces those manual steps with a **two-layer automated verification suite**:
- **Mock Test Layer** (default, CI-friendly): Fast tests using a mock Agent CLI
- **Real Call Layer** (manual opt-in): Tests against the real Kimi/Claude CLI

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Automated Verification Suite                    │
│                   (issue #38 automation)                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────────┐    │
│  │   Mock Test Layer   │    │  Real Call Test Layer   │    │
│  │   (pytest, CI)      │    │  (manual / nightly)     │    │
│  │                     │    │                         │    │
│  │  • Verify scheduling│    │  • Verify real Kimi CLI │    │
│  │  • Verify log writes│    │  • Verify full chain    │    │
│  │  • Verify state file│    │  • Verify long-running  │    │
│  │  • Verify history   │    │    stability            │    │
│  │  • Verify graceful  │    │                         │    │
│  │    stop             │    │  Trigger:               │    │
│  │                     │    │  pytest --real-agent    │    │
│  │  Run: pytest        │    │  or ./scripts/verify.sh │    │
│  │  Time: ~30s         │    │  Time: ~5-10min         │    │
│  └─────────────────────┘    └─────────────────────────┘    │
│                                                             │
│  Mock Agent: A shim script that simulates Kimi CLI          │
│  Real Agent: A lightweight PJob (e.g., read README)         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Mock Test Layer (Default / CI)

### 3.1 New Test File

`tests/integration/test_issue38_daemon_verification.py`

Uses `TestIsolator` base class to redirect `~/.zima` to a temporary directory.

### 3.2 Test Cases

All test classes inherit from `TestIsolator` (see `tests/base.py`). The autouse `setup_isolation` fixture handles ZIMA_HOME redirection and config directory creation. **Do not** manually set `monkeypatch.setenv("ZIMA_HOME", ...)` in individual tests — `TestIsolator` already does this.

**Note:** `TestIsolator.setup_isolation` currently creates dirs for `agents`, `workflows`, `variables`, `envs`, `pmgs` but NOT `pjobs` or `schedules`. Tests that need those must create them in the test setup (or this can be added to `TestIsolator`).

**Daemon subprocess timing:** Tests that wait for daemon output must use **polling with timeout** instead of fixed `time.sleep()`. Pattern:

```python
import time

def _wait_for_file(path: Path, timeout: float = 15.0, interval: float = 0.5) -> bool:
    """Poll until file exists or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(interval)
    return False
```

**Windows process alive check:** To verify a daemon process has exited, use:

```python
import ctypes

def _process_alive(pid: int) -> bool:
    """Check if a process is still running. Returns False if exited."""
    if sys.platform != "win32":
        import os
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
```

| Test Case | Acceptance Criteria | Description |
|-----------|-------------------|-------------|
| `test_pjob_run_mock_agent` | #1 Single execution | Execute PJob with mock agent, assert success status and log file creation |
| `test_daemon_start_and_state` | #2 Scheduling + #4 state.json | Start daemon with 1-minute test schedule, assert PID file and state.json are created with correct cycle/stage |
| `test_daemon_logs_written` | #3 Log writes | After daemon runs, poll for `daemon.log` and assert it contains cycle entry markers |
| `test_daemon_history_jsonl` | #5 Execution history | Start daemon with a work-stage PJob, poll for `history/<date>.jsonl` and assert it contains execution records |
| `test_daemon_stop_graceful` | #6 Graceful stop | Start then stop daemon, assert PID file removed and process has exited |

### 3.3 Mock Agent Injection (`tests/fixtures/mock_agent.py`)

#### Production Code Change: `mockCommand` parameter support

Add a `mockCommand` check to `AgentConfig.get_cli_command_template()` in `zima/models/agent.py`:

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

This is a 3-line addition that:
- Only activates when `mockCommand` is present in agent parameters
- Returns the mock script path as the base command, then `build_command()` appends type-specific flags normally
- Does not affect any production agent (no real agent config has `mockCommand`)

Tests set `mockCommand` when creating the test agent via `ConfigManager`:
```python
agent_data["spec"]["parameters"]["mockCommand"] = str(mock_script_path)
```

#### Mock Agent Script

`tests/fixtures/mock_agent.py` — a Python script that mimics the Kimi CLI interface:

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
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default="mock")
    parser.add_argument("--max-steps-per-turn", type=int, default=10)
    parser.add_argument("--max-ralph-iterations", type=int, default=3)
    parser.add_argument("--max-retries-per-step", type=int, default=1)
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--work-dir", default=".")
    parser.add_argument("--output-format", default="text")
    args = parser.parse_args()

    # Validate prompt file exists
    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"Error: Prompt file not found: {args.prompt}", file=sys.stderr)
        return 1

    # Read and echo a snippet (proves file was read)
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

Note: The mock script accepts all flags that `_build_kimi_command()` generates (`--model`, `--max-steps-per-turn`, `--max-ralph-iterations`, `--max-retries-per-step`, `--yolo`, `--output-format`), so the command built by `build_command()` will parse cleanly.

### 3.4 Fast Schedule Configuration

Tests use a 1-minute cycle schedule (instead of the default 45-minute) so the full cycle completes quickly. Created via Python code using the dataclass API:

```python
from zima.models.schedule import ScheduleConfig, ScheduleStage, ScheduleCycleType

schedule = ScheduleConfig.create(code="verify-sched", name="Verify Schedule")
schedule.cycle_minutes = 1
schedule.daily_cycles = 32
schedule.stages = [
    ScheduleStage(name="work", offset_minutes=0, duration_minutes=1),
]
schedule.cycle_types = [
    ScheduleCycleType(type_id="verify", work=[pjob_code])
]
schedule.cycle_mapping = ["idle", "verify"] + ["idle"] * 30
```

**Key note:** `ScheduleStage` and `ScheduleCycleType` are top-level classes in `zima.models.schedule`, not inner classes of `ScheduleConfig`. Use direct imports.

Daemon is started, allowed to enter cycle 1 (work stage), then stopped. Total test time per case: ~5-10 seconds.

---

## 4. Real Call Layer (Manual / Optional)

### 4.1 When to Use

Run before merging borobo-related changes, or when suspecting daemon/PJob integration issues that mock tests cannot catch.

### 4.2 How to Trigger

```bash
# Option A: pytest with custom marker
pytest tests/integration/test_issue38_daemon_verification.py --real-agent -v

# Option B: convenience script
./scripts/verify-issue38.sh --real-agent
```

When `--real-agent` is not passed, real-call tests are skipped with a clear message.

### 4.3 Manual Verification Steps

If you prefer to run the verification manually (or need to debug), follow these steps:

**Step 1 — Create a lightweight verification Agent:**

```bash
zima agent create \
  --name "Verify Agent" \
  --code verify-agent \
  --type kimi \
  --param model=kimi-code/kimi-for-coding \
  --param maxStepsPerTurn=10 \
  --param workDir="$(pwd)"
```

**Step 2 — Create a simple Workflow:**

```bash
zima workflow create \
  --name "Verify WF" \
  --code verify-wf \
  --template "Read README.md and tell me the project name in one sentence."
```

**Step 3 — Create a PJob:**

```bash
zima pjob create \
  --name "Verify PJob" \
  --code verify-pjob \
  --agent verify-agent \
  --workflow verify-wf
```

**Step 4 — Test single execution (AC #1):**

```bash
zima pjob run verify-pjob
```

Expected: success status, log written to `~/.zima/agents/verify-agent/logs/`.

**Step 5 — Create a fast Schedule (AC #2–#5):**

```bash
zima schedule create \
  --name "Verify Schedule" \
  --code verify-sched \
  --cycle-minutes 1 \
  --daily-cycles 32

# Add cycle type and mapping via update
zima schedule update verify-sched \
  --add-cycle-type verify --work verify-pjob

zima schedule update verify-sched \
  --set-mapping "1:verify"
```

**Step 6 — Start daemon and observe:**

```bash
zima daemon start --schedule verify-sched

# In another terminal, check status
zima daemon status
zima daemon logs --tail 20
```

Observe: `state.json` updates, logs accumulate, `history/*.jsonl` records appear.

**Step 7 — Stop gracefully (AC #6):**

```bash
zima daemon stop
```

Verify: PID file deleted, no residual `python.exe -m zima.daemon_runner` processes.

### 4.4 Automated Checklist Script

`scripts/verify_issue38_checklist.py` inspects the filesystem and prints a pass/fail checklist:

```bash
$ python scripts/verify_issue38_checklist.py

Issue #38 Verification Checklist
==================================
[PASS] PJob execution log exists
       ~/.zima/agents/verify-agent/logs/20260420_001500_1.log
[PASS] Daemon state file exists and is valid JSON
       ~/.zima/daemon/state.json
[PASS] Execution history JSONL exists
       ~/.zima/daemon/history/2026-04-20.jsonl
[PASS] PID file cleaned up after stop
[PASS] No orphaned daemon processes

Result: 5/5 passed
```

**Windows process detection:** On Windows, use `wmic process where "commandline like '%daemon_runner%'" get processid` or PowerShell `Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*daemon_runner*' }` to detect orphaned daemon processes. Do NOT use `tasklist` — it does not include command-line arguments, so it cannot distinguish daemon processes from other Python processes.

---

## 5. Integration with Existing Tests

| Existing File | Relationship |
|--------------|-------------|
| `tests/integration/test_daemon_commands.py` | Covers basic daemon CLI (start without schedule, stop not running). The new file covers *functional* daemon behavior (scheduling, state, history). |
| `tests/integration/test_pjob_lifecycle.py` | Covers PJob CRUD and dry-run. The new file covers *actual execution* (with mock agent). |
| `tests/base.py` (`TestIsolator`) | Reused for `ZIMA_HOME` isolation. |

### pytest Markers

```python
# Mock tests — run in all CI tiers
pytest tests/integration/test_issue38_daemon_verification.py

# Real-agent tests — skipped unless --real-agent
pytest tests/integration/test_issue38_daemon_verification.py --real-agent
```

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "real_agent: tests that call the real Kimi/Claude CLI (slow, manual)",
]
```

---

## 6. Acceptance Criteria Mapping

| Issue #38 AC | Mock Test Coverage | Real Call Coverage |
|-------------|-------------------|-------------------|
| #1 `zima pjob run` works | `test_pjob_run_mock_agent` | Step 4 (manual) |
| #2 Daemon starts 32-cycle scheduling | `test_daemon_start_and_state` | Step 6 (manual) |
| #3 Logs written to `~/.zima/agents/<code>/logs/` | `test_pjob_run_mock_agent` | Step 4 (manual) |
| #4 `state.json` updates correctly | `test_daemon_start_and_state` | Step 6 (manual) |
| #5 History JSONL recorded | `test_daemon_history_jsonl` | Step 6 (manual) |
| #6 `zima daemon stop` graceful | `test_daemon_stop_graceful` | Step 7 (manual) |

---

## 7. Implementation Scope

### New Files

| Path | Description |
|------|-------------|
| `tests/integration/test_issue38_daemon_verification.py` | Main test suite (mock + real call tests) |
| `tests/fixtures/mock_agent.py` | Mock Kimi CLI shim |
| `scripts/verify_issue38_checklist.py` | Filesystem verification checklist script |
| `scripts/verify-issue38.sh` | Convenience wrapper script |

### Modified Files

| Path | Change |
|------|--------|
| `zima/models/agent.py` | Add `mockCommand` check to `get_cli_command_template()` (3 lines) |
| `pyproject.toml` | Add `real_agent` pytest marker |

---

## 8. Self-Review Checklist

- [x] No placeholders or TODOs
- [x] Mock and real layers are clearly separated
- [x] Manual verification steps are explicit and copy-pasteable
- [x] All 6 acceptance criteria from issue #38 are covered
- [x] Scope is focused (one test file + fixtures + scripts + 3-line production change)
- [x] Compatible with existing `TestIsolator` and CI tiering
- [x] Mock agent injection uses `mockCommand` parameter (option B) — minimal production code change
- [x] `ScheduleStage`/`ScheduleCycleType` imported as top-level classes from `zima.models.schedule`
- [x] Daemon tests use polling with timeout instead of fixed `time.sleep()`
- [x] Windows process detection uses `OpenProcess(SYNCHRONIZE)` with correct alive/exited logic
- [x] Checklist script uses `wmic` or PowerShell (not `tasklist`) for command-line-based process detection
- [x] Mock agent script accepts all flags that `_build_kimi_command()` generates

---

*Design approved for implementation.*
