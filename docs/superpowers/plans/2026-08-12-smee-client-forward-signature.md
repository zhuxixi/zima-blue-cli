# Smee Client Forward Signature Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 smee.io 转发事件无 rawBody 时签名失效的问题（issue #149），让 webhook 触发链路首次真实可用。

**Architecture:** smee client（`zima/webhook/smee.py`）持有 secret，无 rawBody 时对 `json.dumps(body)` 的字节重新 HMAC-SHA256 签名并以 `data=` 发送同一份字节（「发什么就签什么」），有 rawBody 时保留原始字节路径不变；forward 后检查响应码非 2xx 记日志。CLI 层（`zima/commands/webhook.py`）把已有 secret 透传给 smee 线程。

**Tech Stack:** Python 3.10+、requests（SSE stream + POST）、hmac/hashlib、pytest + monkeypatch。

## Global Constraints

- Python 3.10+，dataclasses，Google-style docstrings（项目 AGENTS.md）。
- Black 格式 100 字符；ruff 无错误（`uv run ruff check zima/ tests/`）。
- 覆盖率 ≥60%（`uv run pytest tests/ --cov=zima --cov-fail-under=60`）。
- commit 格式 `type(scope): description`，如 `fix(webhook): ...`。
- 工作目录必须是 worktree：`/home/elling/git-repo/github/zima-blue-cli/.claude/worktrees/issue-149-smee-client-forward-signature`，禁碰 main。
- 不改 server 验签逻辑（`payload.py` / `server.py`）、不重构 SSE 重连/退避逻辑。

---

### Task 1: smee client 无 rawBody 时用 secret 重签转发（核心修复）

**Files:**
- Modify: `zima/webhook/smee.py`（`run_smee_client` 签名 + 无 rawBody 分支）
- Test: `tests/unit/test_webhook_smee.py`（新增用例；既有用例不动）

**Interfaces:**
- Consumes: `zima/webhook/smee.py::extract_smee_payload`（已有，返回 `(body, headers, raw_body)`）
- Produces: `run_smee_client(smee_url: str, target_url: str, secret: Optional[str] = None) -> None`——secret 为 None 时行为与旧版完全一致；有 secret 且无 rawBody 时对 `json.dumps(body).encode("utf-8")` 重签并 `data=` 发送。Task 3 依赖此签名。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_webhook_smee.py` 的 `TestRunSmeeClient` 类中新增（照抄既有 `test_forwards_body_and_headers` 的 FakeResponse/fake_get 骨架，只改 post 断言）：

```python
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
            raise requests.RequestException("stop loop after first event")

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            posts.append((url, json, data, headers, timeout))

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client(
                "https://smee.io/test", "http://127.0.0.1:8765/webhook", secret=secret
            )
        except (RuntimeError, requests.RequestException):
            pass

        assert len(posts) == 1
        url, body, data, headers, timeout = posts[0]
        assert url == "http://127.0.0.1:8765/webhook"
        assert body is None
        assert data is not None
        expected_bytes = json.dumps(sse_payload["body"]).encode("utf-8")
        expected_sig = "sha256=" + hmac_module.new(
            secret.encode("utf-8"), expected_bytes, hashlib.sha256
        ).hexdigest()
        assert data == expected_bytes
        assert headers["x-hub-signature-256"] == expected_sig
        assert headers["Content-Type"] == "application/json"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_webhook_smee.py::TestRunSmeeClient::test_forwards_resigned_body_with_secret -v`
Expected: FAIL（当前 `run_smee_client` 无 secret 参数 → TypeError，且即使有参数也不会重签）

- [ ] **Step 3: 实现重签逻辑**

在 `zima/webhook/smee.py`：

1. 顶部 import 增加：
```python
import hmac
from hashlib import sha256
```
2. 签名改为 `def run_smee_client(smee_url: str, target_url: str, secret: Optional[str] = None) -> None:`，docstring 补一句：「``secret`` 用于在 smee.io 事件缺少原始签名字节（rawBody）时重新计算 HMAC 签名；为 None 时原样转发（本地无 secret 调试）。」
3. 事件循环内 forward 分支改为（替换现有 if/else，保持 try/except 结构）：

```python
                    if isinstance(raw_body, str):
                        # Forward the original signed bytes so that HMAC
                        # verification on the local server stays valid.
                        forward_headers = headers.copy()
                        forward_headers["Content-Type"] = "application/json"
                        resp = requests.post(
                            target_url,
                            data=raw_body.encode("utf-8"),
                            headers=forward_headers,
                            timeout=10,
                        )
                    elif secret:
                        # smee.io dropped the raw signed bytes (no rawBody):
                        # resign the exact bytes we are about to send, so the
                        # signature always matches the payload on the server.
                        payload_bytes = json.dumps(body).encode("utf-8")
                        forward_headers = headers.copy()
                        forward_headers["x-hub-signature-256"] = "sha256=" + hmac.new(
                            secret.encode("utf-8"), payload_bytes, sha256
                        ).hexdigest()
                        forward_headers["Content-Type"] = "application/json"
                        resp = requests.post(
                            target_url,
                            data=payload_bytes,
                            headers=forward_headers,
                            timeout=10,
                        )
                    else:
                        resp = requests.post(target_url, json=body, headers=headers, timeout=10)
                    if not 200 <= resp.status_code < 300:
                        print(
                            f"[smee] forward got {resp.status_code}: {resp.text}",
                            file=sys.stderr,
                        )
