"""Webhook server command for zima."""

from __future__ import annotations

import sys
import threading
from typing import List, Optional
from urllib.parse import urlparse

import typer
from rich.console import Console

from zima.utils import validate_code_with_error
from zima.webhook.server import run_server
from zima.webhook.smee import run_smee_client

app = typer.Typer(
    name="webhook-server",
    help="Run GitHub webhook receiver for automatic PJob triggers",
    invoke_without_command=True,
)
console = Console(legacy_windows=False)

# smee.io is the only allowed forwarder host (SSRF guard on --smee-url).
_ALLOWED_SMEE_HOSTS = {"smee.io"}


def _validate_smee_url(url: str) -> tuple[bool, str]:
    """Validate that ``url`` is an https smee.io URL (SSRF guard)."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False, "must be an https:// URL"
    if parsed.hostname not in _ALLOWED_SMEE_HOSTS:
        return False, f"must point at smee.io (got {parsed.hostname or 'no host'})"
    return True, ""


def _run_smee_forwarder(smee_url: str, target_url: str) -> None:
    """Wrap run_smee_client so the forwarder thread never dies silently."""
    try:
        run_smee_client(smee_url, target_url)
    except Exception as exc:  # noqa: BLE001 - never let the forwarder thread die silently
        print(f"[smee] forwarder thread exited unexpectedly: {exc}", file=sys.stderr)


@app.callback()
def serve(
    ctx: typer.Context,
    pjob: List[str] = typer.Option([], "--pjob", help="PJob code to trigger (can be repeated)"),
    smee_url: Optional[str] = typer.Option(None, "--smee-url", help="smee.io channel URL"),
    port: int = typer.Option(8765, "--port", help="Local HTTP port"),
    secret: Optional[str] = typer.Option(
        None,
        "--secret",
        help="GitHub webhook secret. Prefer the ZIMA_WEBHOOK_SECRET env var so the "
        "secret is not visible in `ps` / /proc/<pid>/cmdline.",
        envvar="ZIMA_WEBHOOK_SECRET",
        hidden=True,
    ),
    allow_no_secret: bool = typer.Option(
        False,
        "--allow-no-secret",
        help="INSECURE: run without HMAC verification. Local loopback testing only.",
    ),
    skip_draft: bool = typer.Option(True, "--skip-draft/--no-skip-draft", help="Skip draft PRs"),
):
    """Run webhook server and optionally connect to smee.io."""
    if ctx.invoked_subcommand is not None:
        return

    # Fail-closed on signature verification by default: refuse to run without a
    # secret unless --allow-no-secret is explicitly passed. smee.io channels are
    # public, so --smee-url ALWAYS requires a secret regardless.
    if smee_url and not secret:
        console.print(
            "[red]✗[/red] --smee-url requires --secret (or ZIMA_WEBHOOK_SECRET): "
            "smee.io channels are publicly readable, so without a secret anyone "
            "who discovers the channel URL can forge events."
        )
        raise typer.Exit(1)
    if not secret and not allow_no_secret:
        console.print(
            "[red]✗[/red] A webhook secret is required (set --secret or the "
            "ZIMA_WEBHOOK_SECRET env var). Without it, HMAC verification is disabled "
            "and forged events could trigger arbitrary PJob execution. Pass "
            "--allow-no-secret only for local loopback testing."
        )
        raise typer.Exit(1)
    if not secret:
        console.print(
            "[yellow]⚠[/yellow] Running with --allow-no-secret: HMAC signature "
            "verification is DISABLED. Only safe for local loopback — do NOT "
            "expose the server publicly."
        )

    if not pjob:
        console.print("[red]✗[/red] At least one --pjob is required")
        raise typer.Exit(1)

    for code in pjob:
        is_valid, error = validate_code_with_error(code)
        if not is_valid:
            console.print(f"[red]✗[/red] Invalid PJob code '{code}': {error}")
            raise typer.Exit(1)

    if smee_url:
        ok, serr = _validate_smee_url(smee_url)
        if not ok:
            console.print(f"[red]✗[/red] Invalid --smee-url: {serr}")
            raise typer.Exit(1)

    def _on_listening() -> None:
        # Called by run_server after the listening socket is bound, so the smee
        # forwarder won't race the bind (no ECONNREFUSED for early events).
        if smee_url:
            target_url = f"http://127.0.0.1:{port}/webhook"
            threading.Thread(
                target=_run_smee_forwarder,
                args=(smee_url, target_url),
                daemon=True,
            ).start()
            console.print(f"[green]✓[/green] Connected to smee.io, forwarding to {target_url}")
        console.print(
            f"[green]✓[/green] Webhook server listening on http://127.0.0.1:{port}/webhook"
        )

    run_server(
        port=port,
        pjob_codes=list(pjob),
        secret=secret,
        skip_draft=skip_draft,
        on_listening=_on_listening,
    )
