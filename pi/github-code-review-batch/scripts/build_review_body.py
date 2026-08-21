#!/usr/bin/env python3
"""Build a Round-N PR review comment body.

Input (stdin): JSON object with the following fields:
  round              int   — current round (>=1)
  pr_number          int
  head_sha           str   — 40-char SHA
  previous_head_sha  str | null
  repo_owner         str
  repo_name          str
  timestamp          str   — ISO 8601, e.g. "2026-04-21T10:00:00Z"
  issues             list  — each item: {id, description, reason, file, lines,
                                          status, first_round, severity?,
                                          resolution?, committer_note?}
  resolved_issues    list  — items with description (used in Round-N summary line)
  acknowledged_issues list — items with description, committer_note
  new_issues         list  — items with id, description, reason, file, lines
  unresolved_issues  list  — items with description, reason, file, lines
  prev_round_count   int   — total issues in previous round (Round-1 ignores)

Output (stdout): full review body (HTML metadata + Markdown).
"""

from __future__ import annotations

import json
import sys

from issue_policy import count_issues, is_active_issue, normalize_issue

reconfigure = getattr(sys.stdout, "reconfigure", None)
if reconfigure is not None:
    reconfigure(encoding="utf-8")


def gh_link(owner: str, repo: str, sha: str, file: str, lines: str) -> str:
    return f"https://github.com/{owner}/{repo}/blob/{sha}/{file}#L{lines.replace('-', '-L')}"


# Severity ordering for the human-readable review body (#119). Lower rank sorts
# first (critical on top). Metadata `issues[]` keeps input order; only the
# rendered Markdown is re-sorted, so the historical record is preserved.
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _severity(issue: dict) -> str:
    """Issue severity with a 'medium' fallback (backward-compat, #119)."""
    sev = issue.get("severity") or "medium"
    return sev if sev in SEVERITY_RANK else "medium"


def _severity_rank(issue: dict) -> int:
    return SEVERITY_RANK[_severity(issue)]


def _short_label(text: str, limit: int = 60) -> str:
    """Summary-line truncation for Round-N labels (#175).

    Old behavior cut every description at exactly 40 characters, slicing CJK
    text mid-word and English mid-word alike. Prefer a word boundary when a
    space exists in the tail half of the window; CJK text without spaces
    falls back to a character cut. Always append an explicit ellipsis so the
    cut is visible. Metadata keeps the full description untouched — this only
    affects the human-readable summary line.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    tail = cut[limit // 2 :]
    if " " in tail:
        cut = cut[: cut.rfind(" ")]
    return cut + "..."


def _normalized(items: list[dict]) -> list[dict]:
    """Normalize issue copies without mutating the caller's payload."""
    return [normalize_issue(item) for item in items]


def _active(items: list[dict]) -> list[dict]:
    """Return active issue references under the shared lifecycle policy."""
    return [item for item in items if is_active_issue(item)]


def _issue_identity(issue: dict) -> tuple:
    """Return a stable identity for matching canonical issues to round buckets."""
    if issue.get("id"):
        return ("id", issue["id"])
    return (
        "content",
        issue.get("description"),
        issue.get("reason"),
        issue.get("file"),
        issue.get("lines"),
    )


