"""Contract gate for the `github-code-review-batch` skill (pr-automation plugin).

These tests are the shared safety net for all changes to the skill. They assert
the *external contracts* that must never break, regardless of which issue is
being implemented:

  1. Trigger phrases — zima daemon invokes the skill by literal phrase.
  2. Status report block + 3-state `Status:` enum — zima daemon greps it.
  3. `<!-- pi-cr-meta -->` metadata marker + documented top-level schema keys.
  4. Round-trip: metadata written by build_review_body must parse back.
  5. Portability: scripts are Python-stdlib only (no MCP / no third-party deps),
     and SKILL.md still instructs the `gh` CLI path.
  6. Backward-compat / robustness: old/minimal schemas must not crash.

The skill scripts live under pi/ (not the `zima` package) and are plain
stdin/stdout CLIs, so we exercise them as subprocess black boxes — the same way
the skill itself invokes them. Run from anywhere; paths resolve from this file.

Every test here MUST stay green before AND after each of the 8 optimization
issues (#119–#126). New behavior (e.g. severity in #119) adds assertions, it
does not weaken these.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/unit/<this> -> repo root
SKILL_DIR = _REPO_ROOT / "pi" / "github-code-review-batch"
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


def _load_build_review_body():
    """Load the standalone script so mutation contracts can call it in-process."""
    script_dir = str(SCRIPTS)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location(
        "cr_batch_build_review_body", _script("build_review_body.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
# Documentation contract: blocking-aware workflow and convergence terminology
# ---------------------------------------------------------------------------


class TestBlockingPolicyDocumentation:
    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        return {
            "flow": (SKILL_DIR / "references" / "flow.md").read_text(encoding="utf-8"),
            "monitor": (_REPO_ROOT / "pi" / "zima-pr-monitor" / "SKILL.md").read_text(
                encoding="utf-8"
            ),
            "examples": (SKILL_DIR / "references" / "output-examples.md").read_text(
                encoding="utf-8"
            ),
        }

    def test_flow_documents_blocking_normalization_and_counts(self, texts):
        assert "blocking=false" in texts["flow"]
        assert "blocking_open_count" in texts["flow"]
        assert "status: open" in texts["flow"]

    def test_monitor_documents_blocking_convergence_count(self, texts):
        assert "blocking_new_count" in texts["monitor"]

    def test_examples_label_advisory_findings(self, texts):
        assert "Advisory / non-blocking findings" in texts["examples"]

    def test_flow_step8_uses_blocking_aware_templates(self, texts):
        step8 = texts["flow"].split("## Step 8:", 1)[1].split("## Step 9:", 1)[0]
        assert "Found N blocking issues:" in step8
        assert "No blocking issues found." in step8
        assert "Found N issues:" not in step8
        assert "No issues found." not in step8

    def test_low_only_example_retains_monitor_safety_gates(self, texts):
        low_only = (
            texts["examples"]
            .split("## Round-1：仅 advisory findings", 1)[1]
            .split("## Round-1：无问题", 1)[0]
        )
        assert "multi-flow" in low_only
        assert "in-flight" in low_only
        assert "CI" in low_only


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
        # #176: the report block still ends with the ruler; the machine-readable
        # <zima-review> XML follows it as a trailer.
        assert "================================" in lines
        assert lines[-1] == "</zima-review>"
        status_lines = [ln for ln in lines if ln.startswith("Status:")]
        assert len(status_lines) == 1
        assert status_lines[0] == f"Status: {status}"

    def _parsed(self, payload: dict):
        from zima.review.parser import ReviewParser

        out = _run_json(_script("render_status_report.py"), payload)
        return out, ReviewParser.parse(out)

    def test_xml_trailer_needs_fix_parses_to_needs_fix(self):
        d = _status_input("NEEDS_FIX")
        d["open_count"] = 3
        out, parsed = self._parsed(d)
        assert "<zima-review>" in out
        assert parsed.verdict == "needs_fix"
        assert parsed.summary

    def test_xml_trailer_pass_parses_to_approved(self):
        out, parsed = self._parsed(_status_input("PASS"))
        assert parsed.verdict == "approved"

    def test_xml_trailer_no_new_commits_with_open_issues_is_needs_fix(self):
        d = _status_input("NO_NEW_COMMITS")
        d["open_count"] = 2
        _, parsed = self._parsed(d)
        assert parsed.verdict == "needs_fix"

    def test_xml_trailer_no_new_commits_with_zero_open_is_approved(self):
        d = _status_input("NO_NEW_COMMITS")
        d["open_count"] = 0
        _, parsed = self._parsed(d)
        assert parsed.verdict == "approved"

    def test_low_only_new_policy_is_pass_and_approved(self):
        payload = _status_input("NEEDS_FIX")
        payload.update(
            {
                "open_count": 3,
                "new_count": 3,
                "blocking_open_count": 0,
                "blocking_new_count": 0,
                "advisory_open_count": 3,
                "advisory_new_count": 3,
            }
        )
        out, parsed = self._parsed(payload)
        assert "Total open issues: 3" in out
        assert "Blocking open issues: 0" in out
        assert "- New blocking this round: 0" in out
        assert "Advisory open issues: 3" in out
        assert "- New advisory this round: 3" in out
        assert "Status: PASS" in out
        assert "Verdict: READY_TO_MERGE" in out
        assert parsed.verdict == "approved"
        assert "no blocking issues" in out

    def test_mixed_policy_still_needs_fix(self):
        payload = _status_input("PASS")
        payload.update(
            {
                "open_count": 3,
                "new_count": 2,
                "blocking_open_count": 1,
                "blocking_new_count": 1,
                "advisory_open_count": 2,
                "advisory_new_count": 1,
                "critical_count": 0,
            }
        )
        out, parsed = self._parsed(payload)
        assert "Blocking open issues: 1" in out
        assert "- New blocking this round: 1" in out
        assert "Advisory open issues: 2" in out
        assert "- New advisory this round: 1" in out
        assert "Status: NEEDS_FIX" in out
        assert "Verdict: MERGE_WITH_CAUTION" in out
        assert parsed.verdict == "needs_fix"

    def test_legacy_payload_keeps_old_needs_fix_behavior(self):
        payload = _status_input("NEEDS_FIX")
        payload.update({"open_count": 3, "new_count": 2})
        out, parsed = self._parsed(payload)
        assert "Status: NEEDS_FIX" in out
        assert "Verdict: MERGE_WITH_CAUTION" in out
        assert parsed.verdict == "needs_fix"
        assert "CR batch NEEDS_FIX: 3 open issue(s)" in out

    def test_no_new_commits_preserves_skip_behavior_with_blocking_counts(self):
        payload = _status_input("NO_NEW_COMMITS")
        payload.update(
            {
                "open_count": 3,
                "blocking_open_count": 0,
                "blocking_new_count": 0,
                "advisory_open_count": 3,
                "advisory_new_count": 0,
            }
        )
        out, parsed = self._parsed(payload)
        assert "Status: NO_NEW_COMMITS" in out
        assert "Verdict: SKIP" in out
        assert parsed.verdict == "approved"
        assert "no blocking issues" in out

    def test_new_policy_blocking_critical_is_block_merge(self):
        payload = _status_input("PASS")
        payload.update(
            {
                "open_count": 2,
                "new_count": 1,
                "blocking_open_count": 1,
                "blocking_new_count": 1,
                "advisory_open_count": 1,
                "advisory_new_count": 0,
                "critical_count": 1,
            }
        )
        out, parsed = self._parsed(payload)
        assert "Status: NEEDS_FIX" in out
        assert "Blocking open issues: 1" in out
        assert "Critical issues: 1" in out
        assert "Verdict: BLOCK_MERGE" in out
        assert parsed.verdict == "needs_fix"

    def test_new_policy_derives_missing_advisory_counts(self):
        payload = _status_input("PASS")
        payload.update(
            {
                "open_count": 4,
                "new_count": 3,
                "blocking_open_count": 1,
                "blocking_new_count": 1,
            }
        )
        out, _ = self._parsed(payload)
        assert "Advisory open issues: 3" in out
        assert "- New advisory this round: 2" in out

    def test_invalid_status_exits_nonzero(self):
        proc = _run(_script("render_status_report.py"), json.dumps(_status_input("BOGUS")))
        assert proc.returncode != 0
        assert proc.stdout == ""


# ---------------------------------------------------------------------------
# Contract 3: pi-cr-meta marker + metadata top-level schema keys
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
    "blocking_open_count",
    "blocking_new_count",
    "advisory_open_count",
    "advisory_new_count",
}


class TestReviewBody:
    def test_round1_markers(self):
        out = _run_json(_script("build_review_body.py"), ROUND1_INPUT)
        assert "<!-- pi-cr-meta" in out
        assert "-->" in out
        assert "### Code Review | Round-1" in out
        assert "🤖 Generated with pi-coding-agent" in out

    def test_roundn_recheck_header(self):
        out = _run_json(_script("build_review_body.py"), ROUND2_INPUT)
        assert "### Code Review | Round-2 (Re-check)" in out

    def test_metadata_top_level_keys_stable(self):
        """The documented metadata key contract includes blocking policy counts."""
        out = _run_json(_script("build_review_body.py"), ROUND1_INPUT)
        start = out.index("<!-- pi-cr-meta")
        end = out.index("-->", start)
        payload = json.loads(out[start + len("<!-- pi-cr-meta") : end].strip())
        assert METADATA_KEYS.issubset(payload.keys())


# ---------------------------------------------------------------------------
# Contract 4: round-trip — built metadata must parse back via parse_metadata
# ---------------------------------------------------------------------------


class TestRound1MetadataDefaults:
    """#173: Round-1 must not report new_count=0 when issues were found.

    Round-1 semantics: every discovered issue is new. render_round_1 prints
    active blocking/advisory findings from `issues[]`; metadata `new_count` must use the same
    count (open, non-acknowledged) when the caller did not pass explicit
    new_count / new_issues.
    """

    def _meta(self, out: str) -> dict:
        start = out.index("<!-- pi-cr-meta")
        end = out.index("-->", start)
        return json.loads(out[start + len("<!-- pi-cr-meta") : end].strip())

    def test_round1_new_count_defaults_to_open_issues(self):
        payload = {
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
                    "description": "bug one",
                    "reason": "bug",
                    "file": "a.py",
                    "lines": "1-2",
                    "status": "open",
                    "first_round": 1,
                },
                {
                    "id": "issue-2",
                    "description": "bug two",
                    "reason": "logic",
                    "file": "b.py",
                    "lines": "3-4",
                    "status": "open",
                    "first_round": 1,
                },
                {
                    "id": "issue-3",
                    "description": "logic flaw",
                    "reason": "logic",
                    "file": "c.py",
                    "lines": "5-6",
                    "status": "open",
                    "first_round": 1,
                },
            ],
        }
        out = _run_json(_script("build_review_body.py"), payload)
        meta = self._meta(out)
        # Round-1 reality: all issues are open discoveries — metadata and the
        # rendered "Found N issues" must agree.
        assert meta["new_count"] == 3
        assert meta["total_issues"] == 3
        assert "Found 3 blocking issues" in out

    def test_round1_explicit_new_count_still_wins(self):
        payload = dict(ROUND1_INPUT)
        payload["new_count"] = 7
        out = _run_json(_script("build_review_body.py"), payload)
        meta = self._meta(out)
        assert meta["new_count"] == 7

    def test_round1_metadata_normalizes_blocking_and_counts(self):
        payload = dict(ROUND1_INPUT)
        payload["issues"] = [
            {
                "id": "low",
                "description": "finding low",
                "reason": "style",
                "file": "a.py",
                "lines": "1-2",
                "status": "open",
                "severity": "low",
            },
            {
                "id": "high",
                "description": "finding high",
                "reason": "bug",
                "file": "b.py",
                "lines": "3-4",
                "status": "open",
                "severity": "high",
            },
        ]
        out = _run_json(_script("build_review_body.py"), payload)
        meta = self._meta(out)
        assert meta["total_issues"] == 2
        assert meta["new_count"] == 2
        assert meta["blocking_open_count"] == 1
        assert meta["blocking_new_count"] == 1
        assert meta["advisory_open_count"] == 1
        assert meta["advisory_new_count"] == 1
        assert meta["issues"][0]["blocking"] is False

    def test_round1_missing_status_is_active_and_inactive_findings_are_excluded(self):
        payload = dict(ROUND1_INPUT)
        payload["issues"] = [
            {
                "id": "legacy-active",
                "description": "legacy active",
                "reason": "bug",
                "file": "active.py",
                "lines": "1-2",
                "severity": "high",
            },
            {
                "id": "resolved",
                "description": "resolved finding",
                "reason": "bug",
                "file": "resolved.py",
                "lines": "1-2",
                "status": "resolved",
                "severity": "critical",
            },
            {
                "id": "acknowledged",
                "description": "acknowledged finding",
                "reason": "style",
                "file": "ack.py",
                "lines": "1-2",
                "resolution": "acknowledged",
                "severity": "low",
            },
            {
                "id": "wontfix",
                "description": "wontfix finding",
                "reason": "bug",
                "file": "wontfix.py",
                "lines": "1-2",
                "status": "open",
                "resolution": "wontfix",
                "severity": "high",
            },
        ]
        out = _run_json(_script("build_review_body.py"), payload)
        meta = self._meta(out)
        assert meta["total_issues"] == 1
        assert meta["new_count"] == 1
        assert meta["blocking_open_count"] == 1
        assert meta["blocking_new_count"] == 1
        assert meta["advisory_open_count"] == 0
        assert meta["advisory_new_count"] == 0
        assert "Found 1 blocking issue" in out
        assert "legacy active" in out
        assert "resolved finding" not in out.split("-->", 1)[1]
        assert "acknowledged finding" not in out.split("-->", 1)[1]
        assert "wontfix finding" not in out.split("-->", 1)[1]

    def test_normalization_does_not_mutate_input_collections(self):
        payload = deepcopy(ROUND2_INPUT)
        payload["new_issues"] = [
            {
                "id": "new-low",
                "description": "new advisory",
                "reason": "style",
                "file": "new.py",
                "lines": "1-2",
                "severity": "low",
            }
        ]
        before = deepcopy(payload)

        build_review_body = _load_build_review_body()
        build_review_body.render_body(payload)

        assert payload == before
        assert "blocking" not in payload["issues"][0]
        assert "blocking" not in payload["unresolved_issues"][0]
        assert "blocking" not in payload["new_issues"][0]

    def test_explicit_blocking_override_and_legacy_issue_are_normalized(self):
        payload = dict(ROUND1_INPUT)
        payload["issues"] = [
            {
                "id": "override",
                "description": "explicit low override",
                "reason": "bug",
                "file": "a.py",
                "lines": "1-2",
                "status": "open",
                "severity": "low",
                "blocking": True,
            },
            {
                "id": "legacy",
                "description": "legacy issue",
                "reason": "bug",
                "file": "b.py",
                "lines": "3-4",
                "status": "open",
                "severity": "low",
            },
        ]
        out = _run_json(_script("build_review_body.py"), payload)
        meta = self._meta(out)
        assert meta["blocking_open_count"] == 1
        assert meta["blocking_new_count"] == 1
        assert meta["issues"][0]["blocking"] is True
        assert meta["issues"][1]["blocking"] is False

    def test_roundn_metadata_uses_unresolved_and_new_fallback(self):
        payload = dict(ROUND2_INPUT)
        payload["issues"] = []
        payload["unresolved_issues"] = [
            {
                "id": "carried-low",
                "description": "finding carried-low",
                "reason": "style",
                "file": "a.py",
                "lines": "1-2",
                "severity": "low",
            }
        ]
        payload["new_issues"] = [
            {
                "id": "new-high",
                "description": "finding new-high",
                "reason": "bug",
                "file": "b.py",
                "lines": "3-4",
                "status": "open",
                "severity": "high",
            }
        ]
        out = _run_json(_script("build_review_body.py"), payload)
        meta = self._meta(out)
        assert meta["total_issues"] == 2
        assert meta["new_count"] == 1
        assert meta["blocking_open_count"] == 1
        assert meta["blocking_new_count"] == 1
        assert meta["advisory_open_count"] == 1
        assert meta["advisory_new_count"] == 0
        assert [issue["id"] for issue in meta["issues"]] == ["carried-low", "new-high"]
        assert all(isinstance(issue["blocking"], bool) for issue in meta["issues"])

    def test_explicit_policy_counts_remain_authoritative(self):
        payload = dict(ROUND1_INPUT)
        payload.update(
            {
                "total_issues": 8,
                "new_count": 7,
                "blocking_open_count": 6,
                "blocking_new_count": 5,
                "advisory_open_count": 4,
                "advisory_new_count": 3,
            }
        )
        meta = self._meta(_run_json(_script("build_review_body.py"), payload))
        assert meta["total_issues"] == 8
        assert meta["new_count"] == 7
        assert meta["blocking_open_count"] == 6
        assert meta["blocking_new_count"] == 5
        assert meta["advisory_open_count"] == 4
        assert meta["advisory_new_count"] == 3


class TestLowSeverityAdvisoryRendering:
    """Low findings remain visible as explicit non-blocking advisories."""

    def _issue(self, id_: str, sev: str, **extra) -> dict:
        issue = {
            "id": id_,
            "description": f"finding {id_}",
            "reason": "bug",
            "file": f"{id_}.py",
            "lines": "1-2",
            "status": "open",
            "first_round": 1,
            "severity": sev,
        }
        issue.update(extra)
        return issue

    def test_round1_low_only_is_explicitly_advisory(self):
        payload = dict(ROUND1_INPUT)
        payload["issues"] = [self._issue("i1", "low")]
        out = _run_json(_script("build_review_body.py"), payload)
        part_b = out.split("-->", 1)[1]
        assert "No blocking issues found" in part_b
        assert "advisory" in part_b.lower()
        assert "<details>" in part_b
        assert "finding i1" in part_b
        assert "suppressed" not in part_b.lower()
        assert "<summary>Advisory / non-blocking findings (1)</summary>" in part_b
        assert f"https://github.com/owner/repo/blob/{HEAD_SHA_A}/i1.py#L1-L2" in part_b

    def test_round1_mixed_keeps_blocking_list_and_advisory_details(self):
        payload = dict(ROUND1_INPUT)
        payload["issues"] = [self._issue("low", "low"), self._issue("high", "high")]
        out = _run_json(_script("build_review_body.py"), payload)
        part_b = out.split("-->", 1)[1]
        blocking_section, advisory_details = part_b.split("<details>", 1)
        assert "Found 1 blocking issue" in blocking_section
        assert "finding high" in blocking_section
        assert "finding low" in advisory_details
        assert "(bug, low)" in advisory_details
        assert f"https://github.com/owner/repo/blob/{HEAD_SHA_A}/low.py#L1-L2" in advisory_details

    def test_roundn_low_only_does_not_claim_all_findings_resolved(self):
        payload = dict(ROUND2_INPUT)
        payload["issues"] = []
        payload["unresolved_issues"] = [self._issue("u1", "low")]
        payload["new_issues"] = []
        out = _run_json(_script("build_review_body.py"), payload)
        part_b = out.split("-->", 1)[1]
        assert "No blocking issues remain" in part_b
        assert "All issues resolved" not in part_b
        assert "Advisory / non-blocking findings" in part_b
        assert "finding u1" in part_b

    def test_roundn_explicit_low_override_is_rendered_as_blocking(self):
        payload = dict(ROUND2_INPUT)
        payload["issues"] = []
        payload["unresolved_issues"] = [self._issue("u1", "low", blocking=True)]
        payload["new_issues"] = []
        out = _run_json(_script("build_review_body.py"), payload)
        part_b = out.split("-->", 1)[1]
        assert "- **Still open**: 1 blocking; 0 advisory" in part_b
        assert "New issues found: 0 blocking; 0 advisory" in part_b
        assert "finding u1" in part_b

    def test_roundn_only_new_advisory_is_counted_and_labeled_new(self):
        payload = dict(ROUND2_INPUT)
        payload["issues"] = []
        payload["unresolved_issues"] = []
        payload["new_issues"] = [self._issue("new-low", "low", first_round=2)]

        out = _run_json(_script("build_review_body.py"), payload)
        meta = TestRound1MetadataDefaults()._meta(out)
        part_b = out.split("-->", 1)[1]

        assert meta["new_count"] == 1
        assert meta["blocking_new_count"] == 0
        assert meta["advisory_new_count"] == 1
        assert "- **Still open**: 0 blocking; 0 advisory" in part_b
        assert "New issues found: 0 blocking; 1 advisory" in part_b
        assert "#### New this round (1)" in part_b
        assert "finding new-low" in part_b
        assert "#### Carried from previous rounds" not in part_b

    def test_roundn_nonempty_issues_are_canonical_for_metadata_and_body(self):
        payload = dict(ROUND2_INPUT)
        payload["issues"] = [
            self._issue("canonical-carried", "high", first_round=1),
            self._issue("canonical-new", "low", first_round=2),
        ]
        payload["unresolved_issues"] = [self._issue("bucket-ghost", "low", first_round=1)]
        payload["new_issues"] = [self._issue("new-bucket-ghost", "critical", first_round=2)]

        out = _run_json(_script("build_review_body.py"), payload)
        meta = TestRound1MetadataDefaults()._meta(out)
        part_b = out.split("-->", 1)[1]

        assert meta["total_issues"] == 2
        assert meta["new_count"] == 1
        assert meta["blocking_open_count"] == 1
        assert meta["blocking_new_count"] == 0
        assert meta["advisory_open_count"] == 1
        assert meta["advisory_new_count"] == 1
        assert "- **Still open**: 1 blocking; 0 advisory" in part_b
        assert "New issues found: 0 blocking; 1 advisory" in part_b
        assert "finding canonical-carried" in part_b
        assert "finding canonical-new" in part_b
        assert "bucket-ghost" not in part_b
        assert "new-bucket-ghost" not in part_b
        assert "#### New this round (1)" in part_b

    def test_roundn_nonempty_inactive_issues_do_not_revive_bucket_ghosts(self):
        payload = dict(ROUND2_INPUT)
        payload["issues"] = [
            self._issue("resolved-canonical", "high", status="resolved"),
            self._issue("acknowledged-canonical", "low", resolution="acknowledged"),
            self._issue("wontfix-canonical", "critical", resolution="wontfix"),
        ]
        payload["unresolved_issues"] = [self._issue("carried-bucket-ghost", "high")]
        payload["new_issues"] = [self._issue("new-bucket-ghost", "critical", first_round=2)]

        out = _run_json(_script("build_review_body.py"), payload)
        meta = TestRound1MetadataDefaults()._meta(out)
        part_b = out.split("-->", 1)[1]

        assert meta["total_issues"] == 0
        assert meta["new_count"] == 0
        assert meta["blocking_open_count"] == 0
        assert meta["blocking_new_count"] == 0
        assert meta["advisory_open_count"] == 0
        assert meta["advisory_new_count"] == 0
        assert meta["issues"] == []
        assert "carried-bucket-ghost" not in part_b
        assert "new-bucket-ghost" not in part_b
        assert "All issues resolved" in part_b


class TestRoundNResolvedLabelTruncation:
    """#175: resolved summary line must not hard-cut CJK descriptions mid-word.

    Old behavior: description[:40] cut Chinese text at an arbitrary byte.
    New behavior: word-boundary (or CJK-safe) cut at 60 chars with explicit
    ellipsis; metadata keeps the full description untouched.
    """

    LONG_EN = (
        "fix environment variable passthrough for the watchdog thread "
        "so that _enable_line_buffered_stdout docstring mismatch no longer"
    )
    # 42 chars: old [:40] code cut this mid-sentence; new 60-char limit keeps it whole.
    MID_ZH = (
        "修复看门狗线程的环境变量传递问题，避免标准输出行缓冲配置在守护进程重启后失效并污染日志"
    )
    # >60 chars: must be cut with an explicit ellipsis.
    LONG_ZH = (
        "修复看门狗线程的环境变量传递问题，避免标准输出行缓冲配置在守护进程重启后失效并污染日志，"
        "同时确保重连路径上的响应对象正确关闭且不泄漏套接字资源，以及状态文件的原子写入顺序"
    )

    def _payload(self, description: str) -> dict:
        return {
            "round": 2,
            "pr_number": 123,
            "head_sha": HEAD_SHA_B,
            "previous_head_sha": HEAD_SHA_A,
            "repo_owner": "owner",
            "repo_name": "repo",
            "timestamp": "2026-06-17T10:30:00Z",
            "issues": [],
            "resolved_issues": [{"description": description}],
            "unresolved_issues": [
                {
                    "description": "still open bug",
                    "reason": "bug",
                    "file": "x.py",
                    "lines": "1-2",
                }
            ],
        }

    def test_long_english_cut_at_word_boundary_with_ellipsis(self):
        out = _run_json(_script("build_review_body.py"), self._payload(self.LONG_EN))
        assert "**Resolved**: 1 (" in out
        label = out.split("**Resolved**: 1 (", 1)[1].split(")", 1)[0]
        assert label.endswith("...")
        assert "  " not in label  # cut at a word boundary, not mid-word space

    def test_mid_chinese_no_longer_cut_at_40(self):
        out = _run_json(_script("build_review_body.py"), self._payload(self.MID_ZH))
        assert f"({self.MID_ZH})" in out  # 42 chars fit within the 60 limit

    def test_long_chinese_cut_with_ellipsis(self):
        out = _run_json(_script("build_review_body.py"), self._payload(self.LONG_ZH))
        label = out.split("**Resolved**: 1 (", 1)[1].split(")", 1)[0]
        assert label.endswith("...")
        assert len(label) < len(self.LONG_ZH)

    def test_short_description_untouched(self):
        out = _run_json(_script("build_review_body.py"), self._payload("short desc"))
        assert "(short desc)" in out


class TestRoundTrip:
    def test_build_then_parse_preserves_round_and_sha(self):
        body = _run_json(_script("build_review_body.py"), ROUND2_INPUT)
        reviews_obj = {"reviews": [{"body": body, "submitted_at": "2026-06-17T10:30:00Z"}]}
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews_obj))
        # parse_metadata returns the latest pi-cr-meta object
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
            non_stdlib = sorted(
                {m for m in imports if m not in sys.stdlib_module_names and m != "issue_policy"}
            )
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
        medium_pos = body.index("Medium edge case")
        assert crit_pos < medium_pos  # critical sorts above medium
        assert "(bug, critical)" in body
        assert "<summary>Advisory / non-blocking findings (1)</summary>" in body
        assert "Low-severity naming nit" in body
        assert "suppressed" not in body.lower()
        meta = out[out.index("<!-- pi-cr-meta") + len("<!-- pi-cr-meta") : out.index("-->")]
        assert "Low-severity naming nit" in meta

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


# ---------------------------------------------------------------------------
# #120: diff truncation visibility (compress_diff --meta-file + status report)
# ---------------------------------------------------------------------------


class TestTruncationMeta:
    """compress_diff must emit structured coverage meta when asked (#120)."""

    def test_meta_no_truncation(self, tmp_path):
        diff = "diff --git a/foo.py b/foo.py\n+keep()\n"
        meta_path = tmp_path / "meta.json"
        proc = _run(_script("compress_diff.py"), diff, "--meta-file", str(meta_path))
        assert proc.returncode == 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["diff_truncated"] is False
        assert meta["total_files"] == 1
        assert meta["covered_files"] == 1
        assert meta["dropped_test_files"] == []

    def test_meta_truncation_within_file(self, tmp_path):
        # Single file whose content exceeds max-len: header survives, content cut.
        diff = "diff --git a/big.py b/big.py\n" + "+added\n" * 300
        meta_path = tmp_path / "meta.json"
        proc = _run(
            _script("compress_diff.py"), diff, "--max-len", "100", "--meta-file", str(meta_path)
        )
        assert proc.returncode == 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["diff_truncated"] is True
        assert meta["total_files"] == 1
        assert meta["covered_files"] == 1  # header present, body truncated

    def test_meta_truncation_drops_tail_file(self, tmp_path):
        # First file huge (truncation cuts inside it); tail file dropped entirely.
        diff = (
            "diff --git a/big.py b/big.py\n"
            + "+x\n" * 200
            + "diff --git a/tail.py b/tail.py\n+tail()\n"
        )
        meta_path = tmp_path / "meta.json"
        proc = _run(
            _script("compress_diff.py"), diff, "--max-len", "100", "--meta-file", str(meta_path)
        )
        assert proc.returncode == 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["diff_truncated"] is True
        assert meta["total_files"] == 2
        assert "tail.py" in meta["truncated_dropped_files"]

    def test_meta_filter_tests_drops_test_files(self, tmp_path):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n+keep()\n"
            "diff --git a/tests/test_app.py b/tests/test_app.py\n+drop()\n"
        )
        meta_path = tmp_path / "meta.json"
        proc = _run(
            _script("compress_diff.py"), diff, "--filter-tests", "--meta-file", str(meta_path)
        )
        assert proc.returncode == 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["filter_tests"] is True
        assert meta["total_files"] == 2
        assert meta["kept_files"] == 1
        assert "tests/test_app.py" in meta["dropped_test_files"]

    def test_no_meta_file_is_backward_compatible(self, tmp_path):
        # Omitting --meta-file must not change stdout or write anything.
        diff = "diff --git a/foo.py b/foo.py\n+keep()\n"
        proc = _run(_script("compress_diff.py"), diff)
        assert proc.returncode == 0
        assert "keep()" in proc.stdout
        assert not list(tmp_path.iterdir())


