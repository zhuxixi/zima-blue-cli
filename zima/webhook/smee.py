"""smee.io client for receiving GitHub webhooks locally.

Trust model note: when a ``secret`` is configured and smee.io drops
``rawBody``, this client re-signs events on the channel (see
``run_smee_client``). The smee channel is publicly readable, so anyone
who knows the channel URL can inject events; the HMAC then only
authenticates "forwarded by our local client", not "originated from
GitHub".
"""

from __future__ import annotations

import hmac
import json
import sys
import threading
import time
import uuid
from hashlib import sha256
from typing import Any, Optional

import requests

# Keys that smee.io mixes into the event object but are not original HTTP headers.
_SMEE_METADATA_KEYS = {"body", "headers", "query", "timestamp", "rawBody"}

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
# Watchdog: smee.io sends a keep-alive frame every 30s (lib/keep-alive.js),
# and the server never closes idle connections (socket.setTimeout(0)). When
# the connection silently dies (TCP half-open / server-side drop), requests'
# read timeout never fires because heartbeat bytes keep arriving -- only an
# application-level "last byte received" check detects the zombie (#163).
_WATCHDOG_CHECK_INTERVAL = 15.0
_DEAD_AFTER = 180.0
# Probe: form-B zombies (heartbeats flowing, EventBus detached) are
# indistinguishable from healthy idle by passive checks -- only an active
# round-trip probe detects them. Self-POST a probe event to the channel every
# _PROBE_INTERVAL; it must echo back over our SSE stream within _PROBE_TIMEOUT.
_PROBE_INTERVAL = 300.0
_PROBE_TIMEOUT = 120.0
_RESIGN_WARNING_LOGGED = False
_RESIGN_WARNING_LOCK = threading.Lock()


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


class SmeeWatchdogTimeout(Exception):
    """Raised when the SSE stream goes silent past the dead threshold."""


def _start_watchdog(
    response: requests.Response,
    smee_url: str,
    activity: list,
    probe_pending: list,
    stop_event: threading.Event,
    fired_event: threading.Event,
) -> None:
    """Start a daemon thread that closes ``response`` when the stream is stale.

    Two liveness criteria (checked every ``_WATCHDOG_CHECK_INTERVAL``):

    - Bytes: ``activity[0]`` (last received line) older than ``_DEAD_AFTER``
      -> no-bytes zombie (form A). The requests read timeout already covers
      this; the watchdog is defense-in-depth with better logging.
    - Probe: every ``_PROBE_INTERVAL`` self-POST ``{"_zima_probe": <uuid>}``
      to the smee channel; if no matching echo arrives over the SSE stream
      within ``_PROBE_TIMEOUT``, the connection is detached from the event
      bus (form B). Probe echoes are consumed by the read loop (never
      forwarded to the local server).

    ``activity``/``probe_pending`` are one-element lists shared with the read
    loop (mutable containers -- a plain local reassignment would not be
    visible to this thread). ``probe_pending[0]`` is ``None`` or a
    ``(probe_id, sent_monotonic)`` tuple. ``fired_event`` is set before
    closing so the read loop can tell a watchdog kill apart from a clean
    stream end.
    """

    def _close_stale(message: str) -> None:
        if not fired_event.is_set():
            fired_event.set()
            print(message, file=sys.stderr)
        try:
            response.close()
        except Exception:  # noqa: BLE001 - close is best-effort
            pass
        # No return: a cross-thread close() may not interrupt a C-level
        # blocked recv on the first try, so re-close every check interval
        # until the stream exits.

    def _watch() -> None:
        last_probe_sent = time.monotonic()  # fresh connection: no immediate probe
        try:
            while not stop_event.wait(_WATCHDOG_CHECK_INTERVAL):
                now = time.monotonic()
                age = now - activity[0]
                if age > _DEAD_AFTER:
                    _close_stale(
                        f"[smee] watchdog: no SSE data for {age:.0f}s, closing stale connection"
                    )
                    continue
                pending = probe_pending[0]
                if pending is not None:
                    probe_id, sent_at = pending
                    pending_age = now - sent_at
                    if pending_age > _PROBE_TIMEOUT:
                        _close_stale(
                            f"[smee] watchdog: probe {probe_id} got no echo for "
                            f"{pending_age:.0f}s, closing detached connection"
                        )
                    continue
                if now - last_probe_sent > _PROBE_INTERVAL:
                    probe_id = uuid.uuid4().hex
                    try:
                        requests.post(smee_url, json={"_zima_probe": probe_id}, timeout=10)
                        probe_pending[0] = (probe_id, now)
                    except Exception as exc:  # noqa: BLE001 - network-level failure
                        # Cannot judge detachment; log and retry next interval.
                        print(f"[smee] watchdog: probe POST failed ({exc})", file=sys.stderr)
                    last_probe_sent = now
        except Exception as exc:  # noqa: BLE001 - log before dying (#163 CR)
            # A silently dead watchdog would re-create the original #163
            # failure mode (silent event loss), so always log before exiting.
            print(f"[smee] watchdog thread died: {exc}", file=sys.stderr)

    threading.Thread(target=_watch, daemon=True).start()

    threading.Thread(target=_watch, daemon=True).start()


