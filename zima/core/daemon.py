"""Daemon mode for running agents in background"""

from __future__ import annotations

import sys
from pathlib import Path


def start_daemon(agent_dir: Path) -> int:
    """
    Start an agent as a background process (daemon)

    Returns:
        Process ID of the daemon
    """
    # Create log file for daemon output
    log_file = agent_dir / "daemon.log"

    # Start the agent in background using subprocess
    # We use sys.executable to ensure we use the same Python
    cmd = [sys.executable, "-m", "zima.daemon_runner", str(agent_dir)]

    # Start process detached (Windows)
    if sys.platform == "win32":
        import subprocess

        # Create process with CREATE_NEW_PROCESS_GROUP to allow it to run independently
        process = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
    else:
        # Unix-like systems
        process = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    # Save PID to file
    pid_file = agent_dir / "daemon.pid"
    pid_file.write_text(str(process.pid))

    return process.pid


def stop_daemon(agent_dir: Path) -> bool:
    """Stop a running daemon"""
    pid_file = agent_dir / "daemon.pid"

    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())

        if sys.platform == "win32":
            import subprocess

            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
        else:
            import os
            import signal

            os.kill(pid, signal.SIGTERM)

        pid_file.unlink()
        return True
    except (ValueError, OSError, ProcessLookupError):
        pid_file.unlink(missing_ok=True)
        return False


def is_daemon_running(agent_dir: Path) -> bool:
    """Check if daemon is running"""
    pid_file = agent_dir / "daemon.pid"

    if not pid_file.exists():
        return False

    try:
        pid = int(pid_file.read_text().strip())

        # Check if process exists
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            import os

            os.kill(pid, 0)
            return True
    except (ValueError, OSError, ProcessLookupError):
        pid_file.unlink(missing_ok=True)
        return False
