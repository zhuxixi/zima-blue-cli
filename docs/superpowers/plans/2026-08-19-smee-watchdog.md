# smee SSE 僵尸连接心跳看门狗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `run_smee_client` 加应用层心跳看门狗——SSE 流 180s 无任何字节即主动断开重连，根治 smee 僵尸连接导致的 webhook 事件静默丢失（#163）。

**Architecture:** 主读循环用共享可变容器 `activity = [time.monotonic()]` 记录最近字节时间（任何 raw_line 到达即刷新，先于 parse/跳过）；每条连接配一个 daemon 看门狗线程，每 15s 检查 `now - activity[0] > _DEAD_AFTER`，超时则打日志（含静默时长）、置 `fired` Event、`response.close()`；iter_lines 两种退出路径（抛异常 / 正常返回）都汇入既有 backoff 重连。顺带：空事件（smee `data: {}` 心跳帧）不再转发；webhook 命令入口 stdout 行缓冲。

**Tech Stack:** Python 3.10+, requests (stream), threading, pytest + monkeypatch。

**Worktree:** 所有命令在 `/home/elling/git-repo/github/zima-blue-cli/.claude/worktrees/issue-163-smee-watchdog` 下执行（pi session cwd 固定，用 `git -C <worktree>` 或绝对路径）。

**Spec:** `docs/superpowers/specs/2026-08-19-smee-watchdog-design.md`（本仓库内，含根因取证与形态边界）。

## Global Constraints

- 只覆盖**形态 A（无字节僵尸）**；形态 B（有心跳的 EventBus 脱钩）是非目标。
- 常量：`_WATCHDOG_CHECK_INTERVAL = 15.0`，`_DEAD_AFTER = 180.0`（模块级，测试可 monkeypatch）。
- `last_activity` 共享必须用可变容器（`list`），禁止局部变量重绑。
- activity 刷新必须在 `parse_smee_event` **之前**。
- 看门狗日志格式：`[smee] watchdog: no SSE data for {age:.0f}s, closing stale connection`（stderr，含静默时长）。
- Python 3.10+；black 100 chars；ruff 无警告；commit 格式 `type(scope): description`。
- 测试隔离：monkeypatch `time.sleep` 的既有测试模式里，FakeResponse 内**禁用 `time.sleep`**（会被替换），用 `threading.Event.wait(timeout)` 模拟阻塞。

---

### Task 1: 跳过 smee 心跳帧（空事件不转发）

smee.io 每 30s 发 `event: ping\ndata: {}\n\n`，`parse_smee_event("data: {}")` 返回 `{}`（非 None），现有代码把它当事件每 30s POST 一次到本地 server。一行修复，先行合入以简化 Task 2 的测试。

**Files:**
- Modify: `zima/webhook/smee.py`（`run_smee_client` 的 iter_lines 循环内）
- Test: `tests/unit/test_webhook_smee.py`

**Interfaces:**
- Consumes: 既有 `parse_smee_event(line: str) -> Optional[dict]`
- Produces: 无新接口；行为变化：空 dict 事件（`{}`）不触发 POST。

- [ ] **Step 1: 写失败测试**

追加到 `tests/unit/test_webhook_smee.py` 的 `TestRunSmeeClient`：

```python
    def test_skips_empty_heartbeat_event(self, monkeypatch):
        """smee.io keep-alive ping frames (data: {}) must not be forwarded.

        smee.io sends ``event: ping\\ndata: {}`` every 30s (lib/keep-alive.js).
        parse_smee_event returns {} for that line, which used to be forwarded
        as a real event (noise POST every 30s; re-signed when secret is set).
        """
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
                return [
                    b"id: 1",
                    b"event: ping",
                    b"data: {}",
                    b'data: {"body": {"action": "labeled"}, "rawBody": "{\\"action\\":\\"labeled\\"}", "headers": {"x-hub-signature-256": "sha256=sig"}}',
                ]

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        class FakePostResponse:
            status_code = 200
            text = "ok"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            posts.append((url, json, data, headers, timeout))
            return FakePostResponse()

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        # Only the real event is forwarded; the {} heartbeat is skipped.
        assert len(posts) == 1
        assert posts[0][2] == b'{"action":"labeled"}'
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.claude/worktrees/issue-163-smee-watchdog
uv run pytest tests/unit/test_webhook_smee.py::TestRunSmeeClient::test_skips_empty_heartbeat_event -v
```

