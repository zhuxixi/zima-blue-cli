# Issue #163 — smee SSE 僵尸连接心跳看门狗：根因报告 + 设计 spec

## 1. 根因（已取证）

**一句话**：smee.io 服务端的连接保活机制让客户端所有既有检测手段全部失效——每 30s 心跳帧使读超时永不触发、服务端 `socket.setTimeout(0)` 使连接永不主动断开，EventBus 投递脱钩（多实例/redis 订阅丢失）后连接「活着但收不到事件」，客户端无限阻塞在 `iter_lines()`。

**证据链**（来自 issue 实测 + 服务端源码取证）：

| # | 证据 | 来源 |
|---|------|------|
| 1 | GitHub → smee `last_response: 200 OK`；smee → 本地 SSE 事件零痕迹；本地手动 POST 立即触发 | issue Evidence 表（三层对照） |
| 2 | journal 9 小时无任何 `[smee] connection lost` 日志 → 循环从未退出过 | issue |
| 3 | smee.io `KeepAlive(30000)` 每 30s 写 `id: N\nevent: ping\ndata: {}\n\n` | probot/smee.io `lib/keep-alive.js` + `lib/server.js`（ssePing） |
| 4 | SSE handler `reply.raw.socket.setTimeout(0)` — 服务端永不主动断开 | probot/smee.io `lib/server.js` |
| 5 | 事件经 EventBus（内存/redis pub-sub）投递；投递与连接脱钩即僵尸 | probot/smee.io `lib/server.js`（`bus.on(channel, reply.sse)`） |

**为什么 requests `timeout=(10, 60)` 失效**：urllib3 读超时是「单次 recv 无数据的最长等待」。心跳帧每 30s 到达 → 每次 recv 都有数据 → 永不超时。TCP keepalive 同理（连接层活跃）。**必须应用层判据：最近收到字节时间。**

**僵尸形态与判定修正（CR round-1 推翻初判）**：

| 形态 | 机制 | 心跳帧还发吗 | 既有读超时 `(10,60)` | 「任何字节」看门狗 |
|------|------|-------------|---------------------|------------------|
| **A. 无字节僵尸** | TCP 半开 / 中间设备静默丢包，服务端整条连接死亡 | 不发 | **60s 内必抛 ReadTimeoutError** → backoff 重连（有日志） | ✅ 但冗余（读超时已兜底） |
| **B. 脱钩僵尸** | EventBus 投递脱钩（redis 订阅丢失/多实例），但 KeepAlive 是独立内存 timer、持有 reply 引用，**与 bus listener 是两套** | **照发，每 30s** | 永不触发（心跳喂饱） | ❌ activity 被心跳持续刷新 |

**实证案例实为形态 B（CR round-1 修正初判）**，证据链：
1. 若形态 A：读超时 60s 必抛异常 → journal 必有 `[smee] connection lost` 日志；实测 9h 零日志 → 形态 A 排除。
2. 初判的反证（「心跳到达 → 误转发 `data:{}` → server 打 stderr」）**不成立**：server 处理链是 `json.loads("{}")` 成功 → `parse_pull_request_labeled({})` 返回 None → **静默 200 `{"ignored": true}`，无 stderr**（server.py `event is None` 分支）。形态 B 下 journal 同样干净。
3. 结论：心跳每 30s 正常到达（读超时与字节看门狗均被喂饱），EventBus 投递脱钩（事件到不了）。**被动判据无法区分「脱钩」与「正常空闲」，必须主动探测。**

**附带 bug（调研发现，issue 未提及）**：心跳帧 `data: {}` 会被 `parse_smee_event` 解析为 `{}`（非 None）→ 现有代码每 30s 向本地 server 转发一个 `{}` 空事件（有 secret 时重签 HMAC POST）。本地 server 会过滤掉，无实际危害，但应顺带修复。

## 2. 修复方案（6 项）

### 2.1 字节级心跳看门狗（形态 A 防御）— `zima/webhook/smee.py`

> CR round-1 定位修正：形态 A 下既有读超时 `(10,60)` 已免底（60s 必重连），本节看门狗价值降为防御层（更准的日志 + 读超时失效的边角场景）；真正修复实证失效模式的是 2.2 主动探测。

