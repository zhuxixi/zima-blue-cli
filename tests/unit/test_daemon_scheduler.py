import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from zima.core.daemon_scheduler import DaemonScheduler
from zima.models.schedule import ScheduleConfig


class TestCycleMath:
    def test_current_cycle_num_at_midnight(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        dt = datetime(2026, 4, 16, 0, 0, 0)
        assert sched._current_cycle_num(dt) == 0

    def test_current_cycle_num_at_45_min(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        dt = datetime(2026, 4, 16, 0, 45, 0)
        assert sched._current_cycle_num(dt) == 1

    def test_current_cycle_num_at_22_30(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        dt = datetime(2026, 4, 16, 22, 30, 0)
        assert sched._current_cycle_num(dt) == 30

    def test_cycle_start_time(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        # 10:15 is in the cycle that started at 9:45 (13th cycle: 13*45=585min=9h45m)
        dt = datetime(2026, 4, 16, 10, 15, 0)
        start = sched._cycle_start_time(dt)
        assert start == datetime(2026, 4, 16, 9, 45, 0)


class TestStageTransitions:
    def test_kill_all_pjobs_records_timeout(self, tmp_path):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, tmp_path)
        sched.current_cycle = 5
        sched.current_stage = "work"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        sched.active_pjobs["p1"] = mock_proc

        sched._kill_all_pjobs("rest")

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5)

        # Check history file
        history_file = tmp_path / "history"
        jsonl_files = list(history_file.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        lines = jsonl_files[0].read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["pjobCode"] == "p1"
        assert record["status"] == "killed_timeout"

    def test_start_pjob_launch_failed(self, tmp_path):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, tmp_path)
        sched.current_cycle = 1
        sched.current_stage = "work"

        with patch("zima.core.daemon_scheduler.subprocess.Popen", side_effect=OSError("boom")):
            sched._start_pjob("bad-pjob")

        history_file = tmp_path / "history"
        jsonl_files = list(history_file.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        record = json.loads(jsonl_files[0].read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["pjobCode"] == "bad-pjob"
        assert record["status"] == "launch_failed"
