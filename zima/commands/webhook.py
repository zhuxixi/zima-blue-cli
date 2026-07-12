"""Webhook server command for zima."""

from __future__ import annotations

from typing import List, Optional

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


@app.callback()
def serve(
    ctx: typer.Context,
    pjob: List[str] = typer.Option([], "--pjob", help="PJob code to trigger (can be repeated)"),
    smee_url: Optional[str] = typer.Option(None, "--smee-url", help="smee.io channel URL"),
    port: int = typer.Option(8765, "--port", help="Local HTTP port"),
    secret: Optional[str] = typer.Option(
        None,
        "--secret",
        help="GitHub webhook secret (can also be set via the ZIMA_WEBHOOK_SECRET env var)",
        envvar="ZIMA_WEBHOOK_SECRET",
    ),
    skip_draft: bool = typer.Option(True, "--skip-draft/--no-skip-draft", help="Skip draft PRs"),
):
    """Run webhook server and optionally connect to smee.io."""
    if ctx.invoked_subcommand is not None:
        return

    if smee_url and not secret:
        console.print(
            "[red]✗[/red] --secret (or ZIMA_WEBHOOK_SECRET) is required when "
            "--smee-url is set: smee.io channels are publicly readable, so "
            "without a secret anyone who discovers the channel URL can forge "
            "events and trigger arbitrary PJob execution."
        )
        raise typer.Exit(1)
    if not secret:
        console.print(
            "[yellow]⚠[/yellow] Running without --secret: HMAC signature "
            "verification is disabled. This is only safe for local loopback "
            "testing — do NOT expose the server publicly."
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
        import threading

        target_url = f"http://127.0.0.1:{port}/webhook"
        smee_thread = threading.Thread(
            target=run_smee_client,
            args=(smee_url, target_url),
            daemon=True,
        )
        smee_thread.start()
        console.print(f"[green]✓[/green] Connected to smee.io, forwarding to {target_url}")

    console.print(f"[green]✓[/green] Webhook server listening on http://127.0.0.1:{port}/webhook")
    run_server(port=port, pjob_codes=list(pjob), secret=secret, skip_draft=skip_draft)
