"""Execution history management for PJob."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from zima.utils import generate_timestamp, get_zima_home


@dataclass
class ExecutionRecord:
    """
    Single execution record.
    
    Attributes:
        execution_id: Unique execution ID
        pjob_code: PJob code
        status: Execution status
        returncode: Process return code
        command: Executed command
        started_at: Start timestamp
        finished_at: Finish timestamp
        duration_seconds: Execution duration
        stdout_preview: First N chars of stdout
        stderr_preview: First N chars of stderr
        error_detail: Detailed error information
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
        )
    
    @classmethod
    def from_result(cls, result) -> ExecutionRecord:
        """Create from ExecutionResult."""
        # Truncate previews
        stdout_preview = result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout
        stderr_preview = result.stderr[:500] + "..." if len(result.stderr) > 500 else result.stderr
        # Truncate error_detail if too long
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
        )


class ExecutionHistory:
    """
    Manages execution history for all PJobs.
    
    History is stored in ~/.zima/history/pjobs.json
    """
    
    MAX_HISTORY_PER_PJOB = 100
    
    def __init__(self):
        """Initialize history manager."""
        self.history_file = get_zima_home() / "history" / "pjobs.json"
        self._ensure_dir()
    
    def _ensure_dir(self) -> None:
        """Ensure history directory exists."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_all(self) -> dict:
        """Load all history records."""
        if not self.history_file.exists():
            return {}
        
        try:
            content = self.history_file.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save_all(self, data: dict) -> None:
        """Save all history records."""
        self._ensure_dir()
        self.history_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    
    def add(self, record: ExecutionRecord) -> None:
        """
        Add a new execution record.
        
        Args:
            record: Execution record to add
        """
        data = self._load_all()
        pjob_code = record.pjob_code
        
        if pjob_code not in data:
            data[pjob_code] = []
        
        # Add to front
        data[pjob_code].insert(0, record.to_dict())
        
        # Trim to max size
        if len(data[pjob_code]) > self.MAX_HISTORY_PER_PJOB:
            data[pjob_code] = data[pjob_code][:self.MAX_HISTORY_PER_PJOB]
        
        self._save_all(data)
    
    def get_history(
        self,
        pjob_code: str,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> list[ExecutionRecord]:
        """
        Get execution history for a PJob.
        
        Args:
            pjob_code: PJob code
            limit: Maximum number of records
            status: Filter by status (optional)
            
        Returns:
            List of execution records
        """
        data = self._load_all()
        records = data.get(pjob_code, [])
        
        # Filter by status
        if status:
            records = [r for r in records if r.get("status") == status]
        
        # Convert to objects
        result = [ExecutionRecord.from_dict(r) for r in records[:limit]]
        
        return result
    
    def get_record(self, pjob_code: str, execution_id: str) -> Optional[ExecutionRecord]:
        """
        Get a specific execution record.
        
        Args:
            pjob_code: PJob code
            execution_id: Execution ID
            
        Returns:
            Execution record or None
        """
        data = self._load_all()
        records = data.get(pjob_code, [])
        
        for r in records:
            if r.get("execution_id") == execution_id:
                return ExecutionRecord.from_dict(r)
        
        return None
    
    def clear_history(self, pjob_code: str) -> bool:
        """
        Clear history for a PJob.
        
        Args:
            pjob_code: PJob code
            
        Returns:
            True if cleared successfully
        """
        data = self._load_all()
        
        if pjob_code in data:
            del data[pjob_code]
            self._save_all(data)
            return True
        
        return False
    
    def get_all_pjobs(self) -> list[str]:
        """
        Get all PJob codes with history.
        
        Returns:
            List of PJob codes
        """
        data = self._load_all()
        return list(data.keys())
    
    def get_stats(self, pjob_code: str) -> dict:
        """
        Get execution statistics for a PJob.
        
        Args:
            pjob_code: PJob code
            
        Returns:
            Statistics dictionary
        """
        history = self.get_history(pjob_code, limit=self.MAX_HISTORY_PER_PJOB)
        
        if not history:
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
            }
        
        total = len(history)
        success = sum(1 for h in history if h.status == "success")
        failed = total - success
        
        durations = [h.duration_seconds for h in history if h.duration_seconds > 0]
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "success_rate": success / total * 100,
            "avg_duration": round(avg_duration, 2),
        }
