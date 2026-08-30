#!/usr/bin/env python3
"""auto-merge-guarded: auto approve + squash merge after CR convergence.

Whitelisted collaborators' PRs are merged automatically once CI required
checks are green and the Zima CR round has safely converged.  Scheduled by
cron every 45 minutes.  All secrets live outside this file (Pushover keys
in ~/.config/claude-notify.json, GitHub auth via the gh CLI login state).
"""

from __future__ import annotations

import argparse
import fcntl
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
            # Inline comments: a '#' preceded by whitespace starts a comment (YAML convention)
            value = re.sub(r"\s+#.*$", "", value)
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
    the boolean False.  YAML 1.1 boolean spellings (true/false/yes/no/on/off,
    case-insensitive) are also coerced; otherwise `enabled: no` would parse as
    the truthy string "no" and silently flip the auto-merge kill switch ON.
    """
    value = value.strip().strip("'\"").strip()
    lowered = value.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
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
       state for hard-killed processes; a running entry with pid=None is the
       spawn-race window and still blocks);
    b. every pi-cr-meta review for the current head is clean (multi-stream
       trap: one clean stream + one late stream with a blocking finding must
       NOT merge);
    c. the zima:needs-review label has been removed by postExec.
    """
    for execution in executions:
        if execution.get("status") == "running" and (
            execution.get("pid") is None or pid_alive(execution.get("pid"))
        ):
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


def gate_head_stable(head_before: str, head_now: str) -> GateResult:
    """Gate 6: head must not have moved between verification and action.

    A collaborator push between approve and merge invalidates the approve
    (owner-approval policy binds to the head sha).  A drifted head naturally
    returns to the not-converged state and is re-evaluated next round.
    """
    if head_before != head_now:
        return GateResult(False, "waiting", f"head drift: {head_before[:8]} -> {head_now[:8]}")
    return GateResult(True, "merge", "head stable")


def run_gates(
    pr: dict, check_runs: list[dict], executions: list[dict], repo_cfg: RepoConfig
) -> GateResult:
    """Run gates 1-5 in order; return the first non-passing result.

    Gate 6 (head drift) is NOT run here — it is checked inside the action
    chain right before approve, against a freshly fetched head.
    """
    files = [f.get("path", "") for f in pr.get("files") or []]
    labels = [label.get("name", "") for label in pr.get("labels") or []]
    gates = [
        gate_candidate(pr, repo_cfg.allow_authors),
        gate_sensitive_paths(files, repo_cfg.sensitive_paths),
        gate_required_checks(
            check_runs, repo_cfg.required_checks, repo_cfg.expected_failing_checks
        ),
        gate_mergeable(pr.get("mergeable", "UNKNOWN")),
        gate_cr_convergence(executions, pr.get("reviews") or [], pr.get("headRefOid", ""), labels),
    ]
    for result in gates:
        if not result.passed:
            return result
    return GateResult(True, "merge", "all gates passed")


def gh_json(args: list[str]) -> dict | list:
    """Run `gh <args>` and parse stdout as JSON.  Raises on failure."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)


def gh_run(args: list[str]) -> None:
    """Run `gh <args>` without parsing output.  Raises on failure."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {proc.stderr.strip()[:500]}")


def remove_label(repo: str, number: int, label: str, dry: bool) -> None:
    """Remove a label.  Removing zima:needs-fix does NOT trigger a new CR
    stream (the webhook only listens for zima:needs-review)."""
    if dry:
        return
    gh_run(["pr", "edit", str(number), "--repo", repo, "--remove-label", label])


def approve(repo: str, number: int, dry: bool) -> None:
    """Approve the PR.

    The review binds to the PR's current head at submission (GitHub
    semantics).  Head-drift protection is structural: the action chain
    re-fetches the head and checks gate_head_stable immediately before this
    call, so a collaborator push between check and approve aborts the round.
    """
    if dry:
        return
    gh_run(
        [
            "pr",
            "review",
            str(number),
            "--repo",
            repo,
            "--approve",
            "--body",
            "auto-merge: CR converged + CI green",
        ]
    )


