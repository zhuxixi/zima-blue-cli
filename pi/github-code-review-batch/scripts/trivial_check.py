#!/usr/bin/env python3
"""Deterministic trivial-PR precheck for the github-code-review-batch skill.

Decides whether a PR is safe to skip LLM review (v1: open, non-draft,
first-round, complete file list, no rename/copy, all changed files end in
.md). Exit codes:
  0  data valid; trivial decision in stdout JSON (default mode) or the full
     status report (--report mode, trivial only)
  1  data valid but not trivial (--report mode only)
  2  data/API error — caller must fail open to the normal Step 1 path
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_status_report  # noqa: E402  (same-directory skill script)

GH_TIMEOUT = 30
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
OWNER_REPO_N_RE = re.compile(r"^([^/\s]+)/([^/\s]+)#(\d+)$")
VALID_FILE_STATUSES = {
    "added",
    "modified",
    "deleted",
    "renamed",
    "copied",
    "changed",
    "unchanged",
}
PI_MARKER = "Generated with pi-coding-agent"
META_MARKER = "<!-- pi-cr-meta"
META_RE = re.compile(r"<!--\s*pi-cr-meta\s*\n(.*?)\n\s*-->", re.DOTALL)


def normalize_pr_ref(ref: str, explicit_repo: str | None) -> tuple[str, int]:
    """Parse a PR number, github.com PR URL, or owner/repo#N into (repo, number).

    The repo part is "" when only a bare number was given (caller resolves it
    later). Raises ValueError for unsupported refs or repo conflicts.
    """
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("empty PR ref")
    if ref.isdigit():
        number = int(ref)
        if number <= 0:
            raise ValueError(f"invalid PR number: {ref}")
        return (explicit_repo or ""), number
    match = PR_URL_RE.match(ref)
    if match:
        repo = f"{match.group(1)}/{match.group(2)}"
        number = int(match.group(3))
        if number <= 0:
            raise ValueError(f"invalid PR number: {ref}")
        if explicit_repo and explicit_repo.lower() != repo.lower():
            raise ValueError(f"repo conflict: URL says {repo}, --repo says {explicit_repo}")
        return repo, number
    match = OWNER_REPO_N_RE.match(ref)
    if match:
        repo = f"{match.group(1)}/{match.group(2)}"
        number = int(match.group(3))
        if number <= 0:
            raise ValueError(f"invalid PR number: {ref}")
        if explicit_repo and explicit_repo.lower() != repo.lower():
            raise ValueError(f"repo conflict: ref says {repo}, --repo says {explicit_repo}")
        return repo, number
    raise ValueError(f"unsupported PR ref: {ref!r}")


def parse_pr_view(raw: dict) -> dict:
    """Validate and normalize `gh pr view --json number,state,isDraft,changedFiles,headRefOid,reviews`."""
    if not isinstance(raw, dict):
        raise ValueError("pr view payload is not an object")
    number = raw.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise ValueError("pr view: number missing or invalid")
    state = raw.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("pr view: state missing or invalid")
    is_draft = raw.get("isDraft")
    if not isinstance(is_draft, bool):
        raise ValueError("pr view: isDraft missing or invalid")
    changed_files = raw.get("changedFiles")
    if isinstance(changed_files, bool) or not isinstance(changed_files, int) or changed_files < 0:
        raise ValueError("pr view: changedFiles missing or invalid")
    head_sha = raw.get("headRefOid")
    if not isinstance(head_sha, str) or not SHA_RE.match(head_sha):
        raise ValueError("pr view: headRefOid missing or invalid")
    reviews = raw.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("pr view: reviews missing or invalid")
    return {
        "number": number,
        "state": state,
        "is_draft": is_draft,
        "head_sha": head_sha,
        "changed_files": changed_files,
        "reviews": reviews,
    }


def inspect_metadata(reviews: list) -> str:
    """Classify pi-cr metadata presence: 'empty' | 'present' | 'unavailable'.

    'unavailable' covers malformed review records and pi-cr-marked comments
    whose metadata JSON cannot be parsed — the caller must fail open.
    """
    candidates: list[str] = []
    for review in reviews:
        if not isinstance(review, dict):
            return "unavailable"
        body = review.get("body")
        if not isinstance(body, str):
            return "unavailable"
        if PI_MARKER in body and META_MARKER in body:
            candidates.append(body)
    if not candidates:
        return "empty"
    for body in candidates:
        match = META_RE.search(body)
        if not match:
            return "unavailable"
        try:
            meta = json.loads(match.group(1))
        except json.JSONDecodeError:
            return "unavailable"
        if not isinstance(meta, dict):
            return "unavailable"
    return "present"


def flatten_file_pages(raw: list) -> list[dict]:
    """Flatten `gh api --paginate --slurp` output (array of page arrays)."""
    if not isinstance(raw, list):
        raise ValueError("paginated files payload is not an array")
    records: list[dict] = []
    for page in raw:
        if not isinstance(page, list):
            raise ValueError("paginated files page is not an array")
        records.extend(page)
    return records


def normalize_file(record: dict) -> dict:
    """Normalize one REST PR-file record into {path, status, previous_path}."""
    if not isinstance(record, dict):
        raise ValueError("file record is not an object")
    path = record.get("filename")
    if not isinstance(path, str) or not path:
        raise ValueError("file record: filename missing or invalid")
    status = record.get("status")
    if not isinstance(status, str) or status not in VALID_FILE_STATUSES:
        raise ValueError(f"file record: unknown status {status!r}")
    previous = record.get("previous_filename")
    if previous is not None and not isinstance(previous, str):
        raise ValueError("file record: previous_filename invalid")
    return {"path": path, "status": status, "previous_path": previous or None}


def classify_files(files: list[dict]) -> dict:
    """Count markdown/non-markdown/rename-copy files and detect duplicates."""
    seen: set[str] = set()
    markdown = 0
    non_markdown = 0
    rename_copy = 0
    for file in files:
        path = file["path"]
        if path in seen:
            raise ValueError(f"duplicate file path: {path}")
        seen.add(path)
        if file["status"] in ("renamed", "copied") or file["previous_path"]:
            rename_copy += 1
        if path.lower().endswith(".md"):
            markdown += 1
        else:
            non_markdown += 1
    return {
        "files_total": len(files),
        "markdown_files": markdown,
        "non_markdown_files": non_markdown,
        "rename_copy_files": rename_copy,
    }


def evaluate(pr_data: dict) -> dict:
    """Apply G0-G4; returns {trivial, matched_rules, reason, stats}.

    metadata_state 'unavailable' is handled by the caller (exit 2); here any
    non-'empty' state simply cannot be trivial.
    """
    stats = classify_files(pr_data["files"])
    if pr_data["metadata_state"] != "empty":
        return {
            "trivial": False,
            "matched_rules": [],
            "reason": "metadata not empty",
            "stats": stats,
        }
    if pr_data["state"] != "OPEN" or pr_data["is_draft"]:
        return {
            "trivial": False,
            "matched_rules": [],
            "reason": "not open or draft",
            "stats": stats,
        }
    if pr_data["changed_files"] <= 0:
        return {"trivial": False, "matched_rules": [], "reason": "no changed files", "stats": stats}
    if stats["rename_copy_files"] > 0:
        return {
            "trivial": False,
            "matched_rules": [],
            "reason": "rename/copy present",
            "stats": stats,
        }
    if stats["non_markdown_files"] > 0:
        return {
            "trivial": False,
            "matched_rules": [],
            "reason": "non-markdown files present",
            "stats": stats,
        }
    return {
        "trivial": True,
        "matched_rules": ["markdown-only"],
        "reason": f"all {stats['files_total']} changed files have .md extension",
        "stats": stats,
    }


def build_report_payload(pr_data: dict, result: dict) -> dict:
    """Assemble the fixed Round-1 PASS payload for render_status_report."""
    return {
        "pr_number": pr_data["number"],
        "round": 1,
        "head_sha": pr_data["head_sha"],
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
        "note": f"trivial precheck skip: {result['reason']}",
    }


def _run_gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def _resolve_repo() -> str:
    proc = _run_gh(["repo", "view", "--json", "nameWithOwner"])
    if proc.returncode != 0:
        raise RuntimeError(f"gh repo view failed: {proc.stderr.strip()}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh repo view payload invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("gh repo view payload is not an object")
    name = payload.get("nameWithOwner")
    if not isinstance(name, str) or not name:
        raise RuntimeError("gh repo view: nameWithOwner missing")
    return name


def fetch_pr_data(ref: str, repo: str | None) -> dict:
    """Fetch PR base fields and the complete paginated file list via gh."""
    resolved_repo, number = normalize_pr_ref(ref, repo)
    if not resolved_repo:
        resolved_repo = _resolve_repo()
    view = _run_gh(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            resolved_repo,
            "--json",
            "number,state,isDraft,changedFiles,headRefOid,reviews",
        ]
    )
    if view.returncode != 0:
        raise RuntimeError(f"gh pr view failed: {view.stderr.strip()}")
    try:
        pr = parse_pr_view(json.loads(view.stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"gh pr view payload invalid: {exc}") from exc
    files_proc = _run_gh(
        ["api", "--paginate", "--slurp", f"repos/{resolved_repo}/pulls/{number}/files?per_page=100"]
    )
    if files_proc.returncode != 0:
        raise RuntimeError(f"gh api files failed: {files_proc.stderr.strip()}")
    try:
        records = flatten_file_pages(json.loads(files_proc.stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"gh api files payload invalid: {exc}") from exc
    files = [normalize_file(record) for record in records]
    if len(files) != pr["changed_files"]:
        raise RuntimeError(
            f"file list incomplete: changedFiles={pr['changed_files']}, got {len(files)}"
        )
    return {
        "number": pr["number"],
        "state": pr["state"],
        "is_draft": pr["is_draft"],
        "head_sha": pr["head_sha"],
        "changed_files": pr["changed_files"],
        "metadata_state": inspect_metadata(pr["reviews"]),
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", help="PR number, github.com PR URL, or owner/repo#N")
    parser.add_argument("--repo", default=None, help="owner/repo override")
    parser.add_argument(
        "--report",
        action="store_true",
        help="emit the full status report on trivial hit (Step 1 mode)",
    )
    args = parser.parse_args(argv)

    try:
        pr_data = fetch_pr_data(args.pr, args.repo)
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"trivial_check: {exc}", file=sys.stderr)
        return 2

    if pr_data["metadata_state"] == "unavailable":
        print("trivial_check: pi-cr metadata state unavailable", file=sys.stderr)
        return 2

    result = evaluate(pr_data)

    if args.report:
        if not result["trivial"]:
            print(f"trivial_check: not trivial: {result['reason']}", file=sys.stderr)
            return 1
        try:
            payload = build_report_payload(pr_data, result)
            sys.stdout.write(render_status_report.render(payload))
        except Exception as exc:  # noqa: BLE001 - renderer must never emit a partial report
            print(f"trivial_check: render failed: {exc}", file=sys.stderr)
            return 2
        return 0

    out = {
        "trivial": result["trivial"],
        "matched_rules": result["matched_rules"],
        "reason": result["reason"],
        "stats": result["stats"],
        "pr": {
            "number": pr_data["number"],
            "state": pr_data["state"],
            "is_draft": pr_data["is_draft"],
            "head_sha": pr_data["head_sha"],
        },
        "metadata_state": pr_data["metadata_state"],
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
