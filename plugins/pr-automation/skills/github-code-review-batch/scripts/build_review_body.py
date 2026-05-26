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
                                          status, first_round, resolution?, committer_note?}
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def gh_link(owner: str, repo: str, sha: str, file: str, lines: str) -> str:
    return f"https://github.com/{owner}/{repo}/blob/{sha}/{file}#L{lines.replace('-', '-L')}"


def build_metadata(d: dict) -> str:
    keys = [
        "round", "pr_number", "head_sha", "previous_head_sha",
        "total_issues", "resolved_count", "new_count", "acknowledged_count",
        "issues", "timestamp",
    ]
    payload = {k: d.get(k) for k in keys}
    payload["total_issues"] = d.get("total_issues", len([
        i for i in d.get("issues", [])
        if i.get("status") == "open" and i.get("resolution") not in ("acknowledged", "wontfix")
    ]))
    payload["resolved_count"] = d.get("resolved_count", len(d.get("resolved_issues", [])))
    payload["new_count"] = d.get("new_count", len(d.get("new_issues", [])))
    payload["acknowledged_count"] = d.get("acknowledged_count", len(d.get("acknowledged_issues", [])))
    return f"<!-- cc-cr-meta\n{json.dumps(payload, ensure_ascii=False)}\n-->"


def render_round_1(d: dict) -> str:
    issues = d.get("issues", [])
    if not issues:
        return "### Code Review | Round-1\n\nNo issues found. Checked for bugs, CLAUDE.md and AGENTS.md compliance."
    parts = ["### Code Review | Round-1", "", f"Found {len(issues)} issues:", ""]
    for i, issue in enumerate(issues, 1):
        parts.append(f"{i}. {issue['description']} ({issue['reason']})")
        parts.append("")
        parts.append(gh_link(d["repo_owner"], d["repo_name"], d["head_sha"],
                             issue["file"], issue["lines"]))
        parts.append("")
    return "\n".join(parts).rstrip()


def render_round_n(d: dict) -> str:
    n = d["round"]
    prev_n = n - 1
    prev_count = d.get("prev_round_count", 0)
    resolved = d.get("resolved_issues", [])
    acknowledged = d.get("acknowledged_issues", [])
    unresolved = d.get("unresolved_issues", [])
    new_issues = d.get("new_issues", [])

    still_open = len(unresolved)
    all_resolved = (still_open == 0 and len(new_issues) == 0)

    lines: list[str] = [f"### Code Review | Round-{n} (Re-check)", ""]
    lines.append(f"Previous Round-{prev_n} issues: {prev_count}")
    if all_resolved:
        lines.append(f"- **Resolved**: {len(resolved)}")
        lines.append("- **Still open**: 0")
        lines.extend(["", "New issues found: 0", "", "✅ **All issues resolved!**"])
        return "\n".join(lines)

    resolved_label = ", ".join(r.get("description", "")[:40] for r in resolved) if resolved else ""
    ack_label = ", ".join(a.get("description", "")[:40] for a in acknowledged) if acknowledged else ""
    lines.append(f"- **Resolved**: {len(resolved)}" + (f" ({resolved_label})" if resolved_label else ""))
    if acknowledged:
        lines.append(f"- **Acknowledged / Won't Fix**: {len(acknowledged)}" + (f" ({ack_label})" if ack_label else ""))
    lines.append(f"- **Still open**: {still_open}")
    lines.append("")
    lines.append(f"New issues found: {len(new_issues)}")
    lines.append("")

    if acknowledged:
        lines.append("#### Acknowledged / Won't Fix")
        lines.append("")
        for i, item in enumerate(acknowledged, 1):
            note = item.get("committer_note", "")
            suffix = f" (committer: {note})" if note else ""
            lines.append(f"{i}. {item['description']}{suffix}")
        lines.append("")

    if unresolved:
        lines.append(f"#### Still Open from Previous Rounds")
        lines.append("")
        for i, item in enumerate(unresolved, 1):
            lines.append(f"{i}. {item['description']} ({item['reason']})")
            lines.append("")
            lines.append(gh_link(d["repo_owner"], d["repo_name"], d["head_sha"],
                                 item["file"], item["lines"]))
            lines.append("")

    if new_issues:
        lines.append("#### New Issues")
        lines.append("")
        for i, item in enumerate(new_issues, 1):
            lines.append(f"{i}. {item['description']} ({item['reason']})")
            lines.append("")
            lines.append(gh_link(d["repo_owner"], d["repo_name"], d["head_sha"],
                                 item["file"], item["lines"]))
            lines.append("")

    return "\n".join(lines).rstrip()


def render_body(d: dict) -> str:
    metadata = build_metadata(d)
    body = render_round_1(d) if d["round"] == 1 else render_round_n(d)
    return f"{metadata}\n\n{body}\n\n🤖 Generated with Claude Code\n"


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