Expected: FAIL — `len(posts) == 2`（`{}` 也被 POST）。

- [ ] **Step 3: 实现（一行）**

`zima/webhook/smee.py` 的 iter_lines 循环内，`event = parse_smee_event(line)` 之后：

```python
                    event = parse_smee_event(line)
                    if not event:
                        # Skip smee.io keep-alive ping frames (data: {}) and
                        # non-data/blank/undecodable lines (None).
                        continue
```

（替换原有 `if event is None: continue`。）

- [ ] **Step 4: 跑测试确认通过 + 全文件回归**

```bash
uv run pytest tests/unit/test_webhook_smee.py -v
```

Expected: 全绿（含既有 `test_fallback_when_no_body_key`——fallback 事件 `{"action": "labeled"}` 非空，不受影响）。

- [ ] **Step 5: Commit**

```bash
git add zima/webhook/smee.py tests/unit/test_webhook_smee.py
git commit -m "fix(webhook): skip smee.io keep-alive ping frames instead of forwarding (#163)"
```

---

### Task 2: 心跳看门狗（核心）

**Files:**
- Modify: `zima/webhook/smee.py`（模块常量 + `SmeeWatchdogTimeout` + `_start_watchdog` + `run_smee_client` 循环）
- Test: `tests/unit/test_webhook_smee.py`

**Interfaces:**
- Consumes: Task 1 后的循环结构（`if not event: continue` 已存在）。
- Produces:
  - `_WATCHDOG_CHECK_INTERVAL: float = 15.0`（模块常量）
  - `_DEAD_AFTER: float = 180.0`（模块常量）
  - `class SmeeWatchdogTimeout(Exception)`（模块级）
  - `_start_watchdog(response, activity: list[float], stop_event: threading.Event, fired_event: threading.Event) -> None`

- [ ] **Step 1: 写失败测试（3 个）**

追加到 `TestRunSmeeClient`。**注意**：FakeResponse 内用 `threading.Event.wait()` 模拟阻塞，禁用 `time.sleep`（被 monkeypatch）；测试文件顶部需补 `import time`（FakeResponse 里的 `time.monotonic()` 解析自测试模块全局命名空间）。