**实现选项对比**：

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| A. 看门狗线程（选定） | 读循环记录 `last_activity`；daemon 线程每 15s 检查，超 180s 调 `response.close()` | 改动最小、复用既有 iter_lines + backoff；线程开销可忽略（15s 一次 wait） | 需处理 close 后 iter_lines 的两种退出路径 |
| B. iter_content 手动分帧 | 放弃 iter_lines，按 `\n\n` 分帧解析，循环内检查时钟 | 无线程 | 重写帧解析，跨 chunk 边界处理复杂，回归风险大 |
| C. 调小读超时 | `timeout=(10, 10)` | 零代码 | **无效**（心跳帧保底 30s 一次） |

**选 A**。细节：

- `last_activity = time.monotonic()` 在**任何 raw_line 到达时**刷新（含心跳/注释/空行——"有字节"即活着）。
- 看门狗线程每 `WATCHDOG_CHECK_INTERVAL = 15.0s` 检查 `now - last_activity > DEAD_AFTER = 180.0s`（心跳 30s 的 6 倍，容忍抖动；连接建立后 180s 内至少应有 6 个心跳帧）→ 触发时：
  - 打日志：`[smee] watchdog: no SSE data for {age:.0f}s, closing stale connection`（**含静默时长**，对应 acceptance 1）
  - 设置共享标志 `watchdog_fired = True`（线程安全：主循环读标志，用简单 bool + GIL 即可；或用 threading.Event）
  - `response.close()`
- **两种退出路径都覆盖**：
  - iter_lines 抛异常（`ChunkedEncodingError`/`ConnectionError`）→ 外层 except 正常走 backoff 重连（日志已含原因）
  - iter_lines 正常退出（close 后 stop iteration 不抛）→ for 循环后检查 `watchdog_fired`，手动 `raise SmeeWatchdogTimeout` 走同一 except 路径
**实现注意（review 补充的 3 个坑）**：

1. **`last_activity` 必须用可变容器共享**（如 `activity = [time.monotonic()]`，主循环写 `activity[0]`，watchdog 读 `activity[0]`）。主循环里直接 `last_activity = time.monotonic()` 是重新绑定局部变量，watchdog 线程读到的是旧引用，看门狗会误杀健康连接。
2. **刷新顺序：先刷新看门狗，再 parse/跳过**。`activity[0] = time.monotonic()` 在 `parse_smee_event` **之前**执行（任何 raw_line 到达即刷新，含心跳帧）——否则「跳过心跳帧不转发」的修复会把看门狗饿死（心跳帧不再更新活动时间，健康空闲连接反被误杀）。
3. **旧看门狗线程要显式退出**：每次连接成功新建 watchdog 线程并配一个 `stop_event`；主循环退出该连接的 iter_lines 后 `stop_event.set()`，线程下一次 wait 唤醒即 return。不通知的话旧线程多活 ~180s 后去 close 已关闭的 response（幂等无害，但不干净）。`watchdog_fired` 同样用 `threading.Event`，比裸 bool 干净。
- 自定义异常 `SmeeWatchdogTimeout(Exception)`，被外层 `except Exception` 捕获（既有 backoff 路径），无需新增 except 分支。

**常量**（模块级，可测）：
```python
_WATCHDOG_CHECK_INTERVAL = 15.0   # watchdog thread poll cadence
_DEAD_AFTER = 180.0               # no bytes for this long -> stale connection
```

### 2.2 主动探测回环（形态 B 核心，CR round-1 新增）

被动判据无法区分形态 B（心跳活跃、事件脱钩）与正常空闲，改为**端到端主动探测**：

- 看门狗线程每 `_PROBE_INTERVAL = 300.0s` 向 smee channel **self-POST 探测事件** `{"_zima_probe": "<uuid4hex>"}`（POST 到 `smee_url` 本身，走 smee 正常投递路径）。
- SSE 读循环识别回环：`event["body"]["_zima_probe"]` 匹配 pending 探测 id → 清除 pending，**不转发本地 server**（对 server 零噪音）。
- 判据：pending 探测超 `_PROBE_TIMEOUT = 120.0s` 未回环 → 判定脱钩 → 打日志（含探测 id 与等待时长）→ `fired.set()` + `response.close()`（与字节看门狗同一重连路径）。
- POST 失败（网络层）→ 打日志、不置 pending（无法判定脱钩），`_PROBE_INTERVAL` 后再试。
- smee 回环延迟通常 <5s；检测延迟最坏 `PROBE_INTERVAL + PROBE_TIMEOUT` ≈ 7 分钟（对比修复前：永不）。
- 探测事件在 smee 公开 channel 可见，但 payload 无秘密。
- 常量模块级、monkeypatch 友好；`_PROBE_INTERVAL` 默认 300s 远大于单测时长，既有测试不受影响。

