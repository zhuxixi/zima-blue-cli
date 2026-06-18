"""Tests for the cross-PR suppression list (#126).

Default-off, opt-in suppression: matching issues are demoted out of `open`
(never trigger fix-agent) but kept in `suppressed` for human visibility.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    _REPO_ROOT
    / "plugins"
    / "pr-automation"
    / "skills"
    / "github-code-review-batch"
    / "scripts"
    / "apply_suppressions.py"
)

sys.path.insert(0, str(SCRIPT.parent))
import apply_suppressions as asu  # noqa: E402

TODAY = date(2026, 6, 18)


def _run(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _issue(desc="x", reason="bug"):
    return {"description": desc, "reason": reason, "file": "a.py", "lines": "1-2"}


class TestPortability:
    def test_stdlib_only(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
        non_stdlib = sorted({m for m in imports if m not in sys.stdlib_module_names})
        assert not non_stdlib, f"non-stdlib imports: {non_stdlib}"


class TestMatches:
    def test_by_reason(self):
        assert asu._matches({"reason": "CLAUDE.md"}, _issue(reason="CLAUDE.md"))

    def test_reason_mismatch(self):
        assert not asu._matches({"reason": "CLAUDE.md"}, _issue(reason="bug"))

    def test_by_pattern(self):
        assert asu._matches({"pattern": "naming"}, _issue(desc="bad naming here"))

    def test_pattern_mismatch(self):
        assert not asu._matches({"pattern": "naming"}, _issue(desc="nothing here"))

    def test_both_must_hold(self):
        assert asu._matches(
            {"reason": "CLAUDE.md", "pattern": "naming"},
            _issue(desc="naming nit", reason="CLAUDE.md"),
        )
        assert not asu._matches(
            {"reason": "CLAUDE.md", "pattern": "naming"},
            _issue(desc="naming nit", reason="bug"),
        )


class TestExpiry:
    def test_no_expires_is_active(self):
        assert asu._is_active({}, TODAY)

    def test_future_active(self):
        assert asu._is_active({"expires": "2027-01-01"}, TODAY)

    def test_past_expired(self):
        assert not asu._is_active({"expires": "2020-01-01"}, TODAY)

    def test_invalid_date_ignored_as_inactive(self):
        # unparseable expires => treated as None => active (fail-open, not fail-closed)
        assert asu._is_active({"expires": "not-a-date"}, TODAY)


class TestApply:
    def test_suppress_by_reason(self):
        r = asu.apply_suppressions(
            [_issue(reason="CLAUDE.md"), _issue(reason="bug")],
            [{"reason": "CLAUDE.md"}],
            TODAY,
        )
        assert [i["reason"] for i in r["open"]] == ["bug"]
        assert [i["reason"] for i in r["suppressed"]] == ["CLAUDE.md"]

    def test_no_suppressions_all_open(self):
        r = asu.apply_suppressions([_issue(), _issue()], [], TODAY)
        assert len(r["open"]) == 2 and r["suppressed"] == []

    def test_expired_not_applied(self):
        r = asu.apply_suppressions(
            [_issue(reason="CLAUDE.md")],
            [{"reason": "CLAUDE.md", "expires": "2020-01-01"}],
            TODAY,
        )
        assert len(r["open"]) == 1 and r["suppressed"] == []

    def test_suppressed_marked_with_rationale(self):
        r = asu.apply_suppressions(
            [_issue(desc="naming", reason="CLAUDE.md")],
            [{"pattern": "naming", "rationale": "style not reviewed"}],
            TODAY,
        )
        assert r["suppressed"][0]["suppressed_reason"] == "style not reviewed"


class TestEndToEnd:
    def test_cli_default_off(self):
        r = _run({"issues": [_issue(), _issue()], "suppressions": []})
        assert len(r["open"]) == 2 and r["suppressed"] == []

    def test_cli_expired_via_today(self):
        r = _run(
            {
                "issues": [_issue(reason="CLAUDE.md")],
                "suppressions": [{"reason": "CLAUDE.md", "expires": "2020-01-01"}],
                "today": "2026-06-18",
            }
        )
        assert len(r["open"]) == 1 and r["suppressed"] == []

    def test_cli_suppress_by_pattern(self):
        r = _run(
            {
                "issues": [_issue(desc="naming nit"), _issue(desc="real crash")],
                "suppressions": [{"pattern": "naming"}],
                "today": "2026-06-18",
            }
        )
        assert [i["description"] for i in r["open"]] == ["real crash"]
        assert [i["description"] for i in r["suppressed"]] == ["naming nit"]