```python
    def test_watchdog_closes_stale_connection(self, monkeypatch, capsys):
        """No SSE bytes for _DEAD_AFTER -> watchdog closes the connection and
        the loop reconnects via the existing backoff path. Core fix for #163."""
        import threading

        monkeypatch.setattr("zima.webhook.smee._DEAD_AFTER", 0.3)
        monkeypatch.setattr("zima.webhook.smee._WATCHDOG_CHECK_INTERVAL", 0.05)

        get_calls = []
        close_calls = []
        stream_closed = threading.Event()
        sleeps = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def close(self):
                close_calls.append(None)
                stream_closed.set()

            def iter_lines(self):
                # Zombie stream: open but no bytes ever arrive. Block until the
                # watchdog closes us, then end cleanly (the no-exception exit
                # path close() can cause).
                stream_closed.wait(timeout=10)
                return []

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_sleep(seconds):
            sleeps.append(seconds)
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert len(close_calls) == 1  # watchdog closed the stale connection
        assert sleeps == [1.0]  # reconnected via backoff (delay was reset on connect)
        err = capsys.readouterr().err
        assert "[smee] watchdog: no SSE data for" in err
        assert "closing stale connection" in err

    def test_watchdog_survives_heartbeats(self, monkeypatch, capsys):
        """A stream delivering heartbeat frames stays alive (no close)."""
        import threading

        monkeypatch.setattr("zima.webhook.smee._DEAD_AFTER", 0.3)
        monkeypatch.setattr("zima.webhook.smee._WATCHDOG_CHECK_INTERVAL", 0.05)

        get_calls = []
        close_calls = []
        pace = threading.Event()

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def close(self):
                close_calls.append(None)

            def iter_lines(self):
                # Heartbeat frames every ~0.05s for ~0.5s (> _DEAD_AFTER),
                # then the stream ends cleanly.
                deadline = time.monotonic() + 0.5
                while time.monotonic() < deadline:
                    yield b"data: {}"
                    pace.wait(0.05)

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", lambda *a, **k: None)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert close_calls == []  # heartbeats kept the watchdog fed
        err = capsys.readouterr().err
        assert "watchdog" not in err

    def test_watchdog_iter_lines_exception_path(self, monkeypatch, capsys):
        """If close() makes iter_lines raise (the other exit path), the
        existing outer except handles it and reconnects with backoff."""
        import threading

        monkeypatch.setattr("zima.webhook.smee._DEAD_AFTER", 0.3)
        monkeypatch.setattr("zima.webhook.smee._WATCHDOG_CHECK_INTERVAL", 0.05)

        get_calls = []
        close_calls = []
        stream_closed = threading.Event()
        sleeps = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def close(self):
                close_calls.append(None)
                stream_closed.set()

            def iter_lines(self):
                stream_closed.wait(timeout=10)
                raise requests.exceptions.ChunkedEncodingError("connection broken")

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_sleep(seconds):
            sleeps.append(seconds)
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert len(close_calls) == 1
        assert sleeps == [1.0]
        err = capsys.readouterr().err
        assert "[smee] watchdog: no SSE data for" in err
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/unit/test_webhook_smee.py -k watchdog -v
```

Expected: 3 个全 FAIL（AttributeError: FakeResponse has no close 被调用 / 无 watchdog 日志 / close_calls 为空）。注意 `test_watchdog_closes_stale_connection` 会阻塞到 `stream_closed.wait(timeout=10)` 超时——失败较慢是正常的。

- [ ] **Step 3: 实现**

`zima/webhook/smee.py`：

模块常量区（`_MAX_BACKOFF` 附近）加：

```python
# Watchdog: smee.io sends a keep-alive frame every 30s (lib/keep-alive.js),
# and the server never closes idle connections (socket.setTimeout(0)). When
# the connection silently dies (TCP half-open / server-side drop), requests'
# read timeout never fires because heartbeat bytes keep arriving -- only an
# application-level "last byte received" check detects the zombie (#163).
_WATCHDOG_CHECK_INTERVAL = 15.0
_DEAD_AFTER = 180.0


class SmeeWatchdogTimeout(Exception):
    """Raised when the SSE stream goes silent past the dead threshold."""


def _start_watchdog(
    response: requests.Response,
    activity: list,
    stop_event: threading.Event,
    fired_event: threading.Event,
) -> None:
    """Start a daemon thread that closes ``response`` if no SSE bytes arrive
    within ``_DEAD_AFTER`` seconds.

    ``activity`` is a one-element list holding the last-activity monotonic
    timestamp; the read loop refreshes ``activity[0]`` on every raw line
    (mutable container -- a plain local reassignment would not be visible to
    the watchdog thread). ``fired_event`` is set before closing so the read
    loop can tell a watchdog kill apart from a clean stream end.
    """

    def _watch() -> None:
        try:
            while not stop_event.wait(_WATCHDOG_CHECK_INTERVAL):
                age = time.monotonic() - activity[0]
                if age > _DEAD_AFTER:
                    fired_event.set()
                    print(
                        f"[smee] watchdog: no SSE data for {age:.0f}s, closing stale connection",
                        file=sys.stderr,
                    )
                    try:
                        response.close()
                    except Exception:  # noqa: BLE001 - close is best-effort
                        pass
                    return
        except Exception:  # noqa: BLE001 - watchdog failure must not kill the reader
            return

    threading.Thread(target=_watch, daemon=True).start()
```

`run_smee_client` 内，连接成功（`delay = _INITIAL_BACKOFF` 重置）之后、iter_lines 循环之前：

