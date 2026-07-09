"""GitHub webhook payload parsing and validation."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from hashlib import sha256
from typing import Optional


@dataclass
class PullRequestLabeledEvent:
    """Normalized pull_request.labeled event."""

    action: str
    label_name: str
    repo: str
    pr_number: int
    head_sha: str
    draft: bool
    state: str


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature.

    If no secret is configured, verification is skipped.
    """
    if not secret:
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_pull_request_labeled(payload: dict) -> Optional[PullRequestLabeledEvent]:
    """Parse a pull_request.labeled event for zima:needs-review."""
    if not isinstance(payload, dict):
        return None

    if payload.get("action") != "labeled":
        return None

    label = payload.get("label") or {}
    if label.get("name") != "zima:needs-review":
        return None

    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        return None

    repo = pr.get("base", {}).get("repo", {}).get("full_name")
    if not repo:
        return None

    return PullRequestLabeledEvent(
        action="labeled",
        label_name="zima:needs-review",
        repo=repo,
        pr_number=int(pr.get("number", 0)),
        head_sha=str(pr.get("head", {}).get("sha", "")),
        draft=bool(pr.get("draft", False)),
        state=str(pr.get("state", "")),
    )


def should_trigger_review(event: PullRequestLabeledEvent, skip_draft: bool = True) -> bool:
    """Decide whether to trigger review for this event."""
    if event.state != "open":
        return False
    if skip_draft and event.draft:
        return False
    return True
