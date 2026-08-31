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

    def test_quoted_bool_with_inner_whitespace_coerces_false(self, tmp_path):
        # `enabled: " false "` (quoted + inner whitespace) must still parse as
        # boolean False, not a truthy string that flips the kill switch ON.
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text('enabled: " false "\n', encoding="utf-8")
        cfg = amg.load_config(cfg_file)
        assert cfg.enabled is False

    def test_yaml_11_booleans_coerce(self, tmp_path):
        # YAML 1.1 boolean spellings (yes/no/on/off) must coerce, not parse as
        # truthy strings — enabled: no silently keeping the kill switch ON is a
        # safety inversion.
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text(
            "enabled: no\n" "repos:\n" "  r/repo:\n" "    delete_branch: off\n",
            encoding="utf-8",
        )
        cfg = amg.load_config(cfg_file)
        assert cfg.enabled is False
        assert cfg.repos["r/repo"].delete_branch is False

        cfg_file.write_text("enabled: yes\n", encoding="utf-8")
        cfg = amg.load_config(cfg_file)
        assert cfg.enabled is True

    def test_load_config_missing_file_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            amg.load_config(tmp_path / "nope.yaml")

    def test_example_template_parses_correctly(self):
        """The shipped template must parse to the documented defaults."""
        template_path = (
            Path(__file__).resolve().parents[2]
            / "examples"
            / "auto-merge"
            / "auto-merge.yaml.example"
        )
        cfg = amg.load_config(template_path)
        assert cfg.enabled is True
        assert cfg.pushover_config_file == "~/.config/claude-notify.json"
        repo = cfg.repos["OWNER/REPO"]
        assert repo.allow_authors == ["collaborator-login"]
        assert repo.required_checks == ["Test (Node 22)", "Test (Node 24)"]
        assert repo.expected_failing_checks == ["Owner approval policy"]
        assert repo.merge_method == "squash"
        assert repo.delete_branch is True
        assert repo.sensitive_paths == [".github/**", "*.pjob.*", "**/branch-protection*"]
        assert repo.cr_pjob_code == "<repo>-pi-cr-job"

    def test_inline_comments_stripped(self, tmp_path):
        """Inline comments after a value must not corrupt the parsed config."""
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text(
            """
repos:
  r/repo:
    allow_authors: [ccccyk0919]  # trusted colleague
    merge_method: squash  # squash | merge
""",
            encoding="utf-8",
        )
        cfg = amg.load_config(cfg_file)
        repo = cfg.repos["r/repo"]
        assert repo.allow_authors == ["ccccyk0919"]
        assert repo.merge_method == "squash"

    def test_block_style_lists_parse(self, tmp_path):
        # Block-style lists (`- item`) must not be silently dropped (fail-open).
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text(
            """
repos:
  r/repo:
    allow_authors:
      - ccccyk0919
      - someone-else
    required_checks:
      - "Test (Node 22)"
      - "Test (Node 24)"
    sensitive_paths:
      - ".github/**"
      - "**/branch-protection*"
""",
            encoding="utf-8",
        )
        repo = amg.load_config(cfg_file).repos["r/repo"]
        assert repo.allow_authors == ["ccccyk0919", "someone-else"]
        assert repo.required_checks == ["Test (Node 22)", "Test (Node 24)"]
        assert repo.sensitive_paths == [".github/**", "**/branch-protection*"]

    def test_unsupported_merge_method_raises(self, tmp_path):
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text("repos:\n  r/repo:\n    merge_method: rebase\n", encoding="utf-8")
        import pytest

        with pytest.raises(ValueError, match="unsupported merge method"):
            amg.load_config(cfg_file)


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

    def test_author_none_skips(self):
        result = amg.gate_candidate(self._pr(author=None), ["ccccyk0919"])
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

    def test_double_star_matches_root_file(self):
        # fnmatch's `**/` does not match root-level files; gate 2 must also
        # test the pattern without the `**/` prefix.
        result = amg.gate_sensitive_paths(["branch-protection.json"], ["**/branch-protection*"])
        assert result.passed is False
        assert result.decision == "attention"


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

    def test_running_with_none_pid_waits(self, monkeypatch):
        # Spawn-race window: a running entry with pid=None must be treated as
        # still running (fail-closed), not terminated.  Reviews are clean so a
        # fail-open implementation would wrongly return "merge".
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("running", None)]
        reviews = [
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->')
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_review_without_meta_blocks(self, monkeypatch):
        # Fail-closed user ruling: any head review without pi-cr-meta (e.g. a
        # human review) blocks merge.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [self._review("abc", "plain human review, no meta")]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_self_approve_review_is_skipped(self, monkeypatch):
        # This script's own approve marker has no pi-cr-meta; it must not
        # deadlock the next round when one clean meta review is also present.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("abc", "auto-merge: CR converged + CI green"),
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->'),
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True

    def test_non_meta_human_review_still_blocks(self, monkeypatch):
        # A non-meta review without the auto-merge: prefix still blocks.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [self._review("abc", "LGTM")]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_meta_from_other_author_ignored(self, monkeypatch):
        # Forgery guard: pi-cr-meta from a non-expected author is ignored.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            {
                "commit": {"oid": "abc"},
                "author": {"login": "attacker"},
                "body": '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->',
            }
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [], expected_author="owner")
        assert result.passed is False
        assert result.decision == "waiting"
        assert "no CR review" in result.reason

    def test_meta_from_owner_evaluated(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            {
                "commit": {"oid": "abc"},
                "author": {"login": "owner"},
                "body": '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->',
            }
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [], expected_author="owner")
        assert result.passed is True

    def test_none_executions_waits(self, monkeypatch):
        # Missing history dir must fail closed, not vacuous.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        reviews = [
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->')
        ]
        result = amg.gate_cr_convergence(None, reviews, "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_stale_running_entry_counts_terminated(self, monkeypatch):
        # A running entry started > 90 min ago is provably stale.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        stale_started = (
            amg.datetime.now(amg.timezone.utc) - amg.timedelta(minutes=120)
        ).isoformat()
        executions = [{"status": "running", "pid": 123, "started_at": stale_started}]
        reviews = [
            self._review("abc", '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->')
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True

    def test_fresh_running_entry_waits(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        fresh_started = (amg.datetime.now(amg.timezone.utc) - amg.timedelta(minutes=10)).isoformat()
        executions = [{"status": "running", "pid": 123, "started_at": fresh_started}]
        result = amg.gate_cr_convergence(executions, [], "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"


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
        monkeypatch.setattr(amg, "gh_run", lambda args: calls.append(args))
        amg.remove_label("r/repo", 5, "zima:needs-fix", dry=False)
        assert calls == [
            ["pr", "edit", "5", "--repo", "r/repo", "--remove-label", "zima:needs-fix"]
        ]

    def test_remove_label_dry_skips_gh(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: calls.append(args))
        amg.remove_label("r/repo", 5, "zima:needs-fix", dry=True)
        assert calls == []

    def test_approve_builds_command(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: calls.append(args))
        amg.approve("r/repo", 5, dry=False)
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
            ]
        ]

    def test_merge_pr_squash_delete_branch(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: calls.append(args))
        amg.merge_pr("r/repo", 5, "squash", True, dry=False)
        assert calls == [["pr", "merge", "5", "--repo", "r/repo", "--squash", "--delete-branch"]]

    def test_merge_pr_merge_method_no_delete(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: calls.append(args))
        amg.merge_pr("r/repo", 5, "merge", False, dry=False)
        assert calls == [["pr", "merge", "5", "--repo", "r/repo", "--merge"]]

    def test_merge_pr_unknown_method_raises(self):
        import pytest

        with pytest.raises(ValueError, match="unsupported merge method"):
            amg.merge_pr("r/repo", 5, "rebase", True, dry=False)

    def test_merge_pr_appends_match_head_commit(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: calls.append(args))
        amg.merge_pr("r/repo", 5, "squash", True, dry=False, head_sha="abc123")
        assert calls == [
            [
                "pr",
                "merge",
                "5",
                "--repo",
                "r/repo",
                "--squash",
                "--delete-branch",
                "--match-head-commit",
                "abc123",
            ]
        ]

    def test_gh_json_timeout_raises_runtime_error(self, monkeypatch):
        import subprocess

        def fake_run(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=120)

        monkeypatch.setattr(amg.subprocess, "run", fake_run)
        import pytest

        with pytest.raises(RuntimeError, match="timed out"):
            amg.gh_json(["api", "user"])

    def test_check_runs_uses_per_page_not_paginate(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {"check_runs": []})
        amg.GhClient().check_runs("r/repo", "abc")
        assert calls == [["api", "repos/r/repo/commits/abc/check-runs", "-f", "per_page=100"]]

    def test_list_prs_uses_limit(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or [])
        amg.GhClient().list_prs("r/repo")
        assert "--limit" in calls[0]
        assert "200" in calls[0]

    def test_fetch_files_builds_paginated_api_call(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or [])
        amg.GhClient().fetch_files("r/repo", 5)
        assert calls == [["api", "repos/r/repo/pulls/5/files", "--paginate"]]

    def test_fetch_files_maps_filename_to_path(self, monkeypatch):
        # The REST pulls/{n}/files response keys files by `filename`, not `path`;
        # gate 2 reads `path`, so the mapping here is what keeps the
        # sensitive-path guard from silently failing open.
        api_shaped = [
            {"filename": ".github/workflows/ci.yml", "status": "modified", "additions": 3},
            {"filename": "src/main.ts", "status": "added", "additions": 10},
        ]
        monkeypatch.setattr(amg, "gh_json", lambda args: api_shaped)
        mapped = amg.GhClient().fetch_files("r/repo", 5)
        assert mapped == [
            {"path": ".github/workflows/ci.yml"},
            {"path": "src/main.ts"},
        ]
        # The mapped shape feeds gate 2 via run_gates' path extraction
        # (run_gates does `f.get("path", "")` then calls gate_sensitive_paths).
        paths = [f.get("path", "") for f in mapped]
        result = amg.gate_sensitive_paths(paths, [".github/**"])
        assert result.decision == "attention"

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
        monkeypatch.setattr(amg.time, "sleep", lambda s: None)  # avoid the 10s poll latency
        rerun_calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: rerun_calls.append(args))
        # gh run view returns completed immediately so the poll loop exits
        monkeypatch.setattr(
            amg,
            "gh_json_view",
            lambda args: {"status": "completed", "conclusion": "success"},
        )
        amg.rerun_failed_jobs("r/repo", "abc", "Owner approval policy", dry=False)
        assert rerun_calls == [["run", "rerun", "1", "--failed", "--repo", "r/repo"]]

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


