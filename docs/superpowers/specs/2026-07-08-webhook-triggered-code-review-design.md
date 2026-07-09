# Webhook 触发自动 Code Review（Phase 1）

**Date**: 2026-07-08
**Status**: Draft
**Related Issues**: #29, #32, #35, #36, #37
**Related Docs**: [2026-04-20-issue-29-borobo-design.md](./2026-04-20-issue-29-borobo-design.md), [2026-04-13-pr-auto-code-review-design.md](./2026-04-13-pr-auto-code-review-design.md)

## 1. 背景

当前 Zima 通过 daemon scheduler 以 45 分钟为周期扫描打了 `zima:needs-review` 标签的 PR，然后启动两个 PJob 分别调用 Claude Code 和 Kimi CLI 做代码审查。这种时间轮询模式在开发时间不固定（如工作之余、晚上）时存在明显问题：

- 事件响应延迟高（平均 22.5 分钟）
- 大部分时间空转
- 与用户实际开发动作不同步

本设计实现一个最小可用的 webhook 触发版本：当 GitHub PR 被打上 `zima:needs-review` 标签时，立即并行触发 Claude Code 和 Kimi Code CLI 两个 reviewer PJob。

## 2. 目标与非目标

### 目标

- PR 被打上 `zima:needs-review` 标签后，数秒内触发 review。
- 同时触发两个独立 PJob：一个跑 Claude Code，一个跑 Kimi Code CLI。
- Webhook 接收器运行在用户本地机器，通过 smee.io 接收公网事件。
- 与现有 PJob / action / provider 体系完全兼容，不改动 executor 和 daemon scheduler。
- 把 `zima/models/agent.py` 中的 Kimi 命令从旧 `kimi-cli` 更新为 Kimi Code CLI。

### 非目标

- 不实现完整的 babysit / fix 闭环（仍由现有 session 层或未来 borobo 负责）。
- 不替代 daemon scheduler 的所有功能（只替代基于轮询的 review 触发）。
- 不实现 GitHub App（使用仓库级 webhook）。
- 不实现多仓库配置（Phase 1 先支持单个目标仓库，架构上可扩展）。

## 3. 整体架构

```
GitHub PR labeled zima:needs-review
        │
        ▼
   smee.io channel
        │
        ▼
zima webhook-server (本地进程)
        │
        ▼
校验 payload + 标签名
        │
        ▼
并行调用两次 zima pjob run:
  ├─ zima pjob run claude-cr --set-var repo=<owner/repo> --set-var pr=<n> --set-var head_sha=<sha>
  └─ zima pjob run kimi-cr --set-var repo=<owner/repo> --set-var pr=<n> --set-var head_sha=<sha>
        │
        ▼
两个 PJob 各自渲染 workflow → 调 agent → 出 review → post PR 评论
```

## 4. 新增/修改组件

| 组件 | 类型 | 说明 |
|---|---|---|
| `zima/commands/webhook.py` | 新增 | `zima webhook-server` 子命令实现 |
| `zima/webhook/server.py` | 新增 | HTTP 服务，接收并响应 webhook |
| `zima/webhook/smee.py` | 新增 | smee.io SSE client，连接 smee channel 并把收到的事件 POST 到本地 HTTP 服务 |
| `zima/webhook/payload.py` | 新增 | GitHub payload 解析与校验 |
| `zima/cli.py` | 修改 | 注册 `webhook` 子命令 |
| `zima/models/agent.py` | 修改 | Kimi agent 命令模板从 `kimi-cli` 更新为 Kimi Code CLI |
| `examples/webhook/` | 新增 | 示例 PJob / workflow / agent / variable / env YAML |

## 5. 触发与数据流

### 监听事件

只订阅仓库 webhook 的 `Pull requests` 事件，本地只处理 `action == "labeled"` 且 `label.name == "zima:needs-review"` 的情况。

```json
{
  "action": "labeled",
  "label": { "name": "zima:needs-review" },
  "pull_request": {
    "number": 123,
    "state": "open",
    "draft": false,
    "head": { "sha": "abc123..." },
    "base": { "repo": { "full_name": "owner/repo" } }
  }
}
```

### 过滤条件

必须同时满足：

1. `action == "labeled"`
2. `label.name == "zima:needs-review"`
3. `pull_request.state == "open"`
4. `--skip-draft` 为 true 时跳过 `pull_request.draft == true`

### 注入变量

通过 `--set-var` 传给 PJob：

| 变量名 | 来源 | 用途 |
|---|---|---|
| `repo` | `pull_request.base.repo.full_name` | 被审仓库 |
| `pr` | `pull_request.number` | 被审 PR 编号 |
| `head_sha` | `pull_request.head.sha` | 当前 HEAD，供增量审查比对 |

### 执行模型

webhook-server 并行调用两次 `zima pjob run` CLI。`zima pjob run` 本身会以 detached subprocess 启动 background runner，因此 webhook-server 不需要等待 agent 执行完成，应立即返回 HTTP 200 给 smee.io / GitHub。agent 执行结果由 PJob 自己的 history 和 postExec 处理。

