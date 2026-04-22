from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewIssue:
    """Single review issue found in code.

    Attributes:
        severity: Issue severity level. One of "error", "warning", or "info".
        file: Path to the file where the issue was found.
        line: Line number in the file where the issue was found.
        message: Human-readable description of the issue.
    """

    severity: str = "warning"  # error, warning, info
    file: str = ""
    line: int = 0
    message: str = ""


@dataclass
class ReviewResult:
    """Parsed result of an agent code review.

    Attributes:
        verdict: Overall review verdict. One of "approved", "needs_fix",
            or "needs_discussion".
        summary: High-level summary of the review findings.
        issues: List of individual issues found during the review.
    """

    verdict: str = ""  # approved, needs_fix, needs_discussion
    summary: str = ""
    issues: list[ReviewIssue] = field(default_factory=list)
