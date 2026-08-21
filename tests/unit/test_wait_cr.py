"""Unit tests for pi/zima-pr-monitor/scripts/wait-cr.py."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "pi" / "zima-pr-monitor" / "scripts" / "wait-cr.py"


def _load():
    spec = importlib.util.spec_from_file_location("wait_cr", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wait_cr = _load()

NOW = datetime(2026, 8, 22, 0, 30, tzinfo=timezone.utc)


def write_state(state_dir, eid, state):
    path = state_dir / f"{eid}.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def terminal_state(status="success", started_minutes_ago=2, **extra):
    started = (NOW - timedelta(minutes=started_minutes_ago)).isoformat()
    return {"execution_id": "x", "status": status, "started_at": started, **extra}


def cutoff_minutes_ago(minutes=10):
    return NOW - timedelta(minutes=minutes)


class TestLoadStates:
    def test_skips_torn_json(self, tmp_path):
        write_state(tmp_path, "good", {"status": "success"})
        (tmp_path / "torn.json").write_text('{"status": "run', encoding="utf-8")
        states = wait_cr.load_states(tmp_path)
        assert set(states) == {"good"}

    def test_empty_dir(self, tmp_path):
        assert wait_cr.load_states(tmp_path) == {}


class TestIsActive:
    def test_running_is_always_active(self):
        assert wait_cr.is_active({"status": "running"}, None) is True

    def test_terminal_within_cutoff_is_active(self):
        state = terminal_state("success", started_minutes_ago=5)
        assert wait_cr.is_active(state, cutoff_minutes_ago(10)) is True

    def test_terminal_before_cutoff_is_inactive(self):
        state = terminal_state("success", started_minutes_ago=30)
        assert wait_cr.is_active(state, cutoff_minutes_ago(10)) is False

    def test_unknown_status_is_inactive(self):
        assert wait_cr.is_active({"status": "weird"}, cutoff_minutes_ago(10)) is False


class TestIsStale:
    def test_dead_pid_is_stale(self, monkeypatch):
        monkeypatch.setattr(wait_cr, "pid_alive", lambda pid: False)
        assert wait_cr.is_stale({"status": "running", "pid": 12345}) is True

    def test_alive_pid_not_stale(self, monkeypatch):
        monkeypatch.setattr(wait_cr, "pid_alive", lambda pid: True)
        assert wait_cr.is_stale({"status": "running", "pid": 12345}) is False

    def test_pid_none_not_stale(self):
        assert wait_cr.is_stale({"status": "running", "pid": None}) is False

    def test_terminal_not_stale(self, monkeypatch):
        monkeypatch.setattr(wait_cr, "pid_alive", lambda pid: False)
        assert wait_cr.is_stale({"status": "success", "pid": 12345}) is False


class TestRunLoop:
    def test_all_terminal_returns_zero(self, tmp_path, capsys):
        write_state(tmp_path, "a", terminal_state("success", 1))
        write_state(tmp_path, "b", terminal_state("failed", 2))
        rc = wait_cr.run_loop(tmp_path, cutoff_minutes_ago(10), timeout=60, poll=1, grace=5)
        out = capsys.readouterr().out
        assert rc == 0
        assert "eid=a" in out and "eid=b" in out
        assert "status=success" in out and "status=failed" in out

    def test_waits_for_running_to_finish(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(wait_cr, "pid_alive", lambda pid: True)
        path = write_state(tmp_path, "a", terminal_state("running", 0, pid=99999))
        calls = {"n": 0}

        def fake_sleep(sec):
            calls["n"] += 1
            if calls["n"] == 1:
                path.write_text(json.dumps(terminal_state("success", 0)), encoding="utf-8")

        def fake_monotonic():
            return 1000.0 + calls["n"] * 30.0

        rc = wait_cr.run_loop(
            tmp_path,
            cutoff_minutes_ago(10),
            timeout=2100,
            poll=30,
            grace=60,
            sleep=fake_sleep,
            monotonic=fake_monotonic,
        )
        assert rc == 0
        assert "status=success" in capsys.readouterr().out

    def test_stale_running_treated_as_finished(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(wait_cr, "pid_alive", lambda pid: False)
        write_state(tmp_path, "a", terminal_state("running", 0, pid=99999))
        rc = wait_cr.run_loop(tmp_path, cutoff_minutes_ago(10), timeout=60, poll=1, grace=5)
        assert rc == 0
        assert "STALE" in capsys.readouterr().out

    def test_timeout_returns_one(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(wait_cr, "pid_alive", lambda pid: True)
        write_state(tmp_path, "a", terminal_state("running", 0, pid=99999))
        calls = {"n": 0}

        def fake_sleep(sec):
            calls["n"] += 1

        def fake_monotonic():
            return 1000.0 + calls["n"] * 1000.0

        rc = wait_cr.run_loop(
            tmp_path,
            cutoff_minutes_ago(10),
            timeout=1,
            poll=30,
            grace=5,
            sleep=fake_sleep,
            monotonic=fake_monotonic,
        )
        assert rc == 1
        assert "timeout" in capsys.readouterr().err

    def test_no_execution_returns_two(self, tmp_path, capsys):
        calls = {"n": 0}

        def fake_sleep(sec):
            calls["n"] += 1

        def fake_monotonic():
            return 1000.0 + calls["n"] * 100.0

        rc = wait_cr.run_loop(
            tmp_path,
            cutoff_minutes_ago(10),
            timeout=60,
            poll=30,
            grace=60,
            sleep=fake_sleep,
            monotonic=fake_monotonic,
        )
        assert rc == 2

    def test_new_execution_appears_within_grace(self, tmp_path, capsys):
        calls = {"n": 0}

        def fake_sleep(sec):
            calls["n"] += 1
            if calls["n"] == 1:
                write_state(tmp_path, "a", terminal_state("success", 0))

        def fake_monotonic():
            return 1000.0 + calls["n"] * 30.0

        rc = wait_cr.run_loop(
            tmp_path,
            cutoff_minutes_ago(10),
            timeout=2100,
            poll=30,
            grace=120,
            sleep=fake_sleep,
            monotonic=fake_monotonic,
        )
        assert rc == 0


class TestMain:
    def test_main_smoke_all_terminal(self, tmp_path, capsys):
        state_dir = tmp_path / "fake-home" / "history" / "pjobs" / "pjob-code"
        state_dir.mkdir(parents=True)
        started = datetime.now(timezone.utc).isoformat()
        write_state(state_dir, "a", {"status": "success", "started_at": started})
        rc = wait_cr.main(
            [
                "pjob-code",
                "--zima-home",
                str(tmp_path / "fake-home"),
                "--grace",
                "0",
                "--timeout",
                "5",
                "--poll",
                "1",
            ]
        )
        assert rc == 0
