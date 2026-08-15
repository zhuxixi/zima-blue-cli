# Spec: fix(webhook) smee client forward 破坏签名，webhook 触发从未生效（issue #149）

日期：2026-08-12
状态：待确认
路由：bug → systematic-debugging（Phase 1-3 根因调查已完成于 issue #149 + JFox 笔记，本文档是 Phase 4 实现设计）

## 一句话修复思路

让 smee 转发器持有 secret，在原始签名字节丢失（无 rawBody）时，对「自己即将发送的字节」重新算 HMAC 签名再转发——保证签名和字节永远匹配；同时 forward 后检查响应码，非 2xx 打日志，杜绝静默失败。

## 背景：签名机制（为什么字节必须一致）

GitHub 发 webhook 时用共享 secret 对请求体**原始字节**算 HMAC-SHA256 指纹（`x-hub-signature-256: sha256=<hex>`）。本地 server（`zima/webhook/payload.py::verify_signature`）收到请求后对收到的字节重算并比对，一致才信任。这要求**签名时的字节 == 验签时的字节**，差一个空格都不行。

## 根因（已确认）

链路是 GitHub → smee.io（中转）→ zima webhook-server。断点在中转环节：

1. smee.io 转发事件时把请求体解析成 JSON dict（`body`）再重新打包，**原始字节串丢了**——smee 事件里没有 `rawBody` 字段（`zima/webhook/smee.py::extract_smee_payload` 返回 `raw_body=None`）。
2. `run_smee_client` 无 rawBody 时走 `requests.post(target_url, json=body, ...)`——requests 按自己的规则把 dict 重新序列化成字节（字段顺序/空格/unicode 转义都不可控），与 GitHub 签名所基于的字节不一致。
3. 本地 server 拿「新字节」验「旧签名」→ 永远 400 invalid signature。
4. `requests.post` 不检查响应码，4xx 不抛异常 → **静默失败**，无日志、无 spawn。

证据链（issue #149 三层对照法，JFox 笔记 202608122243131666）：
- GitHub→smee 通（deliveries 200）；本地 server 通（直接 POST 签名事件 spawn 成功）；smee 推送通（curl 收到事件）；仅 smee client forward 路径复现 400。
- 修复方向已验证：用 secret 对 `json.dumps(body)` 重新 HMAC 后 forward → **200 triggered ok**。

## 为什么修复 = 重签，而不是找回原始字节

原始字节已被 smee 丢弃，找不回来。唯一可行路径：放弃沿用 GitHub 签名，改由 smee 转发器自己用 secret 重算。本地 server 不关心签名最初是谁算的，只关心「签名和字节匹配」——转发器签的就是它实际发送的字节，验签必然通过。

## 核心技巧：发什么就签什么

现有代码的坑是 `json=body`：requests 的序列化结果不可控，签名跟不上新字节。修复反过来：

```
payload_bytes = json.dumps(body).encode("utf-8")   # 1. 自己序列化，拿到字节
sig = "sha256=" + hmac(secret, payload_bytes)      # 2. 对这份字节算签名
requests.post(target, data=payload_bytes, ...)     # 3. 原样发送同一份字节
```

签名和发送用同一份字节 → 无论序列化规则怎么变都成立，从根上消除「两边序列化不一致」这一类问题，而不是去对齐 requests 的序列化细节。

## 设计决策表

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 签名字节来源 | 用 `json.dumps(body)` 的字节做 HMAC，并以 `data=` 发送同一份字节 | 「发什么就签什么」，从根上消除序列化不一致 |
| secret 传入 | `run_smee_client(smee_url, target_url, secret)` 新参数；CLI `_run_smee_forwarder` / `_on_listening` 透传 `serve()` 已有的 secret | secret 在 CLI 层已有完整链路（envvar `ZIMA_WEBHOOK_SECRET` / `--secret`），无需新增配置面 |
| 无 secret 行为 | 保持 `json=body` 原行为 | `--allow-no-secret` 本地调试场景：server 的 `verify_signature` 在 secret 为空时恒真，不签也能通 |
| 有 rawBody 行为 | 继续走「原始字节 + 原始签名头」路径，不重签 | 签名本来就有效，动它反而破坏；改动最小 |
| 响应码检查 | forward 后检查 status，非 2xx 记 `[smee] forward got {status}: {body}` 到 stderr，不抛异常 | 杜绝再静默失败；事件级失败不 kill SSE 流（不触发重连） |
| 签名格式 | `x-hub-signature-256: sha256=<hex>` | 与 `payload.py::verify_signature` 的期望格式严格一致 |

## 修改点

### `zima/webhook/smee.py`
1. `run_smee_client(smee_url: str, target_url: str, secret: Optional[str] = None)` 加参数。
2. 无 rawBody 分支（现有 else 分支）改为：
   - 有 secret：`payload_bytes = json.dumps(body).encode("utf-8")` → HMAC 签名 → headers 覆写 `x-hub-signature-256` → `requests.post(target_url, data=payload_bytes, headers=headers, timeout=10)`。
   - 无 secret：保持 `json=body`（现有行为，本地调试）。
3. 两个 forward 分支统一在 post 后检查响应码：`if not 200 <= resp.status_code < 300: print("[smee] forward got ...", file=sys.stderr)`。
4. 新增 import：`hmac`、`hashlib.sha256`。

### `zima/commands/webhook.py`
5. `_run_smee_forwarder(smee_url, target_url, secret)`：调用 `run_smee_client(smee_url, target_url, secret)`。
6. `_on_listening` 中启动 smee 线程的 args 加 `secret`。

## 测试计划（TDD：先写失败测试，再实现）

`tests/unit/test_webhook_smee.py`：
- **改** `test_forwards_body_and_headers`：无 rawBody + secret 时，断言 `data=` 为 `json.dumps(body)` 的字节、`x-hub-signature-256` 是用该字节独立重算的 `sha256=...`、`json` 参数为 None。
- **新增** `test_forwards_no_secret_keeps_json_body`：无 rawBody + secret=None 时仍走 `json=body`。
- **新增** `test_forward_logs_non_2xx`：fake post 返回 500，capsys 断言 stderr 含 `forward got 500`。
- **保留** `test_forwards_raw_body_bytes`（rawBody 优先路径不变）及其余既有用例。

`tests/integration/test_webhook_command.py`：检查 `_run_smee_forwarder` 签名变化是否影响既有调用（应无，线程启动在 CLI 内部）。

## 非目标

- 不改 server 验签逻辑（`payload.py`、`server.py`）。
- 不做 GitHub 原始签名保真（smee 已丢 rawBody，无法还原；重签是唯一可行路径）。
- 不重构 smee SSE 重连/退避逻辑。
- 不处理 webhook 与 daemon 轮询重复触发（既有设计，不在本 issue 范围）。

## 验收标准

1. `uv run pytest tests/unit/test_webhook_smee.py` 全绿（含新用例）。
2. 全量 `uv run pytest tests/` 通过，覆盖率 ≥60% 不破。
3. 部署后真实链路验收：给 PR 打 `zima:needs-review` → journalctl 看到 spawn 日志 / `zima pjob history zima-zc-cr-job` 出现 webhook 触发的非整点记录（这是链路自 v0.6.0 部署以来的首次真实触发）。
