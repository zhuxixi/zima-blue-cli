"""Shared severity, blocking, and count policy for code-review issues."""

from typing import Any, Iterable, Mapping

_VALID_SEVERITIES = ("critical", "high", "medium", "low")
_DEFAULT_SEVERITY = "medium"


def normalize_severity(issue: Mapping[str, Any]) -> str:
    """Return a supported severity, defaulting missing or invalid values to medium."""
    severity = issue.get("severity")
    if severity in _VALID_SEVERITIES:
        return severity
    return _DEFAULT_SEVERITY


def is_blocking(issue: Mapping[str, Any]) -> bool:
    """Return an explicit boolean override or the severity-based default."""
    blocking = issue.get("blocking")
    if isinstance(blocking, bool):
        return blocking
    return normalize_severity(issue) != "low"


def normalize_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    """Copy an issue and add its normalized blocking policy decision."""
    normalized = dict(issue)
    normalized["blocking"] = is_blocking(issue)
    return normalized


def is_active_issue(issue: Mapping[str, Any]) -> bool:
    """Return whether an issue remains open and actionable.

    Legacy issue dictionaries predate the lifecycle field, so a missing status
    is treated as open. Explicit lifecycle or resolution markers still make a
    finding inactive.
    """
    return issue.get("status", "open") == "open" and issue.get("resolution") not in (
        "resolved",
        "acknowledged",
        "wontfix",
    )


def count_issues(issues: Iterable[Mapping[str, Any]], active_only: bool = False) -> dict[str, int]:
    """Count total, blocking, advisory, and blocking-critical issues."""
    counts = {"total": 0, "blocking": 0, "advisory": 0, "critical": 0}
    for issue in issues:
        if active_only and not is_active_issue(issue):
            continue

        blocking = is_blocking(issue)
        counts["total"] += 1
        if blocking:
            counts["blocking"] += 1
            if normalize_severity(issue) == "critical":
                counts["critical"] += 1
        else:
            counts["advisory"] += 1

    return counts
