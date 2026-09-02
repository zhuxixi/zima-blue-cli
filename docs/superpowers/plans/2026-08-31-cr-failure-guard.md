# CR Failure Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop burning paid model calls on a CR target `(pjob, repo, pr_number, head_sha)` whose consecutive executions produced no valid review, by skipping agent launch during a cooldown window.

**Architecture:** A new stdlib-only module `zima/execution/failure_guard.py` owns all guard logic (pure classification + atomic per-target state files under `<ZIMA_HOME>/state/failure-guard/`). The executor checks the guard after preExec scan (SkipAction → SKIPPED, no postExec) and records the outcome in the `finally` block. The operator override travels through `Overrides.failure_guard_off` → CLI `--overrides` JSON → background runner — no background_runner or daemon changes needed.

**Tech Stack:** Python 3.10+, dataclasses, pytest, stdlib only (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-08-31-cr-failure-guard-design.md` (approved 2026-08-31)

## Global Constraints

- Worktree: all work happens in this worktree (`/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-202-cr-failure-guard`); use `git -C <WT>` for git ops. Never touch the main checkout.
- Defaults: `failure_threshold=2`, `cooldown_minutes=60`; env overrides `ZIMA_FAILURE_GUARD_THRESHOLD` / `ZIMA_FAILURE_GUARD_COOLDOWN_MINUTES` (valid ranges 1..10 and 1..1440; invalid values fall back to defaults).
- Skip semantics: cooldown hit raises `SkipAction` inside the preExec block → `SKIPPED`, no agent launch, no postExec, no label changes.
- Classification: `NEEDS_FIX` / `PASS` / `NO_NEW_COMMITS` are VALID (they clear the streak); startup errors, timeout, crashes, and rc=0-without-verdict are countable failures.
- `--dedup-off` must NOT bypass the guard; only `Overrides.failure_guard_off` (CLI `--failure-guard-off`) bypasses the check — and it still records outcomes.
- Corrupt state = fail closed (SkipAction with a clear message); never silently reset a corrupt streak to 0. Guard-observability failures during *recording* must not fail the execution (print a Warning).
- No new third-party dependencies; stdlib only. No secrets in code, logs, or state files.
- Black at 100 chars (`uv run black zima/ tests/ --line-length 100`), ruff clean (`uv run ruff check zima/ tests/`), Google-style docstrings, English comments, conventional commits (`feat(cr): ...`).
- Tests must be isolated: `tmp_path` / `isolated_zima_home` fixtures only — never touch the real `~/.zima`.
- `uv run` works inside the worktree (first run syncs `.venv` from `uv.lock`; untracked, fine).

---

### Task 1: `zima/execution/failure_guard.py` core module + unit tests

**Files:**
- Create: `zima/execution/failure_guard.py`
- Test: `tests/unit/test_failure_guard.py`

**Interfaces:**
- Consumes: `zima.utils.get_zima_home`, `zima.execution.actions_runner.normalize_pr_number`, `zima.review.parser.ReviewParser`
- Produces (Task 2 consumes these exact names):
  - `normalize_target(pjob_code: str, repo: str, pr_number: str, head_sha: str) -> FailureTarget`
  - `FailureTarget.key() -> str`, `FailureTarget.to_dict() -> dict`
  - `classify_execution_result(*, status: str, returncode: int, stdout: str, expect_review_verdict: bool) -> GuardOutcome`
  - `GuardOutcome.kind`, `GuardOutcome.countable_failure`, `GuardOutcome.clears_streak`
  - `FailureGuard(store: FailureGuardStore | None = None, *, threshold: int | None = None, cooldown_minutes: int | None = None, now: Callable[[], datetime] | None = None)`
  - `FailureGuard.check(target) -> str | None` (skip reason or None; raises `GuardStateError`)
  - `FailureGuard.record(target, outcome: GuardOutcome, execution_id: str = "") -> None`
  - `FailureGuardStore(base_dir: Path | None = None)` with `.path_for(target) -> Path`
  - `GuardStateError`
  - `DEFAULT_FAILURE_THRESHOLD = 2`, `DEFAULT_COOLDOWN_MINUTES = 60`

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_failure_guard.py`:

```python
"""Unit tests for zima.execution.failure_guard (#202)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        assert classify_execution_result(
            status="timeout", returncode=124, stdout="", expect_review_verdict=True
        ).kind == "invalid_timeout"
        assert classify_execution_result(
            status="cancelled", returncode=130, stdout="", expect_review_verdict=True
        ).countable_failure

    def test_skipped_never_counts(self):
        o = classify_execution_result(
            status="skipped", returncode=0, stdout="", expect_review_verdict=True
        )
        assert o.kind == "skipped" and not o.countable_failure and not o.clears_streak


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
        expected = (T0 + timedelta(minutes=DEFAULT_COOLDOWN_MINUTES)).isoformat().replace(
            "+00:00", "Z"
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
        assert not FailureGuardStore(tmp_path).path_for(t).exists()

    def test_skipped_outcome_is_not_recorded(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        skipped = classify_execution_result(
            status="skipped", returncode=0, stdout="", expect_review_verdict=True
        )
        g.record(t, skipped)
        assert not FailureGuardStore(tmp_path).path_for(t).exists()

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

    def test_no_tmp_files_left_after_write(self, tmp_path):
        g = _guard(tmp_path)
        t = _target()
        fail = classify_execution_result(
            status="failed", returncode=1, stdout="", expect_review_verdict=True
        )
        g.record(t, fail)
        assert [p.name for p in tmp_path.iterdir()] == [f"{t.key()}.json"]

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-202-cr-failure-guard && uv run pytest tests/unit/test_failure_guard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'zima.execution.failure_guard'`

- [ ] **Step 3: Implement `zima/execution/failure_guard.py`**

```python
"""Failure guard — cooldown after repeated invalid CR executions (#202).

Distinct from nearby mechanisms with similar shapes:

- webhook server ``_dup_key``: 60s transport dedup for event redelivery;
- executor dedup (#181): same (repo, pr, head) already running or recently
  succeeded — prevents parallel duplicate *reviews*;
- scan_pr failure skip-set (#158): polling path avoids re-picking a PR that
  failed within 90min — does not cover the pinned webhook/manual path;
- **this module**: after N consecutive executions that produced no valid
  review, stop launching the paid agent for a cooldown window — prevents
  failure-retry cost burn (issue #202, e.g. pi-agent-board PR #43: 13s +
  736s + 466s of paid calls with zero review output).

Spec: docs/superpowers/specs/2026-08-31-cr-failure-guard-design.md
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from zima.execution.actions_runner import normalize_pr_number
from zima.utils import get_zima_home

DEFAULT_FAILURE_THRESHOLD = 2
DEFAULT_COOLDOWN_MINUTES = 60
MAX_FAILURE_THRESHOLD = 10
MAX_COOLDOWN_MINUTES = 24 * 60

_ENV_THRESHOLD = "ZIMA_FAILURE_GUARD_THRESHOLD"
_ENV_COOLDOWN = "ZIMA_FAILURE_GUARD_COOLDOWN_MINUTES"

_SAFE_PART = re.compile(r"[^a-z0-9._-]+")


def _sanitize(part: str, default: str) -> str:
    """Make a target component safe for a filesystem key."""
    cleaned = _SAFE_PART.sub("_", str(part or "").strip().lower())
    return cleaned or default


def _fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ts(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _env_int(name: str, default: int, min_v: int, max_v: int) -> int:
    """Read an int env var with bounds; invalid/missing falls back to default."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_v or value > max_v:
        return default
    return value


class GuardStateError(Exception):
    """Guard state is unreadable/corrupt — callers must fail closed."""


@dataclass(frozen=True)
class FailureTarget:
    """Normalized identity of a review target."""

    pjob_code: str
    repo: str
    pr_number: str
    head_sha: str

    def key(self) -> str:
        """Filesystem-safe unique key for this target."""
        return "--".join(
            [
                _sanitize(self.pjob_code, "nopjob"),
                _sanitize(self.repo.replace("/", "__"), "norepo"),
                _sanitize(self.pr_number, "nopr"),
                _sanitize(self.head_sha, "nohead"),
            ]
        )

    def to_dict(self) -> dict:
        return {
            "pjob": self.pjob_code,
            "repo": self.repo,
            "pr_number": self.pr_number,
            "head_sha": self.head_sha,
        }


def normalize_target(pjob_code: str, repo: str, pr_number: str, head_sha: str) -> FailureTarget:
    """Normalize a target the same way executor scan validation does."""
    return FailureTarget(
        pjob_code=str(pjob_code or "").strip(),
        repo=str(repo or "").strip().lower(),
        pr_number=normalize_pr_number(pr_number or ""),
        head_sha=str(head_sha or "").strip().lower(),
    )


@dataclass(frozen=True)
class GuardOutcome:
    """Classification of one execution for guard accounting."""

    kind: str
    countable_failure: bool
    clears_streak: bool


def _has_review_verdict(stdout: str) -> bool:
    """True when stdout carries a parseable <zima-review> verdict."""
    if "<zima-review>" not in (stdout or ""):
        return False
    from zima.review.parser import ReviewParser

    try:
        parsed = ReviewParser.parse(stdout)
    except Exception:
        return False
    return bool(parsed and parsed.verdict)


def classify_execution_result(
    *,
    status: str,
    returncode: int,
    stdout: str,
    expect_review_verdict: bool,
) -> GuardOutcome:
    """Classify one terminal execution (pure function).

    A verdict in stdout always wins, even when postExec action errors flipped
    the status to failed afterwards (the review itself is valid). Skipped
    executions are neutral — they never touch the streak.
    """
    if status == "skipped":
        return GuardOutcome("skipped", countable_failure=False, clears_streak=False)
    if _has_review_verdict(stdout):
        return GuardOutcome("valid_review", countable_failure=False, clears_streak=True)
    if status == "success":
        if expect_review_verdict:
            return GuardOutcome("invalid_no_review", countable_failure=True, clears_streak=False)
        return GuardOutcome("valid_other", countable_failure=False, clears_streak=True)
    if status == "timeout":
        return GuardOutcome("invalid_timeout", countable_failure=True, clears_streak=False)
    if status in ("failed", "cancelled", "dead"):
        if returncode != 0 and not stdout:
            return GuardOutcome("invalid_startup", countable_failure=True, clears_streak=False)
        return GuardOutcome("invalid_process", countable_failure=True, clears_streak=False)
    return GuardOutcome("skipped", countable_failure=False, clears_streak=False)


@dataclass
class GuardState:
    """Persistent failure-guard state for one target."""

    target: dict = field(default_factory=dict)
    failure_streak: int = 0
    last_failure_at: str = ""
    cooldown_until: str = ""
    last_failure_kind: str = ""
    last_execution_id: str = ""

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "failure_streak": self.failure_streak,
            "last_failure_at": self.last_failure_at,
            "cooldown_until": self.cooldown_until,
            "last_failure_kind": self.last_failure_kind,
            "last_execution_id": self.last_execution_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GuardState":
        if not isinstance(data, dict):
            raise ValueError("guard state must be a JSON object")
        streak = data.get("failure_streak", 0)
        if not isinstance(streak, int) or isinstance(streak, bool) or streak < 0:
            raise ValueError(f"invalid failure_streak: {streak!r}")
        for key in ("last_failure_at", "cooldown_until", "last_failure_kind", "last_execution_id"):
            if not isinstance(data.get(key, ""), str):
                raise ValueError(f"invalid {key}: {data.get(key)!r}")
        target = data.get("target")
        return cls(
            target=target if isinstance(target, dict) else {},
            failure_streak=streak,
            last_failure_at=data.get("last_failure_at", ""),
            cooldown_until=data.get("cooldown_until", ""),
            last_failure_kind=data.get("last_failure_kind", ""),
            last_execution_id=data.get("last_execution_id", ""),
        )


@contextmanager
def _locked(state_path: Path):
    """Best-effort advisory lock across read-modify-write.

    Atomic temp-file replace already prevents torn writes; the lock prevents
    lost increments under concurrent recorders. Lock failures degrade to
    unlocked operation rather than breaking the guard.
    """
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    try:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except OSError:
            pass
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


class FailureGuardStore:
    """Atomic per-target JSON state under <zima_home>/state/failure-guard/."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = Path(base_dir) if base_dir else get_zima_home() / "state" / "failure-guard"

    def path_for(self, target: FailureTarget) -> Path:
        return self._base / f"{target.key()}.json"

    def read(self, target: FailureTarget) -> GuardState:
        path = self.path_for(target)
        if not path.exists():
            return GuardState(target=target.to_dict())
        try:
            return GuardState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            raise GuardStateError(f"failure-guard state unreadable: {path}: {exc}") from exc

    def write(self, target: FailureTarget, state: GuardState) -> None:
        path = self.path_for(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state.to_dict(), fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def clear(self, target: FailureTarget) -> None:
        try:
            self.path_for(target).unlink()
        except FileNotFoundError:
            pass


class FailureGuard:
    """Cooldown policy over a FailureGuardStore."""

    def __init__(
        self,
        store: Optional[FailureGuardStore] = None,
        *,
        threshold: Optional[int] = None,
        cooldown_minutes: Optional[int] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._store = store or FailureGuardStore()
        self._threshold = (
            threshold
            if threshold is not None
            else _env_int(_ENV_THRESHOLD, DEFAULT_FAILURE_THRESHOLD, 1, MAX_FAILURE_THRESHOLD)
        )
        self._cooldown = (
            cooldown_minutes
            if cooldown_minutes is not None
            else _env_int(_ENV_COOLDOWN, DEFAULT_COOLDOWN_MINUTES, 1, MAX_COOLDOWN_MINUTES)
        )
        self._now = now or (lambda: datetime.now(timezone.utc))

    def check(self, target: FailureTarget) -> Optional[str]:
        """Return a skip reason when the target is in cooldown, else None.

        Raises:
            GuardStateError: state is unreadable — caller must fail closed.
        """
        with _locked(self._store.path_for(target)):
            state = self._store.read(target)
        if not state.cooldown_until:
            return None
        until = _parse_ts(state.cooldown_until)
        if until is None:
            raise GuardStateError(
                f"failure-guard: invalid cooldown_until {state.cooldown_until!r} "
                f"for target {target.key()}"
            )
        if self._now() >= until:
            return None  # expired — allow this attempt; streak kept for the next failure
        return (
            f"failure-guard: cooldown active for ({target.repo}, PR "
            f"#{target.pr_number}, head={target.head_sha or 'unknown'}) after "
            f"{state.failure_streak} invalid executions; next allowed at "
            f"{state.cooldown_until}; override with --failure-guard-off"
        )

    def record(self, target: FailureTarget, outcome: GuardOutcome, execution_id: str = "") -> None:
        """Record one terminal outcome for the target."""
        if outcome.kind == "skipped":
            return
        with _locked(self._store.path_for(target)):
            if outcome.clears_streak:
                self._store.clear(target)
                return
            if not outcome.countable_failure:
                return
            state = self._store.read(target)  # GuardStateError propagates — never reset
            now = self._now()
            state.target = target.to_dict()
            state.failure_streak += 1
            state.last_failure_at = _fmt_ts(now)
            state.last_failure_kind = outcome.kind
            state.last_execution_id = execution_id
            if state.failure_streak >= self._threshold:
                state.cooldown_until = _fmt_ts(now + timedelta(minutes=self._cooldown))
            self._store.write(target, state)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd <WT> && uv run pytest tests/unit/test_failure_guard.py -q`
Expected: PASS (all ~20 tests)

- [ ] **Step 5: Lint, format, commit**

Run: `cd <WT> && uv run ruff check zima/execution/failure_guard.py tests/unit/test_failure_guard.py && uv run black zima/execution/failure_guard.py tests/unit/test_failure_guard.py --line-length 100 && uv run pytest tests/unit/test_failure_guard.py -q`
Expected: clean + PASS

```bash
git -C <WT> add zima/execution/failure_guard.py tests/unit/test_failure_guard.py
git -C <WT> commit -m "feat(cr): failure guard core — classify outcomes, cooldown on repeated invalid executions (#202)"
```

---

### Task 2: Overrides flag + executor wiring + integration tests

**Files:**
- Modify: `zima/models/pjob.py` (Overrides dataclass, ~line 55-90)
- Modify: `zima/execution/executor.py` (two insertion points, see below)
- Test: `tests/integration/test_failure_guard_executor.py`

**Interfaces:**
- Consumes (from Task 1): `normalize_target`, `classify_execution_result`, `FailureGuard`, `GuardStateError`
- Produces: `Overrides.failure_guard_off: bool = False` (Task 3 CLI sets it); executor behavior: cooldown → `SKIPPED` before agent launch; terminal outcome recorded in `finally`

- [ ] **Step 1: Add the Overrides field**

In `zima/models/pjob.py`, `Overrides` dataclass: add the field and update `is_empty()`:

```python
    failure_guard_off: bool = False
```

Docstring addition for the class Attributes list:

```python
        failure_guard_off: Operator override — bypass the failure-guard
            cooldown check for this run (#202). Does not bypass the dedup
            guard (use --dedup-off for that); outcomes are still recorded.
```

`is_empty()`:

```python
    def is_empty(self) -> bool:
        """Check if overrides are empty."""
        return not any(
            [
                self.agent_params,
                self.variable_values,
                self.env_vars,
                self.pmg_params,
                self.failure_guard_off,
            ]
        )
```

- [ ] **Step 2: Write the failing integration tests** — create `tests/integration/test_failure_guard_executor.py`:

```python
"""Integration tests: failure guard wired into PJobExecutor (#202)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from tests.base import TestIsolator
from zima.execution.executor import PJobExecutor
from zima.execution.failure_guard import FailureGuardStore, normalize_target
from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction
from zima.models.pjob import Overrides, PJobConfig
from zima.utils import get_zima_home

REPO = "owner/repo"
PR = "42"
HEAD = "abc123def456"
VERDICT_OK = "<zima-review>\n<verdict>approved</verdict>\n<summary>ok</summary>\n</zima-review>"


def _pin():
    return Overrides(variable_values={"repo": REPO, "pr_number": PR, "head_sha": HEAD})


def _mock_provider(executor):
    provider = MagicMock()
    provider.verify_pr_label.return_value = True
    provider.fetch_diff.return_value = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ +1\n"
    registry = MagicMock()
    registry.get.return_value = provider
    executor._actions_runner._registry = registry
    return provider


def _write_guard_state(head_sha, *, streak, cooldown_until):
    target = normalize_target("fg-pjob", REPO, PR, head_sha)
    store = FailureGuardStore(get_zima_home() / "state" / "failure-guard")
    path = store.path_for(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "target": target.to_dict(),
                "failure_streak": streak,
                "last_failure_at": "2026-08-31T00:00:00Z",
                "cooldown_until": cooldown_until,
                "last_failure_kind": "invalid_process",
                "last_execution_id": "seed",
            }
        ),
        encoding="utf-8",
    )
    return path


class _Base(TestIsolator):
    @pytest.fixture
    def configs(self, isolated_zima_home, config_manager):
        from zima.models.workflow import WorkflowConfig

        config_manager.save_config(
            "agent",
            "fg-agent",
            {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "fg-agent", "name": "FG Agent"},
                "spec": {"type": "pi", "parameters": {"mockCommand": ["echo", VERDICT_OK]}},
            },
        )
        wf = WorkflowConfig.create(
            code="fg-wf", name="FG Workflow", template="Review {{repo}}#{{pr_number}}", variables=[]
        )
        config_manager.save_config("workflow", "fg-wf", wf.to_dict())
        pjob = PJobConfig.create(code="fg-pjob", name="FG PJob", agent="fg-agent", workflow="fg-wf")
        pjob.spec.actions = ActionsConfig(
            pre_exec=[
                PreExecAction(
                    condition="always", type="scan_pr", repo=REPO, label="zima:needs-review"
                )
            ],
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    repo=REPO,
                    issue=PR,
                )
            ],
        )
        config_manager.save_config("pjob", "fg-pjob", pjob.to_dict())

    def _agent(self, config_manager, mock_command):
        data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "fg-agent", "name": "FG Agent"},
            "spec": {"type": "pi", "parameters": {"mockCommand": mock_command}},
        }
        config_manager.save_config("agent", "fg-agent", data)


class TestCooldownSkip(_Base):
    def test_cooldown_skips_before_agent_launch(self, configs, isolated_zima_home):
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace(
            "+00:00", "Z"
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        executor = PJobExecutor()
        provider = _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        assert result.status.value == "skipped"
        assert "cooldown" in result.stderr
        assert "next allowed at" in result.stderr
        provider.add_label.assert_not_called()  # no postExec on SKIPPED

    def test_corrupt_state_fails_closed(self, configs, isolated_zima_home):
        path = _write_guard_state(HEAD, streak=1, cooldown_until="")
        path.write_text("{ corrupted", encoding="utf-8")
        executor = PJobExecutor()
        _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        assert result.status.value == "skipped"
        assert "fail closed" in result.stderr

    def test_dedup_off_does_not_bypass_guard(self, configs, isolated_zima_home):
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace(
            "+00:00", "Z"
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        executor = PJobExecutor()
        _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin(), dedup_off=True)
        assert result.status.value == "skipped"

    def test_failure_guard_off_bypasses_check_but_still_records(
        self, configs, config_manager, isolated_zima_home
    ):
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace(
            "+00:00", "Z"
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        self._agent(config_manager, ["false"])  # keep failing
        executor = PJobExecutor()
        _mock_provider(executor)
        overrides = _pin()
        overrides.failure_guard_off = True
        result = executor.execute("fg-pjob", overrides=overrides)
        assert result.status.value == "failed"  # ran despite cooldown
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        data = json.loads(
            FailureGuardStore(get_zima_home() / "state" / "failure-guard")
            .path_for(target)
            .read_text(encoding="utf-8")
        )
        assert data["failure_streak"] == 3  # outcome still recorded


class TestRecording(_Base):
    def test_two_failures_then_cooldown_skip(self, configs, config_manager, isolated_zima_home):
        self._agent(config_manager, ["false"])
        for expected in ("failed", "failed"):
            executor = PJobExecutor()
            _mock_provider(executor)
            result = executor.execute("fg-pjob", overrides=_pin())
            assert result.status.value == expected
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        path = FailureGuardStore(get_zima_home() / "state" / "failure-guard").path_for(target)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["failure_streak"] == 2
        assert data["cooldown_until"]
        # Third attempt: skipped before launch, no further postExec.
        executor = PJobExecutor()
        provider = _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        assert result.status.value == "skipped"
        assert provider.add_label.call_count == 0

    def test_valid_review_clears_streak(self, configs, isolated_zima_home):
        _write_guard_state(HEAD, streak=1, cooldown_until="")
        executor = PJobExecutor()
        _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        assert result.status.value == "success"
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        path = FailureGuardStore(get_zima_home() / "state" / "failure-guard").path_for(target)
        assert not path.exists()

    def test_new_head_has_independent_budget(self, configs, isolated_zima_home):
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace(
            "+00:00", "Z"
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        executor = PJobExecutor()
        _mock_provider(executor)
        new_head = Overrides(
            variable_values={"repo": REPO, "pr_number": PR, "head_sha": "ffff00001111"}
        )
        result = executor.execute("fg-pjob", overrides=new_head)
        assert result.status.value == "success"  # new head is not blocked

    def test_needs_fix_verdict_is_valid_and_clears(self, configs, config_manager, isolated_zima_home):
        needs_fix = (
            "<zima-review>\n<verdict>needs_fix</verdict>\n<summary>issues</summary>\n</zima-review>"
        )
        self._agent(config_manager, ["echo", needs_fix])
        _write_guard_state(HEAD, streak=1, cooldown_until="")
        executor = PJobExecutor()
        provider = _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        # postExec failure branch fires (verdict needs_fix → effective rc 1)
        provider.add_label.assert_called()
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        path = FailureGuardStore(get_zima_home() / "state" / "failure-guard").path_for(target)
        assert not path.exists()  # NEEDS_FIX cleared the streak


class TestCliFlag:
    def test_run_passes_failure_guard_off_into_overrides(
        self, configs, isolated_zima_home, monkeypatch, cli_runner
    ):
        from zima.cli import app

        captured = {}

        class FakeExecutor:
            def execute(self, pjob_code, overrides=None, dry_run=False, keep_temp=False):
                captured["overrides"] = overrides
                from zima.execution.executor import ExecutionResult, ExecutionStatus

                return ExecutionResult(
                    pjob_code=pjob_code, status=ExecutionStatus.SUCCESS, command=["echo", "x"]
                )

        monkeypatch.setattr("zima.commands.pjob.PJobExecutor", FakeExecutor)
        result = cli_runner.invoke(
            app, ["pjob", "run", "fg-pjob", "--failure-guard-off", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert captured["overrides"].failure_guard_off is True
```

- [ ] **Step 3: Run integration tests to verify they fail**

Run: `cd <WT> && uv run pytest tests/integration/test_failure_guard_executor.py -q`
Expected: FAIL — cooldown skip tests fail (agent executes instead of skipping); `AttributeError: 'Overrides' object has no attribute 'failure_guard_off'` if Step 1 not yet applied.

- [ ] **Step 4: Wire the guard into `zima/execution/executor.py`**

**Edit A — imports** (add to the import block near `from zima.execution.history import ExecutionHistory`):

```python
from zima.execution.failure_guard import (
    FailureGuard,
    GuardStateError,
    classify_execution_result,
    normalize_target,
)
```

**Edit B — pre-launch check.** In `execute()`, immediately after the dedup `SkipAction` block (the `if not dry_run and not dedup_off and result.scan_pr_result:` block ending with `raise SkipAction("dedup: duplicate review skipped — ...")`) and before `except SkipAction as e:`, insert:

```python
                        # Failure guard (#202): stop burning paid calls on a
                        # target whose recent executions produced no valid
                        # review. Independent of the dedup guard above:
                        # --dedup-off bypasses dedup ONLY; only the explicit
                        # failure-guard override bypasses this check.
                        if not dry_run and result.scan_pr_result and not (
                            runtime_overrides and runtime_overrides.failure_guard_off
                        ):
                            _fg_target = normalize_target(
                                pjob_code=pjob_code,
                                repo=result.scan_pr_result.get("repo", ""),
                                pr_number=result.scan_pr_result.get("pr_number", ""),
                                head_sha=result.scan_pr_result.get("head_sha", ""),
                            )
                            try:
                                _fg_reason = FailureGuard().check(_fg_target)
                            except GuardStateError as _fg_exc:
                                _fg_reason = (
                                    "failure-guard: state unreadable — refusing to "
                                    f"start a paid execution (fail closed): {_fg_exc}"
                                )
                            if _fg_reason:
                                self._history.update_runtime_state(
                                    pjob_code,
                                    execution_id,
                                    failure_guard={
                                        "status": "cooldown_skip",
                                        "target": _fg_target.to_dict(),
                                        "reason": _fg_reason,
                                    },
                                )
                                raise SkipAction(_fg_reason)
```

**Edit C — outcome recording.** In the `finally` block, immediately after the action-error flip (`if result.status == ExecutionStatus.SUCCESS and result.action_errors: ...`) and before `# Cleanup temp directory`, insert:

```python
            # Failure-guard accounting (#202): once the terminal status is
            # final, record whether this execution produced a valid review.
            # Skipped / dry-run executions never touch the guard; the operator
            # override bypasses the check but still records outcomes so the
            # streak stays truthful. Recording failures must not fail the run.
            _fg_spr = getattr(result, "scan_pr_result", None) or {}
            if (
                not dry_run
                and result.status != ExecutionStatus.SKIPPED
                and _fg_spr.get("repo")
                and _fg_spr.get("pr_number")
            ):
                try:
                    _fg_outcome = classify_execution_result(
                        status=result.status.value,
                        returncode=result.returncode,
                        stdout=result.stdout,
                        expect_review_verdict=True,
                    )
                    _fg_target = normalize_target(
                        pjob_code=pjob_code,
                        repo=_fg_spr.get("repo", ""),
                        pr_number=_fg_spr.get("pr_number", ""),
                        head_sha=_fg_spr.get("head_sha", ""),
                    )
                    FailureGuard().record(_fg_target, _fg_outcome, execution_id=execution_id)
                    if _fg_outcome.countable_failure:
                        self._history.update_runtime_state(
                            pjob_code,
                            execution_id,
                            failure_guard={
                                "status": "recorded_failure",
                                "kind": _fg_outcome.kind,
                            },
                        )
                    elif _fg_outcome.clears_streak:
                        self._history.update_runtime_state(
                            pjob_code,
                            execution_id,
                            failure_guard={"status": "cleared"},
                        )
                except Exception as _fg_exc:  # noqa: BLE001 - observability must not fail the run
                    print(f"Warning: failure-guard record failed: {_fg_exc}")
```

- [ ] **Step 5: Run all guard tests to verify they pass**

Run: `cd <WT> && uv run pytest tests/unit/test_failure_guard.py tests/integration/test_failure_guard_executor.py -q`
Expected: PASS

- [ ] **Step 6: Lint, format, commit**

Run: `cd <WT> && uv run ruff check zima/ tests/ && uv run black zima/ tests/ --line-length 100 && uv run pytest tests/unit/test_failure_guard.py tests/integration/test_failure_guard_executor.py -q`
Expected: clean + PASS

```bash
git -C <WT> add zima/models/pjob.py zima/execution/executor.py tests/integration/test_failure_guard_executor.py
git -C <WT> commit -m "feat(cr): wire failure guard into executor — pre-launch cooldown skip + outcome recording (#202)"
```

---

### Task 3: CLI `--failure-guard-off` flag + docs + full regression

**Files:**
- Modify: `zima/commands/pjob.py` (`run` command — options list and overrides assembly)
- Modify: `CLAUDE.md` (add a short operational note)
- Test: covered by `TestCliFlag` in Task 2's test file (already written)

**Interfaces:**
- Consumes (from Task 2): `Overrides.failure_guard_off` — CLI only sets it; serialization to background_runner JSON is automatic (`Overrides.to_dict()` → `failureGuardOff` → `Overrides.from_dict`).

- [ ] **Step 1: Add the CLI option**

In `zima/commands/pjob.py` `run()`, add to the option list (next to `dedup_off`):

```python
    failure_guard_off: bool = typer.Option(
        False,
        "--failure-guard-off",
        help=(
            "Bypass the failure-guard cooldown for this run (operator override; "
            "the dedup guard still applies unless --dedup-off is also given)"
        ),
    ),
```

After the `overrides` assembly block (`if set_param: ...`), add:

```python
    if failure_guard_off:
        overrides.failure_guard_off = True
```

No change needed downstream: `overrides_json = json.dumps(overrides.to_dict()) if not overrides.is_empty() else "{}"` now serializes the flag, and `background_runner` deserializes it via `Overrides.from_dict`.

- [ ] **Step 2: Add CLAUDE.md operational note**

Append a short section to `CLAUDE.md` (place it near the other CR/executor gotchas):

```markdown
### Failure guard (#202)

Repeated invalid CR executions on the same `(pjob, repo, pr_number, head_sha)` target trip a cooldown: after `ZIMA_FAILURE_GUARD_THRESHOLD` (default 2) consecutive executions with no valid `<zima-review>` verdict, the executor skips agent launch for `ZIMA_FAILURE_GUARD_COOLDOWN_MINUTES` (default 60). The skip happens before launch (status `skipped`, no postExec, no label churn). State lives in `<ZIMA_HOME>/state/failure-guard/*.json`; a corrupt state file fails closed (skip, not run). `NEEDS_FIX` is a valid review and clears the streak. `--dedup-off` does NOT bypass this guard — use `zima pjob run --failure-guard-off` for a deliberate operator retry (outcomes are still recorded).
```

- [ ] **Step 3: Verify the CLI flag test passes**

Run: `cd <WT> && uv run pytest tests/integration/test_failure_guard_executor.py::TestCliFlag -q`
Expected: PASS

- [ ] **Step 4: Full regression**

Run: `cd <WT> && uv run pytest tests/ -q`
Expected: PASS (entire suite, including existing `tests/unit/test_cr_batch_contracts.py` and `tests/integration/test_pjob_lifecycle.py` — no regressions)

Run: `cd <WT> && uv run ruff check zima/ tests/ && uv run black --check zima/ tests/ --line-length 100`
Expected: clean

- [ ] **Step 5: Commit**

```bash
git -C <WT> add zima/commands/pjob.py CLAUDE.md
git -C <WT> commit -m "feat(cr): --failure-guard-off operator override + failure-guard ops note (#202)"
```

---

### Task 4: Post-implementation manual verification (user acceptance, U1)

**Files:** none (no code changes)

**Interfaces:** consumes Tasks 1–3 merged state.

- [ ] **Step 1:** With the user, pick a test PR carrying `zima:needs-review` (or create one). Run `zima pjob run <pi-cr-job> --set-var=repo=... --set-var=pr_number=... --set-var=head_sha=...` twice with an agent forced to fail (e.g. temporarily point to a bogus pi path or use a dry-run harness), then confirm the third attempt is skipped with the cooldown reason and `next allowed at` visible in `zima pjob status <pjob>` / the background log, and that no labels changed.
- [ ] **Step 2:** Push a new head to the PR, re-run, confirm the new head executes (independent budget).
- [ ] **Step 3:** Confirm `zima pjob run --failure-guard-off` deliberately bypasses the cooldown and the run is recorded.
- [ ] **Step 4:** Record the observed results (commands + outcomes) back on issue #202.

## Self-Review

**Spec coverage:**
- §5.1 classification (valid vs invalid; NEEDS_FIX valid; postExec errors don't convert valid review into failure) → Task 1 `classify_execution_result` + tests; Task 2 `test_needs_fix_verdict_is_valid_and_clears`
- §5.2 state shape/keying/normalization/atomic write/fail-closed → Task 1 store + tests
- §5.3 threshold/cooldown/clear/reset-on-new-head → Task 1 rules tests; Task 2 `test_new_head_has_independent_budget`
- §5.4 operator override separate from `--dedup-off`, still records → Task 2 `test_dedup_off_does_not_bypass_guard`, `test_failure_guard_off_bypasses_check_but_still_records`; Task 3 CLI flag
- §6 integration points (pre-launch check in preExec block; record in finally; observability into runtime state) → Task 2 Edits B/C
- §7 compatibility (no YAML schema change required; old Overrides JSON without the field defaults to False) → Task 1 `TestOverridesFlag`; Task 3 full regression
- A1–A8 automated acceptance → Tasks 1–3 tests; U1 → Task 4

**Placeholder scan:** none — all steps carry runnable code or exact commands.

**Type consistency:** `FailureTarget`/`GuardOutcome`/`FailureGuard` names identical across Tasks 1–2; `Overrides.failure_guard_off` identical across Tasks 2–3; test helpers (`_pin`, `_mock_provider`, `_write_guard_state`) defined once in the Task 2 test file and used throughout.
