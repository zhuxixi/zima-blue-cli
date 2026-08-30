#!/usr/bin/env python3
"""auto-merge-guarded: auto approve + squash merge after CR convergence.

Whitelisted collaborators' PRs are merged automatically once CI required
checks are green and the Zima CR round has safely converged.  Scheduled by
cron every 45 minutes.  All secrets live outside this file (Pushover keys
in ~/.config/claude-notify.json, GitHub auth via the gh CLI login state).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoConfig:
    """Per-repo rules loaded from auto-merge.yaml."""

    allow_authors: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    expected_failing_checks: list[str] = field(default_factory=list)
    merge_method: str = "squash"
    delete_branch: bool = True
    sensitive_paths: list[str] = field(default_factory=list)
    cr_pjob_code: str = ""


@dataclass
class AppConfig:
    """Top-level config loaded from auto-merge.yaml."""

    enabled: bool = True
    pushover_config_file: str = "~/.config/claude-notify.json"
    repos: dict[str, RepoConfig] = field(default_factory=dict)


def load_config(path: Path) -> AppConfig:
    """Load auto-merge.yaml into an AppConfig.  Raises FileNotFoundError."""
    data = json.loads(json.dumps(_read_yaml(path)))
    cfg = AppConfig()
    cfg.enabled = bool(data.get("enabled", True))
    pushover = data.get("pushover") or {}
    cfg.pushover_config_file = pushover.get("config_file", cfg.pushover_config_file)
    for repo_name, repo_data in (data.get("repos") or {}).items():
        cfg.repos[repo_name] = RepoConfig(
            allow_authors=list(repo_data.get("allow_authors") or []),
            required_checks=list(repo_data.get("required_checks") or []),
            expected_failing_checks=list(repo_data.get("expected_failing_checks") or []),
            merge_method=repo_data.get("merge_method", "squash"),
            delete_branch=bool(repo_data.get("delete_branch", True)),
            sensitive_paths=list(repo_data.get("sensitive_paths") or []),
            cr_pjob_code=repo_data.get("cr_pjob_code", ""),
        )
    return cfg


def _read_yaml(path: Path) -> dict:
    """Minimal YAML subset parser: flat key/value maps and lists of scalars.

    The config schema only needs nested dicts and scalar lists, so a tiny
    indentation-based parser avoids a third-party dependency.  Raises
    FileNotFoundError when the file is missing.
    """
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if ":" in content:
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                child: dict = {}
                parent[key] = child
                stack.append((indent, child))
            elif value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                parent[key] = [
                    item.strip().strip("'\"") for item in inner.split(",") if item.strip()
                ]
            else:
                parent[key] = _scalar(value)
    return root


def _scalar(value: str):
    """Coerce a YAML scalar string to bool/int/float/str.

    Quotes are stripped before coercion so that `enabled: "false"` parses as
    the boolean False (a quoted boolean is a common YAML habit).  Without
    this, the quoted string "false" is truthy and silently flips the
    auto-merge kill switch the wrong way.
    """
    value = value.strip().strip("'\"")
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


class AuditLogger:
    """Append-only JSONL audit log."""

    def __init__(self, path: Path):
        self.path = path

    def log(self, entry: dict) -> None:
        """Append one JSON object as a single line."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


@dataclass
class GateResult:
    """Outcome of one gate: passed flag plus a decision and human reason.

    decision is one of: merge (keep going), skip (silent, not a candidate),
    attention (notify owner, never auto-merge), waiting (silent, retry next
    round), error (notify owner, abort this PR).
    """

    passed: bool
    decision: str
    reason: str


def gate_candidate(pr: dict, allow_authors: list[str]) -> GateResult:
    """Gate 1: PR must be open, non-draft, and authored by a whitelisted user."""
    if pr.get("state") != "OPEN":
        return GateResult(False, "skip", f"PR #{pr.get('number')} state={pr.get('state')}")
    if pr.get("isDraft"):
        return GateResult(False, "skip", f"PR #{pr.get('number')} is draft")
    author = (pr.get("author") or {}).get("login", "")
    if author not in allow_authors:
        return GateResult(False, "skip", f"author {author!r} not in whitelist")
    return GateResult(True, "merge", "candidate ok")


def gate_sensitive_paths(files: list[str], sensitive_paths: list[str]) -> GateResult:
    """Gate 2: changed files must not match any sensitive glob pattern.

    Sensitive paths (workflows, CI config) can rewrite the review and gate
    rules themselves, so they always require a human.
    """
    for path in files:
        for pattern in sensitive_paths:
            if fnmatch.fnmatch(path, pattern):
                return GateResult(
                    False,
                    "attention",
                    f"sensitive path {path!r} matches {pattern!r}",
                )
    return GateResult(True, "merge", "no sensitive paths")


