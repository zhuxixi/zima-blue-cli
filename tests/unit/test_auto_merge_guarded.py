"""Unit tests for examples/auto-merge/auto-merge-guarded.py."""

from __future__ import annotations

import http.client
import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "auto-merge" / "auto-merge-guarded.py"
)


def _load_script():
    """Load the script as a module via importlib (file has a hyphen, not importable by name)."""
    spec = importlib.util.spec_from_file_location("auto_merge_guarded", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    # Python 3.13 dataclass processing reads sys.modules[cls.__module__]; the
    # module must be registered or dataclass() crashes with AttributeError.
    sys.modules["auto_merge_guarded"] = module
    spec.loader.exec_module(module)
    return module


amg = _load_script()


class TestLoadConfig:
    def test_load_config_parses_repos(self, tmp_path):
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text(
            """
enabled: true
pushover:
  config_file: "~/.config/claude-notify.json"
repos:
  zhuxixi/pi-agent-board:
    allow_authors: [ccccyk0919]
    required_checks: ["Test (Node 22)", "Test (Node 24)"]
    expected_failing_checks: ["Owner approval policy"]
    merge_method: squash
    delete_branch: true
    sensitive_paths: [".github/**", "*.pjob.*"]
    cr_pjob_code: pi-agent-board-pi-cr-job
""",
            encoding="utf-8",
        )
        cfg = amg.load_config(cfg_file)
        assert cfg.enabled is True
        assert cfg.pushover_config_file == "~/.config/claude-notify.json"
        repo = cfg.repos["zhuxixi/pi-agent-board"]
        assert repo.allow_authors == ["ccccyk0919"]
        assert repo.required_checks == ["Test (Node 22)", "Test (Node 24)"]
        assert repo.expected_failing_checks == ["Owner approval policy"]
        assert repo.merge_method == "squash"
        assert repo.delete_branch is True
        assert repo.sensitive_paths == [".github/**", "*.pjob.*"]
        assert repo.cr_pjob_code == "pi-agent-board-pi-cr-job"

    def test_quoted_booleans_coerce_to_false(self, tmp_path):
        # Quoted booleans are a common YAML habit; they must NOT be truthy
        # strings (enabled: "false" flipping the kill switch ON would be a
        # safety inversion).
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text(
            """
enabled: "false"
pushover:
  config_file: "~/.config/claude-notify.json"
repos:
  zhuxixi/pi-agent-board:
    allow_authors: [ccccyk0919]
    required_checks: ["Test (Node 22)"]
    expected_failing_checks: ["Owner approval policy"]
    merge_method: squash
    delete_branch: "false"
    sensitive_paths: [".github/**"]
    cr_pjob_code: pi-agent-board-pi-cr-job
""",
            encoding="utf-8",
        )
        cfg = amg.load_config(cfg_file)
        assert cfg.enabled is False
        assert cfg.repos["zhuxixi/pi-agent-board"].delete_branch is False

    def test_load_config_missing_file_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            amg.load_config(tmp_path / "nope.yaml")


class TestAuditLogger:
    def test_log_writes_jsonl_line(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = amg.AuditLogger(log_path)
        logger.log({"ts": "2026-08-30T00:00:00+00:00", "repo": "r", "pr": 1, "decision": "skip"})
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["decision"] == "skip"

    def test_log_appends_not_overwrites(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = amg.AuditLogger(log_path)
        logger.log({"n": 1})
        logger.log({"n": 2})
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2


class TestGateCandidate:
    def _pr(self, **overrides):
        pr = {
            "number": 1,
            "title": "t",
            "author": {"login": "ccccyk0919"},
            "state": "OPEN",
            "isDraft": False,
        }
        pr.update(overrides)
        return pr

    def test_open_whitelisted_non_draft_passes(self):
        result = amg.gate_candidate(self._pr(), ["ccccyk0919"])
        assert result.passed is True
        assert result.decision == "merge"

    def test_author_not_whitelisted_skips(self):
        result = amg.gate_candidate(self._pr(author={"login": "stranger"}), ["ccccyk0919"])
        assert result.passed is False
        assert result.decision == "skip"
        assert "whitelist" in result.reason

    def test_draft_skips(self):
        result = amg.gate_candidate(self._pr(isDraft=True), ["ccccyk0919"])
        assert result.passed is False
        assert result.decision == "skip"

    def test_closed_state_skips(self):
        result = amg.gate_candidate(self._pr(state="CLOSED"), ["ccccyk0919"])
        assert result.passed is False
        assert result.decision == "skip"


class TestGateSensitivePaths:
    def test_no_match_passes(self):
        result = amg.gate_sensitive_paths(["src/main.ts", "README.md"], [".github/**"])
        assert result.passed is True

    def test_workflow_file_blocks(self):
        result = amg.gate_sensitive_paths(
            ["src/main.ts", ".github/workflows/ci.yml"], [".github/**"]
        )
        assert result.passed is False
        assert result.decision == "attention"
        assert ".github/workflows/ci.yml" in result.reason

    def test_glob_pattern_matches(self):
        result = amg.gate_sensitive_paths(["foo.pjob.bar"], ["*.pjob.*"])
        assert result.passed is False
        assert result.decision == "attention"

    def test_empty_sensitive_paths_passes(self):
        result = amg.gate_sensitive_paths(["anything.ts"], [])
        assert result.passed is True


class TestGateRequiredChecks:
    def _runs(self, *pairs):
        # pairs of (name, conclusion); later entries are newer (API returns newest first)
        return [{"name": n, "conclusion": c, "status": "completed"} for n, c in pairs]

    def test_all_required_success_passes(self):
        runs = self._runs(("Test (Node 22)", "success"), ("Test (Node 24)", "success"))
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is True

    def test_required_failure_waits(self):
        runs = self._runs(("Test (Node 22)", "failure"), ("Test (Node 24)", "success"))
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is False
        assert result.decision == "waiting"
        assert "Test (Node 22)" in result.reason

    def test_expected_failing_check_ignored(self):
        runs = self._runs(
            ("Test (Node 22)", "success"),
            ("Test (Node 24)", "success"),
            ("Owner approval policy", "failure"),
        )
        result = amg.gate_required_checks(
            runs, ["Test (Node 22)", "Test (Node 24)"], ["Owner approval policy"]
        )
        assert result.passed is True

    def test_in_progress_required_check_waits(self):
        runs = [
            {"name": "Test (Node 22)", "conclusion": None, "status": "in_progress"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_missing_required_check_waits(self):
        runs = self._runs(("Test (Node 24)", "success"))
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_newest_run_wins_for_same_name(self):
        # API returns newest first; a newer success overrides an older failure
        runs = self._runs(
            ("Test (Node 22)", "success"),
            ("Test (Node 22)", "failure"),
            ("Test (Node 24)", "success"),
        )
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is True


class TestGateMergeable:
    def test_mergeable_passes(self):
        result = amg.gate_mergeable("MERGEABLE")
        assert result.passed is True

    def test_conflicting_attention(self):
        result = amg.gate_mergeable("CONFLICTING")
        assert result.passed is False
        assert result.decision == "attention"

    def test_unknown_waits(self):
        result = amg.gate_mergeable("UNKNOWN")
        assert result.passed is False
        assert result.decision == "waiting"


class TestParseCrMeta:
    def test_extracts_json_from_html_comment(self):
        body = 'review text\n<!-- pi-cr-meta {"round": 1, "blocking_new_count": 0} -->\nmore text'
        meta = amg.parse_cr_meta(body)
        assert meta == {"round": 1, "blocking_new_count": 0}

    def test_returns_none_without_meta(self):
        assert amg.parse_cr_meta("plain review, no meta") is None

    def test_returns_none_on_broken_json(self):
        assert amg.parse_cr_meta("<!-- pi-cr-meta {not json -->") is None


class TestEffectiveBlocking:
    def test_boolean_blocking_used_directly(self):
        assert amg.effective_blocking({"blocking": True}) is True
        assert amg.effective_blocking({"blocking": False}) is False

    def test_legacy_severity_fallback(self):
        assert amg.effective_blocking({"severity": "low"}) is False
        assert amg.effective_blocking({"severity": "medium"}) is True
        assert amg.effective_blocking({"severity": "high"}) is True
        assert amg.effective_blocking({"severity": "critical"}) is True

    def test_missing_severity_defaults_to_blocking(self):
        assert amg.effective_blocking({}) is True


class TestReviewClean:
    def test_clean_meta(self):
        meta = {"blocking_new_count": 0, "issues": []}
        ok, reason = amg.review_clean(meta)
        assert ok is True

    def test_blocking_new_count_blocks(self):
        meta = {"blocking_new_count": 1, "issues": []}
        ok, reason = amg.review_clean(meta)
        assert ok is False
        assert "blocking_new_count" in reason

    def test_open_blocking_finding_blocks(self):
        meta = {
            "blocking_new_count": 0,
            "issues": [{"status": "open", "blocking": True}],
        }
        ok, reason = amg.review_clean(meta)
        assert ok is False

    def test_acknowledged_or_resolved_findings_do_not_block(self):
        meta = {
            "blocking_new_count": 0,
            "issues": [
                {"status": "acknowledged", "blocking": True},
                {"status": "resolved", "blocking": True},
            ],
        }
        ok, reason = amg.review_clean(meta)
        assert ok is True

    def test_open_advisory_finding_does_not_block(self):
        meta = {
            "blocking_new_count": 0,
            "issues": [{"status": "open", "blocking": False}],
        }
        ok, reason = amg.review_clean(meta)
        assert ok is True


class TestGateCrConvergence:
    def _exec(self, status, pid=None):
        return {"status": status, "pid": pid}

    def _review(self, head_sha, body):
        return {"commit": {"oid": head_sha}, "body": body}

    def test_all_three_conditions_pass(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->')
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True

    def test_running_execution_waits(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("running", 123)]
        result = amg.gate_cr_convergence(executions, [], "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_running_with_dead_pid_counts_as_terminated(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: False)
        executions = [self._exec("running", 123)]
        reviews = [
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->')
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True

    def test_needs_review_label_still_present_waits(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->')
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", ["zima:needs-review"])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_no_review_for_head_waits(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        result = amg.gate_cr_convergence(executions, [], "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_second_stream_with_blocking_finding_blocks(self, monkeypatch):
        # Multi-stream trap (jfox #402): ALL reviews for this head must be clean.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->'),
            self._review(
                "abc",
                '<!-- pi-cr-meta {"blocking_new_count": 0, '
                '"issues": [{"status": "open", "blocking": true}]} -->',
            ),
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_review_for_other_head_ignored(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("oldsha", '<!-- pi-cr-meta {"blocking_new_count": 5, "issues": []} -->'),
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->'),
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True


class TestGateHeadStable:
    def test_same_head_passes(self):
        result = amg.gate_head_stable("abc", "abc")
        assert result.passed is True

    def test_drifted_head_aborts(self):
        result = amg.gate_head_stable("abc", "def")
        assert result.passed is False
        assert result.decision == "waiting"
        assert "drift" in result.reason


class TestRunGates:
    def _repo_cfg(self):
        return amg.RepoConfig(
            allow_authors=["ccccyk0919"],
            required_checks=["Test (Node 22)", "Test (Node 24)"],
            expected_failing_checks=["Owner approval policy"],
            merge_method="squash",
            delete_branch=True,
            sensitive_paths=[".github/**"],
            cr_pjob_code="pi-agent-board-pi-cr-job",
        )

    def _pr(self, **overrides):
        pr = {
            "number": 1,
            "title": "t",
            "author": {"login": "ccccyk0919"},
            "state": "OPEN",
            "isDraft": False,
            "headRefOid": "abc",
            "mergeable": "MERGEABLE",
            "labels": [],
            "files": [{"path": "src/main.ts"}],
            "reviews": [],
        }
        pr.update(overrides)
        return pr

    def _check_runs(self):
        return [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]

    def test_all_gates_pass(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        pr = self._pr(
            reviews=[
                {
                    "commit": {"oid": "abc"},
                    "body": '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->',
                }
            ]
        )
        executions = [{"status": "success", "pid": 123}]
        result = amg.run_gates(pr, self._check_runs(), executions, self._repo_cfg())
        assert result.passed is True
        assert result.decision == "merge"

    def test_gate_order_stops_at_first_failure(self, monkeypatch):
        # Non-whitelisted author: gate 1 fails, later gates never consulted.
        pr = self._pr(author={"login": "stranger"})
        result = amg.run_gates(pr, [], [], self._repo_cfg())
        assert result.passed is False
        assert result.decision == "skip"
        assert "whitelist" in result.reason

    def test_sensitive_path_attention(self, monkeypatch):
        pr = self._pr(files=[{"path": ".github/workflows/ci.yml"}])
        result = amg.run_gates(pr, self._check_runs(), [], self._repo_cfg())
        assert result.passed is False
        assert result.decision == "attention"


class TestActions:
    def test_remove_label_builds_command(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.remove_label("r/repo", 5, "zima:needs-fix", dry=False)
        assert calls == [
            ["pr", "edit", "5", "--repo", "r/repo", "--remove-label", "zima:needs-fix"]
        ]

    def test_remove_label_dry_skips_gh(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.remove_label("r/repo", 5, "zima:needs-fix", dry=True)
        assert calls == []

    def test_approve_binds_head_sha(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.approve("r/repo", 5, "abc123", dry=False)
        assert calls == [
            [
                "pr",
                "review",
                "5",
                "--repo",
                "r/repo",
                "--approve",
                "--body",
                "auto-merge: CR converged + CI green",
                "--commit-id",
                "abc123",
            ]
        ]

    def test_merge_pr_squash_delete_branch(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.merge_pr("r/repo", 5, "squash", True, dry=False)
        assert calls == [["pr", "merge", "5", "--repo", "r/repo", "--squash", "--delete-branch"]]

    def test_merge_pr_merge_method_no_delete(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.merge_pr("r/repo", 5, "merge", False, dry=False)
        assert calls == [["pr", "merge", "5", "--repo", "r/repo", "--merge"]]

    def test_rerun_failed_jobs_no_failed_runs(self, monkeypatch):
        monkeypatch.setattr(
            amg,
            "gh_json",
            lambda args: [
                {"databaseId": 1, "name": "Owner approval policy", "conclusion": "success"}
            ],
        )
        rerun_calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: rerun_calls.append(args))
        amg.rerun_failed_jobs("r/repo", "abc", "Owner approval policy", dry=False)
        assert rerun_calls == []

    def test_rerun_failed_jobs_reruns_and_waits(self, monkeypatch):
        run_list = [
            {"databaseId": 1, "name": "Owner approval policy", "conclusion": "failure"},
            {"databaseId": 2, "name": "Test (Node 22)", "conclusion": "success"},
        ]
        monkeypatch.setattr(amg, "gh_json", lambda args: run_list)
        rerun_calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: rerun_calls.append(args))
        # gh run view returns completed immediately so the poll loop exits
        monkeypatch.setattr(
            amg,
            "gh_json_view",
            lambda args: {"status": "completed", "conclusion": "success"},
        )
        amg.rerun_failed_jobs("r/repo", "abc", "Owner approval policy", dry=False)
        assert rerun_calls == [["run", "rerun", "1", "--failed"]]

    def test_rerun_failed_jobs_dry_skips(self, monkeypatch):
        run_list = [{"databaseId": 1, "name": "Owner approval policy", "conclusion": "failure"}]
        monkeypatch.setattr(amg, "gh_json", lambda args: run_list)
        rerun_calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: rerun_calls.append(args))
        amg.rerun_failed_jobs("r/repo", "abc", "Owner approval policy", dry=True)
        assert rerun_calls == []


class TestTruncateChars:
    def test_short_text_unchanged(self):
        assert amg.truncate_chars("hello", 250) == "hello"

    def test_chinese_truncated_by_characters_not_bytes(self):
        text = "中" * 300  # 900 bytes, 300 chars
        result = amg.truncate_chars(text, 250)
        assert len(result) == 250
        assert result.endswith("中")  # no broken UTF-8 sequence


class TestLoadPushoverKeys:
    def test_reads_keys(self, tmp_path):
        cfg = tmp_path / "notify.json"
        cfg.write_text('{"PUSHOVER_API_KEY": "k", "PUSHOVER_USER_KEY": "u"}', encoding="utf-8")
        assert amg.load_pushover_keys(str(cfg)) == ("k", "u")

    def test_missing_file_returns_none(self, tmp_path):
        assert amg.load_pushover_keys(str(tmp_path / "nope.json")) is None

    def test_missing_keys_returns_none(self, tmp_path):
        cfg = tmp_path / "notify.json"
        cfg.write_text('{"BUSY_TIME": "x"}', encoding="utf-8")
        assert amg.load_pushover_keys(str(cfg)) is None

    def test_non_object_json_returns_none(self, tmp_path):
        # Valid JSON that is not an object (e.g. a list) must not raise
        # AttributeError on .get; it degrades to None.
        cfg = tmp_path / "notify.json"
        cfg.write_text("[]", encoding="utf-8")
        assert amg.load_pushover_keys(str(cfg)) is None

    def test_non_utf8_file_returns_none(self, tmp_path):
        # Non-UTF-8 bytes raise UnicodeDecodeError (a ValueError subclass not
        # covered by json.JSONDecodeError); must degrade to None.
        cfg = tmp_path / "notify.json"
        cfg.write_bytes(b"\xff\xfe\x00")
        assert amg.load_pushover_keys(str(cfg)) is None


class TestSendPushover:
    def test_posts_and_returns_true(self, monkeypatch):
        posted = []

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            posted.append(req)
            return FakeResponse()

        # Key loading is covered by TestLoadPushoverKeys; mock it here so the
        # POST path (the behavior under test) is actually exercised.
        monkeypatch.setattr(amg, "load_pushover_keys", lambda config_file: ("k", "u"))
        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        ok = amg.send_pushover("action", "[auto-merge] merged", "body", "unused")
        assert ok is True
        assert len(posted) == 1
        # Pushover's API accepts form-urlencoded POST bodies (not JSON); the
        # payload fields must be present and URL-encoded correctly.
        payload = urllib.parse.parse_qs(posted[0].data.decode("utf-8"))
        assert payload["token"] == ["k"]
        assert payload["user"] == ["u"]
        assert payload["title"] == ["[auto-merge] merged"]
        assert payload["message"] == ["body"]

    def test_attention_level_sets_priority(self, monkeypatch):
        posted = []

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            posted.append(req)
            return FakeResponse()

        monkeypatch.setattr(amg, "load_pushover_keys", lambda config_file: ("k", "u"))
        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        amg.send_pushover("attention", "t", "m", "unused")
        payload = urllib.parse.parse_qs(posted[0].data.decode("utf-8"))
        assert payload["priority"] == ["1"]

    def test_http_error_returns_false(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise amg.urllib.error.URLError("boom")

        monkeypatch.setattr(amg, "load_pushover_keys", lambda config_file: ("k", "u"))
        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        assert amg.send_pushover("action", "t", "m", "unused") is False

    def test_http_exception_returns_false(self, monkeypatch):
        # BadStatusLine is an http.client.HTTPException, neither URLError nor
        # OSError; the notification path must still fail closed to False.
        def fake_urlopen(req, timeout=None):
            raise http.client.BadStatusLine("boom")

        monkeypatch.setattr(amg, "load_pushover_keys", lambda config_file: ("k", "u"))
        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        assert amg.send_pushover("action", "t", "m", "unused") is False

    def test_unknown_level_priority_zero(self, monkeypatch):
        posted = []

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None):
            posted.append(req)
            return FakeResponse()

        monkeypatch.setattr(amg, "load_pushover_keys", lambda config_file: ("k", "u"))
        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        ok = amg.send_pushover("unknown", "t", "m", "unused")
        assert ok is True
        payload = urllib.parse.parse_qs(posted[0].data.decode("utf-8"))
        assert payload["priority"] == ["0"]
