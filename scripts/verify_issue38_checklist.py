#!/usr/bin/env python3
"""Issue #38 verification checklist — inspects ~/.zima filesystem state."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from zima.utils import get_zima_home


def check_pass(name: str, detail: str = "") -> dict:
    return {"status": "PASS", "name": name, "detail": detail}


def check_fail(name: str, detail: str = "") -> dict:
    return {"status": "FAIL", "name": name, "detail": detail}


def check_file_exists(path: Path, name: str) -> dict:
    if path.exists():
        return check_pass(name, str(path))
    return check_fail(name, f"Not found: {path}")


def main() -> int:
    zima_home = get_zima_home()
    checks = []

    # AC #1 + #3: PJob execution history
    history_file = zima_home / "history" / "pjobs.json"
    if history_file.exists():
        try:
            history_data = json.loads(history_file.read_text(encoding="utf-8"))
            if history_data:
                checks.append(check_pass("PJob execution history exists", str(history_file)))
            else:
                checks.append(check_fail("PJob execution history exists", "File is empty"))
        except json.JSONDecodeError as e:
            checks.append(check_fail("PJob execution history exists", f"Invalid JSON: {e}"))
    else:
        checks.append(check_fail("PJob execution history exists", f"Not found: {history_file}"))

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
        checks.append(check_fail("Execution history JSONL exists", "No .jsonl files in daemon/history/"))

    # AC #6: PID file cleaned up
    pid_file = zima_home / "daemon" / "daemon.pid"
    if pid_file.exists():
        checks.append(check_fail("PID file cleaned up after stop", f"Still exists: {pid_file}"))
    else:
        checks.append(check_pass("PID file cleaned up after stop"))

    # AC #6: No orphaned processes
    if sys.platform == "win32":
        # Use wmic to find daemon_runner processes by command line
        # tasklist does NOT include command-line arguments, so it's useless here
        try:
            result = subprocess.run(
                [
                    "wmic", "process", "where",
                    "commandline like '%daemon_runner%'",
                    "get", "processid",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # wmic returns header line + empty lines + PIDs if found
            lines = [
                l.strip() for l in result.stdout.strip().split("\n")
                if l.strip() and l.strip() != "ProcessId"
            ]
            if len(lines) == 0:
                checks.append(check_pass("No orphaned daemon processes"))
            else:
                checks.append(check_fail("No orphaned daemon processes", f"Found PIDs: {', '.join(lines)}"))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            checks.append(check_pass("No orphaned daemon processes", "wmic not available or timed out"))
    else:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "daemon_runner"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:  # pgrep returns 1 if no match
                checks.append(check_pass("No orphaned daemon processes"))
            else:
                pids = result.stdout.strip()
                checks.append(check_fail("No orphaned daemon processes", f"Found PIDs: {pids}"))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            checks.append(check_pass("No orphaned daemon processes", "pgrep not available or timed out"))

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