def rerun_failed_jobs(
    repo: str, head_sha: str, workflow_name: str, dry: bool, timeout: int = 300
) -> None:
    """Rerun failed runs of the expected-failing workflow on this head.

    After approve, the Owner approval policy workflow re-runs and turns
    green; without this the PR list icon stays red from the old failed run.
    Polls until the rerun completes or `timeout` seconds elapse.
    """
    runs = gh_json(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--commit",
            head_sha,
            "--json",
            "databaseId,name,conclusion",
        ]
    )
    failed_ids = [
        str(r["databaseId"])
        for r in runs
        if r.get("name") == workflow_name and r.get("conclusion") == "failure"
    ]
    if not failed_ids:
        return
    if dry:
        return
    for run_id in failed_ids:
        gh_run(["run", "rerun", run_id, "--failed"])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        statuses = [
            gh_json_view(["run", "view", run_id, "--repo", repo, "--json", "status,conclusion"])
            for run_id in failed_ids
        ]
        if all(s.get("status") == "completed" for s in statuses):
            return
        time.sleep(15)
    raise RuntimeError(f"rerun of {workflow_name} did not complete within {timeout}s")


def gh_json_view(args: list[str]) -> dict:
    """Alias for gh_json kept separate so tests can mock the poll loop."""
    return gh_json(args)


def merge_pr(repo: str, number: int, method: str, delete_branch: bool, dry: bool) -> None:
    """Squash-merge (or merge) the PR, optionally deleting the branch."""
    if dry:
        return
    if method == "squash":
        method_flag = "--squash"
    elif method == "merge":
        method_flag = "--merge"
    else:
        raise ValueError(f"unsupported merge method: {method!r}")
    cmd = ["pr", "merge", str(number), "--repo", repo, method_flag]
    if delete_branch:
        cmd.append("--delete-branch")
    gh_run(cmd)


PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
MESSAGE_CHAR_LIMIT = 250

# Pushover priority per notification level
LEVEL_PRIORITY = {"action": 0, "attention": 1, "error": 1}


def truncate_chars(text: str, limit: int) -> str:
    """Truncate by characters, never bytes (UTF-8 Chinese would corrupt)."""
    if len(text) <= limit:
        return text
    return text[:limit]


def load_pushover_keys(config_file: str) -> tuple[str, str] | None:
    """Read (api_key, user_key) from the shared notify config, or None.

    Never raises: a corrupt, non-UTF-8, or non-object config degrades to
    None so the caller can fall back to log-only notifications.
    """
    path = Path(config_file).expanduser()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    api_key = data.get("PUSHOVER_API_KEY")
    user_key = data.get("PUSHOVER_USER_KEY")
    if not api_key or not user_key:
        return None
    return str(api_key), str(user_key)


