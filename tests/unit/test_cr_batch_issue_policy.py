"""Tests for shared code-review issue blocking and count policy."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = _REPO_ROOT / "pi" / "github-code-review-batch" / "scripts"

sys.path.insert(0, str(_SCRIPT_DIR))
import issue_policy  # type: ignore[import-not-found]  # noqa: E402


def test_low_defaults_to_non_blocking():
    issue = {"severity": "low"}

    assert issue_policy.normalize_severity(issue) == "low"
    assert issue_policy.is_blocking(issue) is False


def test_medium_high_critical_default_to_blocking():
    for severity in ("medium", "high", "critical"):
        assert issue_policy.is_blocking({"severity": severity}) is True

    assert issue_policy.normalize_severity({}) == "medium"
    assert issue_policy.normalize_severity({"severity": "invalid"}) == "medium"


def test_explicit_boolean_override_wins_for_low():
    assert issue_policy.is_blocking({"severity": "low", "blocking": True}) is True
    assert issue_policy.is_blocking({"severity": "low", "blocking": False}) is False


def test_non_boolean_override_falls_back_to_severity():
    for value in (0, 1, "false", None):
        assert issue_policy.is_blocking({"severity": "medium", "blocking": value}) is True


def test_normalize_issue_does_not_mutate_input_and_adds_boolean():
    issue = {"severity": "low", "description": "advisory"}

    normalized = issue_policy.normalize_issue(issue)

    assert normalized == {"severity": "low", "description": "advisory", "blocking": False}
    assert issue == {"severity": "low", "description": "advisory"}
    assert normalized is not issue


def test_active_filter_treats_missing_status_as_open():
    assert issue_policy.is_active_issue({}) is True
    assert issue_policy.is_active_issue({"status": "open"}) is True


def test_active_filter_excludes_resolved_acknowledged_and_wontfix():
    assert issue_policy.is_active_issue({"status": "resolved"}) is False
    for resolution in ("resolved", "acknowledged", "wontfix"):
        assert issue_policy.is_active_issue({"resolution": resolution}) is False
        assert issue_policy.is_active_issue({"status": "open", "resolution": resolution}) is False


def test_count_issues_separates_blocking_advisory_and_critical():
    issues = [
        {"severity": "low", "status": "open"},
        {"severity": "medium", "status": "open"},
        {"severity": "critical", "status": "resolved"},
        {"severity": "high", "status": "open", "resolution": "acknowledged"},
    ]

    assert issue_policy.count_issues(issues) == {
        "total": 4,
        "blocking": 3,
        "advisory": 1,
        "critical": 1,
    }
    assert issue_policy.count_issues(issues, active_only=True) == {
        "total": 2,
        "blocking": 1,
        "advisory": 1,
        "critical": 0,
    }
