#!/usr/bin/env python3
"""Extract latest cc-cr-meta JSON from PR review comments.

Input (stdin): JSON output of `gh pr view <PR> --json reviews`.
  Either the full object {"reviews": [...]} (gh-native `submittedAt` key)
  or a stream of {body, submitted_at} records (one per line) as produced by
  the --jq filter. Both key spellings are accepted when ordering by timestamp.

Output (stdout): Latest cc-cr-meta JSON object, or {} if not found.
Exit codes:
  0 success (including "no metadata found, output {}")
  2 stdin not valid JSON
"""

from __future__ import annotations

import json
import re
import sys

CC_MARKER = "Generated with Claude Code"
META_MARKER = "<!-- cc-cr-meta"
META_RE = re.compile(r"<!--\s*cc-cr-meta\s*\n(.*?)\n\s*-->", re.DOTALL)


def load_reviews(raw: str) -> list[dict]:
    """Accept both {"reviews": [...]} and JSON-Lines from --jq."""
    raw = raw.strip()
    if not raw:
        return []
    # Try whole-document parse first.
    try:
        doc = json.loads(raw)
        if isinstance(doc, dict) and "reviews" in doc:
            return doc["reviews"]
        if isinstance(doc, list):
            return doc
        if isinstance(doc, dict):
            return [doc]
    except json.JSONDecodeError:
        pass
    # Fall back to JSON-Lines.
    out: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def extract_latest_meta(reviews: list[dict]) -> dict:
    candidates = [
        r
        for r in reviews
        if isinstance(r, dict)
        and isinstance(r.get("body"), str)
        and CC_MARKER in r["body"]
        and META_MARKER in r["body"]
    ]
    if not candidates:
        return {}
    # gh emits `submittedAt` (camelCase) on full `--json reviews` objects; the
    # --jq stream variant renames it to `submitted_at`. Accept both spellings,
    # and coerce missing/null to "" so the stable sort doesn't silently collapse
    # every candidate to an equal key (which would return the OLDEST, not the
    # latest, review).
    candidates.sort(
        key=lambda r: r.get("submittedAt") or r.get("submitted_at") or "",
        reverse=True,
    )
    for review in candidates:
        match = META_RE.search(review["body"])
        if not match:
            continue
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
    return {}


def main() -> int:
    raw = sys.stdin.read()
    try:
        reviews = load_reviews(raw)
    except Exception as exc:
        print(f"parse_metadata: failed to read stdin: {exc}", file=sys.stderr)
        return 2
    meta = extract_latest_meta(reviews)
    json.dump(meta, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