def gate_required_checks(
    check_runs: list[dict], required: list[str], expected_failing: list[str]
) -> GateResult:
    """Gate 3: every required check's newest run must be success.

    check_runs comes from GET /commits/{sha}/check-runs (newest first).
    Checks listed in expected_failing may fail (e.g. Owner approval policy
    before the approve step) without blocking.
    """
    for name in required:
        newest = next((r for r in check_runs if r.get("name") == name), None)
        if newest is None:
            return GateResult(False, "waiting", f"required check {name!r} has no run yet")
        if newest.get("status") != "completed":
            return GateResult(
                False, "waiting", f"required check {name!r} is {newest.get('status')}"
            )
        if newest.get("conclusion") != "success" and name not in expected_failing:
            return GateResult(
                False,
                "waiting",
                f"required check {name!r} conclusion={newest.get('conclusion')}",
            )
    return GateResult(True, "merge", "all required checks green")


def gate_mergeable(mergeable: str) -> GateResult:
    """Gate 4: PR must be mergeable (no conflicts)."""
    if mergeable == "MERGEABLE":
        return GateResult(True, "merge", "mergeable")
    if mergeable == "CONFLICTING":
        return GateResult(False, "attention", "merge conflicts need human resolution")
    return GateResult(False, "waiting", f"mergeable={mergeable}")


CR_META_RE = re.compile(r"<!--\s*pi-cr-meta\s+(\{.*?\})\s*-->", re.DOTALL)


def parse_cr_meta(body: str) -> dict | None:
    """Extract the pi-cr-meta JSON from a review body, or None.

    The pi CR bot embeds its verdict as an HTML comment:
    <!-- pi-cr-meta {"round": 1, "blocking_new_count": 0, "issues": [...]} -->
    """
    match = CR_META_RE.search(body or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def effective_blocking(finding: dict) -> bool:
    """Whether a finding blocks merge, with legacy severity fallback.

    New metadata carries a boolean `blocking`.  Old metadata only has
    `severity`: low -> False, medium/high/critical -> True, missing or
    invalid severity counts as medium (True).
    """
    blocking = finding.get("blocking")
    if isinstance(blocking, bool):
        return blocking
    severity = finding.get("severity", "medium")
    return severity != "low"


def review_clean(meta: dict) -> tuple[bool, str]:
    """True when one pi-cr-meta review has no blocking findings.

    blocking_new_count == 0 alone is NOT enough: carried open findings from
    earlier rounds must also be checked one by one.
    """
    if meta.get("blocking_new_count", 0) != 0:
        return False, f"blocking_new_count={meta.get('blocking_new_count')}"
    for issue in meta.get("issues") or []:
        if issue.get("status") == "open" and effective_blocking(issue):
            return False, f"open blocking finding: {issue.get('title', issue.get('id', '?'))}"
    return True, "clean"


def pid_alive(pid: int | None) -> bool:
    """True when a process with this pid exists (mirrors wait-cr.py)."""
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
        return True
    except ProcessLookupError:
        return False
    except (ValueError, Exception):  # noqa: BLE001 — mirrors wait-cr.py liveness semantics
        return False


def gate_cr_convergence(
    executions: list[dict], reviews: list[dict], head_sha: str, labels: list[str]
) -> GateResult:
    """Gate 5: CR must have safely converged.  Three conditions, all required:

    a. no execution for this (repo, pr) is still running (a running entry
       whose pid is dead counts as terminated — zima never writes a terminal
       state for hard-killed processes);
    b. every pi-cr-meta review for the current head is clean (multi-stream
       trap: one clean stream + one late stream with a blocking finding must
       NOT merge);
    c. the zima:needs-review label has been removed by postExec.
    """
    for execution in executions:
        if execution.get("status") == "running" and pid_alive(execution.get("pid")):
            return GateResult(
                False,
                "waiting",
                f"CR execution {execution.get('execution_id')} still running",
            )
    if "zima:needs-review" in labels:
        return GateResult(False, "waiting", "zima:needs-review label still present")
    head_reviews = [r for r in reviews if ((r.get("commit") or {}).get("oid") or "") == head_sha]
    if not head_reviews:
        return GateResult(False, "waiting", "no CR review for current head yet")
    for review in head_reviews:
        meta = parse_cr_meta(review.get("body") or "")
        if meta is None:
            return GateResult(False, "waiting", "review without pi-cr-meta for current head")
        ok, reason = review_clean(meta)
        if not ok:
            return GateResult(False, "waiting", f"CR not converged: {reason}")
    return GateResult(True, "merge", "CR converged")
