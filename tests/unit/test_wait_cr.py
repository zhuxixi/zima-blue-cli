"""Unit tests for pi/zima-pr-monitor/scripts/wait-cr.py."""

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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
            timeout=120,
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

    def test_running_before_cutoff_finishes_inside_wait(self, tmp_path, capsys, monkeypatch):
        """Regression: an execution that started before the cutoff but is
        still running when the wait begins must not vanish from the active
        set when it turns terminal (long-tail continuation scenario)."""
        monkeypatch.setattr(wait_cr, "pid_alive", lambda pid: True)
        path = write_state(tmp_path, "a", terminal_state("running", 30, pid=99999))
        calls = {"n": 0}

        def fake_sleep(sec):
            calls["n"] += 1
            if calls["n"] == 1:
                path.write_text(json.dumps(terminal_state("success", 30)), encoding="utf-8")

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


class TestTailLog:
    def test_tail_returns_log_end(self, tmp_path):
        log = tmp_path / "job.log"
        log.write_text(
            "x" * 3000 + "\n<zima-review><verdict>approved</verdict></zima-review>\n",
            encoding="utf-8",
        )
        tail = wait_cr.tail_log(str(log), chars=600)
        assert "</zima-review>" in tail
        assert "<verdict>approved</verdict>" in tail

    def test_tail_missing_path_returns_empty(self, tmp_path):
        assert wait_cr.tail_log(str(tmp_path / "nope.log")) == ""
        assert wait_cr.tail_log(None) == ""

    def test_format_summary_includes_log_tail(self, tmp_path):
        log = tmp_path / "job.log"
        log.write_text(
            "start\n<zima-review><verdict>approved</verdict></zima-review>\n",
            encoding="utf-8",
        )
        state = terminal_state("success", 1, log_path=str(log))
        line = wait_cr.format_summary("a", state)
        assert "log_tail=" in line
        assert "approved" in line


class TestPidAlivePermissionError:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="PermissionError semantics are Unix-only (Windows uses ctypes)",
    )
    def test_permission_error_means_alive(self, monkeypatch):
        def raise_perm(pid, sig):
            raise PermissionError()

        monkeypatch.setattr(wait_cr.os, "kill", raise_perm)
        assert wait_cr.pid_alive(12345) is True


class TestLoadStatesUnicode:
    def test_skips_undecodable_bytes(self, tmp_path):
        (tmp_path / "bad.json").write_bytes(b'{"status": "\xff\xfe broken')
        write_state(tmp_path, "good", {"status": "success"})
        states = wait_cr.load_states(tmp_path)
        assert set(states) == {"good"}


class TestGraceBoundedByTimeout:
    def test_no_exec_timeout_wins_when_smaller(self, tmp_path, capsys):
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
            grace=3000,
            sleep=fake_sleep,
            monotonic=fake_monotonic,
        )
        assert rc == 1
        assert "timeout" in capsys.readouterr().err