def send_pushover(level: str, title: str, message: str, config_file: str) -> bool:
    """POST a Pushover message.  Returns False on any failure (callers
    degrade to log-only; notification must never block the merge)."""
    keys = load_pushover_keys(config_file)
    if keys is None:
        return False
    api_key, user_key = keys
    payload = {
        "token": api_key,
        "user": user_key,
        "title": title,
        "message": truncate_chars(message, MESSAGE_CHAR_LIMIT),
        "priority": LEVEL_PRIORITY.get(level, 0),
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(PUSHOVER_URL, data=data)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except Exception:  # noqa: BLE001 — best-effort notification path: any
        # failure (URLError, BadStatusLine, IncompleteRead, ...) must degrade
        # to log-only and never block the merge.
        return False


LOCK_PATH = "/tmp/auto-merge-guarded.lock"
DEFAULT_CONFIG = "~/.zima/configs/auto-merge.yaml"
DEFAULT_LOG = "~/.zima/logs/auto-merge.log"


def load_executions(zima_home: Path, pjob_code: str) -> list[dict]:
    """Read every CR execution state file for a PJob code.

    Torn files (zima writes non-atomically) are skipped — the next round
    sees the completed file.
    """
    state_dir = zima_home / "history" / "pjobs" / pjob_code
    if not state_dir.is_dir():
        return []
    executions: list[dict] = []
    for path in sorted(state_dir.iterdir()):
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if isinstance(data, dict):
            executions.append(data)
    return executions


def executions_for_pr(executions: list[dict], repo: str, pr_number: int) -> list[dict]:
    """Filter executions to those that scanned this (repo, pr)."""
    result = []
    for execution in executions:
        scan = execution.get("scan_pr_result") or {}
        if scan.get("repo") == repo and str(scan.get("pr_number")) == str(pr_number):
            result.append(execution)
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def process_repo(
    repo: str,
    repo_cfg: RepoConfig,
    cfg: AppConfig,
    mode: str,
    gh,
    zima_home: Path,
    audit: AuditLogger,
    notify,
) -> None:
    """One full round for one repo: fetch PRs, run gates, act, notify.

    mode is "live", "dry-run", or "notify-only".  dry-run prints the action
    chain without executing; notify-only additionally sends notifications.
    """
    dry = mode != "live"
    notify_enabled = mode != "dry-run"  # dry-run is a pure local rehearsal
    for pr in gh.list_prs(repo):
        number = pr.get("number")
        head_sha = pr.get("headRefOid", "")
        check_runs = gh.check_runs(repo, head_sha)
        pr["files"] = gh.fetch_files(repo, number)
        executions = executions_for_pr(
            load_executions(zima_home, repo_cfg.cr_pjob_code), repo, number
        )
        result = run_gates(pr, check_runs, executions, repo_cfg)
        audit.log(
            {
                "ts": _now_iso(),
                "mode": mode,
                "repo": repo,
                "pr": number,
                "head_sha": head_sha,
                "decision": result.decision,
                "reason": result.reason,
            }
        )
        if not result.passed:
            if result.decision == "attention" and notify_enabled:
                notify.send(
                    "attention",
                    "[auto-merge] needs your eyes",
                    f"{repo}#{number} {pr.get('title', '')}: {result.reason}",
                )
            # skip / waiting / error are silent (45-min rounds must not spam)
            continue
        # Action chain (each step re-checks current state; idempotent)
        fresh = gh.view_pr(repo, number)
        if fresh.get("state") == "MERGED":
            continue
        drift = gate_head_stable(head_sha, fresh.get("headRefOid", ""))
        if not drift.passed:
            audit.log(
                {
                    "ts": _now_iso(),
                    "mode": mode,
                    "repo": repo,
                    "pr": number,
                    "head_sha": fresh.get("headRefOid"),
                    "decision": drift.decision,
                    "reason": drift.reason,
                }
            )
            continue
        if (fresh.get("reviewDecision") or "") == "APPROVED":
            print(f"[{repo}#{number}] already approved, skipping approve")
        else:
            print(f"[{repo}#{number}] would approve" if dry else f"[{repo}#{number}] approving")
            if not dry:
                approve(repo, number, dry=False)
        labels = [label.get("name", "") for label in fresh.get("labels") or []]
        if "zima:needs-fix" in labels:
            print(
                f"[{repo}#{number}] would remove zima:needs-fix"
                if dry
                else f"[{repo}#{number}] removing zima:needs-fix"
            )
            remove_label(repo, number, "zima:needs-fix", dry)
        for workflow_name in repo_cfg.expected_failing_checks:
            print(
                f"[{repo}#{number}] would rerun failed jobs of {workflow_name}"
                if dry
                else f"[{repo}#{number}] rerunning failed jobs of {workflow_name}"
            )
            rerun_failed_jobs(repo, head_sha, workflow_name, dry)
        fresh = gh.view_pr(repo, number)
        if fresh.get("mergeStateStatus") != "CLEAN":
            if dry:
                # Dry modes never rerun (rerun_failed_jobs returns early), so
                # the merge state cannot be CLEAN yet; the rehearsal reports
                # what it would do and falls through to the would-merge step.
                print(
                    f"[{repo}#{number}] would check mergeStateStatus "
                    f"(currently {fresh.get('mergeStateStatus')})"
                )
            else:
                audit.log(
                    {
                        "ts": _now_iso(),
                        "mode": mode,
                        "repo": repo,
                        "pr": number,
                        "head_sha": head_sha,
                        "decision": "aborted",
                        "reason": f"mergeStateStatus={fresh.get('mergeStateStatus')}",
                    }
                )
                if notify_enabled:
                    notify.send(
                        "error",
                        "[auto-merge] error",
                        f"{repo}#{number}: mergeStateStatus={fresh.get('mergeStateStatus')} after rerun",
                    )
                continue
        print(
            f"[{repo}#{number}] would merge ({repo_cfg.merge_method})"
            if dry
            else f"[{repo}#{number}] merging ({repo_cfg.merge_method})"
        )
        if not dry:
            # Re-verify the head immediately before merging: a collaborator
            # push during the rerun poll (up to 5 minutes) would otherwise be
            # merged on a head whose CR convergence was never checked.
            fresh = gh.view_pr(repo, number)
            drift = gate_head_stable(head_sha, fresh.get("headRefOid", ""))
            if not drift.passed:
                audit.log(
                    {
                        "ts": _now_iso(),
                        "mode": mode,
                        "repo": repo,
                        "pr": number,
                        "head_sha": fresh.get("headRefOid"),
                        "decision": drift.decision,
                        "reason": drift.reason,
                    }
                )
                continue
            merge_pr(repo, number, repo_cfg.merge_method, repo_cfg.delete_branch, dry=False)
            audit.log(
                {
                    "ts": _now_iso(),
                    "mode": mode,
                    "repo": repo,
                    "pr": number,
                    "head_sha": head_sha,
                    "decision": "merged",
                    "reason": "merge completed",
                }
            )
        if notify_enabled:
            if dry:
                notify.send(
                    "action",
                    "[auto-merge] would merge",
                    f"{repo}#{number} {pr.get('title', '')} by "
                    f"{pr.get('author', {}).get('login', '?')} — would merge (notify-only)",
                )
            else:
                notify.send(
                    "action",
                    "[auto-merge] merged",
                    f"{repo}#{number} {pr.get('title', '')} by {pr.get('author', {}).get('login', '?')}",
                )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Auto approve + squash merge whitelisted PRs after CR convergence."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="path to auto-merge.yaml")
    parser.add_argument("--log", default=DEFAULT_LOG, help="path to the JSONL audit log")
    parser.add_argument("--zima-home", default=None, help="override ZIMA_HOME")
    parser.add_argument("--repo", default=None, help="only process this OWNER/REPO (debugging)")
    parser.add_argument(
        "--dry-run", action="store_true", help="run gates, print actions, execute nothing"
    )
    parser.add_argument(
        "--notify-only",
        action="store_true",
        help="run gates, send notifications, never touch GitHub",
    )
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config).expanduser())
    if not cfg.enabled:
        print("auto-merge disabled by config (enabled: false)")
        return 0
    mode = "dry-run" if args.dry_run else ("notify-only" if args.notify_only else "live")
    zima_home = (
        Path(args.zima_home)
        if args.zima_home
        else Path(os.environ.get("ZIMA_HOME") or Path.home() / ".zima")
    )
    audit = AuditLogger(Path(args.log).expanduser())

    lock_file = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another auto-merge round is already running (flock held)")
        return 0

    try:
        for repo, repo_cfg in cfg.repos.items():
            if args.repo and repo != args.repo:
                continue
            process_repo(repo, repo_cfg, cfg, mode, GhClient(), zima_home, audit, Notifier(cfg))
    except Exception as exc:  # noqa: BLE001 — top-level guard: log, notify, exit
        audit.log({"ts": _now_iso(), "mode": mode, "decision": "error", "reason": str(exc)})
        Notifier(cfg).send("error", "[auto-merge] error", str(exc)[:250])
        return 1
    return 0