```

（响应码检查属于 Task 2 的验收，这里一并写出以便测试通过；Task 2 只补该检查的专项测试。）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_webhook_smee.py -v`
Expected: 全绿（既有 `test_forwards_body_and_headers` 走 secret=None 分支不受影响；`test_forwards_raw_body_bytes` 走 rawBody 分支不受影响）

- [ ] **Step 5: Commit**

```bash
git add zima/webhook/smee.py tests/unit/test_webhook_smee.py
git commit -m "fix(webhook): resign forwarded body when smee drops rawBody (#149)"
```

---

### Task 2: forward 非 2xx 响应记日志（杜绝静默失败）

**Files:**
- Modify: `zima/webhook/smee.py`（响应码检查已在 Task 1 步骤 3 写入；本任务只补测试）
- Test: `tests/unit/test_webhook_smee.py`（新增用例）

**Interfaces:**
- Consumes: Task 1 的 `run_smee_client(smee_url, target_url, secret)`——每个 forward 分支后已检查 `resp.status_code`，非 2xx 打印 `[smee] forward got {status}: {text}` 到 stderr（不抛异常、不 kill SSE 流）。
- Produces: 无新接口。

- [ ] **Step 1: 写失败测试**

在 `TestRunSmeeClient` 类中新增：

```python
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

        def fake_get(*args, **kwargs):
            raise requests.RequestException("stop loop after first event")

        def fake_post(url, json=None, data=None, headers=None, timeout=None):
            return FakeResponse500()

        def fake_sleep(seconds):
            raise RuntimeError("stop loop")

        monkeypatch.setattr("zima.webhook.smee.requests.get", fake_get)
        monkeypatch.setattr("zima.webhook.smee.requests.post", fake_post)
        monkeypatch.setattr("zima.webhook.smee.time.sleep", fake_sleep)

        try:
            run_smee_client(
                "https://smee.io/test", "http://127.0.0.1:8765/webhook", secret="s"
            )
        except (RuntimeError, requests.RequestException):
            pass

        err = capsys.readouterr().err
        assert "forward got 500: boom" in err
```

- [ ] **Step 2: 跑测试确认通过（Task 1 步骤 3 已含实现）**

Run: `uv run pytest tests/unit/test_webhook_smee.py::TestRunSmeeClient::test_forward_logs_non_2xx -v`
Expected: PASS（若 Task 1 实现未含响应码检查则此处 FAIL，此时补上 Task 1 步骤 3 的检查代码再跑）

- [ ] **Step 3: 跑全文件回归**