def run_smee_client(smee_url: str, target_url: str, secret: Optional[str] = None) -> None:
    """Connect to smee.io and forward events to local target URL.

    ``secret`` is used to recompute the HMAC signature when a smee.io event
    lacks the original signed bytes (no rawBody); when None, the event is
    forwarded as-is (local no-secret debugging).

    Note on trust: when ``secret`` is set and smee.io drops ``rawBody``, this
    client re-signs any event it receives on the channel with that secret.
    The smee channel is publicly readable and cannot be kept secret; HMAC here
    authenticates "forwarded by our local client", not "originated from GitHub".
    """
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
                # allow_redirects=False: a 3xx isn't an error for raise_for_status,
                # but it carries no SSE stream -> treat as failure (backoff reconnect)
                # instead of tight-looping on an empty redirect response.
                if 300 <= response.status_code < 400:
                    raise requests.RequestException(
                        f"unexpected redirect ({response.status_code}) from smee.io"
                    )
                # Successful connection: reset backoff.
                delay = _INITIAL_BACKOFF
                activity = [time.monotonic()]
                probe_pending: list = [None]
                stop_watchdog = threading.Event()
                watchdog_fired = threading.Event()
                _start_watchdog(
                    response, smee_url, activity, probe_pending, stop_watchdog, watchdog_fired
                )
                try:
                    for raw_line in response.iter_lines():
                        # Refresh BEFORE parse/skip: heartbeat frames are not
                        # forwarded but still prove the connection is alive.
                        # Note: this measures "line consumed by the read loop",
                        # not "bytes arrived at the socket" -- while a forward
                        # POST is stalled (up to its 10s timeout), arriving
                        # heartbeat bytes sit unread and don't refresh; a long
                        # streak of stalled POSTs could false-kill a healthy
                        # connection (cost: one benign reconnect).
                        activity[0] = time.monotonic()
                        if not raw_line:
                            continue
                        line = raw_line.decode("utf-8")
                        event = parse_smee_event(line)
                        if not event:
                            # Skip smee.io keep-alive ping frames (data: {}) and
                            # non-data/blank/undecodable lines (None).
                            continue
                        # Probe echo: a healthy connection delivers our own
                        # probe back over the SSE stream. Consume it here --
                        # never forward it to the local server.
                        probe_body = event.get("body")
                        if isinstance(probe_body, dict) and "_zima_probe" in probe_body:
                            pending = probe_pending[0]
                            if pending and probe_body["_zima_probe"] == pending[0]:
                                probe_pending[0] = None
                            continue
                        body, headers, raw_body = extract_smee_payload(event)
                        try:
                            if isinstance(raw_body, str):
                                # Forward the original signed bytes so that HMAC
                                # verification on the local server stays valid.
                                forward_headers = headers.copy()
                                forward_headers["Content-Type"] = "application/json"
                                with requests.post(
                                    target_url,
                                    data=raw_body.encode("utf-8"),
                                    headers=forward_headers,
                                    timeout=10,
                                ) as resp:
                                    if not 200 <= resp.status_code < 300:
                                        print(
                                            f"[smee] forward got {resp.status_code}: {resp.text}",
                                            file=sys.stderr,
                                        )
                            elif secret:
                                # smee.io dropped the raw signed bytes (no rawBody):
                                # resign the exact bytes we are about to send, so the
                                # signature always matches the payload on the server.
                                payload_bytes = json.dumps(body).encode("utf-8")
                                with _RESIGN_WARNING_LOCK:
                                    global _RESIGN_WARNING_LOGGED
                                    if not _RESIGN_WARNING_LOGGED:
                                        print(
                                            "[smee] warning: event lacks rawBody - re-signing locally; "
                                            "the channel is public, so HMAC authenticates the local "
                                            "forwarder, not GitHub",
                                            file=sys.stderr,
                                        )
                                        _RESIGN_WARNING_LOGGED = True
                                forward_headers = headers.copy()
                                forward_headers["x-hub-signature-256"] = (
                                    "sha256="
                                    + hmac.new(
                                        secret.encode("utf-8"), payload_bytes, sha256
                                    ).hexdigest()
                                )
                                forward_headers["Content-Type"] = "application/json"
                                with requests.post(
                                    target_url,
                                    data=payload_bytes,
                                    headers=forward_headers,
                                    timeout=10,
                                ) as resp:
                                    if not 200 <= resp.status_code < 300:
                                        print(
                                            f"[smee] forward got {resp.status_code}: {resp.text}",
                                            file=sys.stderr,
                                        )
                            else:
                                with requests.post(
                                    target_url, json=body, headers=headers, timeout=10
                                ) as resp:
                                    if not 200 <= resp.status_code < 300:
                                        print(
                                            f"[smee] forward got {resp.status_code}: {resp.text}",
                                            file=sys.stderr,
                                        )
                        except (
                            Exception
                        ) as exc:  # noqa: BLE001 - skip the bad event, keep the stream
                            # Broaden beyond RequestException so a malformed event
                            # (e.g. UnicodeEncodeError on raw_body.encode) skips this
                            # event instead of dropping the whole SSE stream/reconnecting.
                            print(
                                f"[smee] failed to forward event to {target_url}: {exc}",
                                file=sys.stderr,
                            )
                            continue
                finally:
                    stop_watchdog.set()
                if watchdog_fired.is_set():
                    # iter_lines returned cleanly after the watchdog closed the
                    # connection (no exception): route into the same
                    # backoff-reconnect path as the exception exit.
                    raise SmeeWatchdogTimeout(
                        f"no SSE data for over {_DEAD_AFTER:.0f}s; reconnecting"
                    )
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
