"""Tests for smee.io client."""

import json

import requests

from zima.webhook.smee import extract_smee_payload, parse_smee_event, run_smee_client


class TestParseSmeeEvent:
    """Tests for parsing smee SSE data lines."""

    def test_parse_data_event(self):
        """Parse a valid SSE data line."""
        payload = {"action": "labeled", "label": {"name": "zima:needs-review"}}
        line = "data: " + json.dumps(payload)
        event = parse_smee_event(line)
        assert event == payload

    def test_parse_empty_line(self):
        """Empty line returns None."""
        assert parse_smee_event("") is None

    def test_parse_non_data_line(self):
        """Non-data SSE line returns None."""
        assert parse_smee_event("id: 123") is None

    def test_parse_invalid_json(self):
        """Invalid JSON returns None."""
        assert parse_smee_event("data: not-json") is None


class TestExtractSmeePayload:
    """Tests for extracting body and headers from a smee.io event."""

    def test_extract_body_and_headers(self):
        """Body is extracted and original headers are forwarded."""
        body = {"action": "labeled"}
        event = {
            "body": body,
            "x-hub-signature-256": "sha256=abc",
            "x-github-event": "pull_request",
            "query": {},
            "timestamp": 1234567890,
        }
        extracted_body, headers = extract_smee_payload(event)
        assert extracted_body == body
        assert headers["x-hub-signature-256"] == "sha256=abc"
        assert headers["x-github-event"] == "pull_request"
        assert "query" not in headers
        assert "timestamp" not in headers

    def test_host_and_content_headers_removed(self):
        """Hop-by-hop/content headers from smee are not forwarded as-is."""
        event = {
            "body": {"action": "labeled"},
            "host": "smee.io",
            "content-length": "999",
            "content-type": "text/plain",
        }
        _, headers = extract_smee_payload(event)
        assert "host" not in headers
        assert "content-length" not in headers
        assert "content-type" not in headers

    def test_fallback_when_no_body_key(self):
        """If smee event has no body wrapper, treat the whole event as body."""
        event = {"action": "labeled"}
        body, headers = extract_smee_payload(event)
        assert body == event
        assert headers == {}


class TestRunSmeeClient:
    """Tests for smee.io forwarding loop."""

    def test_forwards_body_and_headers(self, monkeypatch):
        """run_smee_client posts original body and headers to target URL."""
        sse_payload = {
            "body": {"action": "labeled", "label": {"name": "zima:needs-review"}},
            "x-hub-signature-256": "sha256=secret",
        }

        get_calls = []
        posts = []

        class FakeResponse:
            def raise_for_status(self):
                pass

            def iter_lines(self):
                return [b"data: " + json.dumps(sse_payload).encode()]

        def fake_get(url, stream, headers, timeout):
            get_calls.append(None)
            # After processing the first (and only) event, make the reconnect fail
            # so the loop exits cleanly.
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_post(url, json, headers, timeout):
            posts.append((url, json, headers, timeout))

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert len(posts) == 1
        url, body, headers, timeout = posts[0]
        assert url == "http://127.0.0.1:8765/webhook"
        assert body == sse_payload["body"]
        assert headers["x-hub-signature-256"] == "sha256=secret"
