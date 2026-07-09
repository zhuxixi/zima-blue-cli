"""Tests for webhook HTTP server."""

import json
import sys
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from zima.webhook.payload import PullRequestLabeledEvent
from zima.webhook.server import (
    _MAX_CONTENT_LENGTH,
    WebhookRequestHandler,
    make_handler,
    trigger_pjobs,
)


class TestTriggerPjobs:
    """Tests for triggering PJobs from an event."""

    def test_trigger_pjobs_invokes_cli(self, monkeypatch):
        """trigger_pjobs calls sys.executable -m zima pjob run for each pjob code."""
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return None

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open"
        )
        trigger_pjobs(event, ["claude-cr", "kimi-cr"])
        assert len(calls) == 2
        assert calls[0][:6] == [sys.executable, "-m", "zima", "pjob", "run", "claude-cr"]
        assert calls[1][:6] == [sys.executable, "-m", "zima", "pjob", "run", "kimi-cr"]
        assert "--set-var=repo=owner/repo" in calls[0]
        assert "--set-var=pr=42" in calls[0]
        assert "--set-var=head_sha=abc" in calls[0]

    def test_trigger_pjobs_survives_missing_zima(self, monkeypatch, capsys):
        """trigger_pjobs logs spawn errors but does not raise."""

        def fake_popen(args, **kwargs):
            raise FileNotFoundError("zima not found")

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open"
        )
        trigger_pjobs(event, ["claude-cr"])
        captured = capsys.readouterr()
        assert "failed to spawn zima" in captured.err


class TestWebhookRequestHandler:
    """Tests for HTTP handler."""

    def test_webhook_request_handler_is_base_handler(self):
        """WebhookRequestHandler is a BaseHTTPRequestHandler subclass."""
        assert issubclass(WebhookRequestHandler, BaseHTTPRequestHandler)

    @pytest.fixture
    def server(self, tmp_path):
        """Start a temporary HTTP server for testing."""
        handler = make_handler(pjob_codes=["claude-cr"], secret=None, skip_draft=True)
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield httpd.server_address
        httpd.shutdown()

    def test_valid_labeled_event(self, server, monkeypatch):
        """Valid labeled event returns 200 and triggers PJob."""
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return None

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)

        host, port = server
        payload = json.dumps(
            {
                "action": "labeled",
                "label": {"name": "zima:needs-review"},
                "pull_request": {
                    "number": 42,
                    "state": "open",
                    "draft": False,
                    "head": {"sha": "abc123"},
                    "base": {"repo": {"full_name": "owner/repo"}},
                },
            }
        ).encode()

        conn = HTTPConnection(host, port)
        conn.request("POST", "/webhook", body=payload, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        assert response.status == 200
        assert len(calls) == 1
        assert calls[0][:5] == [sys.executable, "-m", "zima", "pjob", "run"]
        assert calls[0][5] == "claude-cr"
        assert "--set-var=repo=owner/repo" in calls[0]

    def test_ignores_non_labeled(self, server, monkeypatch):
        """Non-labeled action returns 200 but does not trigger."""
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return None

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)

        host, port = server
        payload = json.dumps(
            {
                "action": "opened",
                "pull_request": {
                    "number": 42,
                    "state": "open",
                    "draft": False,
                    "head": {"sha": "abc"},
                    "base": {"repo": {"full_name": "owner/repo"}},
                },
            }
        ).encode()

        conn = HTTPConnection(host, port)
        conn.request("POST", "/webhook", body=payload, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        assert response.status == 200
        assert calls == []

    def test_invalid_signature_returns_400(self, server):
        """Invalid signature returns 400 when secret is set."""
        handler = make_handler(pjob_codes=["claude-cr"], secret="secret", skip_draft=True)
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            payload = b'{"action":"labeled"}'
            conn = HTTPConnection("127.0.0.1", httpd.server_address[1])
            conn.request(
                "POST",
                "/webhook",
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
            )
            response = conn.getresponse()
            assert response.status == 400
        finally:
            httpd.shutdown()

    def test_payload_too_large_returns_413(self, server):
        """Requests with Content-Length above 1 MB are rejected."""
        host, port = server
        conn = HTTPConnection(host, port)
        conn.request(
            "POST",
            "/webhook",
            body=b"",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(_MAX_CONTENT_LENGTH + 1),
            },
        )
        response = conn.getresponse()
        assert response.status == 413
        body = json.loads(response.read().decode("utf-8"))
        assert body["error"] == "payload too large"

    def test_invalid_content_length_returns_400(self, server):
        """Non-integer Content-Length is rejected."""
        host, port = server
        conn = HTTPConnection(host, port)
        conn.request(
            "POST",
            "/webhook",
            body=b"",
            headers={"Content-Type": "application/json", "Content-Length": "huge"},
        )
        response = conn.getresponse()
        assert response.status == 400
