"""Unit tests for zima.execution.failure_guard (#202)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from zima.execution.failure_guard import (
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_FAILURE_THRESHOLD,
    FailureGuard,
    FailureGuardStore,
    GuardStateError,
    classify_execution_result,
    normalize_target,
)

T0 = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
VALID_XML = "<zima-review>\n<verdict>needs_fix</verdict>\n<summary>x</summary>\n</zima-review>"


def _now_fn(t):
    return lambda: t


def _guard(tmp_path, now=T0, **kw):
    return FailureGuard(FailureGuardStore(tmp_path), now=_now_fn(now), **kw)


def _target(**kw):
    base = dict(pjob_code="zima-pi-cr-job", repo="owner/repo", pr_number="42", head_sha="abc123")
    base.update(kw)
    return normalize_target(**base)


class TestNormalizeTarget:
    def test_repo_pr_head_normalized(self):
        t = normalize_target("Job", "Owner/Repo", "#42", "ABCdef")
        assert t.repo == "owner/repo"
        assert t.pr_number == "42"
        assert t.head_sha == "abcdef"

    def test_key_format_and_sanitization(self):
        assert _target().key() == "zima-pi-cr-job--owner__repo--42--abc123"

    def test_missing_head_uses_nohead_and_distinct_heads_distinct_keys(self):
        assert _target(head_sha="").key().endswith("--nohead")
        assert _target(head_sha="a1").key() != _target(head_sha="b2").key()

    def test_oversized_key_is_hash_truncated_within_filename_limit(self):
        # A repo at GitHub's 256-char limit ("/"→"__" can double it) plus the
        # other components blows past ext4's 255-byte filename limit; the key
        # must truncate to <=200 chars so state and lock filenames stay legal.
        long_repo = "a" * 256
        key = _target(repo=long_repo).key()
        assert len(key) <= 200
        assert len(f"{key}.json.lock") <= 255  # both state and lock filenames fit
        assert key.startswith("zima-pi-cr-job--" + "a" * 170)  # readable prefix kept
        assert key[-14:-12] == "--" and len(key[-12:]) == 12  # hash suffix shape

    def test_truncated_keys_remain_deterministic_and_distinct(self):
        repo_a = "a" * 256
        repo_b = "b" * 256
        assert _target(repo=repo_a).key() == _target(repo=repo_a).key()
        assert _target(repo=repo_a).key() != _target(repo=repo_b).key()
        # Short targets keep the plain readable form (no hash suffix).
        assert _target().key() == "zima-pi-cr-job--owner__repo--42--abc123"


class TestClassify:
    @pytest.mark.parametrize("status", ["success", "failed"])
    def test_verdict_is_valid_review_and_clears(self, status):
        # A verdict in stdout wins even when postExec flipped status to failed.
        o = classify_execution_result(
            status=status, returncode=1, stdout=VALID_XML, expect_review_verdict=True
        )
        assert o.kind == "valid_review" and o.clears_streak and not o.countable_failure

    def test_success_without_verdict_is_invalid_when_verdict_expected(self):
        o = classify_execution_result(
            status="success", returncode=0, stdout="no xml here", expect_review_verdict=True
        )
        assert o.kind == "invalid_no_review" and o.countable_failure

    def test_success_without_verdict_is_valid_other_when_not_expected(self):
        o = classify_execution_result(
            status="success", returncode=0, stdout="ok", expect_review_verdict=False
        )
        assert o.kind == "valid_other" and o.clears_streak

    def test_startup_failure(self):
        o = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        assert o.kind == "invalid_startup" and o.countable_failure

    def test_process_failure_with_output(self):
        o = classify_execution_result(
            status="failed", returncode=1, stdout="some output", expect_review_verdict=True
        )
        assert o.kind == "invalid_process" and o.countable_failure

    def test_timeout_and_cancelled(self):
        assert (
            classify_execution_result(
                status="timeout", returncode=124, stdout="", expect_review_verdict=True
            ).kind
            == "invalid_timeout"
        )
        assert classify_execution_result(
            status="cancelled", returncode=130, stdout="", expect_review_verdict=True
        ).countable_failure

    def test_skipped_never_counts(self):
        o = classify_execution_result(
            status="skipped", returncode=0, stdout="", expect_review_verdict=True
        )
        assert o.kind == "skipped" and not o.countable_failure and not o.clears_streak

    def test_truncated_block_counts_as_invalid(self):
        truncated = "<zima-review>\n<verdict>needs_fix</verdict>\n<summ"
        o = classify_execution_result(
            status="success", returncode=0, stdout=truncated, expect_review_verdict=True
        )
        assert o.kind == "invalid_no_review" and o.countable_failure

    def test_truncated_block_with_timeout_status(self):
        truncated = "<zima-review>\n<verdict>needs_fix</verdict>\n<summ"
        o = classify_execution_result(
            status="timeout", returncode=124, stdout=truncated, expect_review_verdict=True
        )
        assert o.kind == "invalid_timeout" and o.countable_failure

    def test_verdictless_closed_block_counts_as_invalid(self):
        no_verdict = "<zima-review><summary>x</summary></zima-review>"
        o = classify_execution_result(
            status="success", returncode=0, stdout=no_verdict, expect_review_verdict=True
        )
        assert o.kind == "invalid_no_review" and o.countable_failure

    def test_explicit_needs_discussion_in_wellformed_block_is_valid(self):
        discussion = (
            "<zima-review><verdict>needs_discussion</verdict>"
            "<summary>unclear</summary></zima-review>"
        )
        o = classify_execution_result(
            status="success", returncode=0, stdout=discussion, expect_review_verdict=True
        )
        assert o.kind == "valid_review" and o.clears_streak and not o.countable_failure

    def test_status_line_report_only_is_valid_and_clears(self):
        # Spec §5.1: text-only agent with a full status-report block ending in
        # a Status: line (scheduler's grep contract) — no XML anywhere.
        report = "## Code Review Report\n\nFindings: none\n\nStatus: PASS\n"
        o = classify_execution_result(
            status="success", returncode=0, stdout=report, expect_review_verdict=True
        )
        assert o.kind == "valid_review" and o.clears_streak and not o.countable_failure

    def test_status_line_needs_fix_valid_despite_postexec_flip(self):
        o = classify_execution_result(
            status="failed",  # postExec flipped the run after a valid review
            returncode=1,
            stdout="Findings: 2 issues\n\nStatus: NEEDS_FIX\n",
            expect_review_verdict=True,
        )
        assert o.kind == "valid_review" and o.clears_streak and not o.countable_failure

    def test_text_only_without_status_line_or_xml_is_invalid(self):
        o = classify_execution_result(
            status="success",
            returncode=0,
            stdout="looked at it, all good",  # neither Status: line nor XML
            expect_review_verdict=True,
        )
        assert o.kind == "invalid_no_review" and o.countable_failure


class TestGuardRules:
    def test_threshold_reached_sets_cooldown(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail, execution_id="e1")
        assert g.check(t) is None  # streak 1 < threshold 2
        g.record(t, fail, execution_id="e2")
        reason = g.check(t)
        assert reason is not None
        assert "next allowed at" in reason
        expected = (
            (T0 + timedelta(minutes=DEFAULT_COOLDOWN_MINUTES)).isoformat().replace("+00:00", "Z")
        )
        assert expected in reason

    def test_cooldown_expired_allows_next_attempt(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail)
        g.record(t, fail)
        later = _guard(tmp_path, now=T0 + timedelta(minutes=61))
        assert later.check(t) is None

    def test_valid_review_clears_state(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail)
        ok = classify_execution_result(
            status="success", returncode=0, stdout=VALID_XML, expect_review_verdict=True
        )
        g.record(t, ok)
        store = FailureGuardStore(tmp_path)
        assert not store.path_for(t).exists()
        assert not store._lock_path_for(t).exists()  # clear() removes the lock too

    def test_skipped_outcome_is_not_recorded(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        skipped = classify_execution_result(
            status="skipped", returncode=0, stdout="", expect_review_verdict=True
        )
        g.record(t, skipped)
        store = FailureGuardStore(tmp_path)
        assert not store.path_for(t).exists()
        # Neutral outcomes return BEFORE taking the lock: no lock file either.
        assert not store._lock_path_for(t).exists()

    def test_env_threshold_override_and_invalid_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIMA_FAILURE_GUARD_THRESHOLD", "1")
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail)
        assert g.check(t) is not None  # threshold 1 → immediate cooldown
        monkeypatch.setenv("ZIMA_FAILURE_GUARD_THRESHOLD", "not-a-number")
        assert _guard(tmp_path)._threshold == DEFAULT_FAILURE_THRESHOLD
        monkeypatch.setenv("ZIMA_FAILURE_GUARD_THRESHOLD", "999")
        assert _guard(tmp_path)._threshold == DEFAULT_FAILURE_THRESHOLD

    def test_env_cooldown_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ZIMA_FAILURE_GUARD_COOLDOWN_MINUTES", "5")
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail)
        g.record(t, fail)
        later = _guard(tmp_path, now=T0 + timedelta(minutes=6))
        assert later.check(t) is None
        monkeypatch.setenv("ZIMA_FAILURE_GUARD_COOLDOWN_MINUTES", "0")
        assert _guard(tmp_path)._cooldown == DEFAULT_COOLDOWN_MINUTES


class TestStore:
    def test_roundtrip_and_corrupt_fail_closed(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail, execution_id="e1")
        path = FailureGuardStore(tmp_path).path_for(t)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["failure_streak"] == 1 and data["last_execution_id"] == "e1"

        path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(GuardStateError):
            g.check(t)
        with pytest.raises(GuardStateError):
            g.record(t, fail)  # never silently reset a corrupt streak

    def test_state_and_lock_files_only_after_write(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail)
        names = set(p.name for p in tmp_path.iterdir())
        assert names == {f"{t.key()}.json", f"{t.key()}.json.lock"}

    def test_concurrent_records_do_not_lose_counts(self, tmp_path):
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        threads = [
            threading.Thread(target=_guard(tmp_path).record, args=(t, fail)) for _ in range(4)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        data = json.loads(FailureGuardStore(tmp_path).path_for(t).read_text(encoding="utf-8"))
        assert data["failure_streak"] == 4


class TestOverridesFlag:
    def test_roundtrip_and_default(self):
        from zima.models.pjob import Overrides

        assert Overrides().failure_guard_off is False
        assert Overrides.from_dict({}).failure_guard_off is False
        o = Overrides(failure_guard_off=True)
        assert not o.is_empty()
        assert Overrides.from_dict(o.to_dict()).failure_guard_off is True
