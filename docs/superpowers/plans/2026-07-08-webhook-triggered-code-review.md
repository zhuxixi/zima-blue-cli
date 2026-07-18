# Webhook 触发自动 Code Review（Phase 1）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 zima-blue-cli 中新增 `zima webhook-server` 命令，接收 GitHub PR `labeled` 事件并在 `zima:needs-review` 被添加时并行触发 `claude-cr` 和 `kimi-cr` 两个 PJob；同时将 Kimi agent 命令从旧 `kimi-cli` 更新为 Kimi Code CLI。

**Architecture:** 独立 webhook 进程（FastAPI/Flask/标准库 HTTP + 可选 smee.io SSE client）接收并校验 GitHub webhook，过滤事件后通过 `subprocess.Popen` 并行调用 `zima pjob run <code> --set-var repo=... --set-var pr=... --set-var head_sha=...`。所有 agent 执行复用现有 `PJobExecutor` 与 `background_runner`。

**Tech Stack:** Python 3.10+, Typer, standard library `http.server` or FastAPI/Flask, `requests` (for smee SSE), `hmac`/`hashlib` (signature verify), pytest

## Global Constraints

- Python 3.10+，dataclasses，Black 100 字符，ruff lint
- 不改动 `PJobExecutor`、`DaemonScheduler` 核心逻辑
- 所有新增文件放在 `zima/webhook/` 包和 `zima/commands/webhook.py`
- 示例配置放在 `examples/webhook/`
- 单元测试在 `tests/unit/`，集成测试在 `tests/integration/`
- `--set-var` 通过 `Overrides.variable_values` 注入，Jinja2 workflow 模板中用 `{{ repo }}` / `{{ pr }}` / `{{ head_sha }}` 读取
- 默认本地监听 `127.0.0.1:8765`，不暴露公网

---

### Task 1: GitHub Webhook Payload 数据模型与校验

**Files:**
- Create: `zima/webhook/__init__.py`
- Create: `zima/webhook/payload.py`
- Test: `tests/unit/test_webhook_payload.py`

**Interfaces:**
- Consumes: raw GitHub JSON payload (`dict`) and optional webhook secret (`str`)
- Produces:
  - `PullRequestLabeledEvent` dataclass with fields `action: str`, `label_name: str`, `repo: str`, `pr_number: int`, `head_sha: str`, `draft: bool`, `state: str`
  - `verify_signature(payload: bytes, signature: str, secret: str) -> bool`
  - `parse_pull_request_labeled(payload: dict) -> Optional[PullRequestLabeledEvent]`
  - `should_trigger_review(event: PullRequestLabeledEvent, skip_draft: bool = True) -> bool`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_webhook_payload.py`:

```python
"""Tests for GitHub webhook payload parsing."""

import pytest

from zima.webhook.payload import (
    PullRequestLabeledEvent,
    parse_pull_request_labeled,
    should_trigger_review,
    verify_signature,
)


class TestVerifySignature:
    """Tests for HMAC-SHA256 signature verification."""

    def test_verify_signature_valid(self):
        """Valid signature returns True."""
        secret = "my-secret"
        payload = b'{"action":"labeled"}'
        import hmac
        import hashlib

        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_signature(payload, expected, secret) is True

    def test_verify_signature_invalid(self):
        """Invalid signature returns False."""
        assert verify_signature(b"{}", "sha256=abc123", "secret") is False

    def test_verify_signature_missing(self):
        """Missing signature with secret provided returns False."""
        assert verify_signature(b"{}", "", "secret") is False

    def test_verify_signature_no_secret(self):
        """No secret means verification is skipped."""
        assert verify_signature(b"{}", "", "") is True


