"""Fixture/regression tests for committer-response matching (#125).

Exercises scripts/match_committer_response.py — the pure, deterministic core of
flow.md Step 0.2a (match keys + keyword table) — as a subprocess black box.
These fixtures freeze the heuristic's expected behavior so keyword-table or
model drift is caught before it silently changes zima daemon's acknowledged
counts or cross-round metadata.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    _REPO_ROOT
    / "plugins"
    / "pr-automation"
    / "skills"
    / "github-code-review-batch"
    / "scripts"
    / "match_committer_response.py"
)


def _run(payload: dict) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _issue(iid, desc, file="src/a.py", lines="10-12", status="open"):
    return {"id": iid, "description": desc, "file": file, "lines": lines, "status": status}


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


class TestClassifyViaMatch:
    def test_resolved_via_issue_id(self):
        out = _run(
            {
                "previous_issues": [_issue("issue-1", "Memory leak in OAuth state cleanup")],
                "committer_comments": ["issue-1 fixed in commit abc"],
            }
        )
        assert out[0]["resolution"] == "resolved"

    def test_wontfix_via_file_lines(self):
        out = _run(
            {
                "previous_issues": [_issue("issue-2", "Naming inconsistency", "src/b.py", "20-25")],
                "committer_comments": ["src/b.py lines 20-25: by design, wontfix"],
            }
        )
        assert out[0]["resolution"] == "wontfix"

    def test_clarified_via_description_window(self):
        out = _run(
            {
                "previous_issues": [
                    _issue("issue-3", "Missing error handling for OAuth callback handler")
                ],
                "committer_comments": [
                    "Actually, missing error handling for OAuth callback only happens on timeout - clarify"
                ],
            }
        )
        assert out[0]["resolution"] == "clarified"

    def test_no_match_yields_null(self):
        out = _run(
            {
                "previous_issues": [_issue("issue-4", "Some unrelated issue right here now")],
                "committer_comments": ["completely different topic, no signal words"],
            }
        )
        assert out[0]["resolution"] is None
        assert out[0]["committer_note"] is None


class TestPrecedence:
    def test_clarified_beats_wontfix(self):
        # "actually" (clarified) + "by design" (wontfix) -> clarified wins
        out = _run(
            {
                "previous_issues": [_issue("issue-5", "Race condition in the worker pool loop")],
                "committer_comments": ["issue-5: actually by design"],
            }
        )
        assert out[0]["resolution"] == "clarified"

    def test_resolved_beats_clarified(self):
        out = _run(
            {
                "previous_issues": [_issue("issue-6", "Null pointer dereference in parser path")],
                "committer_comments": ["issue-6: fixed, added context: returns None"],
            }
        )
        assert out[0]["resolution"] == "resolved"


class TestEdgeCases:
    def test_non_open_issues_skipped(self):
        out = _run(
            {
                "previous_issues": [
                    _issue("issue-7", "Open issue one", status="open"),
                    _issue("issue-8", "Resolved issue", status="resolved"),
                ],
                "committer_comments": ["issue-7 wontfix", "issue-8 fixed"],
            }
        )
        assert [r["issue_id"] for r in out] == ["issue-7"]

    def test_cjk_description_falls_back_to_id(self):
        # CJK description has no spaces -> <4 tokens -> token-window key never
        # fires; must match via issue-id or file:lines.
        out = _run(
            {
                "previous_issues": [_issue("issue-9", "内存泄漏未清理", "src/c.py", "1-5")],
                "committer_comments": ["issue-9 不需要修复"],
            }
        )
        assert out[0]["resolution"] == "wontfix"

    def test_first_matching_comment_wins(self):
        out = _run(
            {
                "previous_issues": [_issue("issue-10", "Some specific bug right here now")],
                "committer_comments": [
                    "issue-10 actually it is fine",  # clarified, first match
                    "issue-10 fixed later",  # resolved, but second -> ignored
                ],
            }
        )
        assert out[0]["resolution"] == "clarified"