## 6. PJob 配置示例

### `claude-cr` PJob

```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: claude-cr
  name: Claude Code Review
spec:
  agent: claude
  workflow: cr-workflow-claude
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

### `kimi-cr` PJob

```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: kimi-cr
  name: Kimi Code Review
spec:
  agent: kimi
  workflow: cr-workflow-kimi
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

两个 PJob 除了 agent 和 workflow 不同，其余结构一致。workflow 负责构造各自的 prompt / skill 调用。

## 7. CLI 命令

```bash
# 启动 webhook 服务器（带 smee）
ZIMA_WEBHOOK_SECRET=MY_GITHUB_WEBHOOK_SECRET zima webhook-server \
  --smee-url https://smee.io/abc123 \
  --pjob claude-cr \
  --pjob kimi-cr \
  --port 8765

# 不带 smee，仅本地 HTTP（测试用）
zima webhook-server \
  --pjob claude-cr \
  --pjob kimi-cr \
  --port 8765
```

参数说明：

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--smee-url` | smee.io channel URL | 可选；不提供则只监听本地端口 |
| `--pjob` | 事件触发时要运行的 PJob code，可多次指定 | 必填 |
| `--port` | 本地 HTTP 端口 | `8765` |
| `--secret` | GitHub webhook secret | 可选；也可通过 `ZIMA_WEBHOOK_SECRET` 环境变量设置，`--secret` 优先级更高。提供时校验 `X-Hub-Signature-256` |
| `--skip-draft` | 是否跳过 draft PR | `true` |

## 8. 安全

- **Webhook Secret 校验**：支持 HMAC-SHA256 校验 `X-Hub-Signature-256`。建议通过 `ZIMA_WEBHOOK_SECRET` 环境变量传入 secret，避免在命令行中暴露。MVP 阶段未配置 secret 时不校验，但文档提醒生产环境必须配置。
- **事件白名单**：只处理 `pull_request.labeled`。
- **标签白名单**：只响应 `zima:needs-review`。
- **Draft PR 跳过**：默认不触发 draft PR。
- **本地监听**：HTTP 服务默认绑定 `127.0.0.1`，不暴露到公网。

## 9. 错误处理

| 错误场景 | 处理方式 |
|---|---|
| payload 签名校验失败 | 返回 400，记录日志 |
| action/label 不匹配 | 返回 200（正常忽略），记录 debug 日志 |
| PR 不是 open 或 draft | 返回 200（正常忽略），记录 info 日志 |
| fork/exec `zima pjob run` 失败 | 返回 200 避免 GitHub 重试，记录 error 日志 |
| PJob 执行期间失败 | 由 PJob 自身的 postExec / history 处理 |
| smee.io 断开 | 自动重连，指数退避 |

## 10. 与现有 45 分钟轮询的关系

- webhook-server ready 并验证稳定后，可以关闭现有的 45 分钟 review 轮询 schedule。
- 在 webhook-server 未运行期间，可以手动执行 `zima pjob run claude-cr --set-var repo=... --set-var pr=...` 补审。
- daemon scheduler 本身保留，未来仍可用于非 review 类调度任务。

## 11. 待确认项

1. **Kimi Code CLI 实际命令**：需要确认 Kimi Code CLI 的当前调用方式。`zima/models/agent.py` 中的命令模板从 `kimi-cli` 更新为 `kimi`（或 `kimi-code`）及其参数。
2. **smee.io client 实现方式**：Python 中可直接用 `requests` SSE 客户端或依赖 `smee-client` 的 Python 移植包。
3. **PJob 模板仓库**：示例 PJob / workflow 需要针对不同仓库的 prompt 做微调，示例放在 `examples/webhook/`。
4. **`--set-var` 覆盖行为**：需要确认 `zima pjob run --set-var repo=...` 能否覆盖 PJob 中 `{{ repo }}` 这类 Jinja2 变量。

## 12. 成功标准

- [ ] 在 GitHub PR 上添加 `zima:needs-review` 标签后 10 秒内，本地 `zima webhook-server` 收到事件。
- [ ] 校验通过后，两个 PJob（`claude-cr`、`kimi-cr`）被并行启动。
- [ ] 每个 PJob 成功读取 PR diff 并调用对应 agent。
- [ ] Review 结果以 PR 评论形式发布（沿用现有 `postExec: add_comment`）。
- [ ] 旧的 45 分钟轮询 schedule 可以关闭，不再依赖它触发 review。
- [ ] `zima/models/agent.py` 中 Kimi 命令已更新为 Kimi Code CLI。

## 13. 后续演进

- Phase 2：监听 `pull_request.synchronize`，在 PR 有新 push 且仍带 `zima:needs-review` 时自动重审。
- Phase 3：把 babysit / fix 闭环也接到 webhook（`issue_comment.created` 或 review 结果事件）。
- Phase 4：迁移到 borobo GitHub App，支持多仓库统一配置。
