# Daemon Error Handling Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 pre-existing error handling issues in `zima/commands/daemon.py` — Unix stop wait logic, PID file cleanup, state.json corruption, Windows process check permissions, and file read error handling.

**Architecture:** Extract a shared `_is_process_alive(pid) -> bool` helper to fix the Windows `OpenProcess` permission issue (issue #4) in one place, then apply 5 targeted fixes to `stop()`, `status()`, and `logs()`.

**Tech Stack:** Python 3.10+, ctypes (Windows), os/signal (Unix), pytest + unittest.mock for testing

**Design spec:** `docs/superpowers/specs/2026-04-20-daemon-error-handling-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `zima/commands/daemon.py` | Add `_is_process_alive()`, fix 5 error handling issues |
| Create | `tests/unit/test_daemon_helpers.py` | Unit tests for `_is_process_alive()` |
| Modify | `tests/integration/test_daemon_commands.py` | Integration tests for error handling fixes |

---

### Task 1: Extract `_is_process_alive()` helper + fix Windows permission mask (issue #4)

**Files:**
- Modify: `zima/commands/daemon.py` — add helper at module level, replace 3 inline blocks
- Create: `tests/unit/test_daemon_helpers.py`

- [ ] **Step 1: Write unit tests for `_is_process_alive()`**

Create `tests/unit/test_daemon_helpers.py`:

```python
"""Unit tests for daemon command helpers."""

import sys
import pytest
from unittest.mock import patch, MagicMock

from zima.commands.daemon import _is_process_alive


class TestIsProcessAliveWindows:
    """Test _is_process_alive on Windows."""

    @patch("sys.platform", "win32")
    def test_alive_process(self):
        """Returns True when OpenProcess returns a valid handle."""
        with patch("zima.commands.daemon.ctypes") as mock_ctypes:
            mock_handle = MagicMock()
 mock_ctypes.windll.kernel32.OpenProcess.return_value = mock_handle
            assert _is_process_alive(1234) is True
            mock_ctypes.windll.kernel32.OpenProcess.assert_called_once_with(
                0x1000, False, 1234
            )
            mock_ctypes.windll.kernel32.CloseHandle.assert_called_once_with(mock_handle)

    @patch("sys.platform", "win32")
    def test_dead_process(self):
        """Returns False when OpenProcess returns None/0."""
        with patch("zima.commands.daemon.ctypes") as mock_ctypes:
            mock_ctypes.windll.kernel32.OpenProcess.return_value = None
            assert _is_process_alive(1234) is False
            mock_ctypes.windll.kernel32.CloseHandle.assert_not_called()

    @patch("sys.platform", "win32")
    def test_zero_handle(self):
        """Returns False when OpenProcess returns 0."""
        with patch("zima.commands.daemon.ctypes") as mock_ctypes:
            mock_ctypes.windll.kernel32.OpenProcess.return_value = 0
            assert _is_process_alive(1234) is False


class TestIsProcessAliveUnix:
    """Test _is_process_alive on Unix."""

    @patch("sys.platform", "linux")
    def test_alive_process(self):
        """Returns True when os.kill doesn't raise."""
        with patch("zima.commands.daemon.os.kill"):
            assert _is_process_alive(1234) is True

    @patch("sys.platform", "linux")
    def test_dead_process(self):
        """Returns False when os.kill raises OSError."""
        with patch("zima.commands.daemon.os.kill", side_effect=OSError):
            assert _is_process_alive(1234) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_daemon_helpers.py -v`
Expected: FAIL — `ImportError: cannot import name '_is_process_alive'`

- [ ] **Step 3: Implement `_is_process_alive()` and refactor callers**

Add the helper function at the top of `zima/commands/daemon.py` (after imports, before `app = typer.Typer(...)` at line 17). Then replace all 3 inline Windows process-check blocks in `start()`, `stop()`, `status()`.

**Add after line 16** (after `from zima.utils import get_zima_home`):

```python
def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive.

    Uses PROCESS_QUERY_LIMITED_INFORMATION on Windows (more reliable
    than PROCESS_TERMINATE for cross-privilege checks) and os.kill
    with signal 0 on Unix.
    """
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        import os

        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
```

**Replace lines 33-41** in `start()` (the first inline Windows check):

```python
# Before (lines 33-41):
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                console.print(f"[yellow]⚠[/yellow] Daemon already running (PID {pid})")
                raise typer.Exit(1)
            # Process not alive — clean up stale PID file
            pid_file.unlink(missing_ok=True)

# After:
            if _is_process_alive(pid):
                console.print(f"[yellow]⚠[/yellow] Daemon already running (PID {pid})")
                raise typer.Exit(1)
            # Process not alive — clean up stale PID file
            pid_file.unlink(missing_ok=True)
```

**Replace lines 132-139** in `stop()` (the second inline Windows check after force-kill):

```python
# Before (lines 132-139):
                import ctypes

                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)

# After:
                if _is_process_alive(pid):
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
```

**Replace lines 170-179** in `status()` (the alive check block):

```python
# Before (lines 170-179):
    alive = False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(1, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            alive = True
    else:
        import os

        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            pass

# After:
    alive = _is_process_alive(pid)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_daemon_helpers.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run existing daemon command tests to ensure no regressions**

Run: `pytest tests/integration/test_daemon_commands.py -v`
Expected: All 4 existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add zima/commands/daemon.py tests/unit/test_daemon_helpers.py
git commit -m "refactor(daemon): extract _is_process_alive() helper with correct Windows permission

Replace OpenProcess(1) (PROCESS_TERMINATE) with OpenProcess(0x1000)
(PROCESS_QUERY_LIMITED_INFORMATION) for reliable cross-privilege
process checks. Consolidate 3 inline Windows ctypes blocks into one
reusable helper.

Fixes issue #4 of #30."
```

---

### Task 2: Fix Unix `stop()` wait+retry logic (issue #1)

**Files:**
- Modify: `zima/commands/daemon.py:124-146` — the `stop()` function's Unix branch

- [ ] **Step 1: Write integration test for Unix stop wait behavior**

Add to `tests/integration/test_daemon_commands.py`:

```python
class TestDaemonStopCleanup(TestIsolator):
    """Test zima daemon stop PID cleanup behavior."""

    def test_stop_removes_stale_pid_file(self):
        """Daemon stop should remove PID file even for nonexistent process."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        # Write a PID that doesn't exist
        pid_file.write_text("99999999", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        assert not pid_file.exists()
```

- [ ] **Step 2: Run test to see current behavior**

Run: `pytest tests/integration/test_daemon_commands.py::TestDaemonStopCleanup -v`
Expected: May fail or pass depending on platform — on Unix, PID file deletion currently happens unconditionally after SIGTERM, so it passes but the process may not actually be dead yet.

- [ ] **Step 3: Add wait+retry logic to Unix branch of `stop()`**

Replace the `else:` branch (Unix path) in `stop()`, currently at lines 142-146:

```python
# Before (Unix branch in stop):
        else:
            import os
            import signal

            os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        console.print(f"[green]✓[/green] Daemon stopped (PID {pid})")

# After:
        else:
            import os
            import signal

            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            if _is_process_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        pid_file.unlink(missing_ok=True)
        console.print(f"[green]✓[/green] Daemon stopped (PID {pid})")
```

Note: `time` is already imported at the top of the file (line 9).

- [ ] **Step 4: Run all daemon tests**

Run: `pytest tests/unit/test_daemon_helpers.py tests/integration/test_daemon_commands.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/daemon.py tests/integration/test_daemon_commands.py
git commit -m "fix(daemon): add Unix stop() wait+retry with SIGKILL fallback

Unix stop() now waits 2s after SIGTERM and falls back to SIGKILL
if the process is still alive, mirroring the Windows graceful-then-
force pattern. Previously it deleted the PID file immediately after
SIGTERM without confirming process exit.

Fixes issue #1 of #30."
```

---

### Task 3: Fix `status()` — PID cleanup, state.json, and OSError handling (issues #2, #3, #5)

**Files:**
- Modify: `zima/commands/daemon.py:162-199` — the `status()` function

- [ ] **Step 1: Write integration tests for status error handling**

Add to `tests/integration/test_daemon_commands.py`:

```python
class TestDaemonStatusErrors(TestIsolator):
    """Test zima daemon status error handling."""

    def test_status_cleans_up_dead_pid_file(self):
        """Status should remove PID file when process is dead."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        # Write a PID that doesn't exist
        pid_file.write_text("99999999", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert not pid_file.exists()

    def test_status_corrupted_state_json(self):
        """Status should handle corrupted state.json gracefully."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        pid_file.write_text("99999999", encoding="utf-8")
        state_file = daemon_dir / "state.json"
        state_file.write_text("not valid json {{{", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0

    def test_status_unreadable_pid_file(self):
        """Status should handle unreadable PID file gracefully."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        pid_file = daemon_dir / "daemon.pid"
        # Write valid content but we'll test the error path
        # This test verifies (ValueError, OSError) is caught
        pid_file.write_text("not_a_number", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code != 0
        assert "Invalid" in result.output or "Cannot read" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_daemon_commands.py::TestDaemonStatusErrors -v`
Expected: `test_status_cleans_up_dead_pid_file` FAILS (PID file not cleaned up), `test_status_corrupted_state_json` FAILS (json.JSONDecodeError not caught), `test_status_unreadable_pid_file` should already pass (ValueError is caught).

- [ ] **Step 3: Apply all 3 fixes to `status()`**

**Fix issue #5** — expand `except ValueError` to `except (ValueError, OSError)` at line 166:

```python
# Before:
    except ValueError:
        console.print("[red]Invalid PID file[/red]")
        raise typer.Exit(1)

# After:
    except (ValueError, OSError):
        console.print("[red]Cannot read PID file[/red]")
        raise typer.Exit(1)
```

**Fix issue #2** — add PID file cleanup when process is dead, after the `_is_process_alive` check (the `if not alive:` block, currently at line 189):

```python
# Before:
    if not alive:
        console.print(f"[yellow]Daemon PID {pid} is not alive[/yellow]")
        raise typer.Exit(0)

# After:
    if not alive:
        pid_file.unlink(missing_ok=True)
        console.print(f"[yellow]Daemon PID {pid} is not alive[/yellow]")
        raise typer.Exit(0)
```

**Fix issue #3** — wrap `json.loads` in try/except at lines 196-199:

```python
# Before:
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        console.print(f"   Current cycle: {state.get('currentCycle', 'unknown')}")
        console.print(f"   Current stage: {state.get('currentStage', 'unknown')}")
        console.print(f"   Active PJobs: {state.get('activePjobs', [])}")

# After:
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            console.print(f"   Current cycle: {state.get('currentCycle', 'unknown')}")
            console.print(f"   Current stage: {state.get('currentStage', 'unknown')}")
            console.print(f"   Active PJobs: {state.get('activePjobs', [])}")
        except json.JSONDecodeError:
            console.print("[yellow]   Corrupted state file[/yellow]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_daemon_commands.py::TestDaemonStatusErrors -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `pytest tests/unit/test_daemon_helpers.py tests/integration/test_daemon_commands.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add zima/commands/daemon.py tests/integration/test_daemon_commands.py
git commit -m "fix(daemon): improve status() error handling

- Clean up PID file when process found dead (issue #2)
- Handle corrupted state.json with json.JSONDecodeError catch (issue #3)
- Expand PID read error handling to catch OSError (issue #5)

Fixes issues #2, #3, #5 of #30."
```

---

### Task 4: Fix `logs()` file read error handling (issue #6)

**Files:**
- Modify: `zima/commands/daemon.py:202-214` — the `logs()` function

- [ ] **Step 1: Write integration test for logs error handling**

Add to `tests/integration/test_daemon_commands.py`:

```python
class TestDaemonLogsErrors(TestIsolator):
    """Test zima daemon logs error handling."""

    def test_logs_unreadable_file(self):
        """Logs should handle unreadable log file gracefully."""
        daemon_dir = self.temp_dir / "daemon"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        log_file = daemon_dir / "daemon.log"
        # Write valid content — tests that the path exists and is read
        log_file.write_text("line1\nline2\nline3", encoding="utf-8")

        result = runner.invoke(app, ["daemon", "logs"])
        assert result.exit_code == 0
        assert "line1" in result.output
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `pytest tests/integration/test_daemon_commands.py::TestDaemonLogsErrors -v`
Expected: PASS — current code works for normal files. This establishes a baseline.

- [ ] **Step 3: Add error handling to `logs()`**

Replace lines 212-214 in `logs()`:

```python
# Before:
    lines = log_file.read_text(encoding="utf-8").splitlines()
    for line in lines[-tail:]:
        console.print(line)

# After:
    try:
        lines = log_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        console.print(f"[red]✗[/red] Cannot read log file: {e}")
        raise typer.Exit(1)
    for line in lines[-tail:]:
        console.print(line)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_daemon_commands.py::TestDaemonLogsErrors -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/daemon.py tests/integration/test_daemon_commands.py
git commit -m "fix(daemon): add logs() file read error handling

Catch OSError and UnicodeDecodeError when reading daemon log file
to prevent crashes on permission errors or encoding issues.

Fixes issue #6 of #30."
```

---

### Task 5: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest --cov=zima --cov-fail-under=60`
Expected: All tests pass, coverage >= 60%

- [ ] **Step 2: Run linting**

Run: `ruff check zima/ tests/ && black zima/ tests/ --check --line-length 100`
Expected: No errors

- [ ] **Step 3: Squash or rebase if desired (optional)**

If you prefer a single commit for the PR, interactive rebase the 4 commits. Otherwise keep them separate — they each address distinct issues.