### 2.3 心跳帧不再误转发（顺带修复）— `zima/webhook/smee.py`

`parse_smee_event` 返回 `{}`（心跳 `data: {}`）时，循环内加：

```python
event = parse_smee_event(line)
if not event:          # skip smee.io keep-alive ping frames (data: {})
    continue
```

不破坏 `test_fallback_when_no_body_key`（fallback 布局的真实事件含 action 等键，非空 dict）。

### 2.4 stdout 行缓冲 — 命令入口（防御性）

`zima/commands/webhook.py` 的 serve 回调开头调用 `_enable_line_buffered_stdout()`。

CR round-1 修正：server.py 三处 `[webhook]` 日志全部走 stderr（本就无缓冲），本项对它们无作用；保留仅作防御（启动横幅及未来可能的 stdout 日志），docstring 已据实修正。

### 2.5 看门狗线程自身异常须打日志（CR round-1）

`_watch()` 外层 `except Exception` 不再静默 return——打 `[smee] watchdog thread died: ...` 到 stderr。否则看门狗意外死亡 = 僵尸检测无声失效，重演「静默丢失」原始故障模式。

### 2.6 重连重放 — 不新增机制

看门狗重连后 smee 重放缓存事件：**这是期望行为**（找回僵尸期丢失的事件）。重复触发受现有 60s dedup（repo#pr#head_sha#pjob）拦截；同 head 重复 CR 是 benign 浪费。**不扩展 dedup**（issue 的顺带评估项，结论：维持现状，spec 记录理由）。

## 3. 组件契约

- `run_smee_client(smee_url, target_url, secret=None)` — 签名不变，行为变化仅在内部。
- 新增模块级：`_WATCHDOG_CHECK_INTERVAL`、`_DEAD_AFTER`、`SmeeWatchdogTimeout`。
- `parse_smee_event` / `extract_smee_payload` — 不变。

- 字节级看门狗量的是「读循环消费」而非「socket 到达」：forward POST 阻塞（≤10s）期间到达的字节不刷新 activity——长串 stalled POST 理论上可误杀健康连接（成本一次 benign 重连，已加注释说明）。
- 探测线程职责合并在看门狗线程内：探测 POST 阻塞（≤10s）最多延迟一次检查，可接受。

## 4. 降级路径

- 看门狗线程任何异常 → 打 stderr 日志后退出（不杀主循环，降级为现状行为）。
- `response.close()` 失败/无效 → 循环重试 close（单次跨线程 close 不一定打断 C 级阻塞 recv）；读超时 60s 最终兜底。
- 探测 POST 失败 → 不动作（无法判定），下轮再试。

## 5. 非目标

- 不修 smee.io 服务端（外部服务）。
- 不做 TCP keepalive 参数调优（无效路径）。
- 不扩展 dedup 键（见 2.6）。
- 不改 systemd unit 文件（在 repo 外，运维侧）。

## 6. 测试计划

**单测（tests/unit/test_webhook_smee.py，TDD 先写失败测试）**：
1. `test_watchdog_closes_stale_connection`：零字节流 → 字节看门狗触发 close + 日志 + backoff 重连（形态 A 防御）。
2. `test_watchdog_survives_heartbeats`：心跳持续 → 不触发（0.02s pace vs 0.3s 阈值，15x margin 防 CI flake）。
3. `test_watchdog_iter_lines_exception_path`：close 后 iter_lines 抛异常 → 仍走 backoff。
4. `test_probe_timeout_closes_detached_connection`：心跳活跃但探测无回环（形态 B）→ close + 重连；探测事件不转发本地。
5. `test_probe_echo_keeps_connection_alive`：探测回环正常 → 不 close、探测帧不转发。
6. `test_skips_empty_heartbeat_event`：`data: {}` 不 POST。
7. 既有 10 个测试全绿（无回归）。

**集成/验收（issue Acceptance）**：
- [ ] SSE 流 180s 级无字节 → 主动断开重连，日志含静默时长
- [ ] 手动 kill 连接（iptables drop 模拟半开）→ 看门狗阈值内恢复
- [ ] journal 实时可见 stdout 日志

## 7. 风险与回滚

- 探测误判：回环延迟 <5s vs 超时 120s，margin 24x；smee 整体故障时探测 POST 本身失败（不置 pending），不误杀。
- 回滚：单文件 revert `zima/webhook/smee.py` + `zima/commands/webhook.py` 两处。
