"""Contract gate for the `github-code-review-batch` skill (pr-automation plugin).

These tests are the shared safety net for all changes to the skill. They assert
the *external contracts* that must never break, regardless of which issue is
being implemented:

  1. Trigger phrases — zima daemon invokes the skill by literal phrase.
  2. Status report block + 3-state `Status:` enum — zima daemon greps it.
  3. `<!-- cc-cr-meta -->` metadata marker + documented top-level schema keys.
  4. Round-trip: metadata written by build_review_body must parse back.
  5. Portability: scripts are Python-stdlib only (no MCP / no third-party deps),
     and SKILL.md still instructs the `gh` CLI path.
  6. Backward-compat / robustness: old/minimal schemas must not crash.

The skill scripts live under plugins/ (not the `zima` package) and are plain
stdin/stdout CLIs, so we exercise them as subprocess black boxes — the same way
the skill itself invokes them. Run from anywhere; paths resolve from this file.

Every test here MUST stay green before AND after each of the 8 optimization
issues (#119–#126). New behavior (e.g. severity in #119) adds assertions, it
does not weaken these.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/unit/<this> -> repo root
SKILL_DIR = _REPO_ROOT / "plugins" / "pr-automation" / "skills" / "github-code-review-batch"
SCRIPTS = SKILL_DIR / "scripts"

HEAD_SHA_A = "a" * 40
HEAD_SHA_B = "b" * 40


def _script(name: str) -> Path:
    return SCRIPTS / name


def _run(script: Path, stdin: str, *args: str) -> subprocess.CompletedProcess:
    """Run a skill script, feeding `stdin`, returning the completed process."""
    return subprocess.run(
        [sys.executable, str(script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_json(script: Path, obj: dict, *args: str) -> str:
    return _run(script, json.dumps(obj), *args).stdout


# ---------------------------------------------------------------------------
# Fixtures: representative inputs
# ---------------------------------------------------------------------------

ROUND1_INPUT = {
    "round": 1,
    "pr_number": 123,
    "head_sha": HEAD_SHA_A,
    "previous_head_sha": None,
    "repo_owner": "owner",
    "repo_name": "repo",
    "timestamp": "2026-06-17T10:00:00Z",
    "issues": [
        {
            "id": "issue-1",
            "description": "Missing error handling for OAuth callback",
            "reason": "bug",
            "file": "src/auth.ts",
            "lines": "67-72",
            "status": "open",
            "first_round": 1,
        }
    ],
}

ROUND2_INPUT = {
    "round": 2,
    "pr_number": 123,
    "head_sha": HEAD_SHA_B,
    "previous_head_sha": HEAD_SHA_A,
    "repo_owner": "owner",
    "repo_name": "repo",
    "timestamp": "2026-06-17T10:30:00Z",
    "issues": [
        {
            "id": "issue-3",
            "description": "Memory leak: OAuth state not cleaned up",
            "reason": "bug",
            "file": "src/auth.ts",
            "lines": "88-95",
            "status": "open",
            "first_round": 1,
        }
    ],
    "resolved_issues": [{"description": "Missing error handling"}],
    "acknowledged_issues": [],
    "unresolved_issues": [
        {
            "id": "issue-3",
            "description": "Memory leak: OAuth state not cleaned up",
            "reason": "bug",
            "file": "src/auth.ts",
            "lines": "88-95",
        }
    ],
    "new_issues": [],
    "prev_round_count": 3,
}


def _status_input(status: str) -> dict:
    return {
        "pr_number": 123,
        "round": 2,
        "head_sha": HEAD_SHA_B,
        "previous_head_sha": HEAD_SHA_A,
        "open_count": 1,
        "new_count": 0,
        "unresolved_count": 1,
        "resolved_count": 1,
        "acknowledged_count": 0,
        "status": status,
    }


def _status_input_sev(status: str, critical_count: int = 0, open_count: int = 1) -> dict:
    """Status-report input carrying the #119 critical_count field."""
    base = _status_input(status)
    base["open_count"] = open_count
    base["critical_count"] = critical_count
    return base


# Round-1 input with mixed severities, ordered low -> critical -> medium on
# purpose so the sort-under-test is observable.
SEV_ROUND1_INPUT = {
    "round": 1,
    "pr_number": 55,
    "head_sha": HEAD_SHA_A,
    "previous_head_sha": None,
    "repo_owner": "owner",
    "repo_name": "repo",
    "timestamp": "2026-06-18T10:00:00Z",
    "issues": [
        {
            "id": "issue-1",
            "description": "Low-severity naming nit",
            "reason": "CLAUDE.md",
            "file": "src/a.py",
            "lines": "1-2",
            "status": "open",
            "first_round": 1,
            "severity": "low",
        },
        {
            "id": "issue-2",
            "description": "Critical null-deref crash",
            "reason": "bug",
            "file": "src/b.py",
            "lines": "3-4",
            "status": "open",
            "first_round": 1,
            "severity": "critical",
        },
        {
            "id": "issue-3",
            "description": "Medium edge case",
            "reason": "logic",
            "file": "src/c.py",
            "lines": "5-6",
            "status": "open",
            "first_round": 1,
            "severity": "medium",
        },
    ],
}


