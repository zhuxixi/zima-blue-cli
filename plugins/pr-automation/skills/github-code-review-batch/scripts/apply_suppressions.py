#!/usr/bin/env python3
"""Apply an optional cross-PR suppression list (#126).

Lets a repo owner stop the skill from re-raising issue classes that have been
repeatedly wontfix'd, without editing the skill. Default-off: no suppressions
=> everything stays open. Suppressed issues are NOT counted as open and do NOT
trigger fix-agent, but are still returned (for human visibility in the report).

Input (stdin): JSON
  {
    "issues":        [ {description, reason, ...}, ... ],
    "suppressions":  [ {pattern?, reason?, expires?, rationale?}, ... ],
    "today?":        "YYYY-MM-DD"   # for testing; defaults to today
  }
Output (stdout): JSON { "open": [...], "suppressed": [...] }

A suppression matches an issue iff:
  - reason  unset OR == issue.reason, AND
  - pattern unset OR (pattern, case-insensitive, is a substring of description)
AND the suppression is active (expires unset OR expires >= today).

Portability: stdlib only. Default-off by design — never over-suppress.
"""

from __future__ import annotations

import json
import sys
from datetime import date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _is_active(sup, today: date) -> bool:
    exp = _parse_date(sup.get("expires"))
    return exp is None or exp >= today


def _matches(sup: dict, issue: dict) -> bool:
    reason = sup.get("reason")
    pattern = sup.get("pattern")
    if reason is not None and reason != issue.get("reason"):
        return False
    if (
        pattern is not None
        and str(pattern).lower() not in str(issue.get("description", "")).lower()
    ):
        return False
    return True  # both unset = catch-all; otherwise one/both matched


def apply_suppressions(issues: list[dict], suppressions: list[dict], today=None) -> dict:
    if today is None:
        today = date.today()
    active = [s for s in suppressions if _is_active(s, today)]
    open_out: list[dict] = []
    suppressed: list[dict] = []
    for issue in issues:
        hit = next((s for s in active if _matches(s, issue)), None)
        if hit:
            marked = dict(issue)
            marked["suppressed_reason"] = (
                hit.get("rationale") or hit.get("pattern") or hit.get("reason")
            )
            suppressed.append(marked)
        else:
            open_out.append(issue)
    return {"open": open_out, "suppressed": suppressed}


def main() -> int:
    raw = sys.stdin.read()
    try:
        d = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"apply_suppressions: invalid JSON on stdin: {exc}", file=sys.stderr)
        return 2
    out = apply_suppressions(
        d.get("issues", []),
        d.get("suppressions", []),
        _parse_date(d.get("today")),
    )
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
