"""HTTP server for receiving GitHub webhooks."""

from __future__ import annotations

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, ClassVar, Optional

from zima.webhook.payload import (
    PullRequestLabeledEvent,
    parse_pull_request_labeled,
    should_trigger_review,
    verify_signature,
)


def trigger_pjobs(event: PullRequestLabeledEvent, pjob_codes: list[str]) -> dict[str, str]:
    """Trigger configured PJobs for a labeled event.

    Returns a mapping from PJob code to status string ("ok" or an error
    message). Failures are logged to stderr so they remain observable while
    the HTTP handler still returns 200 to GitHub to avoid retry storms.
    """
    statuses: dict[str, str] = {}
    for code in pjob_codes:
        args = [
            "zima",
            "pjob",
            "run",
            code,
            f"--set-var=repo={event.repo}",
            f"--set-var=pr={event.pr_number}",
            f"--set-var=head_sha={event.head_sha}",
        ]
        try:
            subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            statuses[code] = "ok"
        except (FileNotFoundError, OSError) as exc:
            statuses[code] = f"error: {exc}"
            print(
                f"[webhook] failed to spawn zima for pjob {code}: {exc}",
                file=sys.stderr,
            )
    return statuses


class WebhookRequestHandler(BaseHTTPRequestHandler):
    """Handle GitHub webhook POST requests."""

    pjob_codes: ClassVar[Optional[list[str]]] = None
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

        content_length = int(self.headers.get("Content-Length", "0"))
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

        event = parse_pull_request_labeled(data)
        if event is None:
            self._send_json(200, {"ignored": True})
            return

        if not should_trigger_review(event, skip_draft=self.skip_draft):
            self._send_json(200, {"ignored": True, "reason": "filters not met"})
            return

        if self.on_event:
            self.on_event(event)
        codes = self.pjob_codes or []
        statuses = trigger_pjobs(event, codes)
        body: dict = {"triggered": list(codes)}
        if statuses:
            body["statuses"] = statuses
        self._send_json(200, body)


def make_handler(
    pjob_codes: list[str],
    secret: Optional[str] = None,
    skip_draft: bool = True,
    on_event: Optional[Callable[[PullRequestLabeledEvent], None]] = None,
) -> type[BaseHTTPRequestHandler]:
    """Create a BaseHTTPRequestHandler subclass configured for zima webhooks."""
    return type(
        "ConfiguredWebhookHandler",
        (WebhookRequestHandler,),
        {
            "pjob_codes": list(pjob_codes),
            "secret": secret,
            "skip_draft": skip_draft,
            "on_event": on_event,
        },
    )


def run_server(
    port: int,
    pjob_codes: list[str],
    secret: Optional[str] = None,
    skip_draft: bool = True,
) -> None:
    """Run the webhook HTTP server."""
    handler = make_handler(pjob_codes=pjob_codes, secret=secret, skip_draft=skip_draft)
    server = HTTPServer(("127.0.0.1", port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
