# Design: Daemon Error Handling Fixes

**Date:** 2026-04-20
**Issue:** #30
**Status:** Approved

## Problem

`zima/commands/daemon.py` has 6 pre-existing error handling issues identified during PR #28 code review:

1. Unix `stop()` sends SIGTERM then immediately deletes PID file — no wait for process exit (Windows has 5s wait, Unix has none)
2. `status()` discovers dead process but doesn't clean up PID file — `start()` enters stale PID check branch
3. `status()` has no `json.JSONDecodeError` handling for `state.json` — corrupted JSON crashes the command
4. Windows `OpenProcess(1)` uses PROCESS_TERMINATE for alive checks — may fail with access denied for elevated processes
5. `status()` only catches `ValueError` on PID read — `OSError` from permission errors crashes
6. `logs()` has no error handling on `read_text()` — `OSError` or `UnicodeDecodeError` crashes

## Design

### Approach: Targeted fixes + shared helper

Single-file change to `zima/commands/daemon.py`. Extract a shared `_is_process_alive()` helper to fix the Windows permission issue in one place and reduce duplication across `start()`, `stop()`, `status()`.

### Changes

#### 1. New helper: `_is_process_alive(pid) -> bool`

Module-level private function. Replaces 3 inline Windows ctypes blocks.

- Windows: `OpenProcess(0x1000, False, pid)` (PROCESS_QUERY_LIMITED_INFORMATION)
- Unix: `os.kill(pid, 0)` with `OSError` catch
- Returns `True`/`False`, no side effects, no PID file cleanup

#### 2. `stop()` — Unix wait+retry (issue #1)

After `os.kill(pid, SIGTERM)`: sleep 2s, check `_is_process_alive(pid)`, if still alive send `SIGKILL`. Mirrors Windows pattern (graceful → wait → force).

#### 3. `status()` — PID file cleanup (issue #2)

When `_is_process_alive(pid)` returns `False`, call `pid_file.unlink(missing_ok=True)` before printing "not alive" message.

#### 4. `status()` — state.json error handling (issue #3)

Wrap `json.loads(state_file.read_text(...))` in `try/except json.JSONDecodeError`. Print "[yellow]Corrupted state file[/yellow]" warning and skip state display.

#### 5. `status()` — PID read OSError (issue #5)

Change `except ValueError` to `except (ValueError, OSError)` on PID file `read_text()`. Print "[red]Cannot read PID file[/red]" error message.

#### 6. `logs()` — file read errors (issue #6)

Wrap `log_file.read_text(...)` in `try/except (OSError, UnicodeDecodeError)`. Print "[red]Cannot read log file: <path>[/red]" error and exit.

### Tests

- Unit tests for `_is_process_alive()` (mock ctypes on Windows, mock os.kill on Unix)
- Integration tests: corrupted PID file, corrupted state.json, unreadable log file, Unix stop wait behavior

## Scope

- Single file: `zima/commands/daemon.py`
- Test file: `tests/integration/test_daemon_commands.py` (extend existing)
- New test file: `tests/unit/test_daemon_helpers.py` (for `_is_process_alive`)