# ---------------------------------------------------------------------------
# Contract 1: trigger phrases (literal external contract with zima daemon)
# ---------------------------------------------------------------------------


class TestTriggerPhrases:
    """zima daemon calls the skill by these literal phrases — do not change them."""

    @pytest.fixture(scope="class")
    def skill_md(self) -> str:
        return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "phrase", ["batch review pr", "review pr batch", "scheduled review pr"]
    )
    def test_phrase_present(self, skill_md, phrase):
        assert phrase in skill_md, f"trigger phrase {phrase!r} vanished from SKILL.md"


# ---------------------------------------------------------------------------
# Contract 2: status report block + 3-state Status enum
# ---------------------------------------------------------------------------


class TestStatusReport:
    VALID = ["NEEDS_FIX", "PASS", "NO_NEW_COMMITS"]

    @pytest.mark.parametrize("status", VALID)
    def test_block_shape_and_status_line(self, status):
        out = _run_json(_script("render_status_report.py"), _status_input(status))
        lines = out.splitlines()
        assert lines[0] == "=== CR Batch Status Report ==="
        assert lines[-1] == "================================"
        status_lines = [ln for ln in lines if ln.startswith("Status:")]
        assert len(status_lines) == 1
        assert status_lines[0] == f"Status: {status}"

    def test_invalid_status_exits_nonzero(self):
        proc = _run(_script("render_status_report.py"), json.dumps(_status_input("BOGUS")))
        assert proc.returncode != 0
        assert proc.stdout == ""


# ---------------------------------------------------------------------------
# Contract 3: cc-cr-meta marker + metadata top-level schema keys
# ---------------------------------------------------------------------------


METADATA_KEYS = {
    "round",
    "pr_number",
    "head_sha",
    "previous_head_sha",
    "total_issues",
    "resolved_count",
    "new_count",
    "acknowledged_count",
    "issues",
    "timestamp",
}


class TestReviewBody:
    def test_round1_markers(self):
        out = _run_json(_script("build_review_body.py"), ROUND1_INPUT)
        assert "<!-- cc-cr-meta" in out
        assert "-->" in out
        assert "### Code Review | Round-1" in out
        assert "🤖 Generated with Claude Code" in out

    def test_roundn_recheck_header(self):
        out = _run_json(_script("build_review_body.py"), ROUND2_INPUT)
        assert "### Code Review | Round-2 (Re-check)" in out

    def test_metadata_top_level_keys_stable(self):
        """#119 may add per-issue `severity`, but top-level keys must not change."""
        out = _run_json(_script("build_review_body.py"), ROUND1_INPUT)
        start = out.index("<!-- cc-cr-meta")
        end = out.index("-->", start)
        payload = json.loads(out[start + len("<!-- cc-cr-meta") : end].strip())
        assert METADATA_KEYS.issubset(payload.keys())


# ---------------------------------------------------------------------------
# Contract 4: round-trip — built metadata must parse back via parse_metadata
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_build_then_parse_preserves_round_and_sha(self):
        body = _run_json(_script("build_review_body.py"), ROUND2_INPUT)
        reviews_obj = {"reviews": [{"body": body, "submitted_at": "2026-06-17T10:30:00Z"}]}
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews_obj))
        # parse_metadata returns the latest cc-cr-meta object
        assert parsed.get("round") == 2
        assert parsed.get("head_sha") == HEAD_SHA_B
        assert isinstance(parsed.get("issues"), list)

    def test_parse_empty_reviews_returns_empty_object(self):
        parsed = json.loads(_run_json(_script("parse_metadata.py"), {"reviews": []}))
        assert parsed == {}


# ---------------------------------------------------------------------------
# Contract 5: portability — stdlib-only scripts + gh CLI instruction
# ---------------------------------------------------------------------------


