"""smee.io client for receiving GitHub webhooks locally."""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Optional

import requests

# Keys that smee.io mixes into the event object but are not original HTTP headers.
_SMEE_METADATA_KEYS = {"body", "headers", "query", "timestamp"}


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


def extract_smee_payload(event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Extract original webhook body and headers from a smee.io event.

    smee.io forwards webhooks as SSE events whose JSON payload mixes the original
    request body under a ``body`` key, query parameters under ``query``, and the
    original HTTP headers as sibling keys. This function separates the body from
    the headers so the local webhook server can verify signatures such as
    ``X-Hub-Signature-256``.
    """
    # The original webhook payload. Some older/simple payloads may not wrap the
    # body under a "body" key; fall back to the whole event in that case.
    has_body = isinstance(event, dict) and "body" in event
    body = event["body"] if has_body else event

    headers: dict[str, str] = {}
    if has_body:
        for key, value in event.items():
            if key in _SMEE_METADATA_KEYS:
                continue
            # Forward header values as strings.
            headers[key] = str(value) if value is not None else ""

    # The local server expects JSON; requests.post(json=...) will set these, but
    # make sure we do not keep stale values from the smee event.
    headers.pop("host", None)
    headers.pop("content-length", None)
    headers.pop("content-type", None)

    return body, headers


def run_smee_client(smee_url: str, target_url: str) -> None:
    """Connect to smee.io and forward events to local target URL."""
    while True:
        try:
            response = requests.get(
                smee_url,
                stream=True,
                headers={"Accept": "text/event-stream"},
                timeout=(10, 60),
            )
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8")
                event = parse_smee_event(line)
                if event is None:
                    continue
                body, headers = extract_smee_payload(event)
                try:
                    requests.post(target_url, json=body, headers=headers, timeout=10)
                except requests.RequestException as exc:
                    print(
                        f"[smee] failed to forward event to {target_url}: {exc}",
                        file=sys.stderr,
                    )
                    continue
        except requests.RequestException as exc:
            print(
                f"[smee] connection lost ({exc}); reconnecting in 5s",
                file=sys.stderr,
            )
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            break