class TestCoverageLines:
    """Status report surfaces partial-coverage when the caller provides it (#120)."""

    def test_coverage_lines_when_truncated(self):
        inp = _status_input_sev("NEEDS_FIX", critical_count=1, open_count=3)
        inp["diff_truncated"] = True
        inp["total_files"] = 10
        inp["covered_files"] = 7
        out = _run_json(_script("render_status_report.py"), inp)
        assert "Diff truncated: yes" in out
        assert "Coverage: 7/10 files" in out
        assert "Status: NEEDS_FIX" in out

    def test_coverage_lines_omitted_by_default(self):
        out = _run_json(_script("render_status_report.py"), _status_input("PASS"))
        assert "Diff truncated" not in out
        assert "Coverage" not in out
        # report block still ends with the ruler; #176 XML trailer follows it
        assert out.splitlines()[-1] == "</zima-review>"


class TestDiffReorder:
    """#169: source-first reorder so docs can't starve core code of budget.

    PR #11/#166 evidence: alphabetical diff order put docs/superpowers/
    (31.6KB plan+spec) first; a 4K budget ate only docs and the core source
    file was invisible. Default behavior now stably reorders blocks
    source → test → docs (docs last), so truncation eats docs first.
    """

    DIFF = (
        "diff --git a/docs/plan.md b/docs/plan.md\n+doc line\n"
        "diff --git a/src/core.ts b/src/core.ts\n+core change\n"
        "diff --git a/tests/unit/x.spec.ts b/tests/unit/x.spec.ts\n+test\n"
        "diff --git a/README.md b/README.md\n+readme\n"
        "diff --git a/src/util.ts b/src/util.ts\n+util change\n"
    )

    def test_default_reorder_puts_source_first_docs_last(self, tmp_path):
        meta_path = tmp_path / "meta.json"
        proc = _run(_script("compress_diff.py"), self.DIFF, "--meta-file", str(meta_path))
        assert proc.returncode == 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("reordered") is True
        out = proc.stdout
        core_pos = out.index("src/core.ts")
        util_pos = out.index("src/util.ts")
        test_pos = out.index("x.spec.ts")
        plan_pos = out.index("docs/plan.md")
        assert core_pos < test_pos < plan_pos  # source before test before docs
        assert util_pos < test_pos  # stable within source class
        assert plan_pos < out.index("README.md")  # stable within docs class

    def test_small_budget_keeps_source_drops_docs(self, tmp_path):
        # Budget only fits the source files: docs must be the ones cut.
        meta_path = tmp_path / "meta.json"
        proc = _run(
            _script("compress_diff.py"),
            self.DIFF,
            "--max-len",
            "120",
            "--meta-file",
            str(meta_path),
        )
        assert proc.returncode == 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["diff_truncated"] is True
        assert "docs/plan.md" in meta["truncated_dropped_files"]
        assert "src/core.ts" not in meta["truncated_dropped_files"]

    def test_no_reorder_flag_preserves_input_order(self, tmp_path):
        meta_path = tmp_path / "meta.json"
        proc = _run(
            _script("compress_diff.py"),
            self.DIFF,
            "--no-reorder",
            "--meta-file",
            str(meta_path),
        )
        assert proc.returncode == 0
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("reordered") is False
        assert proc.stdout.index("docs/plan.md") < proc.stdout.index("src/core.ts")
