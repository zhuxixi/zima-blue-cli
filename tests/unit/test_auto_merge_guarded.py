"""Unit tests for examples/auto-merge/auto-merge-guarded.py."""

from __future__ import annotations

import importlib.util
import json
import sys
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
