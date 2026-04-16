"""Daemon scheduler for 32-cycle PJob execution."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from zima.models.schedule import ScheduleConfig


class DaemonScheduler:
    """Runs PJobs on a fixed 45-minute cycle schedule with 3 stages."""

    def __init__(self, schedule: ScheduleConfig, daemon_dir: Path):
        self.schedule = schedule
        self.daemon_dir = daemon_dir
        self.running = False
        self.current_cycle = -1
        self.current_stage: str | None = None
        self.active_pjobs: dict[str, subprocess.Popen] = {}
        self._timers: list[threading.Timer] = []
        self._lock = threading.Lock()

        # Ensure runtime directories
        self.daemon_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = daemon_dir / "history"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> None:
        """Main scheduling loop."""
        self.running = True
        self._log("DaemonScheduler started")
        self._save_state()

        while self.running:
            now = datetime.now()
            cycle_num = self._current_cycle_num(now)
            cycle_start = self._cycle_start_time(now)
            next_cycle_start = cycle_start + timedelta(minutes=self.schedule.cycle_minutes)

            if cycle_num != self.current_cycle:
                self.current_cycle = cycle_num
                self._log(f"Entering cycle {cycle_num}")
                self._start_cycle(cycle_num, cycle_start)

            # Sleep until next cycle boundary
            sleep_seconds = (next_cycle_start - datetime.now()).total_seconds()
            if sleep_seconds > 0:
                self._sleep(sleep_seconds)

        self._log("DaemonScheduler stopped")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self.running = False
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()
        with self._lock:
            self._kill_all_pjobs(stage_name="shutdown")
        self._log("Received stop signal")

    def _start_cycle(self, cycle_num: int, cycle_start: datetime) -> None:
        """Schedule stage timers for this cycle."""
        self._cancel_timers()
        mapped_type = self.schedule.cycle_mapping[cycle_num]

        if mapped_type == "idle":
            self._log(f"Cycle {cycle_num} is idle, sleeping")
            return

        cycle_type = self.schedule.get_cycle_type(mapped_type)
        if cycle_type is None:
            self._log(f"Cycle {cycle_num}: unknown typeId '{mapped_type}', skipping")
            return

        now = datetime.now()
        for stage in self.schedule.stages:
            stage_start = cycle_start + timedelta(minutes=stage.offset_minutes)
            delay = (stage_start - now).total_seconds()
            if delay < 0:
                delay = 0  # Already passed, trigger immediately

            timer = threading.Timer(delay, self._trigger_stage, args=[stage.name, cycle_type])
            timer.daemon = True
            timer.start()
            self._timers.append(timer)

    def _trigger_stage(self, stage_name: str, cycle_type) -> None:
        """Trigger a stage: kill previous, start new PJobs."""
        if not self.running:
            return

        self.current_stage = stage_name
        self._log(f"Stage '{stage_name}' triggered in cycle {self.current_cycle}")

        # Kill previous stage PJobs
        with self._lock:
            self._kill_all_pjobs(stage_name=f"pre-{stage_name}")

        pjob_codes = cycle_type.get_stage_pjobs(stage_name)
        for code in pjob_codes:
            self._start_pjob(code)

        self._save_state()

    def _start_pjob(self, code: str) -> None:
        """Start a PJob asynchronously."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"{code}_{timestamp}_{self.current_cycle}.log"

        cmd = [sys.executable, "-m", "zima.cli", "pjob", "run", code]

        # Build platform-specific subprocess kwargs
        kwargs: dict = {
            "stdout": open(log_file, "w", encoding="utf-8"),  # noqa: SIM115
            "stderr": subprocess.STDOUT,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(cmd, **kwargs)
            with self._lock:
                self.active_pjobs[code] = proc
            self._log(f"Started PJob {code} (PID {proc.pid}), log: {log_file}")
        except Exception as e:
            self._log(f"Failed to start PJob {code}: {e}")
            self._record_history(code, "launch_failed", str(e))

    def _kill_all_pjobs(self, stage_name: str) -> None:
        """Kill all active PJobs and record timeouts."""
        for code, proc in list(self.active_pjobs.items()):
            self._kill_pjob(code, proc, stage_name)
        self.active_pjobs.clear()

    def _kill_pjob(self, code: str, proc: subprocess.Popen, stage_name: str) -> None:
        """Kill a single PJob process."""
        if proc.poll() is not None:
            return  # Already finished

        self._log(f"Killing PJob {code} (PID {proc.pid}) at stage transition '{stage_name}'")
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception as e:
            self._log(f"Error killing PJob {code}: {e}")

        self._record_history(code, "killed_timeout", stage_name)

    def _record_history(self, code: str, status: str, detail: str) -> None:
        """Append a history record."""
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = self.log_dir / f"{today}.jsonl"
        record = {
            "pjobCode": code,
            "scheduleCode": self.schedule.metadata.code,
            "cycleNum": self.current_cycle,
            "stage": self.current_stage or "",
            "status": status,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        }
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _save_state(self) -> None:
        """Persist lightweight runtime state."""
        state_file = self.daemon_dir / "state.json"
        state = {
            "running": self.running,
            "currentCycle": self.current_cycle,
            "currentStage": self.current_stage,
            "activePjobs": list(self.active_pjobs.keys()),
            "updatedAt": datetime.now().isoformat(),
        }
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _log(self, message: str) -> None:
        """Write to daemon log."""
        log_file = self.daemon_dir / "daemon.log"
        line = f"[{datetime.now().isoformat()}] {message}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)

    def _cancel_timers(self) -> None:
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()

    def _sleep(self, seconds: float) -> None:
        """Sleep in small chunks so stop() is responsive."""
        end = time.time() + seconds
        while time.time() < end and self.running:
            time.sleep(min(1.0, end - time.time()))

    def _current_cycle_num(self, dt: datetime) -> int:
        """Compute which 45-minute cycle we're in (0-31) based on midnight."""
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes_since_midnight = (dt - midnight).total_seconds() / 60
        cycle_num = int(minutes_since_midnight // self.schedule.cycle_minutes)
        return cycle_num % self.schedule.daily_cycles

    def _cycle_start_time(self, dt: datetime) -> datetime:
        """Compute the start time of the current cycle."""
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes_since_midnight = (dt - midnight).total_seconds() / 60
        cycle_num = int(minutes_since_midnight // self.schedule.cycle_minutes)
        return midnight + timedelta(minutes=cycle_num * self.schedule.cycle_minutes)