```python
                # Successful connection: reset backoff.
                delay = _INITIAL_BACKOFF
                activity = [time.monotonic()]
                stop_watchdog = threading.Event()
                watchdog_fired = threading.Event()
                _start_watchdog(response, activity, stop_watchdog, watchdog_fired)
                try:
                    for raw_line in response.iter_lines():
                        # Refresh BEFORE parse/skip: heartbeat frames are not
                        # forwarded but still prove the connection is alive.
                        activity[0] = time.monotonic()
                        if not raw_line:
                            continue
                        line = raw_line.decode("utf-8")
                        event = parse_smee_event(line)
                        if not event:
                            continue
                        # ... 既有 forward 逻辑不变 ...
                finally:
                    stop_watchdog.set()
                if watchdog_fired.is_set():
                    # iter_lines returned cleanly after our close() (no
                    # exception): route into the same backoff-reconnect path.
                    raise SmeeWatchdogTimeout(
                        f"no SSE data for over {_DEAD_AFTER:.0f}s; reconnecting"
                    )
```

注意：既有 forward 逻辑（`body, headers, raw_body = extract_smee_payload(event)` 起）整体留在 `try:` 块内、`for` 循环里，缩进不变（原循环体本就在 for 内；只需确认 try/finally 包裹的是整个 for）。

- [ ] **Step 4: 跑测试确认通过 + 全文件回归**

```bash
uv run pytest tests/unit/test_webhook_smee.py -v
```

Expected: 全绿（13 个测试）。既有 `test_exponential_backoff` / `test_backoff_resets_after_success` 保绿 = backoff 无回归。

- [ ] **Step 5: Commit**

```bash
git add zima/webhook/smee.py tests/unit/test_webhook_smee.py
git commit -m "fix(webhook): heartbeat watchdog closes stale smee SSE connections (#163)"
```

---

### Task 3: webhook 命令入口 stdout 行缓冲

`[webhook]` 日志走 stdout，非 tty 下块缓冲导致 journal 积压不可见。代码侧修复，不依赖 systemd 环境。

**Files:**
- Modify: `zima/commands/webhook.py`（新增 `_enable_line_buffered_stdout` + serve 回调开头调用）
- Test: `tests/unit/test_webhook_command.py`（新建）

**Interfaces:**
- Consumes: 无。
- Produces: `zima.commands.webhook._enable_line_buffered_stdout() -> None`（容错：stdout 无 reconfigure 或已关闭时不抛异常）。

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/test_webhook_command.py`：

```python
"""Tests for the webhook-server command entry helpers."""

import sys

from zima.commands.webhook import _enable_line_buffered_stdout


class TestEnableLineBufferedStdout:
    """stdout must be line-buffered so [webhook] logs reach journald in
    real time (block buffering hid them under systemd)."""

    def test_reconfigure_called(self, monkeypatch):
        class FakeStdout:
            def __init__(self):
                self.calls = []

            def reconfigure(self, **kwargs):
                self.calls.append(kwargs)

        fake = FakeStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        _enable_line_buffered_stdout()
        assert fake.calls == [{"line_buffering": True}]

    def test_tolerates_unconfigurable_stdout(self, monkeypatch):
        class BrokenStdout:
            def reconfigure(self, **kwargs):
                raise ValueError("I/O operation on closed file")

        monkeypatch.setattr(sys, "stdout", BrokenStdout())
        _enable_line_buffered_stdout()  # must not raise
```

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/unit/test_webhook_command.py -v
```

Expected: FAIL — `ImportError: cannot import name '_enable_line_buffered_stdout'`。

- [ ] **Step 3: 实现**

`zima/commands/webhook.py` 加：

```python
def _enable_line_buffered_stdout() -> None:
    """Make stdout line-buffered so [webhook] logs reach journald in real time.

    stdout is block-buffered when redirected (systemd/journald), which hid
    [webhook] log lines until the buffer flushed (#163). stderr is already
    unbuffered; this covers the stdout prints in the server.
    """
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError, OSError):
        pass
```

serve 回调函数体最开头（`if not pjob:` 等校验之前）调用：

