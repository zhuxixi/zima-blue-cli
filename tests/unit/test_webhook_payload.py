"""Tests for GitHub webhook payload parsing."""

import hashlib
import hmac

from zima.webhook.payload import (
    PullRequestLabeledEvent,
    is_valid_repo,
    parse_pull_request_labeled,
    should_trigger_review,
    verify_signature,
)


class TestVerifySignature:
    """Tests for HMAC-SHA256 signature verification."""

    def test_verify_signature_valid(self):
        """Valid signature returns True."""
        secret = "my-secret"
        payload = b'{"action":"labeled"}'

        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, expected, secret) is True

    def test_verify_signature_invalid(self):
        """Invalid signature returns False."""
        assert verify_signature(b"{}", "sha256=abc123", "secret") is False

    def test_verify_signature_missing(self):
        """Missing signature with secret provided returns False."""
        assert verify_signature(b"{}", "", "secret") is False

    def test_verify_signature_no_secret(self):
        """No secret means verification is skipped."""
        assert verify_signature(b"{}", "", "") is True


class TestParsePullRequestLabeled:
    """Tests for parsing labeled payload."""

    def test_parse_valid_labeled_event(self):
        """Parse a valid pull_request.labeled event."""
        payload = {
            "action": "labeled",
            "label": {"name": "zima:needs-review"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head": {"sha": "5fd94cc2a5c187d2854fd11b82fe6eac601e2e5a"},
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        }
        event = parse_pull_request_labeled(payload)
        assert event is not None
        assert event.action == "labeled"
        assert event.label_name == "zima:needs-review"
        assert event.repo == "owner/repo"
        assert event.pr_number == 42
        assert event.head_sha == "5fd94cc2a5c187d2854fd11b82fe6eac601e2e5a"
        assert event.draft is False
        assert event.state == "open"

    def test_parse_rejects_malformed_repo(self):
        """Repo with metacharacters is rejected (injection guard)."""
        payload = {
            "action": "labeled",
            "label": {"name": "zima:needs-review"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head": {"sha": "5fd94cc2a5c187d2854fd11b82fe6eac601e2e5a"},
                "base": {"repo": {"full_name": "owner/repo; rm -rf /"}},
            },
        }
        assert parse_pull_request_labeled(payload) is None

    def test_parse_rejects_malformed_head_sha(self):
        """head_sha with non-hex/short value is rejected (injection guard)."""
        payload = {
            "action": "labeled",
            "label": {"name": "zima:needs-review"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head": {"sha": "abc; --dangerous"},
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        }
        assert parse_pull_request_labeled(payload) is None

    def test_parse_wrong_action(self):
        """Non-labeled action returns None."""
        payload = {
            "action": "opened",
            "label": {"name": "zima:needs-review"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head": {"sha": "abc"},
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        }
        assert parse_pull_request_labeled(payload) is None

    def test_parse_wrong_label(self):
        """Wrong label returns None."""
        payload = {
            "action": "labeled",
            "label": {"name": "bug"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head": {"sha": "abc"},
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        }
        assert parse_pull_request_labeled(payload) is None

    def test_parse_missing_pull_request(self):
        """Missing pull_request returns None."""
        payload = {"action": "labeled", "label": {"name": "zima:needs-review"}}
        assert parse_pull_request_labeled(payload) is None


class TestShouldTriggerReview:
    """Tests for trigger decision."""

    def test_trigger_open_non_draft(self):
        """Open non-draft PR triggers."""
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open"
        )
        assert should_trigger_review(event) is True

    def test_skip_draft(self):
        """Draft PR is skipped by default."""
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", True, "open"
        )
        assert should_trigger_review(event) is False

    def test_include_draft_when_configured(self):
        """Draft PR included if skip_draft=False."""
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", True, "open"
        )
        assert should_trigger_review(event, skip_draft=False) is True

    def test_skip_closed(self):
        """Closed PR is skipped."""
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "closed"
        )
        assert should_trigger_review(event) is False


class TestIsValidRepo:
    """Tests for the repo identifier validator (shared by parsing and --repo CLI)."""

    def test_valid_owner_name(self):
        """Plain owner/name is valid."""
        assert is_valid_repo("owner/repo") is True

    def test_valid_with_dots_dashes_underscores(self):
        """Allowable punctuation in owner/name segments is valid."""
        assert is_valid_repo("owner.name/my_repo-1") is True

    def test_valid_mixed_case(self):
        """Mixed case (GitHub owner/repo) is valid."""
        assert is_valid_repo("EllingZheng/zima-blue-cli") is True

    def test_reject_missing_slash(self):
        """No separator is invalid."""
        assert is_valid_repo("ownerrepo") is False

    def test_reject_shell_injection(self):
        """Metacharacters are rejected (injection guard)."""
        assert is_valid_repo("owner/repo; rm -rf /") is False

    def test_reject_non_string(self):
        """Non-string input is rejected rather than raising."""
        assert is_valid_repo(None) is False  # type: ignore[arg-type]
        assert is_valid_repo(123) is False  # type: ignore[arg-type]
