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
    PjobRoute,
    WebhookRequestHandler,
    make_handler,
    trigger_pjobs,
)


class _FakeProc:
    """Fake subprocess.Popen handle: poll() returns None (running) or a code (done)."""

    def __init__(self, poll_result=None):
        self._poll_result = poll_result

    def poll(self):
        return self._poll_result


class TestTriggerPjobs:
    """Tests for triggering PJobs from an event."""

    def test_trigger_pjobs_invokes_cli(self, monkeypatch):
        """trigger_pjobs calls sys.executable -m zima pjob run for each pjob code."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()  # "running"

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open"
        )
        trigger_pjobs(event, [PjobRoute("claude-cr"), PjobRoute("kimi-cr")])
        assert len(calls) == 2
        assert calls[0][:6] == [sys.executable, "-m", "zima", "pjob", "run", "claude-cr"]
        assert calls[1][:6] == [sys.executable, "-m", "zima", "pjob", "run", "kimi-cr"]
        assert "--set-var=repo=owner/repo" in calls[0]
        assert "--set-var=pr_number=42" in calls[0]
        assert "--set-var=head_sha=abc" in calls[0]
        # Both wrapper handles are retained so the reaper can poll/reap them.
        assert len(wh_server._spawned_processes) == 2

    def test_trigger_pjobs_reaps_finished_handles(self, monkeypatch):
        """Finished wrapper handles are reaped (no zombie accumulation)."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        # Seed an already-finished wrapper handle (would-be zombie).
        finished = _FakeProc(poll_result=0)
        wh_server._spawned_processes.append(finished)

        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()  # running

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open"
        )
        trigger_pjobs(event, [PjobRoute("claude-cr")])
        # Finished handle reaped at the start of this trigger; only the new
        # running handle remains.
        assert finished not in wh_server._spawned_processes
        assert len(wh_server._spawned_processes) == 1

    def test_trigger_pjobs_survives_missing_zima(self, monkeypatch, capsys):
        """trigger_pjobs logs spawn errors but does not raise."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()

        def fake_popen(args, **kwargs):
            raise FileNotFoundError("zima not found")

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open"
        )
        trigger_pjobs(event, [PjobRoute("claude-cr")])
        captured = capsys.readouterr()
        assert "failed to spawn zima" in captured.err


class TestTriggerRouting:
    """Tests for repo-aware routing in trigger_pjobs."""

    def test_routes_only_matching_repo(self, monkeypatch):
        """Only the PJob bound to the event's repo is triggered."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "zhuxixi/jfox", 7, "abc", False, "open"
        )
        routes = [
            PjobRoute("zima-cr", "zhuxixi/zima-blue-cli"),
            PjobRoute("jfox-cr", "zhuxixi/jfox"),
            PjobRoute("other-cr", "zhuxixi/other"),
        ]
        trigger_pjobs(event, routes)
        # Only jfox-cr (bound to zhuxixi/jfox) fires.
        assert len(calls) == 1
        assert calls[0][:6] == [sys.executable, "-m", "zima", "pjob", "run", "jfox-cr"]
        assert "--set-var=repo=zhuxixi/jfox" in calls[0]

    def test_broadcast_when_repo_none(self, monkeypatch):
        """Routes with repo=None (legacy broadcast) fire on any repo."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "any/repo", 1, "abc", False, "open"
        )
        trigger_pjobs(event, [PjobRoute("a"), PjobRoute("b")])
        assert len(calls) == 2

    def test_routes_no_match_ignored(self, monkeypatch, capsys):
        """Routing mode + zero repo matches triggers nothing and logs a notice."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "someone/else", 1, "abc", False, "open"
        )
        routes = [PjobRoute("a", "zhuxixi/zima-blue-cli")]
        statuses = trigger_pjobs(event, routes)
        assert calls == []
        assert statuses == {}
        assert "matched no --pjob binding" in capsys.readouterr().err

    def test_routes_case_insensitive(self, monkeypatch):
        """Repo matching is case-insensitive (GitHub owner/repo are)."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 1, "abc", False, "open"
        )
        trigger_pjobs(event, [PjobRoute("a", "Owner/Repo")])
        assert len(calls) == 1

    def test_routes_dedup_still_works(self, monkeypatch):
        """De-dup applies per (event, code) in routing mode too."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent(
            "labeled", "zima:needs-review", "owner/repo", 1, "abc", False, "open"
        )
        routes = [PjobRoute("a", "owner/repo")]
        first = trigger_pjobs(event, routes)
        second = trigger_pjobs(event, routes)
        assert first == {"a": "ok"}
        assert second == {"a": "duplicate"}
        assert len(calls) == 1  # spawned only the first time


