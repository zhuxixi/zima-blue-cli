"""End-to-end integration test for webhook-driven review trigger."""

import json
import sys
import threading
from http.client import HTTPConnection

import pytest

from zima.webhook.server import PjobRoute, make_handler


@pytest.fixture
def webhook_server(tmp_path):
    """Start a local webhook server for end-to-end test (legacy broadcast)."""
    from http.server import HTTPServer

    handler = make_handler(
        routes=[PjobRoute("claude-cr"), PjobRoute("kimi-cr")],
        secret=None,
        skip_draft=True,
    )

    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    yield httpd.server_address

    httpd.shutdown()


def test_labeled_event_triggers_both_pjobs(webhook_server, monkeypatch):
    """A labeled event triggers both claude-cr and kimi-cr."""
    calls = []

    def fake_popen(args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)

    host, port = webhook_server
    payload = json.dumps(
        {
            "action": "labeled",
            "label": {"name": "zima:needs-review"},
            "pull_request": {
                "number": 99,
                "state": "open",
                "draft": False,
                "head": {"sha": "deadbeef"},
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        }
    ).encode()

    conn = HTTPConnection(host, port)
    try:
        conn.request("POST", "/webhook", body=payload, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        assert response.status == 200
    finally:
        conn.close()

    assert len(calls) == 2
    assert calls[0][:5] == [sys.executable, "-m", "zima", "pjob", "run"]
    assert calls[1][:5] == [sys.executable, "-m", "zima", "pjob", "run"]
    assert calls[0][5] == "claude-cr"
    assert calls[1][5] == "kimi-cr"
    assert "--set-var=repo=owner/repo" in calls[0]
    assert "--set-var=pr=99" in calls[0]
    assert "--set-var=head_sha=deadbeef" in calls[0]


def test_labeled_event_routes_by_repo(tmp_path, monkeypatch):
    """In routing mode an event triggers only the PJob bound to its repo."""
    from http.server import HTTPServer

    calls = []

    def fake_popen(args, **kwargs):
        calls.append(args)
        return None

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
                    "number": 3,
                    "state": "open",
                    "draft": False,
                    "head": {"sha": "cafef00d"},
                    "base": {"repo": {"full_name": "zhuxixi/zima-blue-cli"}},
                },
            }
        ).encode()
        conn = HTTPConnection("127.0.0.1", httpd.server_address[1])
        try:
            conn.request(
                "POST", "/webhook", body=payload, headers={"Content-Type": "application/json"}
            )
            response = conn.getresponse()
            assert response.status == 200
        finally:
            conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    # Only zima-cr (bound to zhuxixi/zima-blue-cli) fires; jfox-cr is not spawned.
    assert len(calls) == 1
    assert calls[0][5] == "zima-cr"
    assert "--set-var=repo=zhuxixi/zima-blue-cli" in calls[0]
