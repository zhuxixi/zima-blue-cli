#!/usr/bin/env python3
"""Block until every running Zima PJob execution reaches a terminal state.

Watches the runtime state files that zima's background runner maintains at
``$ZIMA_HOME/history/pjobs/<pjob_code>/<execution_id>.json``.  The terminal
state is written only after postExec actions finish (i.e. after the review
has been posted), so "no running executions left" means "this CR round is
done".  The watcher is strictly read-only: it never writes state files, so
multiple sessions can watch the same executions without interfering.

Exit codes:
    0  all active executions reached a terminal state
    1  timeout while executions were still running
    2  no execution appeared within the grace period (trigger likely failed)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, TextIO

TERMINAL_STATUSES = {"success", "failed", "skipped", "timeout", "cancelled", "dead"}
DEFAULT_TIMEOUT = 2100  # PJob execution.timeout (1800s) + 300s slack
DEFAULT_POLL = 30
DEFAULT_GRACE = 120
DEFAULT_SINCE_MINUTES = 10


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into a tz-aware datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def pid_alive(pid: int | None) -> bool:
    """Return True when a process with this pid exists.

    Mirrors ``zima.execution.history._is_pid_alive`` so the watcher and the
    state-file writer agree on liveness: ``ctypes.GetExitCodeProcess`` on
    Windows, ``os.kill(pid, 0)`` on Unix.  ``PermissionError`` on Unix means
    the process exists but is not ours (alive); ``ProcessLookupError`` means
    it does not exist (dead); anything unexpected is dead.
    """
    if pid is None:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            try:
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        # Process exists but caller lacks permission to signal it.
        return True
    except ProcessLookupError:
        return False
    except (ValueError, Exception):
        return False


def load_states(state_dir: Path) -> dict[str, dict]:
    """Read every state file into {execution_id: state_dict}.

    Files that fail to parse are skipped: zima writes state files
    non-atomically, so a torn read just means "being written right now" —
    the next poll tick will see the completed file.
    """
    states: dict[str, dict] = {}
    if not state_dir.is_dir():
        return states
    for path in sorted(state_dir.iterdir()):
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
            continue
        if isinstance(data, dict):
            states[path.stem] = data
    return states


def tail_log(log_path: str | None, chars: int = 600) -> str:
    """Return the last ``chars`` characters of the log file, or ''.

    The full agent stdout ends with the ``<zima-review>`` verdict; zima
    keeps the whole output in the background log, so the log tail is the
    closest read-only proxy for the verdict. Read-only and bounded (reads
    at most the last 8192 bytes).
    """
    if not log_path:
        return ""
    path = Path(log_path)
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            data = fh.read()
        return data.decode("utf-8", errors="replace")[-chars:].strip()
    except OSError:
        return ""


def is_stale(state: dict) -> bool:
    """True when a 'running' entry's pid is provably dead.

    Such an entry will never receive a terminal state (the process was
    killed hard); zima's own CLI marks these 'dead' on read.  pid=None
    means the spawn is still racing and must NOT be treated as stale.
    """
    return (
        state.get("status") == "running"
        and state.get("pid") is not None
        and not pid_alive(state.get("pid"))
    )


def is_active(state: dict, cutoff: datetime | None) -> bool:
    """True when the execution belongs to the round being waited on.

    Running executions are always active.  Finished ones count only when
    they started after the cutoff (recent enough to be this round's work);
    older terminal files are history and are ignored.
    """
    status = state.get("status")
    if status == "running":
        return True
    if status in TERMINAL_STATUSES and cutoff is not None:
        started = parse_iso(state.get("started_at"))
        return started is not None and started >= cutoff
    return False


def format_summary(eid: str, state: dict) -> str:
    """One human-readable summary line per execution."""
    status = state.get("status", "?")
    duration = state.get("duration_seconds")
    dur = f"{duration:.0f}s" if isinstance(duration, (int, float)) else "-"
    parts = [f"eid={eid}", f"status={status}", f"duration={dur}"]
    if state.get("returncode") is not None:
        parts.append(f"returncode={state['returncode']}")
    if state.get("_stale"):
        parts.append("STALE(pid dead, terminal state never written)")
    spr = state.get("scan_pr_result") or {}
    if spr.get("repo"):
        parts.append(f"repo={spr['repo']}#{spr.get('pr_number')}")
    preview = str(state.get("stdout_preview") or "").strip()
    if preview:
        parts.append(f"preview={preview[:240]}")
    tail = tail_log(state.get("log_path"))
    if tail:
        parts.append(f"log_tail={tail}")
    return "  " + " ".join(parts)


def run_loop(
    state_dir: Path,
    cutoff: datetime | None,
    timeout: int = DEFAULT_TIMEOUT,
    poll: int = DEFAULT_POLL,
    grace: int = DEFAULT_GRACE,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    out: TextIO | None = None,
) -> int:
    """Poll state files until no active execution is running.

    Returns:
        0 when every active execution reached a terminal state,
        1 on timeout, 2 when no execution appeared within the grace period.
    """
    if out is None:
        out = sys.stdout
    deadline = monotonic() + timeout
    no_exec_deadline = monotonic() + grace
    elapsed = 0

    while True:
        states = load_states(state_dir)
        active = {eid: s for eid, s in states.items() if is_active(s, cutoff)}
        for state in active.values():
            if is_stale(state):
                state["_stale"] = True
        running = [
            s for s in active.values() if s.get("status") == "running" and not s.get("_stale")
        ]

        if not running:
            if not active:
                if monotonic() >= deadline:
                    print(
                        f"wait-cr: timeout after {timeout}s; no execution appeared:",
                        file=sys.stderr,
                    )
                    return 1
                if monotonic() < no_exec_deadline:
                    sleep(poll)
                    elapsed += poll
                    continue
                print(
                    "wait-cr: no active execution since cutoff; if a round was "
                    "just triggered, check `zima pjob status <code>`",
                    file=sys.stderr,
                )
                return 2
            for eid, state in sorted(active.items()):
                print(format_summary(eid, state), file=out)
            return 0

        if monotonic() >= deadline:
            print(f"wait-cr: timeout after {timeout}s; still running:", file=sys.stderr)
            for eid, state in sorted(active.items()):
                print(format_summary(eid, state), file=sys.stderr)
            return 1

        print(f"[{elapsed:>5}s] {len(running)} running", file=out, flush=True)
        sleep(poll)
        elapsed += poll


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Wait for Zima PJob executions to reach a terminal state."
    )
    parser.add_argument("pjob_code", help="PJob code to wait for")
    parser.add_argument(
        "--since-minutes",
        type=int,
        default=DEFAULT_SINCE_MINUTES,
        help="count finished executions started within the last N minutes as part of this round",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--poll", type=int, default=DEFAULT_POLL)
    parser.add_argument("--grace", type=int, default=DEFAULT_GRACE)
    parser.add_argument(
        "--zima-home",
        type=Path,
        default=None,
        help="override ZIMA_HOME (default: $ZIMA_HOME or ~/.zima)",
    )
    args = parser.parse_args(argv)

    zima_home = args.zima_home or Path(os.environ.get("ZIMA_HOME") or Path.home() / ".zima")
    state_dir = zima_home / "history" / "pjobs" / args.pjob_code
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.since_minutes)
    return run_loop(
        state_dir=state_dir,
        cutoff=cutoff,
        timeout=args.timeout,
        poll=args.poll,
        grace=args.grace,
    )


if __name__ == "__main__":
    sys.exit(main())