def _round_n_collections(d: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Return canonical current, carried, and new active findings for Round N.

    A non-empty issues[] is the canonical current collection. first_round is
    the primary source marker; matching new_issues identities provide a
    compatibility fallback when old canonical findings lack first_round.
    Empty issues[] falls back to the unresolved/new buckets.
    """
    raw_issues = d.get("issues", [])
    bucket_new = _active(_normalized(d.get("new_issues", [])))
    if not raw_issues:
        carried = _active(_normalized(d.get("unresolved_issues", [])))
        return carried + bucket_new, carried, bucket_new

    issues = _active(_normalized(raw_issues))
    current_round = d.get("round")
    bucket_new_ids = {_issue_identity(issue) for issue in bucket_new}
    new = [
        issue
        for issue in issues
        if issue.get("first_round") == current_round
        or (issue.get("first_round") is None and _issue_identity(issue) in bucket_new_ids)
    ]
    new_ids = {_issue_identity(issue) for issue in new}
    carried = [issue for issue in issues if _issue_identity(issue) not in new_ids]
    return issues, carried, new


def _metadata_collections(d: dict) -> tuple[list[dict], list[dict]]:
    issues = _active(_normalized(d.get("issues", [])))
    if d.get("round") == 1:
        return issues, issues
    current, _, new = _round_n_collections(d)
    return current, new


def build_metadata(d: dict) -> str:
    keys = [
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
    ]
    current, new = _metadata_collections(d)
    current_counts = count_issues(current, active_only=True)
    new_counts = count_issues(new, active_only=True)
    payload = {k: d.get(k) for k in keys}
    payload["issues"] = current
    payload["total_issues"] = d.get("total_issues", current_counts["total"])
    payload["resolved_count"] = d.get("resolved_count", len(d.get("resolved_issues", [])))
    # Round-1 semantics: every active issue in issues[] is a new discovery.
    # Explicit new_count remains authoritative for legacy callers.
    default_new_count = current_counts["total"] if d.get("round") == 1 else len(new)
    payload["new_count"] = d.get("new_count", default_new_count)
    payload["acknowledged_count"] = d.get(
        "acknowledged_count", len(d.get("acknowledged_issues", []))
    )
    derived_counts = {
        "blocking_open_count": current_counts["blocking"],
        "blocking_new_count": new_counts["blocking"],
        "advisory_open_count": current_counts["advisory"],
        "advisory_new_count": new_counts["advisory"],
    }
    for key, value in derived_counts.items():
        payload[key] = d.get(key, value)
    return f"<!-- pi-cr-meta\n{json.dumps(payload, ensure_ascii=False)}\n-->"


def _render_issue(item: dict, d: dict, number: int) -> list[str]:
    description = item.get("description", "")
    reason = item.get("reason", "")
    lines = [f"{number}. {description} ({reason}, {_severity(item)})", ""]
    if item.get("file") and item.get("lines"):
        lines.extend(
            [
                gh_link(
                    d["repo_owner"], d["repo_name"], d["head_sha"], item["file"], item["lines"]
                ),
                "",
            ]
        )
    return lines


def _render_advisories(items: list[dict], d: dict) -> list[str]:
    if not items:
        return []
    lines = [
        "<details>",
        f"<summary>Advisory / non-blocking findings ({len(items)})</summary>",
        "",
    ]
    for i, item in enumerate(sorted(items, key=_severity_rank), 1):
        lines.extend(_render_issue(item, d, i))
    lines.extend(["</details>", ""])
    return lines


def _render_round_n_advisories(carried: list[dict], new: list[dict], d: dict) -> list[str]:
    total = len(carried) + len(new)
    if total == 0:
        return []
    lines = [
        "<details>",
        f"<summary>Advisory / non-blocking findings ({total})</summary>",
        "",
    ]
    if carried:
        lines.extend([f"#### Carried from previous rounds ({len(carried)})", ""])
        for i, item in enumerate(sorted(carried, key=_severity_rank), 1):
            lines.extend(_render_issue(item, d, i))
    if new:
        lines.extend([f"#### New this round ({len(new)})", ""])
        for i, item in enumerate(sorted(new, key=_severity_rank), 1):
            lines.extend(_render_issue(item, d, i))
    lines.extend(["</details>", ""])
    return lines


def render_round_1(d: dict) -> str:
    issues = _active(_normalized(d.get("issues", [])))
    if not issues:
        return "### Code Review | Round-1\n\nNo issues found. Checked for bugs, CLAUDE.md and AGENTS.md compliance."
    blocking = sorted([i for i in issues if i["blocking"]], key=_severity_rank)
    advisory = [i for i in issues if not i["blocking"]]
    parts = ["### Code Review | Round-1", ""]
    if blocking:
        plural = "s" if len(blocking) != 1 else ""
        parts.extend([f"Found {len(blocking)} blocking issue{plural}:", ""])
        for number, issue in enumerate(blocking, 1):
            parts.extend(_render_issue(issue, d, number))
    else:
        parts.append(f"No blocking issues found. {len(advisory)} advisory findings remain.")
        parts.append("")
    parts.extend(_render_advisories(advisory, d))
    return "\n".join(parts).rstrip()


def render_round_n(d: dict) -> str:
    n = d["round"]
    prev_n = n - 1
    prev_count = d.get("prev_round_count", 0)
    resolved = d.get("resolved_issues", [])
    acknowledged = d.get("acknowledged_issues", [])
    _, carried_all, new_all = _round_n_collections(d)
    carried_blocking = sorted([i for i in carried_all if i["blocking"]], key=_severity_rank)
    new_blocking = sorted([i for i in new_all if i["blocking"]], key=_severity_rank)
    carried_advisory = [i for i in carried_all if not i["blocking"]]
    new_advisory = [i for i in new_all if not i["blocking"]]
    all_resolved = not carried_all and not new_all

    lines: list[str] = [f"### Code Review | Round-{n} (Re-check)", ""]
    lines.append(f"Previous Round-{prev_n} issues: {prev_count}")
    if all_resolved:
        lines.append(f"- **Resolved**: {len(resolved)}")
        lines.append("- **Still open**: 0 blocking; 0 advisory")
        lines.extend(
            ["", "New issues found: 0 blocking; 0 advisory", "", "✅ **All issues resolved!**"]
        )
        return "\n".join(lines)

    resolved_label = (
        ", ".join(_short_label(r.get("description", "")) for r in resolved) if resolved else ""
    )
    ack_label = (
        ", ".join(_short_label(a.get("description", "")) for a in acknowledged)
        if acknowledged
        else ""
    )
    lines.append(
        f"- **Resolved**: {len(resolved)}" + (f" ({resolved_label})" if resolved_label else "")
    )
    if acknowledged:
        lines.append(
            f"- **Acknowledged / Won't Fix**: {len(acknowledged)}"
            + (f" ({ack_label})" if ack_label else "")
        )
    lines.append(
        f"- **Still open**: {len(carried_blocking)} blocking; " f"{len(carried_advisory)} advisory"
    )
    lines.append("")
    lines.append(f"New issues found: {len(new_blocking)} blocking; {len(new_advisory)} advisory")
    lines.append("")

    if acknowledged:
        lines.append("#### Acknowledged / Won't Fix")
        lines.append("")
        for i, item in enumerate(acknowledged, 1):
            note = item.get("committer_note", "")
            suffix = f" (committer: {note})" if note else ""
            lines.append(f"{i}. {item.get('description', '')}{suffix}")
        lines.append("")

    if carried_blocking:
        lines.append("#### Still Open from Previous Rounds")
        lines.append("")
        for i, item in enumerate(carried_blocking, 1):
            lines.extend(_render_issue(item, d, i))

    if new_blocking:
        lines.append("#### New Blocking Issues")
        lines.append("")
        for i, item in enumerate(new_blocking, 1):
            lines.extend(_render_issue(item, d, i))

    if not carried_blocking and not new_blocking and (carried_advisory or new_advisory):
        lines.append("No blocking issues remain. Advisory findings remain for visibility.")
        lines.append("")
    lines.extend(_render_round_n_advisories(carried_advisory, new_advisory, d))
    return "\n".join(lines).rstrip()


def render_body(d: dict) -> str:
    metadata = build_metadata(d)
    body = render_round_1(d) if d["round"] == 1 else render_round_n(d)
    return f"{metadata}\n\n{body}\n\n🤖 Generated with pi-coding-agent\n"


def main() -> int:
    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"build_review_body: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(render_body(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
