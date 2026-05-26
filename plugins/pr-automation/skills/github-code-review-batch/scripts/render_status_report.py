#!/usr/bin/env python3
"""Render the CR Batch Status Report block.

Input (stdin): JSON object with the following fields:
  pr_number          int
  round              int
  head_sha           str
  previous_head_sha  str | null
  open_count         int  — total currently-open issues (excluding acknowledged)
  new_count          int
  unresolved_count   int  — open issues carried from previous rounds
  resolved_count     int
  acknowledged_count int
  status             str  — "NEEDS_FIX" | "PASS" | "NO_NEW_COMMITS"

Output (stdout): the multi-line status report block.
"""

from __future__ import annotations

import json
import sys

VALID_STATUSES = {"NEEDS_FIX", "PASS", "NO_NEW_COMMITS"}

TEMPLATE = """\
=== CR Batch Status Report ===
PR: #{pr_number} | Round: {round} | Head SHA: {head_sha}
Previous Head SHA: {previous_head_sha}
Total open issues: {open_count}
- New this round: {new_count}
- Still open from previous: {unresolved_count}
- Resolved this round: {resolved_count}
- Acknowledged / Won't Fix: {acknowledged_count}
Status: {status}
================================
"""


def render(d: dict) -> str:
    status = d.get("status", "")
    if status not in VALID_STATUSES:
        print(f"render_status_report: invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}",
              file=sys.stderr)
        sys.exit(2)
    return TEMPLATE.format(
        pr_number=d.get("pr_number", ""),
        round=d.get("round", ""),
        head_sha=d.get("head_sha", ""),
        previous_head_sha=d.get("previous_head_sha", "null") if d.get("previous_head_sha") is not None else "null",
        open_count=d.get("open_count", 0),
        new_count=d.get("new_count", 0),
        unresolved_count=d.get("unresolved_count", 0),
        resolved_count=d.get("resolved_count", 0),
        acknowledged_count=d.get("acknowledged_count", 0),
        status=status,
    )


def main() -> int:
    raw = sys.stdin.read()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"render_status_report: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(render(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
