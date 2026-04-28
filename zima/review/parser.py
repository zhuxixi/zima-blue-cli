"""Code review result parser - extracts structured review output from agent stdout."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

# Maximum XML content size to prevent billion laughs / XML bomb attacks
_MAX_REVIEW_XML_SIZE = 1024 * 1024  # 1 MB


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


class ReviewParser:
    """Parse structured review output from agent stdout."""

    @staticmethod
    def parse(stdout: str) -> ReviewResult:
        """Extract <zima-review> XML block from stdout and parse into ReviewResult.

        Args:
            stdout: Raw agent output string to parse.

        Returns:
            ReviewResult with parsed verdict, summary, and issues. If no
            <zima-review> block is found or the XML is invalid, falls back
            to parsing skill output patterns (e.g. "Found N issues" or
            "No issues found"). If fallback parsing also fails, returns
            ReviewResult(verdict="needs_discussion").
        """
        # Security: limit input size to prevent billion laughs / XML bomb
        if len(stdout) > _MAX_REVIEW_XML_SIZE:
            return ReviewResult(
                verdict="needs_discussion",
                summary="Agent output too large for review parsing",
            )

        match = re.search(r"<zima-review>(.*?)</zima-review>", stdout, re.DOTALL)
        if not match:
            # Also try to match an unclosed <zima-review> tag (malformed XML)
            unclosed_match = re.search(r"<zima-review>(.*)", stdout, re.DOTALL)
            if unclosed_match:
                xml_content = f"<zima-review>{unclosed_match.group(1)}</zima-review>"
                try:
                    root = ET.fromstring(xml_content)
                except ET.ParseError:
                    return ReviewParser._fallback_parse(stdout)
            else:
                return ReviewParser._fallback_parse(stdout)
        else:
            xml_content = f"<zima-review>{match.group(1)}</zima-review>"
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError:
                return ReviewParser._fallback_parse(stdout)
        verdict = root.findtext("verdict", default="needs_discussion").strip()
        summary = root.findtext("summary", default="").strip()

        issues = []
        issues_elem = root.find("issues")
        if issues_elem is not None:
            for issue_elem in issues_elem.findall("issue"):
                line_str = issue_elem.get("line", "")
                try:
                    line_num = int(line_str) if line_str else 0
                except ValueError:
                    line_num = 0
                issues.append(
                    ReviewIssue(
                        severity=issue_elem.get("severity", "warning"),
                        file=issue_elem.get("file", ""),
                        line=line_num,
                        message=(issue_elem.text or "").strip(),
                    )
                )

        return ReviewResult(verdict=verdict, summary=summary, issues=issues)

    @staticmethod
    def _fallback_parse(stdout: str) -> ReviewResult:
        """Parse review result from skill output patterns when XML is absent."""
        if "No issues found" in stdout:
            return ReviewResult(verdict="approved", summary="No issues found")
        match = re.search(r"\bFound\s+(\d+)\s+issues?\b", stdout, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            if count == 0:
                return ReviewResult(verdict="approved", summary="Found 0 issues")
            return ReviewResult(verdict="needs_fix", summary=f"Found {count} issues")
        return ReviewResult(
            verdict="needs_discussion",
            summary="No review block found in agent output",
        )
