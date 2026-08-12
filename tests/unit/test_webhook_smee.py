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
        extracted_body, headers, raw_body = extract_smee_payload(event)
        assert extracted_body == body
        assert raw_body is None
        assert headers["x-hub-signature-256"] == "sha256=abc"
        assert headers["x-github-event"] == "pull_request"
        assert "query" not in headers
        assert "timestamp" not in headers

    def test_nested_headers_extracted(self):
        """Real smee.io events wrap original headers under a ``headers`` dict."""
        body = {"action": "labeled"}
        event = {
            "body": body,
            "headers": {
                "x-hub-signature-256": "sha256=nested",
                "x-github-event": "pull_request",
            },
        }
        extracted_body, headers, raw_body = extract_smee_payload(event)
        assert extracted_body == body
        assert raw_body is None
        assert headers["x-hub-signature-256"] == "sha256=nested"
        assert headers["x-github-event"] == "pull_request"

    def test_nested_headers_take_precedence(self):
        """Nested headers dict takes precedence over sibling header keys."""
        event = {
            "body": {"action": "labeled"},
            "headers": {"x-hub-signature-256": "sha256=nested"},
            "x-hub-signature-256": "sha256=sibling",
        }
        _, headers, _ = extract_smee_payload(event)
        assert headers["x-hub-signature-256"] == "sha256=nested"

    def test_raw_body_extracted(self):
        """The signed request bytes are returned when present."""
        event = {
            "body": {"action": "labeled"},
            "rawBody": '{"action":"labeled"}',
            "headers": {"x-hub-signature-256": "sha256=signed"},
        }
        body, headers, raw_body = extract_smee_payload(event)
        assert body == {"action": "labeled"}
        assert raw_body == '{"action":"labeled"}'
        assert headers["x-hub-signature-256"] == "sha256=signed"

    def test_host_and_content_headers_removed(self):
        """Hop-by-hop/content headers from smee are not forwarded as-is."""
        event = {
            "body": {"action": "labeled"},
            "host": "smee.io",
            "content-length": "999",
            "content-type": "text/plain",
        }
        _, headers, _ = extract_smee_payload(event)
        assert "host" not in headers
        assert "content-length" not in headers
        assert "content-type" not in headers

    def test_fallback_when_no_body_key(self):
        """If smee event has no body wrapper, treat the whole event as body."""
        event = {"action": "labeled"}
        body, headers, raw_body = extract_smee_payload(event)
        assert body == event
        assert headers == {}
        assert raw_body is None


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
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self):
                return [b"data: " + json.dumps(sse_payload).encode()]

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            # After processing the first (and only) event, make the reconnect fail
            # so the loop exits cleanly.
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            posts.append((url, json, data, headers, timeout))

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
        url, body, data, headers, timeout = posts[0]
        assert url == "http://127.0.0.1:8765/webhook"
        assert body == sse_payload["body"]
        assert data is None
        assert headers["x-hub-signature-256"] == "sha256=secret"

    def test_forwards_resigned_body_with_secret(self, monkeypatch):
        """无 rawBody + secret：对 json.dumps(body) 字节重签后 data= 发送。

        Regression for #149: smee 事件无 rawBody 时旧代码用 requests json=
        重序列化，字节与签名不匹配 -> 本地 server 400。
        """
        import hashlib
        import hmac as hmac_module

        secret = "test-secret"
        sse_payload = {
            "body": {"action": "labeled", "label": {"name": "zima:needs-review"}},
            "x-hub-signature-256": "sha256=stale",
        }

        posts = []
        get_calls = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self):
                return [b"data: " + json.dumps(sse_payload).encode()]

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            # After processing the first (and only) event, make the reconnect fail
            # so the loop exits cleanly.
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            posts.append((url, json, data, headers, timeout))

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook", secret=secret)
        except (RuntimeError, requests.RequestException):
            pass

        assert len(posts) == 1
        url, body, data, headers, timeout = posts[0]
        assert url == "http://127.0.0.1:8765/webhook"
        assert body is None
        assert data is not None
        expected_bytes = json.dumps(sse_payload["body"]).encode("utf-8")
        expected_sig = (
            "sha256="
            + hmac_module.new(secret.encode("utf-8"), expected_bytes, hashlib.sha256).hexdigest()
        )
        assert data == expected_bytes
        assert headers["x-hub-signature-256"] == expected_sig
        assert headers["Content-Type"] == "application/json"

    def test_forwards_raw_body_bytes(self, monkeypatch):
        """When ``rawBody`` is present, forward the signed bytes unchanged."""
        raw = '{"action":"labeled","label":{"name":"zima:needs-review"}}'
        sse_payload = {
            "body": {"action": "labeled", "label": {"name": "zima:needs-review"}},
            "rawBody": raw,
            "headers": {"x-hub-signature-256": "sha256=rawsecret"},
        }

        get_calls = []
        posts = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self):
                return [b"data: " + json.dumps(sse_payload).encode()]

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            posts.append((url, json, data, headers, timeout))

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
        url, body, data, headers, timeout = posts[0]
        assert url == "http://127.0.0.1:8765/webhook"
        assert body is None
        assert data == raw.encode("utf-8")
        assert headers["x-hub-signature-256"] == "sha256=rawsecret"
        assert headers["Content-Type"] == "application/json"

    def test_exponential_backoff(self, monkeypatch):
        """Reconnect delays start at 1s and double up to a 60s cap."""
        sleeps = []

        def fake_get(*args, **kwargs):
            raise requests.RequestException("boom")

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 4:
                raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert sleeps == [1.0, 2.0, 4.0, 8.0]

    def test_backoff_resets_after_success(self, monkeypatch):
        """A successful connection resets the reconnect delay."""
        sleeps = []
        get_calls = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self):
                return []

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            # Succeed once, then fail (reconnect) twice.
            if len(get_calls) in (2, 3):
                raise requests.RequestException("boom")
            return FakeResponse()

        def fake_sleep(seconds):
            sleeps.append(seconds)
            # Stop once the two reconnect backoffs are observed. Must terminate
            # via sleep (raised inside the except handler, so it propagates)
            # rather than via fake_get, because run_smee_client's outer handler
            # catches Exception broadly to keep the forwarder thread alive.
            if len(sleeps) >= 2:
                raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert sleeps == [1.0, 2.0]

    def test_survives_unexpected_exception(self, monkeypatch):
        """A non-RequestException is caught, not propagated (thread must not die).

        Regression: the outer try used to catch only requests.RequestException, so
        any other exception (e.g. UnicodeEncodeError on a malformed rawBody) would
        escape and silently kill the forwarding thread.
        """
        sleeps = []

        def fake_get(*args, **kwargs):
            raise ValueError("unexpected, not a RequestException")

        def fake_sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) >= 3:
                raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        # Must not raise ValueError — it should be caught and retried with backoff.
        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        # If the ValueError had escaped, sleep would never have been called.
        assert sleeps == [1.0, 2.0, 4.0]

    def test_forward_logs_non_2xx(self, monkeypatch, capsys):
        """非 2xx 响应记日志到 stderr，不再静默失败（#149 教训）。

        Regression: 旧代码 requests.post 后不检查响应码，400 invalid
        signature 被静默吞掉 -> 无日志、无 spawn，链路看似正常实为瘫痪。
        """
        sse_payload = {
            "body": {"action": "labeled", "label": {"name": "zima:needs-review"}},
            "x-hub-signature-256": "sha256=stale",
        }

        class FakeResponse500:
            status_code = 500
            text = "boom"

        get_calls = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def iter_lines(self):
                return [b"data: " + json.dumps(sse_payload).encode()]

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            # After processing the first (and only) event, make the reconnect fail
            # so the loop exits cleanly.
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            return FakeResponse500()

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook", secret="s")
        except (RuntimeError, requests.RequestException):
            pass

        err = capsys.readouterr().err
        assert "forward got 500: boom" in err
