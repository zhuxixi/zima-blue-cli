#!/usr/bin/env python3
"""Pure, deterministic core of Step 0.2a — match committer comments to previous
issues and classify the response (#125).

Step 0.2a is intentionally heuristic, but the keyword table + match keys are
deterministic enough to extract and unit-test. This script does the scriptable
part; the skill's LLM still does final adjudication for genuinely ambiguous
multi-signal comments (see flow.md Step 0.2a). Having the rules as a pure
function also gives #125 its regression safety net.

Input (stdin): JSON
  {
    "previous_issues": [ {id, description, file, lines, status}, ... ],
    "committer_comments": [ "comment text", ... ]
  }
Output (stdout): JSON list, one entry per OPEN previous issue:
  [ {issue_id, resolution, committer_note}, ... ]
  resolution in {"resolved","wontfix","clarified", null}
  committer_note is the first matching comment text, or null

Precedence: resolved > clarified > wontfix > null — honoring Step 0.2a's
"prefer clarified over wontfix when ambiguous".
"""

from __future__ import annotations

import json
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Keyword table mirrored from flow.md Step 0.2a. Order within the dict is NOT
# the precedence — see _PRECEDENCE below.
RESOLUTION_KEYWORDS: dict[str, list[str]] = {
    "resolved": ["fixed", "已修复", "done", "resolved", "addressed"],
    "clarified": [
        "clarify",
        "说明",
        "actually",
        "context:",
        "returns",
        "只返回",
        "strictly",
    ],
    "wontfix": [
        "wontfix",
        "won't fix",
        "by design",
        "intentional",
        "not a bug",
        "不需要修复",
        "不修复",
        "设计如此",
    ],
}
# resolved is the strongest signal; clarified beats wontfix when both appear.
_PRECEDENCE = ["resolved", "clarified", "wontfix"]

_TOKEN_RE = re.compile(r"\S+")


def _first_tokens(text: str, limit: int = 10) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)[:limit]]


def comment_mentions_issue(issue: dict, comment: str) -> bool:
    """True if `comment` refers to `issue` via any of the 3 Step 0.2a match keys."""
    c = comment.lower()
    # (a) literal issue-id reference, e.g. "issue-2". The id field already
    #     carries the full token ("issue-1"), so match it as a delimited token
    #     so "issue-1" doesn't match "issue-10".
    iid = str(issue.get("id", "")).lower()
    if iid and re.search(rf"(?<![\w-]){re.escape(iid)}(?![\w-])", c):
        return True
    # (b) file path + lines together
    file = str(issue.get("file", "")).lower()
    lines = str(issue.get("lines", "")).lower()
    if file and lines and file in c and lines in c:
        return True
    # (c) a run of >=4 description tokens quoted in the comment (a deterministic
    #     take on "前 10 个单词"). CJK descriptions without spaces produce <4
    #     tokens and fall back to keys (a)/(b) — documented, tested.
    desc_tokens = _first_tokens(str(issue.get("description", "")), 10)
    if len(desc_tokens) >= 4:
        c_norm = " ".join(_TOKEN_RE.findall(c))
        for i in range(len(desc_tokens) - 3):
            if " ".join(desc_tokens[i : i + 4]) in c_norm:
                return True
    return False


def classify_resolution(comment: str) -> str | None:
    """Classify a committer comment via the keyword table (resolved>clarified>wontfix)."""
    c = comment.lower()
    for category in _PRECEDENCE:
        if any(kw.lower() in c for kw in RESOLUTION_KEYWORDS[category]):
            return category
    return None


def match_committer_response(
    previous_issues: list[dict], committer_comments: list[str]
) -> list[dict]:
    results: list[dict] = []
    for issue in previous_issues:
        if issue.get("status") != "open":
            continue
        note = None
        resolution = None
        for comment in committer_comments:
            if comment_mentions_issue(issue, comment):
                note = comment
                resolution = classify_resolution(comment)
                break
        results.append(
            {"issue_id": issue.get("id"), "resolution": resolution, "committer_note": note}
        )
    return results


def main() -> int:
    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"match_committer_response: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2
    out = match_committer_response(d.get("previous_issues", []), d.get("committer_comments", []))
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