class TestParsePullRequestLabeled:
    """Tests for parsing labeled payload."""

    def test_parse_valid_labeled_event(self):
        """Parse a valid pull_request.labeled event."""
        payload = {
            "action": "labeled",
            "label": {"name": "zima:needs-review"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head": {"sha": "abc123"},
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        }
        event = parse_pull_request_labeled(payload)
        assert event is not None
        assert event.action == "labeled"
        assert event.label_name == "zima:needs-review"
        assert event.repo == "owner/repo"
        assert event.pr_number == 42
        assert event.head_sha == "abc123"
        assert event.draft is False
        assert event.state == "open"

    def test_parse_wrong_action(self):
        """Non-labeled action returns None."""
        payload = {
            "action": "opened",
            "label": {"name": "zima:needs-review"},
            "pull_request": {"number": 42, "state": "open", "draft": False, "head": {"sha": "abc"}, "base": {"repo": {"full_name": "owner/repo"}}},
        }
        assert parse_pull_request_labeled(payload) is None

    def test_parse_wrong_label(self):
        """Wrong label returns None."""
        payload = {
            "action": "labeled",
            "label": {"name": "bug"},
            "pull_request": {"number": 42, "state": "open", "draft": False, "head": {"sha": "abc"}, "base": {"repo": {"full_name": "owner/repo"}}},
        }
        assert parse_pull_request_labeled(payload) is None

    def test_parse_missing_pull_request(self):
        """Missing pull_request returns None."""
        payload = {"action": "labeled", "label": {"name": "zima:needs-review"}}
        assert parse_pull_request_labeled(payload) is None


class TestShouldTriggerReview:
    """Tests for trigger decision."""

    def test_trigger_open_non_draft(self):
        """Open non-draft PR triggers."""
        event = PullRequestLabeledEvent("labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open")
        assert should_trigger_review(event) is True

    def test_skip_draft(self):
        """Draft PR is skipped by default."""
        event = PullRequestLabeledEvent("labeled", "zima:needs-review", "owner/repo", 42, "abc", True, "open")
        assert should_trigger_review(event) is False

    def test_include_draft_when_configured(self):
        """Draft PR included if skip_draft=False."""
        event = PullRequestLabeledEvent("labeled", "zima:needs-review", "owner/repo", 42, "abc", True, "open")
        assert should_trigger_review(event, skip_draft=False) is True

    def test_skip_closed(self):
        """Closed PR is skipped."""
        event = PullRequestLabeledEvent("labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "closed")
        assert should_trigger_review(event) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_webhook_payload.py -v`
Expected: FAIL — modules/functions not defined

- [ ] **Step 3: Write minimal implementation**

Create `zima/webhook/__init__.py`:

```python
"""Webhook support for zima."""
```

Create `zima/webhook/payload.py`:

```python
"""GitHub webhook payload parsing and validation."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from hashlib import sha256
from typing import Optional


@dataclass
class PullRequestLabeledEvent:
    """Normalized pull_request.labeled event."""

    action: str
    label_name: str
    repo: str
    pr_number: int
    head_sha: str
    draft: bool
    state: str


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature.

    If no secret is configured, verification is skipped.
    """
    if not secret:
        return True
    if not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_pull_request_labeled(payload: dict) -> Optional[PullRequestLabeledEvent]:
    """Parse a pull_request.labeled event for zima:needs-review."""
    if not isinstance(payload, dict):
        return None

    if payload.get("action") != "labeled":
        return None

    label = payload.get("label") or {}
    if label.get("name") != "zima:needs-review":
        return None

    pr = payload.get("pull_request")
    if not isinstance(pr, dict):
        return None

    repo = pr.get("base", {}).get("repo", {}).get("full_name")
    if not repo:
        return None

    return PullRequestLabeledEvent(
        action="labeled",
        label_name="zima:needs-review",
        repo=repo,
        pr_number=int(pr.get("number", 0)),
        head_sha=str(pr.get("head", {}).get("sha", "")),
        draft=bool(pr.get("draft", False)),
        state=str(pr.get("state", "")),
    )


def should_trigger_review(event: PullRequestLabeledEvent, skip_draft: bool = True) -> bool:
    """Decide whether to trigger review for this event."""
    if event.state != "open":
        return False
    if skip_draft and event.draft:
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_webhook_payload.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/webhook/ tests/unit/test_webhook_payload.py
git commit -m "feat(webhook): add GitHub payload parser and signature verifier"
```

---

### Task 2: Webhook HTTP Server

**Files:**
- Create: `zima/webhook/server.py`
- Test: `tests/unit/test_webhook_server.py`

**Interfaces:**
- Consumes: `PullRequestLabeledEvent`, pjob codes (`list[str]`), `skip_draft: bool`
- Produces:
  - `WebhookHandler` class (stdlib `BaseHTTPRequestHandler` subclass) or FastAPI app
  - `trigger_pjobs(event: PullRequestLabeledEvent, pjob_codes: list[str]) -> None`
  - `run_server(port: int, pjob_codes: list[str], secret: Optional[str] = None, skip_draft: bool = True) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_webhook_server.py`:

```python
"""Tests for webhook HTTP server."""

import json
import threading
from http.client import HTTPConnection

import pytest

from zima.webhook.payload import PullRequestLabeledEvent
from zima.webhook.server import WebhookRequestHandler, trigger_pjobs


class TestTriggerPjobs:
    """Tests for triggering PJobs from an event."""

    def test_trigger_pjobs_invokes_cli(self, monkeypatch):
        """trigger_pjobs calls zima pjob run for each pjob code."""
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return None

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)
        event = PullRequestLabeledEvent("labeled", "zima:needs-review", "owner/repo", 42, "abc", False, "open")
        trigger_pjobs(event, ["claude-cr", "kimi-cr"])
        assert len(calls) == 2
        assert calls[0][:3] == ["zima", "pjob", "run"]
        assert calls[1][:3] == ["zima", "pjob", "run"]
        assert "--set-var=repo=owner/repo" in calls[0]
        assert "--set-var=pr=42" in calls[0]
        assert "--set-var=head_sha=abc" in calls[0]


class TestWebhookRequestHandler:
    """Tests for HTTP handler."""

    @pytest.fixture
    def server(self, tmp_path):
        """Start a temporary HTTP server for testing."""
        from http.server import HTTPServer
        from zima.webhook.server import make_handler

        handler = make_handler(pjob_codes=["claude-cr"], secret=None, skip_draft=True)
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield httpd.server_address
        httpd.shutdown()

    def test_valid_labeled_event(self, server, monkeypatch):
        """Valid labeled event returns 200 and triggers PJob."""
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return None

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)

        host, port = server
        payload = json.dumps({
            "action": "labeled",
            "label": {"name": "zima:needs-review"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head": {"sha": "abc123"},
                "base": {"repo": {"full_name": "owner/repo"}},
            },
        }).encode()

        conn = HTTPConnection(host, port)
        conn.request("POST", "/webhook", body=payload, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        assert response.status == 200
        assert len(calls) == 1
        assert calls[0][:4] == ["zima", "pjob", "run", "claude-cr"]
        assert "--set-var=repo=owner/repo" in calls[0]

    def test_ignores_non_labeled(self, server, monkeypatch):
        """Non-labeled action returns 200 but does not trigger."""
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(args)
            return None

        monkeypatch.setattr("zima.webhook.server.subprocess.Popen", fake_popen)

        host, port = server
        payload = json.dumps({
            "action": "opened",
            "pull_request": {"number": 42, "state": "open", "draft": False, "head": {"sha": "abc"}, "base": {"repo": {"full_name": "owner/repo"}}},
        }).encode()

        conn = HTTPConnection(host, port)
        conn.request("POST", "/webhook", body=payload, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        assert response.status == 200
        assert calls == []

    def test_invalid_signature_returns_400(self, server):
        """Invalid signature returns 400 when secret is set."""
        from http.server import HTTPServer
        from zima.webhook.server import make_handler

        handler = make_handler(pjob_codes=["claude-cr"], secret="secret", skip_draft=True)
        httpd = HTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            payload = b'{"action":"labeled"}'
            conn = HTTPConnection("127.0.0.1", httpd.server_address[1])
            conn.request("POST", "/webhook", body=payload, headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid",
            })
            response = conn.getresponse()
            assert response.status == 400
        finally:
            httpd.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_webhook_server.py -v`
Expected: FAIL — server module not defined

- [ ] **Step 3: Write minimal implementation**

Create `zima/webhook/server.py`:

```python
"""HTTP server for receiving GitHub webhooks."""

from __future__ import annotations

import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Optional

from zima.webhook.payload import (
    PullRequestLabeledEvent,
    parse_pull_request_labeled,
    should_trigger_review,
    verify_signature,
)


def trigger_pjobs(event: PullRequestLabeledEvent, pjob_codes: list[str]) -> None:
    """Trigger configured PJobs for a labeled event."""
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
        subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_handler(
    pjob_codes: list[str],
    secret: Optional[str] = None,
    skip_draft: bool = True,
    on_event: Optional[Callable[[PullRequestLabeledEvent], None]] = None,
) -> type[BaseHTTPRequestHandler]:
    """Create a BaseHTTPRequestHandler subclass configured for zima webhooks."""

    class WebhookRequestHandler(BaseHTTPRequestHandler):
        """Handle GitHub webhook POST requests."""

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

            if secret:
                signature = self.headers.get("X-Hub-Signature-256", "")
                if not verify_signature(payload, signature, secret):
                    self._send_json(400, {"error": "invalid signature"})
                    return

            try:
                data = json.loads(payload.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid json"})
                return

            event = parse_pull_request_labeled(data)
            if event is None:
                self._send_json(200, {"ignored": True})
                return

            if not should_trigger_review(event, skip_draft=skip_draft):
                self._send_json(200, {"ignored": True, "reason": "filters not met"})
                return

            if on_event:
                on_event(event)
            trigger_pjobs(event, pjob_codes)
            self._send_json(200, {"triggered": pjob_codes})

    return WebhookRequestHandler


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_webhook_server.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/webhook/server.py tests/unit/test_webhook_server.py
git commit -m "feat(webhook): add HTTP server and PJob trigger"
```

---

### Task 3: smee.io Client

**Files:**
- Create: `zima/webhook/smee.py`
- Test: `tests/unit/test_webhook_smee.py`

**Interfaces:**
- Consumes: smee URL (`str`), local target URL (`str`)
- Produces:
  - `run_smee_client(smee_url: str, target_url: str) -> None`
  - `parse_smee_event(line: str) -> Optional[dict]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_webhook_smee.py`:

```python
"""Tests for smee.io client."""

import json

import pytest

from zima.webhook.smee import parse_smee_event


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_webhook_smee.py -v`
Expected: FAIL — smee module not defined

- [ ] **Step 3: Write minimal implementation**

Create `zima/webhook/smee.py`:

```python
"""smee.io client for receiving GitHub webhooks locally."""

from __future__ import annotations

import json
import time
from typing import Optional

import requests


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


def run_smee_client(smee_url: str, target_url: str) -> None:
    """Connect to smee.io and forward events to local target URL."""
    while True:
        try:
            response = requests.get(smee_url, stream=True, headers={"Accept": "text/event-stream"})
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8")
                event = parse_smee_event(line)
                if event is None:
                    continue
                try:
                    requests.post(target_url, json=event, timeout=10)
                except requests.RequestException:
                    # Local server unavailable; log and continue
                    continue
        except requests.RequestException:
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_webhook_smee.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/webhook/smee.py tests/unit/test_webhook_smee.py
git commit -m "feat(webhook): add smee.io SSE client"
```

---

### Task 4: `zima webhook-server` CLI 命令

**Files:**
- Create: `zima/commands/webhook.py`
- Modify: `zima/cli.py:43`
- Test: `tests/integration/test_webhook_command.py`

**Interfaces:**
- Consumes: `zima.webhook.server.run_server`, `zima.webhook.smee.run_smee_client`
- Produces: Typer app `webhook` registered under `zima webhook-server`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_webhook_command.py`:

```python
"""Integration tests for zima webhook-server command."""

import pytest
from typer.testing import CliRunner

from zima.cli import app

runner = CliRunner()


class TestWebhookServerCommand:
    """Tests for 'zima webhook-server'."""

    def test_help_shows_options(self):
        """Help text includes required options."""
        result = runner.invoke(app, ["webhook-server", "--help"])
        assert result.exit_code == 0
        assert "--smee-url" in result.output
        assert "--pjob" in result.output
        assert "--port" in result.output
        assert "--secret" in result.output

    def test_missing_pjob_fails(self):
        """Running without --pjob fails."""
        result = runner.invoke(app, ["webhook-server", "--port", "8765"])
        assert result.exit_code != 0
        assert "--pjob" in result.output

    def test_command_runs_without_subcommand(self):
        """webhook-server without subcommand enters server mode."""
        # We cannot actually start the server in a test, but we can verify
        # the callback is invoked and fails validation before blocking.
        result = runner.invoke(app, ["webhook-server", "--port", "8765"])
        assert result.exit_code != 0
        assert "At least one --pjob is required" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_webhook_command.py -v`
Expected: FAIL — command not registered

- [ ] **Step 3: Write minimal implementation**

Create `zima/commands/webhook.py`:

```python
"""Webhook server command for zima."""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console

from zima.webhook.server import run_server
from zima.webhook.smee import run_smee_client
from zima.utils import validate_code_with_error

app = typer.Typer(
    name="webhook-server",
    help="Run GitHub webhook receiver for automatic PJob triggers",
    invoke_without_command=True,
)
console = Console(legacy_windows=False, force_terminal=True)


@app.callback()
def serve(
    ctx: typer.Context,
    pjob: List[str] = typer.Option(..., "--pjob", help="PJob code to trigger (can be repeated)"),
    smee_url: Optional[str] = typer.Option(None, "--smee-url", help="smee.io channel URL"),
    port: int = typer.Option(8765, "--port", help="Local HTTP port"),
    secret: Optional[str] = typer.Option(None, "--secret", help="GitHub webhook secret"),
    skip_draft: bool = typer.Option(True, "--skip-draft/--no-skip-draft", help="Skip draft PRs"),
):
    """Run webhook server and optionally connect to smee.io."""
    if ctx.invoked_subcommand is not None:
        return

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
```

Modify `zima/cli.py` after line 43:

```python
from zima.commands import webhook as webhook_cmd

# ... existing registrations ...
app.add_typer(webhook_cmd.app, name="webhook-server")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_webhook_command.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/webhook.py zima/cli.py tests/integration/test_webhook_command.py
git commit -m "feat(cli): add zima webhook-server command"
```

---

### Task 5: 更新 Kimi Agent 为 Kimi Code CLI

**Files:**
- Modify: `zima/models/agent.py:171`
- Test: `tests/unit/test_models_agent.py`（已有，补充或修改）

**Interfaces:**
- Consumes: Kimi Code CLI 实际命令（待确认）
- Produces: 更新后的 `get_cli_command_template()` 返回 `["kimi", ...]`

- [ ] **Step 1: 确认 Kimi Code CLI 调用方式**

在目标机器上运行：

```bash
which kimi
kimi --help
kimi --version
```

确认最小非交互式调用方式。常见形式可能是：

```bash
kimi --execute "prompt text"
kimi -c "prompt text"
kimi < prompt.md
```

假设确认后为 `kimi --execute <prompt>`（如果不同，替换实际参数）。

- [ ] **Step 2: Write the failing test**

Append or modify existing `tests/unit/test_models_agent.py`:

```python
class TestKimiCodeCLI:
    """Tests for Kimi Code CLI command template."""

    def test_kimi_command_template(self):
        """Kimi agent uses Kimi Code CLI command."""
        agent = AgentConfig.create(code="test", name="Test", agent_type="kimi")
        cmd = agent.get_cli_command_template()
        assert cmd[0] == "kimi"
        assert "kimi-cli" not in cmd
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_agent.py::TestKimiCodeCLI -v`
Expected: FAIL — template still returns `kimi-cli`

- [ ] **Step 4: Update implementation**

Modify `zima/models/agent.py` line 171:

```python
templates = {
    "kimi": ["kimi"],  # Kimi Code CLI
    "claude": ["claude", "-p"],
}
```

同时检查 `build_command` 中的 prompt 注入逻辑是否仍适用于 Kimi Code CLI。如果 Kimi Code CLI 的 prompt 参数变了，同步修改 `_build_kimi_command` 或 `build_command`。

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_agent.py::TestKimiCodeCLI -v`
Expected: PASS

- [ ] **Step 6: Run full unit tests to catch regressions**

Run: `uv run pytest tests/unit/test_models_agent.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add zima/models/agent.py tests/unit/test_models_agent.py
git commit -m "feat(agent): update Kimi command from kimi-cli to Kimi Code CLI"
```

---

### Task 6: 示例 PJob / Workflow / Agent / Variable / Env 配置

**Files:**
- Create: `examples/webhook/README.md`
- Create: `examples/webhook/agents/claude.yaml`
- Create: `examples/webhook/agents/kimi.yaml`
- Create: `examples/webhook/workflows/cr-claude.yaml`
- Create: `examples/webhook/workflows/cr-kimi.yaml`
- Create: `examples/webhook/variables/cr-vars.yaml`
- Create: `examples/webhook/envs/github-env.yaml`
- Create: `examples/webhook/pjobs/claude-cr.yaml`
- Create: `examples/webhook/pjobs/kimi-cr.yaml`

**Interfaces:**
- Produces: 可一键导入的示例配置

- [ ] **Step 1: Create agent configs**

`examples/webhook/agents/claude.yaml`:

```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: claude
  name: Claude Code
  description: Claude Code reviewer
spec:
  type: claude
  parameters:
    maxTurns: 100
    permissionMode: bypassPermissions
    outputFormat: text
```

`examples/webhook/agents/kimi.yaml`:

```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: kimi
  name: Kimi Code
  description: Kimi Code CLI reviewer
spec:
  type: kimi
  parameters:
    maxStepsPerTurn: 50
    outputFormat: text
```

- [ ] **Step 2: Create variable config**

`examples/webhook/variables/cr-vars.yaml`:

```yaml
apiVersion: zima.io/v1
kind: Variable
metadata:
  code: cr-vars
  name: CR Variables
spec:
  values:
    repo: ""
    pr: ""
    head_sha: ""
```

- [ ] **Step 3: Create env config**

`examples/webhook/envs/github-env.yaml`:

```yaml
apiVersion: zima.io/v1
kind: Env
metadata:
  code: github-env
  name: GitHub Env
spec:
  vars:
    - name: GITHUB_TOKEN
      source: cmd
      value: gh auth token
```

- [ ] **Step 4: Create workflow templates**

`examples/webhook/workflows/cr-claude.yaml`:

```yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: cr-claude
  name: Claude CR Workflow
spec:
  template: |
    Please review PR #{{ pr }} in {{ repo }} at commit {{ head_sha }}.
    Use the github-code-review-batch skill.
```

`examples/webhook/workflows/cr-kimi.yaml`:

```yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: cr-kimi
  name: Kimi CR Workflow
spec:
  template: |
    Please review PR #{{ pr }} in {{ repo }} at commit {{ head_sha }}.
    Use the github-code-review-batch skill.
```

- [ ] **Step 5: Create PJob configs**

`examples/webhook/pjobs/claude-cr.yaml`:

```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: claude-cr
  name: Claude Code Review
spec:
  agent: claude
  workflow: cr-claude
  variables: cr-vars
  env: github-env
  actions:
    preExec:
      - provider: github
        action: scan_pr
        args:
          repo: "{{ repo }}"
          pr: "{{ pr }}"
    postExec:
      - provider: github
        action: add_comment
        condition: always
```

`examples/webhook/pjobs/kimi-cr.yaml`:

```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: kimi-cr
  name: Kimi Code Review
spec:
  agent: kimi
  workflow: cr-kimi
  variables: cr-vars
  env: github-env
  actions:
    preExec:
      - provider: github
        action: scan_pr
        args:
          repo: "{{ repo }}"
          pr: "{{ pr }}"
    postExec:
      - provider: github
        action: add_comment
        condition: always
```

- [ ] **Step 6: Create README**

`examples/webhook/README.md`:

```markdown
# Webhook 触发 Code Review 示例配置

## 安装配置

```bash
# 复制到 ZIMA_HOME
cp -r agents workflows variables envs pjobs ~/.zima/configs/

# 启动 webhook server
zima webhook-server \
  --smee-url https://smee.io/YOUR_CHANNEL \
  --pjob claude-cr \
  --pjob kimi-cr \
  --secret YOUR_WEBHOOK_SECRET
```

## GitHub Webhook 配置

在目标仓库 Settings > Webhooks 添加：
- Payload URL: `https://smee.io/YOUR_CHANNEL`
- Content type: `application/json`
- Secret: 同上
- Events: Pull requests
```

- [ ] **Step 7: Commit**

```bash
git add examples/webhook/
git commit -m "docs(examples): add webhook-triggered code review configs"
```

---

### Task 7: 集成测试与端到端验证

**Files:**
- Test: `tests/integration/test_webhook_end_to_end.py`

**Interfaces:**
- Consumes: all previous components
- Produces: passing integration tests

- [ ] **Step 1: Write integration test**

Create `tests/integration/test_webhook_end_to_end.py`:

```python
"""End-to-end integration test for webhook-driven review trigger."""

import json
import threading
from http.client import HTTPConnection

import pytest

from zima.webhook.server import make_handler


@pytest.fixture
def webhook_server(tmp_path):
    """Start a local webhook server for end-to-end test."""
    from http.server import HTTPServer

    handler = make_handler(
        pjob_codes=["claude-cr", "kimi-cr"],
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
    payload = json.dumps({
        "action": "labeled",
        "label": {"name": "zima:needs-review"},
        "pull_request": {
            "number": 99,
            "state": "open",
            "draft": False,
            "head": {"sha": "deadbeef"},
            "base": {"repo": {"full_name": "zhuxixi/jfox"}},
        },
    }).encode()

    conn = HTTPConnection(host, port)
    conn.request("POST", "/webhook", body=payload, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    assert response.status == 200

    assert len(calls) == 2
    assert calls[0][:4] == ["zima", "pjob", "run", "claude-cr"]
    assert calls[1][:4] == ["zima", "pjob", "run", "kimi-cr"]
    assert "--set-var=repo=zhuxixi/jfox" in calls[0]
    assert "--set-var=pr=99" in calls[0]
    assert "--set-var=head_sha=deadbeef" in calls[0]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_webhook_end_to_end.py -v`
Expected: PASS

- [ ] **Step 3: Run lint and format checks**

Run:

```bash
uv run black zima/ tests/ --line-length 100
uv run ruff check zima/ tests/
```

Expected: No errors

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
Expected: PASS with coverage >= 60%

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_webhook_end_to_end.py
git commit -m "test(webhook): add end-to-end integration test"
```

---

### Task 8: 文档更新与最终验证

**Files:**
- Modify: `README.md`（可选，添加 webhook 使用说明）
- Modify: `AGENTS.md`（可选，更新架构描述）

- [ ] **Step 1: Update README**

在 README 的 Usage 或 Features 部分添加：

```markdown
## Webhook 触发自动 Code Review

```bash
zima webhook-server \
  --smee-url https://smee.io/YOUR_CHANNEL \
  --pjob claude-cr \
  --pjob kimi-cr \
  --secret YOUR_SECRET
```

当 PR 被打上 `zima:needs-review` 标签时，自动触发 Claude Code 和 Kimi Code CLI 审查。
```

- [ ] **Step 2: Final verification**

Run:

```bash
uv run zima --help
uv run zima webhook-server --help
uv run pytest tests/ -m "not slow"
```

Expected: All commands work, all tests pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): add webhook-server usage"
```

---

## Self-Review Checklist

- [ ] Spec coverage: every requirement in the design doc maps to a task above.
- [ ] Placeholder scan: no "TBD", "TODO", or vague steps remain.
- [ ] Type consistency: `PullRequestLabeledEvent`, `trigger_pjobs`, `run_server`, `run_smee_client` signatures match across tasks.
- [ ] Testability: each task has unit or integration tests with expected outputs.
- [ ] No core changes: `PJobExecutor` and `DaemonScheduler` are not modified.