Run: `uv run pytest tests/unit/test_webhook_smee.py -v`
Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add zima/webhook/smee.py tests/unit/test_webhook_smee.py
git commit -m "test(webhook): cover non-2xx forward logging (#149)"
```

---

### Task 3: CLI 层把 secret 透传给 smee 线程

**Files:**
- Modify: `zima/commands/webhook.py`（`_run_smee_forwarder` 签名 + `_on_listening` 线程 args）
- Test: `tests/integration/test_webhook_command.py`（新增用例，照 `test_repo_paired_with_pjob_accepted` 模式）

**Interfaces:**
- Consumes: Task 1 的 `run_smee_client(smee_url, target_url, secret)`；`serve()` 回调已有的 `secret: Optional[str]` 参数（来自 envvar `ZIMA_WEBHOOK_SECRET` / `--secret`）。
- Produces: `_run_smee_forwarder(smee_url: str, target_url: str, secret: Optional[str]) -> None`——内部调用 `run_smee_client(smee_url, target_url, secret)`。

- [ ] **Step 1: 写失败测试**

在 `tests/integration/test_webhook_command.py` 的 `TestWebhookServerCommand` 类中新增：

```python
    def test_smee_forwarder_thread_receives_secret(self, monkeypatch):
        """smee forwarder 线程拿到 serve() 的 secret（透传链路完整）。

        Regression for #149: secret 只在 server 验签用，从未传进 smee
        forwarder -> 无 rawBody 事件无法重签 -> 400。
        """
        import zima.commands.webhook as webhook_cmd

        captured: dict = {}
        thread_spawns = []

        def fake_run_server(**kwargs):
            captured.update(kwargs)

        class FakeThread:
            def __init__(self, target, args, daemon=True):
                thread_spawns.append((target, args))

            def start(self):
                pass

        monkeypatch.setattr(webhook_cmd, "run_server", fake_run_server)
        monkeypatch.setattr(webhook_cmd.threading, "Thread", FakeThread)

        result = runner.invoke(
            app,
            [
                "webhook-server",
                "--smee-url",
                "https://smee.io/x",
                "--secret",
                "s3cret",
                "--pjob",
                "cr",
            ],
        )
        assert result.exit_code == 0, result.output

        captured["on_listening"]()
        assert len(thread_spawns) == 1
        target, args = thread_spawns[0]
        assert target is webhook_cmd._run_smee_forwarder
        assert args == ("https://smee.io/x", "http://127.0.0.1:8765/webhook", "s3cret")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/integration/test_webhook_command.py::TestWebhookServerCommand::test_smee_forwarder_thread_receives_secret -v`
Expected: FAIL（当前 args 只有两个元素，断言 3 元组不匹配）

- [ ] **Step 3: 实现透传**

在 `zima/commands/webhook.py`：

1. `_run_smee_forwarder` 签名改为 `def _run_smee_forwarder(smee_url: str, target_url: str, secret: Optional[str]) -> None:`，函数体调用改为 `run_smee_client(smee_url, target_url, secret)`，docstring 补「secret 透传给 run_smee_client，用于 smee 事件缺 rawBody 时重签」。
2. `_on_listening` 中线程 args 改为 `args=(smee_url, target_url, secret),`。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/integration/test_webhook_command.py -v`
Expected: 全绿（既有用例不受影响）

- [ ] **Step 5: Commit**

```bash
git add zima/commands/webhook.py tests/integration/test_webhook_command.py
git commit -m "fix(webhook): pass webhook secret through to smee forwarder (#149)"
```

---

### Task 4: 全量回归 + lint + 收尾

**Files:**
- 无新文件。

- [ ] **Step 1: 全量测试**

Run: `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
Expected: 全绿，coverage ≥60%

- [ ] **Step 2: lint + 格式**

Run: `uv run ruff check zima/ tests/ && uv run black --check zima/ tests/ --line-length 100`
Expected: 无错误；若有格式问题 `uv run black zima/ tests/ --line-length 100` 修后再 commit

- [ ] **Step 3: 确认改动面只有预期文件**

Run: `git status --short && git log --oneline origin/main..HEAD`
Expected: 仅 `zima/webhook/smee.py`、`zima/commands/webhook.py`、两个测试文件、一个 spec 文档

- [ ] **Step 4: Commit（如有 lint 修复）**

```bash
git add -u
git commit -m "style(webhook): apply black formatting (#149)"
```

## Self-Review

- **Spec 覆盖**：✔ 重签路径（Task 1）✔ 响应码日志（Task 2）✔ secret 透传（Task 3）✔ 无 secret 兼容（Task 1 未动 secret=None 分支，既有测试覆盖）✔ rawBody 优先（既有测试覆盖）✔ 验收标准 1-2（Task 4）。
- **占位符扫描**：无 TBD/TODO；所有步骤含具体代码。
- **类型一致性**：`run_smee_client(smee_url, target_url, secret)` 在 Task 1 定义、Task 2/3 引用，签名一致；`_run_smee_forwarder(smee_url, target_url, secret)` 在 Task 3 定义并被同一任务测试引用。
