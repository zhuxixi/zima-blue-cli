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

import hashlib
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
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

# Joined key components can far exceed ext4's 255-byte filename limit (a
# repo alone allows 256 chars, and "/" doubles to "__"), which would make
# record() fail ENAMETOOLONG (swallowed as a warning) while check() never
# finds the state — a silent fail-open (#202 advisory 2). Oversized keys are
# truncated with a sha256 suffix of the full key so filenames stay within
# limits AND unique. 200 leaves headroom for the ".json.lock" suffix.
_MAX_KEY_LEN = 200

# Spec §5.1: a review is valid when it has an explicit verdict/status output
# (PASS, NEEDS_FIX, NO_NEW_COMMITS) or a verifiable zima-review result. The
# ``Status:`` line is the scheduler's documented grep contract — every
# batch-skill version emits it — so text-only review agents count as valid.
_STATUS_LINE_RE = re.compile(r"^Status: (PASS|NEEDS_FIX|NO_NEW_COMMITS)\s*$", re.MULTILINE)


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
        """Filesystem-safe unique key for this target.

        Short targets keep the readable joined form; keys longer than
        ``_MAX_KEY_LEN`` are truncated and suffixed with a hash of the full
        key so the filename stays unique and under the 255-byte name limit.
        """
        full = "--".join(
            [
                _sanitize(self.pjob_code, "nopjob"),
                _sanitize(self.repo.replace("/", "__"), "norepo"),
                _sanitize(self.pr_number, "nopr"),
                _sanitize(self.head_sha, "nohead"),
            ]
        )
        if len(full) <= _MAX_KEY_LEN:
            return full
        digest = hashlib.sha256(full.encode("utf-8")).hexdigest()[:12]
        return f"{full[:_MAX_KEY_LEN - 14]}--{digest}"

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
    """True when stdout contains a well-formed <zima-review> block with a
    non-empty explicit <verdict> child.

    Truncated output (no closing tag) and verdict-less blocks are rejected,
    because the guard must not silently forgive executions that failed to
    produce a complete review.
    """
    raw = stdout or ""
    match = re.search(r"<zima-review>.*?</zima-review>", raw, re.DOTALL)
    if not match:
        return False
    block = match.group(0)
    try:
        root = ET.fromstring(block)
    except Exception:
        return False
    verdict = root.findtext("verdict")
    return bool(verdict and verdict.strip())


def _has_valid_review_signal(stdout: str) -> bool:
    """True when stdout carries ANY spec §5.1 valid-review signal.

    Accepts a well-formed ``<zima-review>`` XML verdict OR a complete
    ``Status: PASS|NEEDS_FIX|NO_NEW_COMMITS`` line. Truncated output lacking
    BOTH a closed XML block and a complete Status line stays invalid.
    """
    return _has_review_verdict(stdout) or bool(_STATUS_LINE_RE.search(stdout or ""))


def classify_execution_result(
    *,
    status: str,
    returncode: int,
    stdout: str,
    expect_review_verdict: bool,
) -> GuardOutcome:
    """Classify one terminal execution (pure function).

    A valid review signal in stdout always wins, even when postExec flipped
    status to failed afterwards (the review itself is valid). The signal is a
    well-formed ``<zima-review>`` verdict or a complete ``Status:`` line — the
    scheduler's documented grep contract, so text-only review agents count as
    valid per spec §5.1. Skipped executions are neutral — they never touch
    the streak.
    """
    if status == "skipped":
        return GuardOutcome("skipped", countable_failure=False, clears_streak=False)
    if _has_valid_review_signal(stdout):
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
    return GuardOutcome("unknown", countable_failure=False, clears_streak=False)


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

    def _lock_path_for(self, target: FailureTarget) -> Path:
        """Lock file path for a target (mirrors _locked's derivation)."""
        return self.path_for(target).with_suffix(".json.lock")

    def clear_state(self, target: FailureTarget) -> None:
        """Remove the state file only. Safe to call while holding the lock."""
        try:
            self.path_for(target).unlink()
        except FileNotFoundError:
            pass

    def clear_lock(self, target: FailureTarget) -> None:
        """Best-effort lock-file removal.

        Must run OUTSIDE the lock region: unlinking a file with an open
        msvcrt-locked handle raises PermissionError on Windows (POSIX allows
        unlink-while-open). Failures are tolerated — a leftover zero-byte
        lock file is harmless and gets removed by the next clear.
        """
        try:
            self._lock_path_for(target).unlink()
        except (FileNotFoundError, PermissionError, OSError):
            pass

    def clear(self, target: FailureTarget) -> None:
        """Remove state and lock files (for callers not holding the lock)."""
        self.clear_state(target)
        self.clear_lock(target)


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
        # Read without locking: atomic os.replace guarantees readers see
        # complete files; a moment of staleness is acceptable for check.
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
        # Neutral outcomes (skipped/unknown) never touch state: return BEFORE
        # taking the lock so they cannot create the state dir or lock file.
        if not outcome.countable_failure and not outcome.clears_streak:
            return
        cleared = False
        with _locked(self._store.path_for(target)):
            if outcome.clears_streak:
                # State-file removal under the lock serializes with concurrent
                # recorders; the lock FILE is removed after release (Windows
                # cannot unlink a file with an open locked handle).
                self._store.clear_state(target)
                cleared = True
            else:
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
        if cleared:
            self._store.clear_lock(target)
