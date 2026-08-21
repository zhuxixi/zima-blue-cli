"""Unit tests for ExecutionHistory directory-based storage."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from zima.execution.history import ExecutionHistory, ExecutionRecord, _is_pid_alive


class TestExecutionHistoryWriteAndRead:
    @pytest.fixture(autouse=True)
    def setup(self, isolated_zima_home):
        self.history = ExecutionHistory()
        self.pjob_code = "test-pjob"
        self.exec_id = "a1b2c3d4"

    def test_write_runtime_state_creates_file(self):
        import os

        state = {
            "execution_id": self.exec_id,
            "pjob_code": self.pjob_code,
            "status": "running",
            "pid": os.getpid(),
            "command": ["kimi", "code"],
            "started_at": "2026-04-28T10:30:00+08:00",
            "log_path": "/tmp/test.log",
            "agent": "kimi",
            "workflow": "test-workflow",
        }
        path = self.history.write_runtime_state(self.pjob_code, self.exec_id, state)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["status"] == "running"
        assert data["execution_id"] == self.exec_id

    def test_update_runtime_state_modifies_file(self):
        self.history.write_runtime_state(
            self.pjob_code,
            self.exec_id,
            {
                "execution_id": self.exec_id,
                "pjob_code": self.pjob_code,
                "status": "running",
                "pid": 12345,
                "started_at": "2026-04-28T10:30:00+08:00",
            },
        )
        self.history.update_runtime_state(
            self.pjob_code,
            self.exec_id,
            status="success",
            returncode=0,
            duration_seconds=10.5,
            finished_at="2026-04-28T10:30:10+08:00",
            stdout_preview="hello world",
            stderr_preview="",
        )
        data = self.history.get_runtime_state(self.pjob_code, self.exec_id)
        assert data["status"] == "success"
        assert data["returncode"] == 0
        assert data["duration_seconds"] == 10.5

    def test_get_runtime_state_returns_none_for_missing(self):
        result = self.history.get_runtime_state("nonexistent", "a1b2c3d4")
        assert result is None

    def test_list_executions_returns_all(self):
        for eid, status in [("a1", "success"), ("b2", "running"), ("c3", "failed")]:
            self.history.write_runtime_state(
                self.pjob_code,
                eid,
                {
                    "execution_id": eid,
                    "pjob_code": self.pjob_code,
                    "status": status,
                    "pid": 10000,
                    "started_at": f"2026-04-28T10:30:0{eid[-1]}+08:00",
                },
            )
        records = self.history.list_executions(self.pjob_code)
        assert len(records) == 3

    def test_list_executions_filter_by_status(self):
        import os

        for eid, status in [("a1", "success"), ("b2", "running"), ("c3", "failed")]:
            self.history.write_runtime_state(
                self.pjob_code,
                eid,
                {
                    "execution_id": eid,
                    "pjob_code": self.pjob_code,
                    "status": status,
                    "pid": os.getpid() if status == "running" else 99999,
                    "started_at": f"2026-04-28T10:30:0{eid[-1]}+08:00",
                },
            )
        running = self.history.list_executions(self.pjob_code, status="running")
        assert len(running) == 1
        assert running[0]["execution_id"] == "b2"

    def test_get_all_running_across_pjobs(self):
        import os

        self.history.write_runtime_state(
            "foo",
            "a1",
            {
                "execution_id": "a1",
                "pjob_code": "foo",
                "status": "running",
                "pid": os.getpid(),
                "started_at": "2026-04-28T10:30:00+08:00",
            },
        )
        self.history.write_runtime_state(
            "bar",
            "b2",
            {
                "execution_id": "b2",
                "pjob_code": "bar",
                "status": "running",
                "pid": os.getpid(),
                "started_at": "2026-04-28T10:31:00+08:00",
            },
        )
        self.history.write_runtime_state(
            "foo",
            "c3",
            {
                "execution_id": "c3",
                "pjob_code": "foo",
                "status": "success",
                "pid": 99999,
                "started_at": "2026-04-28T10:30:00+08:00",
            },
        )
        running = self.history.get_all_running()
        assert len(running) == 2

    def test_clear_history_removes_directory(self):
        self.history.write_runtime_state(
            self.pjob_code,
            self.exec_id,
            {
                "execution_id": self.exec_id,
                "pjob_code": self.pjob_code,
                "status": "success",
                "pid": 1,
                "started_at": "2026-04-28T10:30:00+08:00",
            },
        )
        self.history.clear_history(self.pjob_code)
        records = self.history.list_executions(self.pjob_code)
        assert len(records) == 0

    def test_get_stats_computes_correctly(self):
        for i, (eid, status, dur) in enumerate(
            [("a1", "success", 10.0), ("b2", "success", 20.0), ("c3", "failed", 5.0)]
        ):
            self.history.write_runtime_state(
                self.pjob_code,
                eid,
                {
                    "execution_id": eid,
                    "pjob_code": self.pjob_code,
                    "status": status,
                    "pid": i,
                    "duration_seconds": dur,
                    "started_at": f"2026-04-28T10:30:0{i}+08:00",
                },
            )
        stats = self.history.get_stats(self.pjob_code)
        assert stats["total"] == 3
        assert stats["success"] == 2
        assert stats["failed"] == 1
        assert stats["avg_duration"] == 15.0

    def test_dead_pid_auto_detection(self):
        """Running entries with dead PIDs are auto-marked 'dead' and persisted."""
        self.history.write_runtime_state(
            self.pjob_code,
            self.exec_id,
            {
                "execution_id": self.exec_id,
                "pjob_code": self.pjob_code,
                "status": "running",
                "pid": 99999999,  # definitely dead
                "started_at": "2026-04-28T10:30:00+08:00",
            },
        )
        records = self.history.list_executions(self.pjob_code)
        assert len(records) == 1
        # Auto-marked in memory
        assert records[0]["status"] == "dead"
        # Persisted to disk
        data = self.history.get_runtime_state(self.pjob_code, self.exec_id)
        assert data is not None
        assert data["status"] == "dead"

    def test_scan_pr_result_round_trip(self):
        """scan_pr_result is persisted and loaded correctly."""
        record = ExecutionRecord(
            execution_id="a1",
            pjob_code="test-pjob",
            status="failed",
            returncode=1,
            scan_pr_result={"repo": "owner/repo", "pr_number": "42"},
            started_at="2026-05-03T10:00:00+08:00",
        )
        data = record.to_dict()
        assert data["scan_pr_result"] == {"repo": "owner/repo", "pr_number": "42"}

        restored = ExecutionRecord.from_dict(data)
        assert restored.scan_pr_result == {"repo": "owner/repo", "pr_number": "42"}

    def test_scan_pr_result_defaults_to_none(self):
        """Existing records without scan_pr_result deserialize as None."""
        record = ExecutionRecord.from_dict(
            {
                "execution_id": "a1",
                "pjob_code": "test-pjob",
                "status": "success",
                "returncode": 0,
            }
        )
        assert record.scan_pr_result is None

    def test_scan_pr_result_excluded_when_none(self):
        """to_dict omits scan_pr_result when it is None."""
        record = ExecutionRecord(
            execution_id="a1",
            pjob_code="test-pjob",
            status="success",
            returncode=0,
        )
        data = record.to_dict()
        assert "scan_pr_result" not in data


class TestGetRecentScanPrFailures:
    @pytest.fixture(autouse=True)
    def setup(self, isolated_zima_home):
        self.history = ExecutionHistory()
        self.pjob_code = "reviewer-kimi"

    def _write_record(self, exec_id, status, scan_pr_result, started_at, minutes_ago=0):
        """Helper to write an execution record."""
        from datetime import datetime, timedelta, timezone

        if started_at is None:
            ts = datetime.now(timezone.utc).astimezone() - timedelta(minutes=minutes_ago)
            started_at = ts.isoformat()
        self.history.write_runtime_state(
            self.pjob_code,
            exec_id,
            {
                "execution_id": exec_id,
                "pjob_code": self.pjob_code,
                "status": status,
                "returncode": 1,
                "started_at": started_at,
                "scan_pr_result": scan_pr_result,
            },
        )

    def test_returns_recently_failed_prs(self):
        self._write_record("a1", "failed", {"repo": "o/r", "pr_number": "10"}, None, minutes_ago=5)
        self._write_record("a2", "failed", {"repo": "o/r", "pr_number": "20"}, None, minutes_ago=30)

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 2
        pr_numbers = {r["scan_pr_result"]["pr_number"] for r in results}
        assert pr_numbers == {"10", "20"}

    def test_excludes_prs_outside_time_window(self):
        self._write_record("a1", "failed", {"repo": "o/r", "pr_number": "10"}, None, minutes_ago=5)
        self._write_record(
            "a2", "failed", {"repo": "o/r", "pr_number": "20"}, None, minutes_ago=120
        )

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 1
        assert results[0]["scan_pr_result"]["pr_number"] == "10"

    def test_excludes_success_and_running_status(self):
        self._write_record("a1", "success", {"repo": "o/r", "pr_number": "10"}, None, minutes_ago=5)
        self._write_record("a2", "running", {"repo": "o/r", "pr_number": "20"}, None, minutes_ago=5)

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 0

    def test_excludes_records_without_scan_pr_result(self):
        self._write_record("a1", "failed", None, None, minutes_ago=5)

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 0

    def test_returns_empty_for_nonexistent_pjob(self):
        results = self.history.get_recent_scan_pr_failures("nonexistent", within_minutes=90)
        assert results == []


class TestLegacyMigration:
    @pytest.fixture(autouse=True)
    def setup(self, isolated_zima_home):
        self.history = ExecutionHistory()
        self.zima_home = isolated_zima_home

    def test_migration_from_pjobs_json(self):
        import json

        legacy_file = Path(self.zima_home) / "history" / "pjobs.json"
        legacy_file.parent.mkdir(parents=True, exist_ok=True)
        legacy_data = {
            "foo": [
                {
                    "execution_id": "a1",
                    "pjob_code": "foo",
                    "status": "success",
                    "returncode": 0,
                    "command": ["echo", "hello"],
                    "started_at": "2026-01-01T00:00:00",
                    "finished_at": "2026-01-01T00:01:00",
                    "duration_seconds": 60.0,
                    "stdout_preview": "output",
                    "stderr_preview": "",
                    "error_detail": "",
                    "pid": 42,
                }
            ],
            "bar": [
                {
                    "execution_id": "b2",
                    "pjob_code": "bar",
                    "status": "failed",
                    "returncode": 1,
                    "command": ["false"],
                    "started_at": "2026-01-02T00:00:00",
                    "finished_at": "2026-01-02T00:00:01",
                    "duration_seconds": 1.0,
                    "stdout_preview": "",
                    "stderr_preview": "error",
                    "error_detail": "",
                    "pid": 99,
                }
            ],
        }
        legacy_file.write_text(json.dumps(legacy_data, ensure_ascii=False))

        records = self.history.list_executions("foo")
        assert len(records) == 1
        assert records[0]["execution_id"] == "a1"
        assert records[0]["status"] == "success"

        bar_records = self.history.list_executions("bar")
        assert len(bar_records) == 1
        assert bar_records[0]["status"] == "failed"

        bak_file = legacy_file.parent / "pjobs.json.bak"
        assert bak_file.exists() or not legacy_file.exists()


class TestPidAlive:
    def test_is_pid_alive_none(self):
        assert not _is_pid_alive(None)

    def test_is_pid_alive_current_process(self):
        import os

        assert _is_pid_alive(os.getpid())

    def test_is_pid_alive_dead_pid(self):
        assert not _is_pid_alive(99999999)


class TestFindRecentDuplicate:
    @pytest.fixture(autouse=True)
    def setup(self, isolated_zima_home):
        self.history = ExecutionHistory()
        self.pjob_code = "test-pjob"
        self.now = datetime.now(timezone.utc)

    def _write(
        self,
        execution_id,
        status,
        repo="owner/repo",
        pr_number="42",
        head_sha="",
        started_minutes_ago=0,
    ):
        started = (self.now - timedelta(minutes=started_minutes_ago)).isoformat()
        spr = {"repo": repo, "pr_number": pr_number}
        if head_sha:
            spr["head_sha"] = head_sha
        self.history.write_runtime_state(
            self.pjob_code,
            execution_id,
            {
                "execution_id": execution_id,
                "pjob_code": self.pjob_code,
                "status": status,
                "pid": None,
                "started_at": started,
                "scan_pr_result": spr,
            },
        )

    def _query(self, head_sha="", **kwargs):
        return self.history.find_recent_duplicate(
            pjob_code=self.pjob_code,
            repo="owner/repo",
            pr_number="42",
            head_sha=head_sha,
            exclude_execution_id="me000001",
            **kwargs,
        )

    def test_running_same_head_blocks(self):
        self._write("dup00001", "running", head_sha="abc123", started_minutes_ago=1)
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_stale_running_record_allows(self):
        # A running record older than the stale window (90min) cannot be a
        # live execution — a crashed run without a recorded pid must not
        # block the target forever (CR round-1 finding).
        self._write("dup00001", "running", head_sha="abc123", started_minutes_ago=95)
        assert self._query(head_sha="abc123") is None

    def test_running_different_head_allows(self):
        self._write("dup00001", "running", head_sha="abc123", started_minutes_ago=1)
        assert self._query(head_sha="def456") is None

    def test_success_within_window_same_head_blocks(self):
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=10)
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_success_within_window_different_head_allows(self):
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=10)
        assert self._query(head_sha="def456") is None

    def test_success_beyond_window_allows(self):
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=45)
        assert self._query(head_sha="abc123") is None

    def test_failed_allows(self):
        self._write("dup00001", "failed", started_minutes_ago=1)
        assert self._query(head_sha="abc123") is None

    def test_skipped_allows(self):
        self._write("dup00001", "skipped", started_minutes_ago=1)
        assert self._query(head_sha="abc123") is None

    def test_excludes_own_execution(self):
        self._write("me000001", "running", head_sha="abc123", started_minutes_ago=1)
        assert self._query(head_sha="abc123") is None

    def test_missing_head_treated_conservatively(self):
        # Candidate without head_sha blocks a query with head_sha (conservative).
        self._write("dup00001", "running", head_sha="", started_minutes_ago=1)
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_query_without_head_treated_conservatively(self):
        # Query without head_sha is blocked by a candidate WITH head_sha.
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=5)
        dup = self._query(head_sha="")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_unparseable_started_treated_in_window(self):
        self.history.write_runtime_state(
            self.pjob_code,
            "dup00001",
            {
                "execution_id": "dup00001",
                "pjob_code": self.pjob_code,
                "status": "success",
                "pid": None,
                "started_at": "not-a-timestamp",
                "scan_pr_result": {"repo": "owner/repo", "pr_number": "42"},
            },
        )
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_other_pjob_not_checked(self):
        self._write("dup00001", "running", head_sha="abc123", started_minutes_ago=1)
        other = ExecutionHistory()
        dup = other.find_recent_duplicate(
            pjob_code="other-pjob",
            repo="owner/repo",
            pr_number="42",
            head_sha="abc123",
            exclude_execution_id="me000001",
        )
        assert dup is None

    def test_candidate_hash_prefixed_pr_number_matches(self):
        self._write("dup00001", "running", pr_number="#42", started_minutes_ago=1)
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_query_hash_prefixed_pr_number_matches(self):
        self._write("dup00001", "running", pr_number="42", started_minutes_ago=1)
        dup = self.history.find_recent_duplicate(
            pjob_code=self.pjob_code,
            repo="owner/repo",
            pr_number="#42",
            head_sha="abc123",
            exclude_execution_id="me000001",
        )
        assert dup is not None and dup["execution_id"] == "dup00001"
