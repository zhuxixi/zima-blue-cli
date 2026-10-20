#!/usr/bin/env python3
"""Block until a Zima CR round finishes.

Two observation modes:

**Local mode** (``wait-cr.py <pjob_code>``) watches the runtime state files
that zima's background runner maintains at
``$ZIMA_HOME/history/pjobs/<pjob_code>/<execution_id>.json``.  The terminal
state is written only after postExec actions finish (i.e. after the review
has been posted), so "no running executions left" means "this CR round is
done".

**Remote mode** (``wait-cr.py --pr owner/repo#N``) polls the pull request
with ``gh`` and returns once a review carrying ``pi-cr-meta`` / ``cc-cr-meta``
appears for the current head commit.  This is the mode for a trigger host
that has no zima runtime (the CR runs on another machine), where local state
files can never show the round.

Both modes are strictly read-only: they never write state files or touch the
pull request, so several sessions can wait on the same work at once.

Exit codes:
    0  converged (local: every active execution is terminal; remote: this
       round's review is on the target head)
    1  timeout while the round was still in flight
    2  local mode: no execution appeared within the grace period
    3  local mode: this host has no zima runtime ($ZIMA_HOME/history/pjobs is
       missing) -> use ``--pr owner/repo#N``
    4  remote mode: the target head changed while waiting (round superseded)
    5  remote mode: the pull request is no longer open
    6  remote mode: ``gh`` failed before the target head could be read
    64  usage error (both modes, neither mode, or an argument the mode rejects)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, TextIO

TERMINAL_STATUSES = {"success", "failed", "skipped", "timeout", "cancelled", "dead"}
DEFAULT_TIMEOUT = 2100  # PJob execution.timeout (1800s) + 300s slack
DEFAULT_POLL = 30
DEFAULT_GRACE = 120
DEFAULT_SINCE_MINUTES = 10

# HTML-comment markers identify the bot that produced the review; the opener is
# required so prose that merely names the marker does not count. ``kimi-cr-meta``
# is retired and deliberately absent.
META_MARKERS = {
    "pi": re.compile(r"<!--\s*pi-cr-meta"),
    "cc": re.compile(r"<!--\s*cc-cr-meta"),
}
META_JSON_RE = re.compile(r"<!--\s*(?:pi|cc)-cr-meta\s+(\{.*?\})\s*-->", re.DOTALL)
REVIEW_JSON_FIELDS = "reviews,headRefOid,state"
GH_START_ATTEMPTS = 3
GH_TIMEOUT = 120


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into a tz-aware datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class GhQueryError(RuntimeError):
    """``gh`` failed, or returned output that is not a pull-request payload."""


def parse_pr_ref(text: str) -> tuple[str, str, int]:
    """Parse ``owner/repo#123`` into its three parts.

    Strict on purpose: a mistyped reference must fail at startup (exit 64)
    instead of polling the wrong repository until the timeout.
    """
    raw = (text or "").strip()
    slug, sep, number = raw.rpartition("#")
    owner, slash, repo = slug.partition("/")
    if not sep or not owner or not slash or not repo or "/" in repo or "#" in owner or "#" in repo:
        raise ValueError(f"expected owner/repo#number, got {text!r}")
    if not number.isdigit() or int(number) <= 0:
        raise ValueError(f"expected a positive PR number, got {number!r}")
    return owner, repo, int(number)


def meta_marker(body: str) -> str | None:
    """Return ``"pi"`` / ``"cc"`` when the body carries a CR metadata block.

    Requires the HTML-comment opener so prose that merely mentions the marker
    does not count; ``kimi-cr-meta`` is retired and never matches.
    """
    for kind, pattern in META_MARKERS.items():
        if pattern.search(body or ""):
            return kind
    return None


def parse_meta_json(body: str) -> dict | None:
    """Best-effort metadata JSON, for the summary line only.

    A malformed block must never influence the convergence decision, so every
    failure collapses to ``None``.
    """
    match = META_JSON_RE.search(body or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def select_meta_review(reviews: list[dict], head_sha: str, not_before: datetime) -> dict | None:
    """Newest metadata review written against ``head_sha`` after ``not_before``.

    ``not_before`` is what keeps a review from an earlier round on the same
    head from ending the wait instantly, while still accepting a round that
    finished moments before the wait started.
    """
    newest: dict | None = None
    newest_at: datetime | None = None
    for review in reviews or []:
        if not isinstance(review, dict):
            continue
        commit = review.get("commit")
        oid = commit.get("oid") if isinstance(commit, dict) else None
        if oid != head_sha:
            continue
        if meta_marker(str(review.get("body") or "")) is None:
            continue
        submitted = parse_iso(review.get("submittedAt"))
        if submitted is None or submitted < not_before:
            continue
        if newest_at is None or submitted >= newest_at:
            newest, newest_at = review, submitted
    return newest


def format_review_summary(review: dict) -> str:
    """One-line summary of the matching review — the session's only signal."""
    body = str(review.get("body") or "")
    meta = parse_meta_json(body) or {}
    author = review.get("author")
    login = author.get("login") if isinstance(author, dict) else None
    commit = review.get("commit")
    oid = commit.get("oid") if isinstance(commit, dict) else None

    def field(key: str) -> str:
        value = meta.get(key)
        return "-" if value is None else str(value)

    parts = [
        f"review={review.get('id') or '?'}",
        f"head={str(oid or '?')[:12]}",
        f"submittedAt={review.get('submittedAt') or '?'}",
        f"author={login or '?'}",
        f"meta={meta_marker(body) or '?'}",
        f"round={field('round')}",
        f"blocking_new={field('blocking_new_count')}",
        f"blocking_open={field('blocking_open_count')}",
    ]
    return "wait-cr: converged: " + " ".join(parts)


