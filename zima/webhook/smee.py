"""smee.io client for receiving GitHub webhooks locally."""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Optional

import requests

# Keys that smee.io mixes into the event object but are not original HTTP headers.
_SMEE_METADATA_KEYS = {"body", "headers", "query", "timestamp"}

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 60.0


def parse_smee_event(line: str) -> Optional[dict]:
    """Parse a single SSE data line from smee.io."""
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def extract_smee_payload(
    event: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], Optional[str]]:
    """Extract original webhook body and headers from a smee.io event.

    smee.io forwards webhooks as SSE events whose JSON payload contains the
    original request body under a ``body`` key, the original HTTP headers under
    a ``headers`` dict, and the raw signed request bytes under ``rawBody``.
    Older/simple payloads may mix headers as sibling keys and omit ``rawBody``;
    this function falls back to those layouts when necessary.

    Returns a tuple of ``(body, headers, raw_body)``. ``raw_body`` is ``None``
    when the event did not provide the original signed bytes.
    """
    # The original webhook payload. Some older/simple payloads may not wrap the
    # body under a "body" key; fall back to the whole event in that case.
    has_body = isinstance(event, dict) and "body" in event
    body = event["body"] if has_body else event

    # Prefer the nested headers dict added by real smee.io events.
    nested_headers = event.get("headers") if isinstance(event.get("headers"), dict) else None

    headers: dict[str, str] = {}
    if nested_headers is not None:
        headers = {
            str(key): str(value) if value is not None else ""
            for key, value in nested_headers.items()
        }
    elif has_body:
        for key, value in event.items():
            if key in _SMEE_METADATA_KEYS:
                continue
            # Forward header values as strings.
            headers[key] = str(value) if value is not None else ""

    # The local server expects JSON; requests will set these. Drop any stale
    # hop-by-hop / content headers from the smee event, case-insensitively —
    # smee may forward them title-cased ("Host" / "Content-Length" / "Content-Type").
    _HOP_BY_HOP = {"host", "content-length", "content-type"}
    headers = {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}

    raw_body = event.get("rawBody")
    return body, headers, raw_body


def run_smee_client(smee_url: str, target_url: str) -> None:
    """Connect to smee.io and forward events to local target URL."""
    delay = _INITIAL_BACKOFF
    while True:
        try:
            # Use the response as a context manager so the underlying streaming
            # connection is closed on reconnect/failure (avoids socket leaks).
            with requests.get(
                smee_url,
                stream=True,
                headers={"Accept": "text/event-stream"},
                timeout=(10, 60),
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                # Successful connection: reset backoff.
                delay = _INITIAL_BACKOFF
                for raw_line in response.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8")
                    event = parse_smee_event(line)
                    if event is None:
                        continue
                    body, headers, raw_body = extract_smee_payload(event)
                    try:
                        if isinstance(raw_body, str):
                            # Forward the original signed bytes so that HMAC
                            # verification on the local server stays valid.
                            forward_headers = headers.copy()
                            forward_headers["Content-Type"] = "application/json"
                            requests.post(
                                target_url,
                                data=raw_body.encode("utf-8"),
                                headers=forward_headers,
                                timeout=10,
                            )
                        else:
                            requests.post(target_url, json=body, headers=headers, timeout=10)
                    except Exception as exc:  # noqa: BLE001 - skip the bad event, keep the stream
                        # Broaden beyond RequestException so a malformed event
                        # (e.g. UnicodeEncodeError on raw_body.encode) skips this
                        # event instead of dropping the whole SSE stream/reconnecting.
                        print(
                            f"[smee] failed to forward event to {target_url}: {exc}",
                            file=sys.stderr,
                        )
                        continue
        except KeyboardInterrupt:
            break
        except Exception as exc:  # noqa: BLE001 - never let the forwarder thread die
            # Any unexpected error (e.g. UnicodeEncodeError on a malformed
            # rawBody, JSON errors) must not kill the forwarding thread; log,
            # back off, and reconnect instead of dying silently.
            print(
                f"[smee] connection lost ({exc}); reconnecting in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay = min(delay * 2, _MAX_BACKOFF)
            continue