class TestWebhookRequestHandler:
    """Tests for HTTP handler."""

    def test_webhook_request_handler_is_base_handler(self):
        """WebhookRequestHandler is a BaseHTTPRequestHandler subclass."""
        assert issubclass(WebhookRequestHandler, BaseHTTPRequestHandler)

    @pytest.fixture
    def server(self, tmp_path):
        """Start a temporary HTTP server for testing."""
        handler = make_handler(routes=[PjobRoute("claude-cr")], secret=None, skip_draft=True)
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield httpd.server_address
        httpd.shutdown()
        httpd.server_close()

    def test_valid_labeled_event(self, server, monkeypatch):
        """Valid labeled event returns 200 and triggers PJob."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

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
                    "head": {"sha": "5fd94cc2a5c187d2854fd11b82fe6eac601e2e5a"},
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

    def test_routed_event_triggers_only_matching_pjob(self, monkeypatch):
        """Two repo-bound routes: an event fires only the matching PJob over HTTP."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)

        handler = make_handler(
            routes=[
                PjobRoute("zima-cr", "zhuxixi/zima-blue-cli"),
                PjobRoute("jfox-cr", "zhuxixi/jfox"),
            ],
            secret=None,
            skip_draft=True,
        )
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            payload = json.dumps(
                {
                    "action": "labeled",
                    "label": {"name": "zima:needs-review"},
                    "pull_request": {
                        "number": 5,
                        "state": "open",
                        "draft": False,
                        "head": {"sha": "5fd94cc2a5c187d2854fd11b82fe6eac601e2e5a"},
                        "base": {"repo": {"full_name": "zhuxixi/jfox"}},
                    },
                }
            ).encode()
            conn = HTTPConnection("127.0.0.1", httpd.server_address[1])
            conn.request(
                "POST", "/webhook", body=payload, headers={"Content-Type": "application/json"}
            )
            response = conn.getresponse()
            assert response.status == 200
        finally:
            httpd.shutdown()
            httpd.server_close()

        # Only jfox-cr (bound to zhuxixi/jfox) is spawned.
        assert len(calls) == 1
        assert calls[0][5] == "jfox-cr"
        assert "--set-var=repo=zhuxixi/jfox" in calls[0]

    def test_unmatched_repo_event_returns_200_and_triggers_nothing(self, monkeypatch):
        """Routing mode: an event for an unbound repo returns 200, fires nothing."""
        from zima.webhook import server as wh_server

        wh_server._spawned_processes.clear()
        wh_server._recent_events.clear()
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return _FakeProc()

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)

        handler = make_handler(
            routes=[PjobRoute("zima-cr", "zhuxixi/zima-blue-cli")],
            secret=None,
            skip_draft=True,
        )
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            payload = json.dumps(
                {
                    "action": "labeled",
                    "label": {"name": "zima:needs-review"},
                    "pull_request": {
                        "number": 8,
                        "state": "open",
                        "draft": False,
                        "head": {"sha": "5fd94cc2a5c187d2854fd11b82fe6eac601e2e5a"},
                        "base": {"repo": {"full_name": "someone/else"}},
                    },
                }
            ).encode()
            conn = HTTPConnection("127.0.0.1", httpd.server_address[1])
            conn.request(
                "POST", "/webhook", body=payload, headers={"Content-Type": "application/json"}
            )
            response = conn.getresponse()
            body = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
        finally:
            httpd.shutdown()
            httpd.server_close()

        # No PJob spawned; response reports an empty triggered set, not a 5xx.
        assert calls == []
        assert body["triggered"] == []

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
        handler = make_handler(routes=[PjobRoute("claude-cr")], secret="secret", skip_draft=True)
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
            httpd.server_close()

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