def has_local_runtime(zima_home: Path) -> bool:
    """True when this host holds any zima PJob runtime state to watch.

    ``history/pjobs`` is the directory zima creates on first execution; its
    absence means no local execution can ever be observed, so waiting on it
    would only produce a misleading "nothing appeared" verdict.
    """
    return (Path(zima_home) / "history" / "pjobs").is_dir()


def _gh_runner(argv: list[str]) -> str:
    """Run one ``gh`` subcommand and return its stdout.

    The single subprocess call on the remote path, so tests can inject a fake
    runner and never touch the network.
    """
    try:
        proc = subprocess.run(
            ["gh", *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhQueryError(f"gh could not run: {exc}") from exc
    if proc.returncode != 0:
        lines = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = lines[-1] if lines else f"exit {proc.returncode}"
        raise GhQueryError(f"gh {' '.join(argv)} failed: {detail}")
    return proc.stdout


def fetch_pr_state(owner: str, repo: str, number: int, runner=_gh_runner) -> dict:
    """Read ``headRefOid`` + ``state`` + ``reviews`` for one pull request."""
    argv = [
        "pr",
        "view",
        str(number),
        "--repo",
        f"{owner}/{repo}",
        "--json",
        REVIEW_JSON_FIELDS,
    ]
    raw = runner(argv)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GhQueryError(f"unparseable gh output: {exc}") from exc
    if not isinstance(data, dict) or not data.get("headRefOid"):
        raise GhQueryError("gh output has no headRefOid")
    return data


def run_pr_loop(
    pr: tuple[str, str, int],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    poll: int = DEFAULT_POLL,
    since_minutes: int = DEFAULT_SINCE_MINUTES,
    fetch: Callable[[], dict] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    out: TextIO | None = None,
) -> int:
    """Poll GitHub until this round's review lands; return the exit code.

    The poll order is a contract: a head change or a closed PR invalidates the
    round *before* a matching review is accepted, so a review written for a
    superseded commit can never be reported as convergence.
    """
    if out is None:
        out = sys.stdout
    owner, repo, number = pr
    if fetch is None:

        def fetch() -> dict:
            return fetch_pr_state(owner, repo, number)

    not_before = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    deadline = monotonic() + timeout
    elapsed = 0

    snapshot: dict | None = None
    head_sha = ""
    for attempt in range(1, GH_START_ATTEMPTS + 1):
        try:
            snapshot = fetch()
            head_sha = str(snapshot.get("headRefOid") or "")
            if head_sha:
                break
        except GhQueryError as exc:
            print(
                f"wait-cr: gh query failed ({attempt}/{GH_START_ATTEMPTS}): {exc}",
                file=sys.stderr,
            )
    if not head_sha:
        print(
            "wait-cr: cannot read the pull request; check `gh auth status` and "
            "the --pr reference",
            file=sys.stderr,
        )
        return 6

    while True:
        if snapshot is None:
            try:
                snapshot = fetch()
            except GhQueryError as exc:
                print(f"wait-cr: gh query failed, retrying: {exc}", file=sys.stderr)

        if snapshot is not None:
            state = str(snapshot.get("state") or "OPEN").upper()
            if state != "OPEN":
                print(
                    f"wait-cr: PR {owner}/{repo}#{number} is {state}; " "nothing left to wait for",
                    file=sys.stderr,
                )
                return 5
            current = str(snapshot.get("headRefOid") or "")
            if current != head_sha:
                print(
                    f"wait-cr: head moved {head_sha[:12]} -> {current[:12]}; "
                    "this round was superseded, re-trigger and wait again",
                    file=sys.stderr,
                )
                return 4
            review = select_meta_review(snapshot.get("reviews") or [], head_sha, not_before)
            if review is not None:
                print(format_review_summary(review), file=out)
                return 0
            snapshot = None

        if monotonic() >= deadline:
            print(
                f"wait-cr: timeout after {timeout}s; no {owner}/{repo}#{number} "
                f"review for head {head_sha[:12]} since {not_before.isoformat()}",
                file=sys.stderr,
            )
            return 1

        print(
            f"[{elapsed:>5}s] waiting for a CR review on {owner}/{repo}#{number} "
            f"head {head_sha[:12]}",
            file=out,
            flush=True,
        )
        sleep(poll)
        elapsed += poll


def pid_alive(pid: int | None) -> bool:
    """Return True when a process with this pid exists.

    Mirrors ``zima.execution.history._is_pid_alive`` so the watcher and the
    state-file writer agree on liveness: ``ctypes.GetExitCodeProcess`` on
    Windows, ``os.kill(pid, 0)`` on Unix.  ``PermissionError`` on Unix means
    the process exists but is not ours (alive); ``ProcessLookupError`` means
    it does not exist (dead); anything unexpected is dead.
    """
    if pid is None:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            try:
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        # Process exists but caller lacks permission to signal it.
        return True
    except ProcessLookupError:
        return False
    except (ValueError, Exception):
        return False


def load_states(state_dir: Path) -> dict[str, dict]:
    """Read every state file into {execution_id: state_dict}.

    Files that fail to parse are skipped: zima writes state files
    non-atomically, so a torn read just means "being written right now" —
    the next poll tick will see the completed file.
    """
    states: dict[str, dict] = {}
    if not state_dir.is_dir():
        return states
    for path in sorted(state_dir.iterdir()):
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
            continue
        if isinstance(data, dict):
            states[path.stem] = data
    return states


def tail_log(log_path: str | None, chars: int = 600) -> str:
    """Return the last ``chars`` characters of the log file, or ''.

    The full agent stdout ends with the ``<zima-review>`` verdict; zima
    keeps the whole output in the background log, so the log tail is the
    closest read-only proxy for the verdict. Read-only and bounded (reads
    at most the last 8192 bytes).
    """
    if not log_path:
        return ""
    path = Path(log_path)
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            data = fh.read()
        return data.decode("utf-8", errors="replace")[-chars:].strip()
    except OSError:
        return ""


def is_stale(state: dict) -> bool:
    """True when a 'running' entry's pid is provably dead.

    Such an entry will never receive a terminal state (the process was
    killed hard); zima's own CLI marks these 'dead' on read.  pid=None
    means the spawn is still racing and must NOT be treated as stale.
    """
    return (
        state.get("status") == "running"
        and state.get("pid") is not None
        and not pid_alive(state.get("pid"))
    )


def is_active(state: dict, cutoff: datetime | None) -> bool:
    """True when the execution belongs to the round being waited on.

    Running executions are always active.  Finished ones count only when
    they started after the cutoff (recent enough to be this round's work);
    older terminal files are history and are ignored.  ``run_loop`` adds
    sticky semantics on top: an execution seen running at any point during
    the wait stays active until it reaches a terminal state, even if its
    ``started_at`` predates the cutoff (long-tail continuation scenario).
    """
    status = state.get("status")
    if status == "running":
        return True
    if status in TERMINAL_STATUSES and cutoff is not None:
        started = parse_iso(state.get("started_at"))
        return started is not None and started >= cutoff
    return False


def format_summary(eid: str, state: dict) -> str:
    """One human-readable summary line per execution."""
    status = state.get("status", "?")
    duration = state.get("duration_seconds")
    dur = f"{duration:.0f}s" if isinstance(duration, (int, float)) else "-"
    parts = [f"eid={eid}", f"status={status}", f"duration={dur}"]
    if state.get("returncode") is not None:
        parts.append(f"returncode={state['returncode']}")
    if state.get("_stale"):
        parts.append("STALE(pid dead, terminal state never written)")
    spr = state.get("scan_pr_result") or {}
    if spr.get("repo"):
        parts.append(f"repo={spr['repo']}#{spr.get('pr_number')}")
    preview = str(state.get("stdout_preview") or "").strip()
    if preview:
        parts.append(f"preview={preview[:240]}")
    tail = tail_log(state.get("log_path"))
    if tail:
        parts.append(f"log_tail={tail}")
    return "  " + " ".join(parts)


def run_loop(
    state_dir: Path,
    cutoff: datetime | None,
    timeout: int = DEFAULT_TIMEOUT,
    poll: int = DEFAULT_POLL,
    grace: int = DEFAULT_GRACE,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    out: TextIO | None = None,
) -> int:
    """Poll state files until no active execution is running.

    Returns:
        0 when every active execution reached a terminal state,
        1 on timeout, 2 when no execution appeared within the grace period.
    """
    if out is None:
        out = sys.stdout
    deadline = monotonic() + timeout
    no_exec_deadline = monotonic() + grace
    elapsed = 0
    sticky: set[str] = set()

    while True:
        states = load_states(state_dir)
        active = {eid: s for eid, s in states.items() if is_active(s, cutoff) or eid in sticky}
        for eid, state in active.items():
            if state.get("status") == "running":
                sticky.add(eid)
        for state in active.values():
            if is_stale(state):
                state["_stale"] = True
        running = [
            s for s in active.values() if s.get("status") == "running" and not s.get("_stale")
        ]

        if not running:
            if not active:
                if monotonic() >= deadline:
                    print(
                        f"wait-cr: timeout after {timeout}s; no execution appeared:",
                        file=sys.stderr,
                    )
                    return 1
                if monotonic() < no_exec_deadline:
                    sleep(poll)
                    elapsed += poll
                    continue
                print(
                    "wait-cr: no active execution since cutoff; if a round was "
                    "just triggered, check `zima pjob status <code>`",
                    file=sys.stderr,
                )
                return 2
            for eid, state in sorted(active.items()):
                print(format_summary(eid, state), file=out)
            return 0

        if monotonic() >= deadline:
            print(f"wait-cr: timeout after {timeout}s; still running:", file=sys.stderr)
            for eid, state in sorted(active.items()):
                print(format_summary(eid, state), file=sys.stderr)
            return 1

        print(f"[{elapsed:>5}s] {len(running)} running", file=out, flush=True)
        sleep(poll)
        elapsed += poll


class _Parser(argparse.ArgumentParser):
    """Argparse that exits 64 on usage errors.

    Exit 2 already means "no execution appeared" in local mode, so the
    argparse default would collide with a runtime verdict.
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(64, f"wait-cr: usage error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: pick the observation mode and run it."""
    parser = _Parser(
        description="Wait for a Zima CR round to finish (local state files or GitHub reviews)."
    )
    parser.add_argument("pjob_code", nargs="?", help="PJob code to wait for (local mode)")
    parser.add_argument(
        "--pr",
        metavar="OWNER/REPO#N",
        help="wait for the CR review of this pull request (remote mode)",
    )
    parser.add_argument(
        "--since-minutes",
        type=int,
        default=DEFAULT_SINCE_MINUTES,
        help=(
            "local: count executions started within N minutes; "
            "remote: accept reviews submitted within N minutes"
        ),
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--poll", type=int, default=DEFAULT_POLL)
    parser.add_argument("--grace", type=int, default=None, help="local mode only")
    parser.add_argument(
        "--zima-home",
        type=Path,
        default=None,
        help="local mode only (default: $ZIMA_HOME or ~/.zima)",
    )
    args = parser.parse_args(argv)

    if bool(args.pjob_code) == bool(args.pr):
        print(
            "wait-cr: usage error: give exactly one of <pjob_code> or --pr owner/repo#N",
            file=sys.stderr,
        )
        return 64

    if args.pr:
        if args.grace is not None or args.zima_home is not None:
            print(
                "wait-cr: usage error: --grace/--zima-home only apply to local mode",
                file=sys.stderr,
            )
            return 64
        try:
            pr = parse_pr_ref(args.pr)
        except ValueError as exc:
            print(f"wait-cr: usage error: {exc}", file=sys.stderr)
            return 64
        return run_pr_loop(
            pr,
            timeout=args.timeout,
            poll=args.poll,
            since_minutes=args.since_minutes,
        )

    zima_home = args.zima_home or Path(os.environ.get("ZIMA_HOME") or Path.home() / ".zima")
    if not has_local_runtime(zima_home):
        missing = zima_home / "history" / "pjobs"
        print(
            f"wait-cr: no local zima runtime (missing {missing}); this host cannot "
            "watch PJob state — use --pr owner/repo#N to wait on GitHub reviews",
            file=sys.stderr,
        )
        return 3

    state_dir = zima_home / "history" / "pjobs" / args.pjob_code
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.since_minutes)
    return run_loop(
        state_dir=state_dir,
        cutoff=cutoff,
        timeout=args.timeout,
        poll=args.poll,
        grace=DEFAULT_GRACE if args.grace is None else args.grace,
    )


if __name__ == "__main__":
    sys.exit(main())