class TestPortability:
    SCRIPT_NAMES = [
        "build_review_body.py",
        "compress_diff.py",
        "parse_metadata.py",
        "render_status_report.py",
    ]

    def test_scripts_are_stdlib_only(self):
        """No MCP / no third-party imports — the skill's portability guarantee."""
        offenders = {}
        for name in self.SCRIPT_NAMES:
            tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module.split(".")[0])
            non_stdlib = sorted({m for m in imports if m not in sys.stdlib_module_names})
            if non_stdlib:
                offenders[name] = non_stdlib
        assert not offenders, f"non-stdlib imports break portability: {offenders}"

    def test_skill_md_prescribes_gh_cli(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        assert "gh pr" in text, "SKILL.md must still prescribe the gh CLI path"


# ---------------------------------------------------------------------------
# Contract 6: backward-compat / robustness
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_build_review_body_tolerates_missing_optional_fields(self):
        """Old/minimal issue dicts (pre-#119, no severity) must not crash."""
        minimal = {
            "round": 1,
            "pr_number": 1,
            "head_sha": HEAD_SHA_A,
            "repo_owner": "o",
            "repo_name": "r",
            "timestamp": "2026-06-17T10:00:00Z",
            "issues": [{"description": "x", "reason": "bug", "file": "a.py", "lines": "1-2"}],
        }
        proc = _run(_script("build_review_body.py"), json.dumps(minimal))
        assert proc.returncode == 0, proc.stderr
        assert "### Code Review | Round-1" in proc.stdout

    def test_render_status_report_defaults_missing_counts(self):
        proc = _run(
            _script("render_status_report.py"),
            json.dumps({"pr_number": 1, "status": "PASS"}),
        )
        assert proc.returncode == 0, proc.stderr
        assert "Status: PASS" in proc.stdout

    def test_compress_diff_short_diff_passthrough(self):
        diff = "diff --git a/foo.py b/foo.py\n+print('hi')\n"
        out = _run(_script("compress_diff.py"), diff, "--max-len", "4000").stdout
        assert "print('hi')" in out
        assert "truncated" not in out

    def test_compress_diff_truncates_when_over_limit(self):
        # Lines that survive keep_hunks_only (they start with '+') and still
        # exceed --max-len, so the hard truncate() branch fires.
        diff = "diff --git a/foo.py b/foo.py\n" + "+added_line_content\n" * 500
        out = _run(_script("compress_diff.py"), diff, "--max-len", "100").stdout
        assert "diff truncated" in out

    def test_compress_diff_filter_tests_drops_test_files(self):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n+keep_me()\n"
            "diff --git a/tests/test_app.py b/tests/test_app.py\n+drop_me()\n"
        )
        out = _run(_script("compress_diff.py"), diff, "--filter-tests", "--max-len", "4000").stdout
        assert "keep_me" in out
        assert "drop_me" not in out


# ---------------------------------------------------------------------------
# #119: severity ranking + verdict (added on top of the baseline gate)
# ---------------------------------------------------------------------------


class TestSeverityVerdict:
    """Status report must surface critical count + a merge verdict (#119)."""

    def test_block_merge_when_critical(self):
        out = _run_json(
            _script("render_status_report.py"),
            _status_input_sev("NEEDS_FIX", critical_count=2, open_count=3),
        )
        assert "Status: NEEDS_FIX" in out
        assert "Critical issues: 2" in out
        assert "Verdict: BLOCK_MERGE" in out

    def test_ready_to_merge_on_pass(self):
        out = _run_json(
            _script("render_status_report.py"),
            _status_input_sev("PASS", critical_count=0, open_count=0),
        )
        assert "Verdict: READY_TO_MERGE" in out

    def test_merge_with_caution(self):
        out = _run_json(
            _script("render_status_report.py"),
            _status_input_sev("NEEDS_FIX", critical_count=0, open_count=2),
        )
        assert "Verdict: MERGE_WITH_CAUTION" in out

    def test_skip_on_no_new_commits(self):
        out = _run_json(
            _script("render_status_report.py"),
            _status_input_sev("NO_NEW_COMMITS", critical_count=0, open_count=1),
        )
        assert "Verdict: SKIP" in out

    def test_critical_count_backward_compat(self):
        """Old callers that omit critical_count must still get a valid block."""
        out = _run_json(_script("render_status_report.py"), _status_input("NEEDS_FIX"))
        assert "Critical issues: 0" in out
        assert "Status: NEEDS_FIX" in out
        assert "Verdict: MERGE_WITH_CAUTION" in out


class TestSeverityRender:
    """Review body sorts issues by severity and annotates it (#119)."""

    def test_round1_sorted_critical_first_and_annotated(self):
        out = _run_json(_script("build_review_body.py"), SEV_ROUND1_INPUT)
        # Skip the metadata block — it deliberately preserves input order; the
        # rendered body is what gets severity-sorted.
        body = out.split("-->", 1)[1]
        crit_pos = body.index("Critical null-deref crash")
        low_pos = body.index("Low-severity naming nit")
        assert crit_pos < low_pos  # critical sorts above low
        assert "(bug, critical)" in body
        assert "(CLAUDE.md, low)" in body

    def test_missing_severity_falls_back_to_medium(self):
        minimal = {
            "round": 1,
            "pr_number": 1,
            "head_sha": HEAD_SHA_A,
            "repo_owner": "o",
            "repo_name": "r",
            "timestamp": "2026-06-18T10:00:00Z",
            "issues": [
                {"description": "no sev field", "reason": "bug", "file": "a.py", "lines": "1-2"}
            ],
        }
        proc = _run(_script("build_review_body.py"), json.dumps(minimal))
        assert proc.returncode == 0, proc.stderr
        assert "(bug, medium)" in proc.stdout