```python
    _enable_line_buffered_stdout()
```

- [ ] **Step 4: 跑测试确认通过 + 命令回归**

```bash
uv run pytest tests/unit/test_webhook_command.py tests/integration/test_webhook_command.py -v
```

Expected: 全绿。

- [ ] **Step 5: Commit**

```bash
git add zima/commands/webhook.py tests/unit/test_webhook_command.py
git commit -m "fix(webhook): line-buffer stdout so server logs reach journald (#163)"
```

---

### Task 4: 全量回归 + lint

- [ ] **Step 1: 全量测试**

```bash
uv run pytest tests/unit/ -q
```

Expected: 全绿。

- [ ] **Step 2: lint + format**

```bash
uv run ruff check zima/ tests/
uv run black --check zima/ tests/ --line-length 100
```

Expected: 无输出（或先 `uv run black zima/webhook/smee.py zima/commands/webhook.py tests/unit/test_webhook_smee.py tests/unit/test_webhook_command.py --line-length 100` 再 check）。

- [ ] **Step 3: 最终 commit（如有格式化改动）**

```bash
git add -u
git commit -m "style: black formatting (#163)" || true
```

---

## CR Round-1 Follow-up（2026-08-19）

CR 推翻形态判定（实证案例是形态 B：心跳照发、EventBus 脱钩；读超时与字节看门狗均被心跳喂饱），新增 Task 5/6。

---

### Task 5: 主动探测回环（形态 B 核心修复）

**Files:**
- Modify: `zima/webhook/smee.py`（`_start_watchdog` 签名与循环 + 读循环探测识别）
- Test: `tests/unit/test_webhook_smee.py`

**Interfaces:**
- Consumes: Task 2 的看门狗骨架。
- Produces:
  - `_PROBE_INTERVAL: float = 300.0`、`_PROBE_TIMEOUT: float = 120.0`（模块常量）
  - `_start_watchdog(response, smee_url, activity, probe_pending, stop_event, fired_event) -> None`（签名变化：新增 `smee_url`、`probe_pending`）
  - `probe_pending: list` —— 共享可变容器，元素为 `None` 或 `(probe_id, sent_monotonic)` 元组；读循环清除，看门狗线程写入。

- [ ] **Step 1: 写失败测试（2 个）**

