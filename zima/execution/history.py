"""Execution history management for PJob -- directory-based storage.

Each execution gets its own JSON file under::

    ~/.zima/history/pjobs/<pjob_code>/<execution_id>.json

The file is written at startup (status: ``running``) and updated on completion.
On read, stale ``running`` entries whose PID is no longer alive are auto-marked
``dead``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from zima.utils import get_zima_home

# =============================================================================
# PID liveness check (cross-platform)
# =============================================================================


def _is_pid_alive(pid: Optional[int]) -> bool:
    """Check whether a PID is still alive (cross-platform).

    Uses ``ctypes`` with ``GetExitCodeProcess`` on Windows and ``os.kill(pid, 0)``
    on Unix.  ``PermissionError`` on Unix means the process *is* alive — the
    caller simply lacks permission to signal it.
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
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        else:
            os.kill(pid, 0)
            return True
    except PermissionError:
        # Process exists but caller lacks permission to signal it.
        return True
    except ProcessLookupError:
        return False
    except (ValueError, Exception):
        return False


# =============================================================================
# ExecutionRecord (backward-compatible dataclass)
# =============================================================================


@dataclass
class ExecutionRecord:
    """Single execution record (backward-compatible dataclass).

    Attributes:
        execution_id: Unique execution ID.
        pjob_code: PJob code.
        status: Execution status (running/success/failed/timeout/cancelled/dead).
        returncode: Process return code.
        command: Executed command.
        started_at: Start timestamp (ISO 8601).
        finished_at: Finish timestamp (ISO 8601).
        duration_seconds: Execution duration.
        stdout_preview: First N chars of stdout.
        stderr_preview: First N chars of stderr.
        error_detail: Detailed error information.
        pid: Process PID.
    """

    execution_id: str
    pjob_code: str
    status: str
    returncode: int
    command: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float = 0.0
    stdout_preview: str = ""
    stderr_preview: str = ""
    error_detail: str = ""
    pid: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "pjob_code": self.pjob_code,
            "status": self.status,
            "returncode": self.returncode,
            "command": self.command,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
            "error_detail": self.error_detail,
            "pid": self.pid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutionRecord:
        """Create from dictionary."""
        return cls(
            execution_id=data.get("execution_id", ""),
            pjob_code=data.get("pjob_code", ""),
            status=data.get("status", ""),
            returncode=data.get("returncode", 0),
            command=data.get("command", []),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
            stdout_preview=data.get("stdout_preview", ""),
            stderr_preview=data.get("stderr_preview", ""),
            error_detail=data.get("error_detail", ""),
            pid=data.get("pid"),
        )

    @classmethod
    def from_result(cls, result) -> ExecutionRecord:
        """Create from ExecutionResult."""
        # Truncate previews
        stdout_preview = result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout
        stderr_preview = result.stderr[:500] + "..." if len(result.stderr) > 500 else result.stderr
        error_detail = result.error_detail
        if len(error_detail) > 2000:
            error_detail = error_detail[:2000] + "...\n[truncated]"

        return cls(
            execution_id=result.execution_id,
            pjob_code=result.pjob_code,
            status=result.status.value,
            returncode=result.returncode,
            command=result.command,
            started_at=result.started_at,
            finished_at=result.finished_at,
            duration_seconds=result.duration_seconds,
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview,
            error_detail=error_detail,
            pid=result.pid,
        )


# =============================================================================
# ExecutionHistory — directory-backed storage
# =============================================================================

_STATE_FILE_FIELDS = [
    "execution_id",
    "pjob_code",
    "status",
    "pid",
    "command",
    "started_at",
    "finished_at",
    "duration_seconds",
    "returncode",
    "stdout_preview",
    "stderr_preview",
    "error_detail",
    "log_path",
    "agent",
    "workflow",
]


