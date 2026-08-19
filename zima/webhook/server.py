"""HTTP server for receiving GitHub webhooks."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, ClassVar, Optional

from zima.webhook.payload import (
    PullRequestLabeledEvent,
    parse_pull_request_labeled,
    should_trigger_review,
    verify_signature,
)

# Maximum request body size accepted by the webhook server (1 MB).
_MAX_CONTENT_LENGTH = 1_048_576

# Window within which duplicate deliveries of the same event are de-duplicated
# (GitHub redelivers on non-2xx and on hook misconfiguration; collapsing those
# avoids double-triggering PJobs for the same PR/SHA).
_DEDUP_WINDOW = 60.0
_REAPER_INTERVAL = 60.0

# Guards the module-global state below, which is mutated by both the
# request-handler threads (ThreadingHTTPServer) and the reaper daemon thread.
_state_lock = threading.Lock()
# Spawned `zima pjob run` wrapper handles, kept so finished ones can be reaped
# (otherwise the long-running server accumulates zombies, one per trigger).
_spawned_processes: list[subprocess.Popen] = []
# event-key -> last-triggered monotonic time, for delivery de-duplication.
_recent_events: dict[str, float] = {}
# Ensures the reaper daemon thread is started only once per process.
_reaper_started = False


@dataclass
class PjobRoute:
    """A PJob binding for the webhook server.

    ``repo`` is the ``owner/name`` the PJob is bound to. ``None`` means
    "trigger on any repo" (broadcast) — the legacy behavior when the server is
    started without any ``--repo`` options. Case-insensitive comparison is used
    because GitHub owner/repo names are case-insensitive in practice.
    """

    code: str
    repo: Optional[str] = None


def _route_matches(route: PjobRoute, event_repo: str) -> bool:
    """Return True if ``route`` should fire for ``event_repo``.

    Broadcast routes (``repo is None``) always match. Bound routes match
    case-insensitively against the event's repo full_name.
    """
    if route.repo is None:
        return True
    return route.repo.lower() == event_repo.lower()


def _reap_children() -> None:
    """Poll spawned wrapper processes and drop finished ones (prevent zombies).

    Also expires stale de-dup entries. Callers must NOT hold ``_state_lock``.
    """
    with _state_lock:
        remaining: list[subprocess.Popen] = []
        for proc in _spawned_processes:
            try:
                if proc.poll() is None:  # still running -> keep
                    remaining.append(proc)
            except Exception:
                # Never let a bad handle break triggering; just drop it.
                pass
        _spawned_processes[:] = remaining
        now = time.monotonic()
        for key in [k for k, ts in _recent_events.items() if now - ts > _DEDUP_WINDOW]:
            _recent_events.pop(key, None)


def _start_reaper_thread() -> None:
    """Start a daemon thread that periodically reaps finished wrapper processes.

    Idempotent: only one reaper per process even if ``run_server`` is called
    again (tests, restart).
    """
    global _reaper_started
    with _state_lock:
        if _reaper_started:
            return
        _reaper_started = True

    def _loop() -> None:
        while True:
            try:
                _reap_children()
            except Exception:
                pass
            time.sleep(_REAPER_INTERVAL)

    threading.Thread(target=_loop, daemon=True, name="zima-webhook-reaper").start()


def _dup_key(event: PullRequestLabeledEvent, code: str) -> str:
    return f"{event.repo}#{event.pr_number}#{event.head_sha}#{code}"


def _is_duplicate(event: PullRequestLabeledEvent, code: str) -> bool:
    """Peek whether this (event, pjob) was triggered within the dedup window."""
    with _state_lock:
        last = _recent_events.get(_dup_key(event, code))
        return last is not None and time.monotonic() - last < _DEDUP_WINDOW


def _mark_seen(event: PullRequestLabeledEvent, code: str) -> None:
    """Record that this (event, pjob) has been handled (for future de-duplication)."""
    with _state_lock:
        _recent_events[_dup_key(event, code)] = time.monotonic()


def trigger_pjobs(event: PullRequestLabeledEvent, routes: list[PjobRoute]) -> dict[str, str]:
    """Trigger configured PJobs for a labeled event, routed by repo.

    Only routes whose ``repo`` matches ``event.repo`` (broadcast routes always
    match) are considered. Returns a mapping from triggered PJob code to a
    status string (``"ok"``, ``"duplicate"``, or an error message). Failures are
    logged to stderr so they remain observable while the HTTP handler still
    returns 200 to GitHub to avoid retry storms.

    When the server is in routing mode (every route has a ``repo``) and none of
    them match the event's repo, nothing is triggered and a single notice is
    logged — this is the "ignore unknown repos" behavior that lets one server
    instance serve many repos without cross-triggering.
    """
    # Opportunistic reap: collect finished wrapper handles before spawning more.
    _reap_children()
    statuses: dict[str, str] = {}
    matched = False
    for route in routes:
        if not _route_matches(route, event.repo):
            continue
        matched = True
        code = route.code
        # De-dup per (event, pjob_code): a transient spawn failure leaves the
        # code unmarked, so a re-delivery / re-label re-runs only that code.
        if _is_duplicate(event, code):
            statuses[code] = "duplicate"
            continue
        args = [
            sys.executable,
            "-m",
            "zima",
            "pjob",
            "run",
            code,
            f"--set-var=repo={event.repo}",
            # pr_number is the consumed name; bare pr kept during the
            # compatibility window so user templates with {{ pr }} still
            # render under webhook triggers (renamed in #158).
            f"--set-var=pr_number={event.pr_number}",
            f"--set-var=pr={event.pr_number}",
            f"--set-var=head_sha={event.head_sha}",
        ]
        try:
            # Detach the spawned PJob so it survives the webhook request cycle,
            # matching the detachment pattern used by the daemon/pjob runners.
            popen_kwargs: dict = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = (
                    subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                )
            else:
                popen_kwargs["start_new_session"] = True
            proc = subprocess.Popen(args, **popen_kwargs)
            # Keep the handle so the reaper can poll/reap it once the wrapper
            # exits (the wrapper returns immediately after spawning background_runner).
            with _state_lock:
                _spawned_processes.append(proc)
            statuses[code] = "ok"
            # Mark only this (event, code) as handled, after a successful spawn.
            _mark_seen(event, code)
        except (FileNotFoundError, OSError) as exc:
            statuses[code] = f"error: {exc}"
            print(
                f"[webhook] failed to spawn zima for pjob {code}: {exc}",
                file=sys.stderr,
            )
    # Routing mode + zero matches: ignore the event but leave a trace so
    # operators can see why a known repo's event triggered nothing.
    if routes and not matched:
        print(
            f"[webhook] event repo {event.repo} matched no --pjob binding; ignored",
            file=sys.stderr,
        )
    return statuses


class WebhookRequestHandler(BaseHTTPRequestHandler):
    """Handle GitHub webhook POST requests."""

    pjob_routes: ClassVar[Optional[list[PjobRoute]]] = None
    secret: ClassVar[Optional[str]] = None
    skip_draft: ClassVar[bool] = True
    on_event: ClassVar[Optional[Callable[[PullRequestLabeledEvent], None]]] = None

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging."""
        pass

    def _send_json(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhook":
            self._send_json(404, {"error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except (ValueError, TypeError):
            self._send_json(400, {"error": "invalid content-length"})
            return

        # Reject negative Content-Length (a crafted "-1" would otherwise bypass
        # the upper-bound guard and make rfile.read(-1) block until EOF).
        if content_length < 0:
            self._send_json(400, {"error": "invalid content-length"})
            return
        if content_length > _MAX_CONTENT_LENGTH:
            self._send_json(413, {"error": "payload too large"})
            return

        payload = self.rfile.read(content_length)

        if self.secret:
            signature = self.headers.get("X-Hub-Signature-256", "")
            if not verify_signature(payload, signature, self.secret):
                self._send_json(400, {"error": "invalid signature"})
                return

        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid json"})
            return

        # Top-level guard: any failure in parsing/triggering must still return
        # 200 to GitHub (avoid retry storms); surface the error in the body/log.
        try:
            event = parse_pull_request_labeled(data)
            if event is None:
                self._send_json(200, {"ignored": True})
                return
            if not should_trigger_review(event, skip_draft=self.skip_draft):
                self._send_json(200, {"ignored": True, "reason": "filters not met"})
                return
            if self.on_event:
                self.on_event(event)
            routes = self.pjob_routes or []
            statuses = trigger_pjobs(event, routes)
            body: dict = {"triggered": list(statuses.keys())}
            if statuses:
                body["statuses"] = statuses
            self._send_json(200, body)
        except Exception as exc:  # noqa: BLE001 - never 500 to GitHub
            print(f"[webhook] error handling delivery: {exc}", file=sys.stderr)
            self._send_json(200, {"error": "internal error"})


def make_handler(
    routes: list[PjobRoute],
    secret: Optional[str] = None,
    skip_draft: bool = True,
    on_event: Optional[Callable[[PullRequestLabeledEvent], None]] = None,
) -> type[BaseHTTPRequestHandler]:
    """Create a BaseHTTPRequestHandler subclass configured for zima webhooks."""
    return type(
        "ConfiguredWebhookHandler",
        (WebhookRequestHandler,),
        {
            "pjob_routes": list(routes),
            "secret": secret,
            "skip_draft": skip_draft,
            "on_event": on_event,
        },
    )


def run_server(
    port: int,
    routes: list[PjobRoute],
    secret: Optional[str] = None,
    skip_draft: bool = True,
    on_listening: Optional[Callable[[], None]] = None,
) -> None:
    """Run the webhook HTTP server.

    ``on_listening`` (if given) is invoked after the listening socket is bound
    but before serving begins, so callers can start dependents (e.g. the smee
    forwarder) that must not race the bind.
    """
    handler = make_handler(routes=routes, secret=secret, skip_draft=skip_draft)
    _start_reaper_thread()
    # ThreadingHTTPServer so a slow/malformed delivery can't block the single
    # worker and stall the whole pipeline.
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    try:
        if on_listening is not None:
            on_listening()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