```python
    def test_probe_timeout_closes_detached_connection(self, monkeypatch, capsys):
        """Heartbeats flowing but probe never echoes back (detached EventBus)
        -> watchdog closes the connection. Core fix for the observed #163
        failure mode (form B)."""
        monkeypatch.setattr("zima.webhook.smee._WATCHDOG_CHECK_INTERVAL", 0.05)
        monkeypatch.setattr("zima.webhook.smee._DEAD_AFTER", 999.0)  # byte watchdog off
        monkeypatch.setattr("zima.webhook.smee._PROBE_INTERVAL", 0.05)
        monkeypatch.setattr("zima.webhook.smee._PROBE_TIMEOUT", 0.2)

        get_calls = []
        close_calls = []
        probe_posts = []
        target_posts = []
        stream_closed = threading.Event()
        sleeps = []
        pace = threading.Event()

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def close(self):
                close_calls.append(None)
                stream_closed.set()

            def iter_lines(self):
                # Form B: heartbeat frames keep arriving (byte watchdog stays
                # fed), but no probe echo ever comes back.
                while not stream_closed.is_set():
                    yield b"data: {}"
                    pace.wait(0.02)

        class FakePostResponse:
            status_code = 200
            text = "ok"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            if url.startswith("https://smee.io"):
                probe_posts.append(json)
            else:
                target_posts.append(json)
            return FakePostResponse()

        def fake_sleep(seconds):
            sleeps.append(seconds)
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert probe_posts  # probe was sent to the smee channel
        assert "_zima_probe" in probe_posts[0]
        assert close_calls  # probe timeout closed the detached connection
        assert target_posts == []  # nothing forwarded to the local server
        assert sleeps == [1.0]
        err = capsys.readouterr().err
        assert "probe" in err and "closing detached connection" in err

    def test_probe_echo_keeps_connection_alive(self, monkeypatch, capsys):
        """A probe echo that round-trips clears the pending probe; the
        connection stays up and the probe frame is never forwarded."""
        monkeypatch.setattr("zima.webhook.smee._WATCHDOG_CHECK_INTERVAL", 0.05)
        monkeypatch.setattr("zima.webhook.smee._DEAD_AFTER", 999.0)
        monkeypatch.setattr("zima.webhook.smee._PROBE_INTERVAL", 0.05)
        monkeypatch.setattr("zima.webhook.smee._PROBE_TIMEOUT", 10.0)

        get_calls = []
        close_calls = []
        probe_ids = []
        echo_sent = threading.Event()
        pace = threading.Event()
        target_posts = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def close(self):
                close_calls.append(None)

            def iter_lines(self):
                deadline = time.monotonic() + 0.6
                while time.monotonic() < deadline:
                    if probe_ids and not echo_sent.is_set():
                        echo = {"body": {"_zima_probe": probe_ids[0]}}
                        echo_sent.set()
                        yield "data: " + json.dumps(echo)
                    else:
                        yield b"data: {}"
                    pace.wait(0.02)

        class FakePostResponse:
            status_code = 200
            text = "ok"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_get(*args, **kwargs):
            get_calls.append(None)
            if len(get_calls) > 1:
                raise requests.RequestException("stop loop")
            return FakeResponse()

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            if url.startswith("https://smee.io"):
                if json and "_zima_probe" in json:
                    probe_ids.append(json["_zima_probe"])
            else:
                target_posts.append(json)
            return FakePostResponse()

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client("https://smee.io/test", "http://127.0.0.1:8765/webhook")
        except RuntimeError:
            pass

        assert probe_ids  # probe was sent
        assert echo_sent.is_set()  # echo was delivered back over the SSE stream
        assert close_calls == []  # echo cleared the pending probe, no close
        assert target_posts == []  # probe frame was not forwarded
        err = capsys.readouterr().err
        assert "watchdog" not in err
```

注意：iter_lines 混 yield str/bytes（回环帧 str、心跳 bytes）——`raw_line.decode` 对 str 会抛 AttributeError！统一 bytes：回环帧用 `("data: " + json.dumps(echo)).encode()`。

- [ ] **Step 2: 跑测试确认失败**

```bash
uv run pytest tests/unit/test_webhook_smee.py -k probe -v
```

Expected: FAIL（`_PROBE_INTERVAL` AttributeError / `_start_watchdog` 签名不匹配 TypeError）。

- [ ] **Step 3: 实现**

`zima/webhook/smee.py` 顶部加 `import uuid`；常量区 `_DEAD_AFTER` 后加：

```python
# Probe: form-B zombies (heartbeats flowing, EventBus detached) are
# indistinguishable from healthy idle by passive checks -- only an active
# round-trip probe detects them. Self-POST a probe event to the channel every
# _PROBE_INTERVAL; it must echo back over our SSE stream within _PROBE_TIMEOUT.
_PROBE_INTERVAL = 300.0
_PROBE_TIMEOUT = 120.0
```

`_start_watchdog` 改为：

```python
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
      -> no-bytes zombie (form A). Read timeout already covers this; the
      watchdog is defense-in-depth with better logging.
    - Probe: every ``_PROBE_INTERVAL`` self-POST ``{"_zima_probe": <uuid>}``
      to the smee channel; if no matching echo arrives within
      ``_PROBE_TIMEOUT``, the connection is detached from the event bus
      (form B). Probe echoes are consumed by the read loop (never forwarded).

    ``activity``/``probe_pending`` are one-element lists shared with the read
    loop (mutable container -- a plain local reassignment would not be
    visible to this thread). ``fired_event`` is set before closing so the
    read loop can tell a watchdog kill apart from a clean stream end.
    """

    def _close_stale(message: str) -> None:
        if not fired_event.is_set():
            fired_event.set()
            print(message, file=sys.stderr)
        try:
            response.close()
        except Exception:  # noqa: BLE001 - close is best-effort
            pass

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
                        requests.post(
                            smee_url, json={"_zima_probe": probe_id}, timeout=10
                        )
                        probe_pending[0] = (probe_id, now)
                    except Exception as exc:  # noqa: BLE001 - network-level failure
                        # Cannot judge detachment; log and retry next interval.
                        print(
                            f"[smee] watchdog: probe POST failed ({exc})",
                            file=sys.stderr,
                        )
                    last_probe_sent = now
        except Exception as exc:  # noqa: BLE001 - log before dying (#163 CR)
            print(f"[smee] watchdog thread died: {exc}", file=sys.stderr)

    threading.Thread(target=_watch, daemon=True).start()
```

