# Webhook Server 多仓库路由 — 设计文档

- **Issue**: [#145](https://github.com/zhuxixi/zima-blue-cli/issues/145)
- **Date**: 2026-08-12
- **Scope**: `zima/webhook/server.py`, `zima/commands/webhook.py`, `zima/webhook/payload.py` + 测试 + 文档

## 1. 问题

单个 `zima webhook-server` 实例无法正确服务多仓库：配置多个 `--pjob`（分属不同仓库）时，每条 `labeled` 事件触发**全部** PJob，且每个 PJob 都通过 `--set-var=repo={event.repo}` 拿到同一个 repo → 交叉触发、审查错误仓库。当前唯一解法是每仓库各起一套独立栈（smee + 端口 + systemd unit + secret），随仓库数线性增长。

## 2. 根因（已读码确认）

- `zima/webhook/server.py::trigger_pjobs(event, pjob_codes)`：遍历全部 code，每个都用 `--set-var=repo={event.repo}` 启动，**无 repo→pjob 绑定**。
- `zima/webhook/payload.py::should_trigger_review`：只判 `state==open && !draft`。这是**事件合法性过滤**，repo 路由是 server 层职责——payload 层不改。
- smee (`zima/webhook/smee.py`)：透明转发器，不改。

## 3. 设计

### 3.1 CLI

新增 repeatable `--repo` 选项，与 `--pjob` **按出现顺序 zip 配对**：

```
zima webhook-server \
  --pjob zima-zc-cr-job --repo zhuxixi/zima-blue-cli \
  --pjob jfox-zc-code-review-job --repo zhuxixi/jfox \
  --smee-url https://smee.io/<共用 channel> \
  --secret "$ZIMA_WEBHOOK_SECRET"
```

Click/Typer 对每个 repeatable option 分别保序收集，故 `--pjob=[A,B]`、`--repo=[X,Y]`，zip 得 `[(A,X),(B,Y)]`——与书写交错无关，只要计数相等。

### 3.2 决策表

| 场景 | `--pjob` | `--repo` | 行为 |
|------|---------|---------|------|
| 单/多仓库路由 | N≥1 | N（与 pjob 相等） | **路由模式**：仅触发 `repo==event.repo` 的 PJob |
| 向后兼容（现状） | N≥1 | 0 | **广播模式**：事件触发全部 PJob（与 v0.6.0 完全一致） |
| 计数不等 | N | M≠N | **报错退出**：明确提示配对要求 |
| 路由模式 + 零匹配 | N | N | 事件被忽略，记日志，不广播 |

### 3.3 向后兼容（issue 待定项的决议）

issue 写「不带 `--repo` 的 `--pjob` 保留当前行为（或明确报错——待定）」。本设计选 **保留当前行为（广播）**：

- 现有 `--pjob A --pjob B`（无 `--repo`）零改动，仍对任意 repo 事件触发两者 → 真正向后兼容。
- 一旦传任何 `--repo` 即进入路由模式（全有或全无，避免"部分绑定部分广播"的歧义语义）。

理由：广播是 issue 列出的首选项；且现有生产 unit（单 `--pjob`）可零改动继续运行。

### 3.4 内部模型

`zima/webhook/server.py` 新增：

```python
@dataclass
class PjobRoute:
    code: str
    repo: Optional[str]   # None => 广播（任意 repo），仅广播模式出现

def _route_matches(route: PjobRoute, event_repo: str) -> bool:
    if route.repo is None:
        return True
    return route.repo.lower() == event_repo.lower()   # 大小写不敏感
```

签名变更（内部 API，同步更新调用方与测试）：

- `trigger_pjobs(event, routes: list[PjobRoute]) -> dict[str, str]`
- `make_handler(routes: list[PjobRoute], ...)`
- `run_server(port, routes: list[PjobRoute], ...)`
- `WebhookRequestHandler.pjob_routes: ClassVar[Optional[list[PjobRoute]]]`

### 3.5 路由逻辑（trigger_pjobs）

```
_reap_children()
for route in routes:
    if not _route_matches(route, event.repo):
        continue                       # 跳过非本仓库绑定
    if _is_duplicate(event, route.code):
        statuses[code] = "duplicate"; continue
    spawn [.., "pjob", "run", code, "--set-var=repo={event.repo}", ..]
    statuses[code] = "ok" | error
if routes and no route matched:
    log("[webhook] event repo {repo} matched no --pjob binding; ignored")
return statuses
```

- 去重 key `event.repo#pr#sha#code` 不变 → 去重仍按 (event, code) 生效。
- 响应体 `triggered` 改为 `list(statuses.keys())`（仅匹配到的 code），比旧"全部 code"更准确。
- 路由模式下零匹配 → 不 spawn、记日志、返回空 statuses。

### 3.6 入参校验（payload.py）

`payload.py` 暴露公共 `is_valid_repo(value: str) -> bool`（复用现有 `_VALID_REPO`），`commands/webhook.py` 用它校验每个 `--repo` 值，集中 repo 校验逻辑、避免正则重复。

## 4. 非目标

- borobo（#29 vNext / #37 多仓库配置层）的 per-repo FSM 规则、`configs/repos/` mapping —— 不在本 issue 范围。
- webhook 事件类型扩展（只处理 `pull_request.labeled zima:needs-review`，不变）。
- 单实例多 channel（仍单 smee channel，多仓库共用）。

## 5. 验收标准映射

| AC | 实现 |
|----|------|
| 每个 `--pjob` 可绑 `--repo`（成对） | 3.1 CLI + 3.2 决策表 |
| repo 不匹配 → 忽略 + 记日志 | 3.5 零匹配分支 |
| 事件只触发匹配 repo 的 PJob | 3.5 `_route_matches` 过滤 |
| 向后兼容（无 `--repo` 保留现状） | 3.3 广播模式 |
| 单测：单仓/多仓路由/不匹配忽略/去重 | 见 plan |
| 文档：README + AGENTS.md | 见 plan（+ CLAUDE.md gotcha） |
