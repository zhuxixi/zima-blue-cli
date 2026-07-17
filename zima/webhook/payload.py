"""GitHub webhook payload parsing and validation."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Optional

# Untrusted webhook fields (repo, head_sha) flow into PJob template variables
# via ``--set-var``. Reject anything outside these strict allow-lists so a
# malformed/forgeable payload cannot inject template or shell metacharacters.
# ``\Z`` (not ``$``) so a trailing newline can't sneak through the allow-list.
_VALID_REPO = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+\Z")
_VALID_SHA = re.compile(r"^[0-9a-f]{7,40}\Z")


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

    Returns ``True`` when ``secret`` is empty — this intentionally means "no
    verification requested". Fail-closed enforcement (refusing to run without a
    secret) lives at the server/command layer, not here, so this function is
    only reached when a secret is configured. See ``zima.commands.webhook``.
    """
    if not secret:
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_pull_request_labeled(payload: dict) -> Optional[PullRequestLabeledEvent]:
    """Parse a pull_request.labeled event for zima:needs-review.

    Defensive against malformed payloads: every nested lookup validates that the
    intermediate value is a dict/str before descending, so a non-dict ``base``
    or a non-string ``full_name`` resolves to ``None`` rather than raising.
    """
    if not isinstance(payload, dict):
        return None

    if payload.get("action") != "labeled":
        return None

    label = payload.get("label")
    if not isinstance(label, dict) or label.get("name") != "zima:needs-review":
        return None

    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        return None

    base = pr.get("base")
    if not isinstance(base, dict):
        return None
    repo_obj = base.get("repo")
    if not isinstance(repo_obj, dict):
        return None
    repo = repo_obj.get("full_name")
    if not isinstance(repo, str) or not _VALID_REPO.match(repo):
        return None

    try:
        pr_number = int(pr.get("number", 0))
    except (ValueError, TypeError):
        return None
    if pr_number <= 0:
        return None

    head = pr.get("head")
    if not isinstance(head, dict):
        return None
    head_sha = head.get("sha")
    if not isinstance(head_sha, str) or not _VALID_SHA.match(head_sha):
        return None

    return PullRequestLabeledEvent(
        action="labeled",
        label_name="zima:needs-review",
        repo=repo,
        pr_number=pr_number,
        head_sha=head_sha,
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
