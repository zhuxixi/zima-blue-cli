"""Tests for the deterministic trivial-PR precheck (issue #223).

Task 1 covers the render_status_report note extension; later tasks add
trivial_check pure-function, fetch and main-level tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = _REPO_ROOT / "pi" / "github-code-review-batch" / "scripts"

sys.path.insert(0, str(_SCRIPT_DIR))
import render_status_report  # type: ignore[import-not-found]  # noqa: E402

PASS_PAYLOAD = {
    "pr_number": 123,
    "round": 1,
    "head_sha": "a" * 40,
    "previous_head_sha": None,
    "open_count": 0,
    "new_count": 0,
    "unresolved_count": 0,
    "resolved_count": 0,
    "acknowledged_count": 0,
    "blocking_open_count": 0,
    "blocking_new_count": 0,
    "advisory_open_count": 0,
    "advisory_new_count": 0,
    "critical_count": 0,
    "status": "PASS",
}

GOLDEN_NO_NOTE = """\
=== CR Batch Status Report ===
PR: #123 | Round: 1 | Head SHA: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Previous Head SHA: null
Total open issues: 0
- New this round: 0
- Still open from previous: 0
- Resolved this round: 0
- Acknowledged / Won't Fix: 0
Blocking open issues: 0
- New blocking this round: 0
Advisory open issues: 0
- New advisory this round: 0
Status: PASS
Critical issues: 0
Verdict: READY_TO_MERGE
================================
<zima-review>
<verdict>approved</verdict>
<summary>CR batch PASS: no open issues</summary>
</zima-review>
"""


def test_format_note_collapses_whitespace():
    assert render_status_report.format_note("a\nb\tc  d") == "a b c d"


def test_format_note_strips_control_chars():
    assert render_status_report.format_note("a\x00b\x1fc") == "abc"


def test_format_note_truncates_at_240():
    assert len(render_status_report.format_note("x" * 500)) == 240


def test_format_note_empty():
    assert render_status_report.format_note("") == ""
    assert render_status_report.format_note("   ") == ""


def test_render_no_note_is_byte_identical_golden():
    assert render_status_report.render(PASS_PAYLOAD) == GOLDEN_NO_NOTE


def test_render_empty_note_equals_no_note():
    with_note = dict(PASS_PAYLOAD, note="")
    assert render_status_report.render(with_note) == GOLDEN_NO_NOTE


def test_render_note_line_after_verdict():
    out = render_status_report.render(dict(PASS_PAYLOAD, note="trivial precheck skip: x"))
    lines = out.splitlines()
    verdict_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Verdict:"))
    assert lines[verdict_idx + 1] == "Note: trivial precheck skip: x"


def test_render_note_xml_escaped_and_parses():
    from zima.review.parser import ReviewParser

    out = render_status_report.render(dict(PASS_PAYLOAD, note="docs & <generated>.md"))
    parsed = ReviewParser.parse(out)
    assert parsed.verdict == "approved"
    assert "docs &amp; &lt;generated&gt;.md" in out
    assert "docs & <generated>.md" in parsed.summary