class TestLoadExecutions:
    def test_reads_state_files(self, tmp_path):
        state_dir = tmp_path / "history" / "pjobs" / "pi-agent-board-pi-cr-job"
        state_dir.mkdir(parents=True)
        (state_dir / "a1.json").write_text(
            json.dumps({"execution_id": "a1", "status": "success"}), encoding="utf-8"
        )
        (state_dir / "b2.json").write_text(
            json.dumps({"execution_id": "b2", "status": "running"}), encoding="utf-8"
        )
        (state_dir / "not-json.txt").write_text("junk", encoding="utf-8")
        executions = amg.load_executions(tmp_path, "pi-agent-board-pi-cr-job")
        assert len(executions) == 2

    def test_missing_dir_returns_none(self, tmp_path):
        # Missing dir must fail closed (None), distinct from an empty dir ([]).
        assert amg.load_executions(tmp_path, "nope") is None


class TestExecutionsForPr:
    def test_filters_by_repo_and_pr(self):
        executions = [
            {"scan_pr_result": {"repo": "r/repo", "pr_number": "5"}},
            {"scan_pr_result": {"repo": "r/repo", "pr_number": "6"}},
            {"scan_pr_result": {"repo": "other/repo", "pr_number": "5"}},
            {},
        ]
        result = amg.executions_for_pr(executions, "r/repo", 5)
        assert len(result) == 1
        assert result[0]["scan_pr_result"]["pr_number"] == "5"

    def test_none_executions_returns_none(self):
        assert amg.executions_for_pr(None, "r/repo", 5) is None

    def test_repo_match_is_case_insensitive(self):
        executions = [
            {"scan_pr_result": {"repo": "Zhuxixi/Repo", "pr_number": "5"}},
        ]
        result = amg.executions_for_pr(executions, "zhuxixi/repo", 5)
        assert len(result) == 1


