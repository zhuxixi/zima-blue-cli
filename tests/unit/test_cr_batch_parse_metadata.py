"""Regression tests for `parse_metadata.py` (pr-automation cr-batch skill).

These exist because of a real field-name bug: `gh pr view --json reviews`
emits `submittedAt` (camelCase), but the script sorted by `submitted_at`
(snake_case). `.get("submitted_at", "")` therefore returned "" for every
review, Python's stable sort left the array in GitHub's oldest-first order,
and the loop returned the *oldest* cc-cr-meta instead of the latest. On a PR
reviewed for multiple rounds this corrupts the round number, `previous_head_sha`,
and can trigger redundant reviews.

The pre-existing round-trip test in `test_cr_batch_contracts.py` used a single
review with a hand-written `submitted_at` key, so it shared the same wrong
assumption and never caught this. These tests exercise the real shapes:
multi-review inputs with gh-native `submittedAt`, the `--jq` stream variant
(`submitted_at`), out-of-order arrays, and Kimi comments that must be ignored.

Scripts are plain stdin/stdout CLIs, exercised as subprocess black boxes —
the same way the skill invokes them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = (
    _REPO_ROOT / "plugins" / "pr-automation" / "skills" / "github-code-review-batch" / "scripts"
)

HEAD_SHA_A = "a" * 40
HEAD_SHA_B = "b" * 40
HEAD_SHA_C = "c" * 40


def _script(name: str) -> Path:
    return SCRIPTS / name


def _run(script: Path, stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_json(script: Path, obj: dict) -> str:
    return _run(script, json.dumps(obj)).stdout


def _cc_body(round_: int, head_sha: str, timestamp: str) -> str:
    """A minimal CC review body carrying a parseable cc-cr-meta block."""
    meta = {
        "round": round_,
        "pr_number": 255,
        "head_sha": head_sha,
        "previous_head_sha": None,
        "total_issues": 0,
        "issues": [],
        "timestamp": timestamp,
    }
    return (
        f"<!-- cc-cr-meta\n{json.dumps(meta)}\n-->\n\n"
        f"### Code Review | Round-{round_}\n\n🤖 Generated with Claude Code\n"
    )


def _kimi_body(round_: int, head_sha: str) -> str:
    """A Kimi-CLI review body (kimi-cr-meta, no CC signature)."""
    meta = {"round": round_, "pr_number": 255, "head_sha": head_sha}
    return f"<!-- kimi-cr-meta\n{json.dumps(meta)}\n-->\n\nKimi review\n"


class TestParsesLatestMeta:
    """The core regression: with multiple cc-cr-meta reviews, return the newest."""

    def test_picks_latest_by_submitted_at_camelcase(self):
        """gh --json reviews emits submittedAt (camelCase) — the bug's real shape.

        Array is deliberately newest-first so passing requires the sort to
        actually fire (a no-op stable sort would return round 1 here).
        """
        reviews = {
            "reviews": [
                {
                    "body": _cc_body(2, HEAD_SHA_B, "2026-06-17T11:00:00Z"),
                    "submittedAt": "2026-06-17T11:00:00Z",
                    "author": {"login": "zhuxixi"},
                    "authorAssociation": "OWNER",
                },
                {
                    "body": _cc_body(1, HEAD_SHA_A, "2026-06-17T10:00:00Z"),
                    "submittedAt": "2026-06-17T10:00:00Z",
                    "author": {"login": "zhuxixi"},
                    "authorAssociation": "OWNER",
                },
            ]
        }
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews))
        assert parsed["round"] == 2
        assert parsed["head_sha"] == HEAD_SHA_B

    def test_picks_latest_by_submitted_at_snakecase(self):
        """The --jq stream renames the field to submitted_at; still must work."""
        # Newest (round 2) placed FIRST in the stream to make a no-op sort fail.
        stream = "\n".join(
            json.dumps(rec)
            for rec in [
                {
                    "body": _cc_body(2, HEAD_SHA_B, "2026-06-17T11:00:00Z"),
                    "submitted_at": "2026-06-17T11:00:00Z",
                },
                {
                    "body": _cc_body(1, HEAD_SHA_A, "2026-06-17T10:00:00Z"),
                    "submitted_at": "2026-06-17T10:00:00Z",
                },
            ]
        )
        parsed = json.loads(_run(_script("parse_metadata.py"), stream).stdout)
        assert parsed["round"] == 2
        assert parsed["head_sha"] == HEAD_SHA_B

    def test_three_rounds_real_world_shape(self):
        """Mirrors PR #255: round 1/2/3 with increasing timestamps → round 3."""
        reviews = {
            "reviews": [
                {
                    "body": _cc_body(r, sha, ts),
                    "submittedAt": ts,
                    "author": {"login": "zhuxixi"},
                    "authorAssociation": "OWNER",
                }
                for r, sha, ts in [
                    (1, HEAD_SHA_A, "2026-06-17T16:32:34Z"),
                    (2, HEAD_SHA_B, "2026-06-17T16:40:50Z"),
                    (3, HEAD_SHA_C, "2026-06-18T14:42:40Z"),
                ]
            ]
        }
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews))
        assert parsed["round"] == 3
        assert parsed["head_sha"] == HEAD_SHA_C

    def test_ignores_kimi_cr_meta(self):
        """kimi-cr-meta reviews (no CC signature) must never be returned."""
        reviews = {
            "reviews": [
                {
                    "body": _cc_body(1, HEAD_SHA_A, "2026-06-17T10:00:00Z"),
                    "submittedAt": "2026-06-17T10:00:00Z",
                    "author": {"login": "zhuxixi"},
                    "authorAssociation": "OWNER",
                },
                {
                    "body": _kimi_body(9, HEAD_SHA_B),
                    "submittedAt": "2026-06-18T20:00:00Z",  # later, but Kimi
                    "author": {"login": "zhuxixi"},
                    "authorAssociation": "OWNER",
                },
            ]
        }
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews))
        assert parsed["round"] == 1  # the CC one, not Kimi round 9
        assert parsed["head_sha"] == HEAD_SHA_A

    def test_null_submitted_at_does_not_crash(self):
        """Missing/null timestamp must coerce to "" (TypeError on None < str)."""
        reviews = {
            "reviews": [
                {
                    "body": _cc_body(1, HEAD_SHA_A, "2026-06-17T10:00:00Z"),
                    "submittedAt": None,
                    "author": {"login": "zhuxixi"},
                    "authorAssociation": "OWNER",
                },
                {
                    "body": _cc_body(2, HEAD_SHA_B, "2026-06-17T11:00:00Z"),
                    "submittedAt": "2026-06-17T11:00:00Z",
                    "author": {"login": "zhuxixi"},
                    "authorAssociation": "OWNER",
                },
            ]
        }
        proc = _run(_script("parse_metadata.py"), json.dumps(reviews))
        assert proc.returncode == 0, proc.stderr
        parsed = json.loads(proc.stdout)
        assert parsed["round"] == 2  # the one with a real timestamp wins


class TestRobustness:
    def test_empty_reviews_returns_empty_object(self):
        parsed = json.loads(_run_json(_script("parse_metadata.py"), {"reviews": []}))
        assert parsed == {}

    def test_no_cc_marker_returns_empty_object(self):
        reviews = {
            "reviews": [
                {
                    "body": "just a normal human comment",
                    "submittedAt": "2026-06-17T10:00:00Z",
                    "author": {"login": "someone"},
                    "authorAssociation": "OWNER",
                }
            ]
        }
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews))
        assert parsed == {}