class GhClient:
    """Thin gh CLI adapter (subclassed/mocked in tests)."""

    def list_prs(self, repo: str) -> list[dict]:
        return gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--json",
                "number,title,author,state,isDraft,headRefOid,mergeable,mergeStateStatus,"
                "reviewDecision,labels,reviews",
            ]
        )

    def fetch_files(self, repo: str, number: int) -> list[dict]:
        """Fetch the complete changed-files list (paginated).

        `gh pr list --json files` caps at 100 files, so a larger PR could hide
        a sensitive path beyond the cap; the dedicated pulls/{n}/files API is
        complete and paginated.  The REST response keys files by `filename`;
        gate 2 reads `path`, so map the response to that shape here.
        """
        data = gh_json(["api", f"repos/{repo}/pulls/{number}/files", "--paginate"])
        return [{"path": f.get("filename", "")} for f in data]

    def check_runs(self, repo: str, head_sha: str) -> list[dict]:
        data = gh_json(["api", f"repos/{repo}/commits/{head_sha}/check-runs", "--paginate"])
        return data.get("check_runs", []) if isinstance(data, dict) else []

    def view_pr(self, repo: str, number: int) -> dict:
        return gh_json(
            [
                "pr",
                "view",
                str(number),
                "--repo",
                repo,
                "--json",
                "state,headRefOid,reviewDecision,labels,mergeStateStatus",
            ]
        )


class Notifier:
    """Pushover adapter with log-only degradation."""

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

    def send(self, level: str, title: str, message: str) -> bool:
        return send_pushover(level, title, message, self.cfg.pushover_config_file)


if __name__ == "__main__":
    sys.exit(main())