class TestPidAliveReal:
    def test_real_alive_pid_returns_true(self):
        assert wait_cr.pid_alive(os.getpid()) is True

    def test_real_dead_pid_returns_false(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        dead_pid = proc.pid
        proc.wait(timeout=10)
        assert wait_cr.pid_alive(dead_pid) is False


class TestParsePrRef:
    def test_parses_owner_repo_number(self):
        assert wait_cr.parse_pr_ref("zhuxixi/zima-blue-cli#264") == (
            "zhuxixi",
            "zima-blue-cli",
            264,
        )

    def test_strips_surrounding_space(self):
        assert wait_cr.parse_pr_ref("  a/b#7 ") == ("a", "b", 7)

    @pytest.mark.parametrize(
        "bad",
        ["a/b", "a#1", "/b#1", "a/#1", "a/b/c#1", "a/b#x", "a/b#0", "a/b#1#2", ""],
    )
    def test_rejects_malformed(self, bad):
        with pytest.raises(ValueError):
            wait_cr.parse_pr_ref(bad)


class TestMetaMarker:
    def test_pi_marker(self):
        assert wait_cr.meta_marker("<!-- pi-cr-meta {}\n-->") == "pi"

    def test_cc_marker_tolerates_whitespace(self):
        assert wait_cr.meta_marker("<!--cc-cr-meta\n{}") == "cc"

    def test_kimi_marker_is_ignored(self):
        assert wait_cr.meta_marker("<!-- kimi-cr-meta {} -->") is None

    def test_prose_mention_is_not_a_marker(self):
        assert wait_cr.meta_marker("we use pi-cr-meta in reviews") is None

    def test_empty_body(self):
        assert wait_cr.meta_marker("") is None


class TestParseMetaJson:
    def test_parses_payload(self):
        body = '<!-- pi-cr-meta {"round": 2, "blocking_new_count": 0} -->'
        assert wait_cr.parse_meta_json(body) == {"round": 2, "blocking_new_count": 0}

    def test_bad_json_returns_none(self):
        assert wait_cr.parse_meta_json('<!-- pi-cr-meta {"round": 2 -->') is None

    def test_non_object_json_returns_none(self):
        assert wait_cr.parse_meta_json("<!-- pi-cr-meta [1, 2] -->") is None

    def test_no_marker_returns_none(self):
        assert wait_cr.parse_meta_json("plain review body") is None


def meta_review(head, minutes_ago, review_id="PRR_1", marker="pi", now=NOW, **extra):
    submitted = (now - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")
    body = f'<!-- {marker}-cr-meta {{"round": 1}} -->'
    return {
        "id": review_id,
        "submittedAt": submitted,
        "commit": {"oid": head},
        "body": body,
        **extra,
    }


class TestSelectMetaReview:
    HEAD = "a" * 40

    def test_picks_review_for_target_head(self):
        review = meta_review(self.HEAD, 1)
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is review

    def test_ignores_review_for_other_head(self):
        review = meta_review("b" * 40, 1)
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is None

    def test_ignores_review_older_than_window(self):
        review = meta_review(self.HEAD, 30)
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is None

    def test_ignores_review_without_metadata(self):
        review = meta_review(self.HEAD, 1)
        review["body"] = "just a comment"
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is None

    def test_returns_newest_match(self):
        older = meta_review(self.HEAD, 5, review_id="PRR_old")
        newer = meta_review(self.HEAD, 1, review_id="PRR_new")
        assert (
            wait_cr.select_meta_review([older, newer], self.HEAD, cutoff_minutes_ago(10)) is newer
        )

    def test_accepts_cc_metadata(self):
        review = meta_review(self.HEAD, 1, marker="cc")
        assert wait_cr.select_meta_review([review], self.HEAD, cutoff_minutes_ago(10)) is review

    def test_tolerates_malformed_entries(self):
        good = meta_review(self.HEAD, 1)
        reviews = [None, {"commit": None}, {"commit": {}}, good]
        assert wait_cr.select_meta_review(reviews, self.HEAD, cutoff_minutes_ago(10)) is good


class TestFormatReviewSummary:
    HEAD = "a" * 40

    def test_includes_identity_and_meta_counts(self):
        review = meta_review(self.HEAD, 1, review_id="PRR_x")
        review["author"] = {"login": "zhuxixi"}
        review["body"] = (
            '<!-- pi-cr-meta {"round": 2, "blocking_new_count": 0, ' '"blocking_open_count": 1} -->'
        )
        line = wait_cr.format_review_summary(review)
        assert "review=PRR_x" in line
        assert "head=aaaaaaaaaaaa" in line
        assert "author=zhuxixi" in line
        assert "meta=pi" in line
        assert "round=2" in line
        assert "blocking_new=0" in line
        assert "blocking_open=1" in line

    def test_missing_counts_render_dash(self):
        review = meta_review(self.HEAD, 1)
        line = wait_cr.format_review_summary(review)
        assert "round=1" in line
        assert "blocking_new=-" in line
        assert "blocking_open=-" in line
        assert "author=?" in line


class TestHasLocalRuntime:
    def test_true_when_pjobs_dir_exists(self, tmp_path):
        (tmp_path / "history" / "pjobs").mkdir(parents=True)
        assert wait_cr.has_local_runtime(tmp_path) is True

    def test_false_when_only_configs(self, tmp_path):
        (tmp_path / "configs").mkdir()
        assert wait_cr.has_local_runtime(tmp_path) is False


class TestFetchPrState:
    def test_builds_gh_argv_and_parses(self):
        seen = {}

        def runner(argv):
            seen["argv"] = argv
            return json.dumps({"headRefOid": "a" * 40, "state": "OPEN", "reviews": []})

        data = wait_cr.fetch_pr_state("o", "r", 7, runner=runner)
        assert seen["argv"] == [
            "pr",
            "view",
            "7",
            "--repo",
            "o/r",
            "--json",
            "reviews,headRefOid,state",
        ]
        assert data["headRefOid"] == "a" * 40

    def test_non_json_output_raises(self):
        with pytest.raises(wait_cr.GhQueryError):
            wait_cr.fetch_pr_state("o", "r", 7, runner=lambda argv: "not json")

    def test_missing_head_raises(self):
        with pytest.raises(wait_cr.GhQueryError):
            wait_cr.fetch_pr_state("o", "r", 7, runner=lambda argv: '{"reviews": []}')


class TestRunPrLoop:
    PR = ("o", "r", 7)
    HEAD = "a" * 40

    def snap(self, reviews=(), head=None, state="OPEN"):
        return {"headRefOid": head or self.HEAD, "state": state, "reviews": list(reviews)}

    def drive(self, snapshots, *, timeout=2100, poll=30):
        """Feed snapshots to run_pr_loop with a fake clock; the last one repeats."""
        seq = list(snapshots)
        calls = {"n": 0}

        def fetch():
            return seq[min(calls["n"], len(seq) - 1)]

        def fake_sleep(sec):
            calls["n"] += 1

        def fake_monotonic():
            return 1000.0 + calls["n"] * poll

        return wait_cr.run_pr_loop(
            self.PR,
            timeout=timeout,
            poll=poll,
            since_minutes=10,
            fetch=fetch,
            sleep=fake_sleep,
            monotonic=fake_monotonic,
        )

    def test_converges_on_first_snapshot(self, capsys):
        rc = self.drive([self.snap([meta_review(self.HEAD, 1, now=datetime.now(timezone.utc))])])
        out = capsys.readouterr().out
        assert rc == 0
        assert "review=PRR_1" in out

    def test_converges_after_waiting(self, capsys):
        fresh = meta_review(self.HEAD, 1, now=datetime.now(timezone.utc))
        rc = self.drive([self.snap(), self.snap(), self.snap([fresh])])
        assert rc == 0
        assert "converged" in capsys.readouterr().out

    def test_timeout_is_one_and_never_says_trigger_failed(self, capsys):
        rc = self.drive([self.snap()], timeout=60)
        err = capsys.readouterr().err
        assert rc == 1
        assert "timeout" in err
        assert "trigger failed" not in err

    def test_head_change_is_four(self, capsys):
        rc = self.drive([self.snap(), self.snap(head="b" * 40)])
        assert rc == 4
        assert "head moved" in capsys.readouterr().err

    def test_closed_pr_is_five(self, capsys):
        rc = self.drive([self.snap(), self.snap(state="MERGED")])
        assert rc == 5
        assert "MERGED" in capsys.readouterr().err

    def test_head_change_wins_over_matching_review(self, capsys):
        stale = meta_review(self.HEAD, 1, now=datetime.now(timezone.utc))
        rc = self.drive([self.snap(), self.snap([stale], head="b" * 40)])
        assert rc == 4

    def test_startup_gh_failure_is_six(self, capsys):
        attempts = {"n": 0}

        def fetch():
            attempts["n"] += 1
            raise wait_cr.GhQueryError("boom")

        rc = wait_cr.run_pr_loop(
            self.PR,
            timeout=60,
            poll=1,
            fetch=fetch,
            sleep=lambda sec: None,
            monotonic=lambda: 1000.0,
        )
        assert rc == 6
        assert attempts["n"] == wait_cr.GH_START_ATTEMPTS
        assert "gh query failed" in capsys.readouterr().err

    def test_loop_gh_failure_recovers(self, capsys):
        state = {"n": 0}

        def fetch():
            state["n"] += 1
            if state["n"] == 2:
                raise wait_cr.GhQueryError("blip")
            if state["n"] == 1:
                return self.snap()
            return self.snap([meta_review(self.HEAD, 1, now=datetime.now(timezone.utc))])

        ticks = {"n": 0}

        def fake_sleep(sec):
            ticks["n"] += 1

        rc = wait_cr.run_pr_loop(
            self.PR,
            timeout=2100,
            poll=30,
            fetch=fetch,
            sleep=fake_sleep,
            monotonic=lambda: 1000.0 + ticks["n"] * 30.0,
        )
        err = capsys.readouterr().err
        assert rc == 0
        assert "retrying" in err


class TestMainLocal:
    def test_missing_runtime_is_three_without_sleeping(self, tmp_path, capsys, monkeypatch):
        slept = []
        monkeypatch.setattr(wait_cr.time, "sleep", lambda sec: slept.append(sec))
        rc = wait_cr.main(
            ["some-code", "--zima-home", str(tmp_path), "--grace", "1", "--timeout", "1"]
        )
        err = capsys.readouterr().err
        assert rc == 3
        assert "no local zima runtime" in err
        assert "--pr" in err
        assert slept == []

    def test_existing_runtime_still_uses_local_loop(self, tmp_path, capsys):
        state_dir = tmp_path / "history" / "pjobs" / "code"
        state_dir.mkdir(parents=True)
        started = datetime.now(timezone.utc).isoformat()
        write_state(state_dir, "a", {"status": "success", "started_at": started})
        rc = wait_cr.main(
            [
                "code",
                "--zima-home",
                str(tmp_path),
                "--grace",
                "0",
                "--timeout",
                "5",
                "--poll",
                "1",
            ]
        )
        assert rc == 0


class TestMainRemote:
    def test_converges_via_injected_fetch(self, monkeypatch, capsys):
        head = "a" * 40
        review = meta_review(head, 1, now=datetime.now(timezone.utc))
        snap = {"headRefOid": head, "state": "OPEN", "reviews": [review]}
        monkeypatch.setattr(wait_cr, "fetch_pr_state", lambda *a, **k: snap)
        rc = wait_cr.main(["--pr", "o/r#7", "--timeout", "30"])
        assert rc == 0
        assert "converged" in capsys.readouterr().out

    def test_startup_gh_failure_is_six(self, monkeypatch, capsys):
        def boom(*args, **kwargs):
            raise wait_cr.GhQueryError("not logged in")

        monkeypatch.setattr(wait_cr, "fetch_pr_state", boom)
        rc = wait_cr.main(["--pr", "o/r#7", "--timeout", "30"])
        assert rc == 6
        assert "gh query failed" in capsys.readouterr().err


class TestUsage:
    def test_no_mode_is_64(self, capsys):
        assert wait_cr.main([]) == 64
        assert "exactly one" in capsys.readouterr().err

    def test_both_modes_is_64(self, capsys):
        assert wait_cr.main(["code", "--pr", "o/r#7"]) == 64

    def test_remote_with_grace_is_64(self, capsys):
        assert wait_cr.main(["--pr", "o/r#7", "--grace", "5"]) == 64

    def test_remote_with_zima_home_is_64(self, tmp_path, capsys):
        assert wait_cr.main(["--pr", "o/r#7", "--zima-home", str(tmp_path)]) == 64

    def test_bad_pr_ref_is_64(self, capsys):
        assert wait_cr.main(["--pr", "o/r"]) == 64

    @pytest.mark.parametrize(
        "argv",
        [
            ["--pr", "o/r#7", "--poll", "0"],
            ["--pr", "o/r#7", "--poll", "-5"],
            ["--pr", "o/r#7", "--since-minutes", "-1"],
            ["--pr", "o/r#7", "--timeout", "0"],
        ],
    )
    def test_non_positive_numbers_are_64(self, argv, capsys):
        assert wait_cr.main(argv) == 64
        assert "must be positive" in capsys.readouterr().err

    def test_argparse_error_is_64(self):
        with pytest.raises(SystemExit) as excinfo:
            wait_cr.main(["--pr", "o/r#7", "--timeout", "abc"])
        assert excinfo.value.code == 64


SKILL_PATH = Path(__file__).resolve().parents[2] / "pi" / "zima-pr-monitor" / "SKILL.md"
CLAUDE_PATH = Path(__file__).resolve().parents[2] / "CLAUDE.md"


class TestSkillDocContract:
    def test_documents_both_wait_modes(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "wait-cr.py <pjob-code>" in text
        assert "--pr 'owner/repo#N'" in text

    def test_documents_remote_exit_codes(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        for code in ("| 3 |", "| 4 |", "| 5 |", "| 6 |"):
            assert code in text, code

    def test_keeps_foreground_blocking_rule(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "禁止结束 turn" in text
        assert "后台/异步监听" in text

    def test_marks_pjob_ps_local_only(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "本地模式专属" in text

    def test_mode_choice_is_a_heuristic(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        assert "启发式" in text

    def test_claude_md_mentions_both_channels(self):
        text = CLAUDE_PATH.read_text(encoding="utf-8")
        assert "history/pjobs" in text
        assert "reviews" in text