class TestProcessRepo:
    def _make_fake_gh(self, prs, check_runs):
        class FakeGh:
            def __init__(self):
                self.calls = []

            def list_prs(self, repo):
                self.calls.append(("list_prs", repo))
                return prs

            def check_runs(self, repo, sha):
                self.calls.append(("check_runs", repo, sha))
                return check_runs

            def view_pr(self, repo, number):
                self.calls.append(("view_pr", repo, number))
                return prs[0]

            def fetch_files(self, repo, number):
                self.calls.append(("fetch_files", repo, number))
                return prs[0].get("files", [])

        return FakeGh()

    def _make_fake_notify(self):
        class FakeNotify:
            def __init__(self):
                self.sent = []

            def send(self, level, title, message):
                self.sent.append((level, title, message))
                return True

        return FakeNotify()

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

    def _empty_state_dir(self, tmp_path):
        """Create (and return) an empty CR state dir so load_executions -> [].

        A missing dir now fails closed (None -> waiting); the action-chain
        tests need an empty-but-present dir to pass gate 5a.
        """
        d = tmp_path / "history" / "pjobs" / "pi-agent-board-pi-cr-job"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _pr(self, **overrides):
        pr = {
            "number": 1,
            "title": "t",
            "author": {"login": "ccccyk0919"},
            "state": "OPEN",
            "isDraft": False,
            "headRefOid": "abc",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "reviewDecision": None,
            "labels": [],
            "files": [{"path": "src/main.ts"}],
            "reviews": [
                {
                    "commit": {"oid": "abc"},
                    "body": '<!-- pi-cr-meta {"blocking_new_count": 0, "issues": []} -->',
                }
            ],
        }
        pr.update(overrides)
        return pr

    def test_merged_pr_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # owner fetch probe
        pr = self._pr(state="MERGED")
        gh = self._make_fake_gh([pr], [])
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "dry-run", gh, tmp_path, audit, notify)
        assert notify.sent == []
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["decision"] == "skip"

    def test_dry_run_prints_actions_without_executing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # rerun probe: no failed runs
        self._empty_state_dir(tmp_path)
        action_calls = []
        monkeypatch.setattr(amg, "approve", lambda *a, **k: action_calls.append("approve"))
        monkeypatch.setattr(amg, "merge_pr", lambda *a, **k: action_calls.append("merge_pr"))
        monkeypatch.setattr(
            amg, "remove_label", lambda *a, **k: action_calls.append("remove_label")
        )
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]
        pr = self._pr()
        gh = self._make_fake_gh([pr], green_runs)
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "dry-run", gh, tmp_path, audit, notify)
        out = capsys.readouterr().out
        assert "would approve" in out
        assert "would merge" in out
        # dry-run never executes actions and never notifies
        assert action_calls == []
        assert notify.sent == []

    def test_notify_only_sends_attention_for_sensitive_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # owner fetch probe
        pr = self._pr(files=[{"path": ".github/workflows/ci.yml"}])
        gh = self._make_fake_gh([pr], [])
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo(
            "r/repo", self._repo_cfg(), cfg, "notify-only", gh, tmp_path, audit, notify
        )
        assert len(notify.sent) == 1
        assert notify.sent[0][0] == "attention"

    def test_waiting_decision_is_silent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # owner fetch probe
        pr = self._pr(mergeable="UNKNOWN")
        gh = self._make_fake_gh([pr], [])
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo(
            "r/repo", self._repo_cfg(), cfg, "notify-only", gh, tmp_path, audit, notify
        )
        assert notify.sent == []

    def test_notify_only_sends_would_merge_not_merged(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # rerun probe: no failed runs
        self._empty_state_dir(tmp_path)
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]
        pr = self._pr()
        gh = self._make_fake_gh([pr], green_runs)
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo(
            "r/repo", self._repo_cfg(), cfg, "notify-only", gh, tmp_path, audit, notify
        )
        assert len(notify.sent) == 1
        assert notify.sent[0][0] == "action"
        assert notify.sent[0][1] == "[auto-merge] would merge"
        assert not any(title == "[auto-merge] merged" for _, title, _ in notify.sent)

    def test_notify_only_rehearses_through_unclean_merge_state(self, tmp_path, monkeypatch, capsys):
        """Dry modes must fall through the mergeStateStatus check and report
        would-merge instead of sending a false error notification."""
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # rerun probe: no failed runs
        self._empty_state_dir(tmp_path)
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]

        class TwoViewGh:
            """First view_pr returns the clean fixture; the second returns BLOCKED."""

            def __init__(self, first_pr, second_pr, check_runs):
                self.first_pr = first_pr
                self.second_pr = second_pr
                self.check_runs_result = check_runs
                self.view_calls = 0

            def list_prs(self, repo):
                return [self.first_pr]

            def check_runs(self, repo, sha):
                return self.check_runs_result

            def view_pr(self, repo, number):
                self.view_calls += 1
                return self.first_pr if self.view_calls == 1 else self.second_pr

            def fetch_files(self, repo, number):
                return self.first_pr.get("files", [])

        pr = self._pr()
        gh = TwoViewGh(pr, self._pr(mergeStateStatus="BLOCKED"), green_runs)
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo(
            "r/repo", self._repo_cfg(), cfg, "notify-only", gh, tmp_path, audit, notify
        )
        assert len(notify.sent) == 1
        assert notify.sent[0][1] == "[auto-merge] would merge"
        assert "live aborts unless CLEAN" in notify.sent[0][2]
        assert not any(title == "[auto-merge] error" for _, title, _ in notify.sent)
        out = capsys.readouterr().out
        assert "would merge (currently BLOCKED; live aborts unless CLEAN)" in out

    def test_live_mode_audits_merge_outcome(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # rerun probe: no failed runs
        self._empty_state_dir(tmp_path)
        monkeypatch.setattr(amg, "approve", lambda *a, **k: None)
        monkeypatch.setattr(amg, "merge_pr", lambda *a, **k: None)
        monkeypatch.setattr(amg, "remove_label", lambda *a, **k: None)
        monkeypatch.setattr(amg, "rerun_failed_jobs", lambda *a, **k: None)
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]
        pr = self._pr()
        gh = self._make_fake_gh([pr], green_runs)
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "live", gh, tmp_path, audit, notify)
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
        assert json.loads(lines[-1])["decision"] == "merged"

    def test_drift_after_approval_aborts(self, tmp_path, monkeypatch):
        # A collaborator push after an approve (or an already-APPROVED PR whose
        # head moved) must abort — the drift check runs BEFORE the APPROVED
        # branch, not only in the un-approved path.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])
        self._empty_state_dir(tmp_path)
        merged = []
        monkeypatch.setattr(amg, "merge_pr", lambda *a, **k: merged.append("merge"))
        monkeypatch.setattr(amg, "approve", lambda *a, **k: None)
        monkeypatch.setattr(amg, "remove_label", lambda *a, **k: None)
        monkeypatch.setattr(amg, "rerun_failed_jobs", lambda *a, **k: None)
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]

        round_pr = self._pr()  # headRefOid "abc"
        approved_drifted_pr = self._pr(reviewDecision="APPROVED", headRefOid="def")

        class DriftGh:
            def list_prs(self, repo):
                return [round_pr]

            def check_runs(self, repo, sha):
                return green_runs

            def fetch_files(self, repo, number):
                return round_pr.get("files", [])

            def view_pr(self, repo, number):
                return approved_drifted_pr

        gh = DriftGh()
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "live", gh, tmp_path, audit, notify)
        assert merged == []
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
        last = json.loads(lines[-1])
        assert last["decision"] == "waiting"
        assert "drift" in last["reason"]

    def test_drift_before_merge_aborts(self, tmp_path, monkeypatch):
        # The pre-merge re-check (third view_pr) must abort on a head that moved
        # during the rerun poll window.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])
        self._empty_state_dir(tmp_path)
        merged = []
        monkeypatch.setattr(amg, "merge_pr", lambda *a, **k: merged.append("merge"))
        monkeypatch.setattr(amg, "approve", lambda *a, **k: None)
        monkeypatch.setattr(amg, "remove_label", lambda *a, **k: None)
        monkeypatch.setattr(amg, "rerun_failed_jobs", lambda *a, **k: None)
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]

        round_pr = self._pr()  # headRefOid "abc"
        drifted_pr = self._pr(headRefOid="def")

        class DriftGh:
            def __init__(self):
                self.view_calls = 0

            def list_prs(self, repo):
                return [round_pr]

            def check_runs(self, repo, sha):
                return green_runs

            def fetch_files(self, repo, number):
                return round_pr.get("files", [])

            def view_pr(self, repo, number):
                self.view_calls += 1
                return drifted_pr if self.view_calls >= 3 else round_pr

        gh = DriftGh()
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "live", gh, tmp_path, audit, notify)
        assert merged == []
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
        last = json.loads(lines[-1])
        assert last["decision"] == "waiting"
        assert "drift" in last["reason"]

    def test_needs_review_label_blocks_merge(self, tmp_path, monkeypatch):
        # If needs-review was re-added on the same head (spawning a new CR
        # stream), the pre-merge re-check must abort.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])
        self._empty_state_dir(tmp_path)
        merged = []
        monkeypatch.setattr(amg, "merge_pr", lambda *a, **k: merged.append("merge"))
        monkeypatch.setattr(amg, "approve", lambda *a, **k: None)
        monkeypatch.setattr(amg, "remove_label", lambda *a, **k: None)
        monkeypatch.setattr(amg, "rerun_failed_jobs", lambda *a, **k: None)
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]

        round_pr = self._pr()
        re_added_pr = self._pr(labels=[{"name": "zima:needs-review"}])

        class LabelGh:
            def __init__(self):
                self.view_calls = 0

            def list_prs(self, repo):
                return [round_pr]

            def check_runs(self, repo, sha):
                return green_runs

            def fetch_files(self, repo, number):
                return round_pr.get("files", [])

            def view_pr(self, repo, number):
                self.view_calls += 1
                return re_added_pr if self.view_calls >= 3 else round_pr

        gh = LabelGh()
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "live", gh, tmp_path, audit, notify)
        assert merged == []
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
        last = json.loads(lines[-1])
        assert last["decision"] == "waiting"
        assert "label re-added" in last["reason"]

    def test_per_pr_isolation_logs_error_and_continues(self, tmp_path, monkeypatch):
        # An exception in one PR must not abort the whole round.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])

        class RaisingGh:
            def list_prs(self, repo):
                return [{"number": 1, "headRefOid": "abc", "title": "t"}]

            def check_runs(self, repo, sha):
                raise RuntimeError("boom")

            def fetch_files(self, repo, number):
                return []

            def view_pr(self, repo, number):
                return {}

        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo(
            "r/repo", self._repo_cfg(), cfg, "live", RaisingGh(), tmp_path, audit, notify
        )
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
        assert json.loads(lines[-1])["decision"] == "error"
        assert "boom" in json.loads(lines[-1])["reason"]


class TestPlatformGuards:
    def test_fcntl_import_guarded(self):
        # fcntl is POSIX-only; the script must degrade to a no-op lock on
        # Windows (import fcntl -> None) so collection succeeds there.
        assert hasattr(amg, "fcntl")
        if sys.platform != "win32":
            assert amg.fcntl is not None

    def test_zima_home_respects_env(self, monkeypatch):
        monkeypatch.setenv("ZIMA_HOME", "/tmp/custom-zima")
        assert str(amg._zima_home()).startswith("/tmp/custom-zima")

    def test_lock_path_under_zima_home(self, monkeypatch):
        monkeypatch.setenv("ZIMA_HOME", "/tmp/custom-zima")
        p = str(amg._lock_path())
        assert p.startswith("/tmp/custom-zima")
        assert p.endswith("auto-merge.lock")

    def test_main_returns_1_on_bad_config(self, tmp_path, monkeypatch, capsys):
        rc = amg.main(["--config", str(tmp_path / "nope.yaml")])
        assert rc == 1
        assert "failed to load config" in capsys.readouterr().out