`run_smee_client` 循环接线（`_start_watchdog` 调用处 + 读循环探测识别）：

```python
                activity = [time.monotonic()]
                probe_pending: list = [None]
                stop_watchdog = threading.Event()
                watchdog_fired = threading.Event()
                _start_watchdog(
                    response, smee_url, activity, probe_pending, stop_watchdog, watchdog_fired
                )
```

读循环里 `if not event: continue` 之后、`extract_smee_payload` 之前：

```python
                        # Probe echo: a healthy connection delivers our own
                        # probe back. Consume it here -- never forward.
                        probe_body = event.get("body")
                        if isinstance(probe_body, dict) and "_zima_probe" in probe_body:
                            pending = probe_pending[0]
                            if pending and probe_body["_zima_probe"] == pending[0]:
                                probe_pending[0] = None
                            continue
```

- [ ] **Step 4: 跑测试确认通过 + 全文件回归（连跑 3 次防 flake）**

```bash
for i in 1 2 3; do uv run pytest tests/unit/test_webhook_smee.py -q | tail -1; done
```

Expected: 3 次全绿（23 个）。既有测试不受影响（`_PROBE_INTERVAL` 默认 300s >> 测试时长）。

- [ ] **Step 5: Commit**

```bash
git add zima/webhook/smee.py tests/unit/test_webhook_smee.py
git commit -m "fix(webhook): active probe round-trip detects EventBus-detached smee connections (#163)"
```

---

### Task 6: CR round-1 剩余修复（watchdog 死亡日志 + docstring 修正）

**Files:**
- Modify: `zima/webhook/smee.py`（`_watch` 外层 except 打日志——已含在 Task 5 实现里，此处仅验证）、`zima/commands/webhook.py`（docstring）
- Test: 无新测试（Task 3 的测试已覆盖行为）

- [ ] **Step 1: 修 `_enable_line_buffered_stdout` docstring**

```python
def _enable_line_buffered_stdout() -> None:
    """Make stdout line-buffered as a defense for stdout prints.

    The server's [webhook] runtime logs go to stderr (already unbuffered);
    stdout only carries the startup banner and any future stdout prints,
    which would otherwise be block-buffered under systemd/journald (#163).
    """
```

- [ ] **Step 2: 验证 + commit**

```bash
uv run pytest tests/unit/test_webhook_command.py -q
git add zima/commands/webhook.py
git commit -m "docs(webhook): correct _enable_line_buffered_stdout docstring (#163)"
```

---

## 验收映射（spec §6，CR round-1 更新）

| Acceptance | 覆盖 |
|---|---|
| 形态 B（实证失效模式）：探测无回环 → 主动断开重连 + 日志 | Task 5 测试 1（单测）+ 合并后实网验收 |
| 形态 A：180s 无字节 → 主动断开重连 + 日志含静默时长 | Task 2 测试 1/3（防御层；读超时 60s 已免底） |
| 心跳持续 / 探测回环正常 → 不误杀 | Task 2 测试 2 + Task 5 测试 2 |
| 看门狗自身死亡有日志 | Task 5/6（_watch 外层 except 打 stderr） |
| 单测 mock「心跳后停住」「心跳在但无回环」 | Task 2 测试 1、Task 5 测试 1 |
| backoff 无回归 | Task 2 测试 2 + 既有 backoff 测试 |