class ExecutionHistory:
    """Manages PJob execution history using one JSON file per execution.

    Directory layout::

        ~/.zima/history/pjobs/
        +-- <pjob_code>/
            +-- <execution_id>.json
    """

    HISTORY_DIR_NAME = "pjobs"
    MAX_HISTORY_PER_PJOB = 100

    def __init__(self):
        self._base_dir = get_zima_home() / "history" / self.HISTORY_DIR_NAME
        self._legacy_migrated = False

    def _ensure_migrated(self) -> None:
        """Run legacy migration at most once, lazily."""
        if not self._legacy_migrated:
            self._migrate_from_legacy()
            self._legacy_migrated = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pjob_dir(self, pjob_code: str) -> Path:
        """Return the directory for a given PJob."""
        path = self._base_dir / pjob_code
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _exec_file(self, pjob_code: str, execution_id: str) -> Path:
        """Return the path to the JSON file for a specific execution."""
        return self._pjob_dir(pjob_code) / f"{execution_id}.json"

    def _load_state(self, pjob_code: str, execution_id: str) -> Optional[dict]:
        """Load the state dict for an execution, or None."""
        self._ensure_migrated()
        path = self._exec_file(pjob_code, execution_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None

    def _iter_state_files(self, pjob_code: str, status: Optional[str] = None) -> list[dict]:
        """Return all state dicts for a PJob, optionally filtered by status.

        Files are sorted by ``started_at`` descending.  Running entries whose
        PID is no longer alive are auto-marked ``dead`` in the returned data
        (and persisted).
        """
        self._ensure_migrated()
        pdir = self._base_dir / pjob_code
        if not pdir.is_dir():
            return []

        raw: list[dict] = []
        for f in sorted(pdir.iterdir(), reverse=True):
            if f.suffix != ".json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                raw.append(data)
            except (json.JSONDecodeError, IOError):
                continue

        # Auto-mark stale "running" entries as "dead"
        for data in raw:
            if data.get("status") == "running":
                pid = data.get("pid")
                if pid is not None and not _is_pid_alive(pid):
                    data["status"] = "dead"
                    # Persist the update (guard against corrupted files)
                    try:
                        pjob = data.get("pjob_code")
                        eid = data.get("execution_id")
                        if pjob and eid:
                            fpath = self._exec_file(pjob, eid)
                            fpath.write_text(
                                json.dumps(data, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                    except (IOError, OSError):
                        pass

        # Sort by started_at descending
        raw.sort(
            key=lambda d: d.get("started_at", ""),
            reverse=True,
        )

        if status:
            raw = [d for d in raw if d.get("status") == status]

        return raw

    # ------------------------------------------------------------------
    # Runtime-state public API (new directory-based methods)
    # ------------------------------------------------------------------

    def write_runtime_state(self, pjob_code: str, execution_id: str, state: dict) -> Path:
        """Write a runtime state dict to disk.

        The ``state`` dict should contain any of the fields listed in
        ``_STATE_FILE_FIELDS``.

        Returns:
            The path of the written JSON file.
        """
        path = self._exec_file(pjob_code, execution_id)
        path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def update_runtime_state(
        self,
        pjob_code: str,
        execution_id: str,
        **fields,
    ) -> None:
        """Update fields on an existing runtime state file.

        Any keyword argument is merged into the existing JSON dict.  If the
        file does not exist this is a no-op.
        """
        path = self._exec_file(pjob_code, execution_id)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return
        data.update(fields)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_runtime_state(self, pjob_code: str, execution_id: str) -> Optional[dict]:
        """Return the runtime state dict, or ``None`` if it doesn't exist."""
        return self._load_state(pjob_code, execution_id)

    def list_executions(
        self,
        pjob_code: str,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List all execution state dicts for a PJob.

        Results are sorted by ``started_at`` descending.
        Running entries whose PID is dead are auto-marked ``dead``.
        """
        return self._iter_state_files(pjob_code, status=status)

    def get_all_running(self) -> list[dict]:
        """Return all running executions across all PJobs.

        Each entry's PID is re-verified; stale entries are auto-marked
        ``dead`` and excluded from the result.
        """
        self._ensure_migrated()
        running: list[dict] = []
        if not self._base_dir.is_dir():
            return running

        for pjob_dir in sorted(self._base_dir.iterdir()):
            if not pjob_dir.is_dir():
                continue
            records = self._iter_state_files(pjob_dir.name, status="running")
            running.extend(records)
        return running

    def clear_history(self, pjob_code: str) -> bool:
        """Delete the entire history directory for a PJob.

        Returns:
            ``True`` if anything was deleted, ``False`` if the directory did
            not exist.
        """
        pdir = self._base_dir / pjob_code
        if not pdir.is_dir():
            return False
        import shutil

        shutil.rmtree(pdir)
        return True

    def get_stats(self, pjob_code: str) -> dict:
        """Compute execution statistics for a PJob."""
        records = self.list_executions(pjob_code)

        if not records:
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
            }

        total = len(records)
        success = sum(1 for r in records if r.get("status") == "success")
        failed = total - success

        durations = [
            r.get("duration_seconds", 0)
            for r in records
            if r.get("status") == "success"
            and isinstance(r.get("duration_seconds"), (int, float))
            and r["duration_seconds"] > 0
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": success / total * 100,
            "avg_duration": round(avg_duration, 2),
        }

    # ------------------------------------------------------------------
    # Backward-compatible API (delegates to directory-based storage)
    # ------------------------------------------------------------------

    def add(self, record: ExecutionRecord) -> None:
        """Add an execution record (backward-compatible).

        Delegates to :meth:`write_runtime_state`.
        """
        state = record.to_dict()
        # Ensure all fields that the new format expects are present
        for fld in _STATE_FILE_FIELDS:
            state.setdefault(
                fld,
                (
                    None
                    if fld == "pid"
                    else ("" if fld in ("log_path", "agent", "workflow") else None)
                ),
            )
        # Convert None values to null-friendly placeholders for JSON
        self.write_runtime_state(record.pjob_code, record.execution_id, state)

    def get_history(
        self,
        pjob_code: str,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> list[ExecutionRecord]:
        """Get execution history as ``ExecutionRecord`` objects.

        Delegates to :meth:`list_executions`.
        """
        raw = self.list_executions(pjob_code, status=status)
        return [ExecutionRecord.from_dict(r) for r in raw[:limit]]

    def get_record(self, pjob_code: str, execution_id: str) -> Optional[ExecutionRecord]:
        """Get a specific execution record (backward-compatible).

        Delegates to :meth:`get_runtime_state`.
        """
        state = self.get_runtime_state(pjob_code, execution_id)
        if state is None:
            return None
        return ExecutionRecord.from_dict(state)

    def get_all_pjobs(self) -> list[str]:
        """List all PJob codes that have history entries."""
        self._ensure_migrated()
        if not self._base_dir.is_dir():
            return []
        return sorted(p.name for p in self._base_dir.iterdir() if p.is_dir())

    # ------------------------------------------------------------------
    # Legacy migration
    # ------------------------------------------------------------------

    def _migrate_from_legacy(self) -> None:
        """Migrate the old single-file ``pjobs.json`` to directory storage.

        Reads ``~/.zima/history/pjobs.json``, writes individual files, and
        renames the legacy file to ``pjobs.json.bak``.
        """
        legacy_file = get_zima_home() / "history" / "pjobs.json"
        if not legacy_file.exists():
            return

        try:
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return

        if not isinstance(data, dict):
            return

        migrated = 0
        for pjob_code, records in data.items():
            if not isinstance(records, list):
                continue
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                eid = rec.get("execution_id")
                if not eid:
                    continue
                rec.setdefault("log_path", "")
                rec.setdefault("agent", "")
                rec.setdefault("workflow", "")
                self.write_runtime_state(pjob_code, eid, rec)
                migrated += 1

        if migrated > 0:
            # Rename legacy file to .bak
            bak = legacy_file.with_suffix(".json.bak")
            legacy_file.rename(bak)
