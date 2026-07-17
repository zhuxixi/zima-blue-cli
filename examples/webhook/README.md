# Webhook 触发 Code Review 示例配置

## 安装配置

从仓库根目录执行（用 `$ZIMA_HOME` 兼容自定义路径，默认 `~/.zima`）：

```bash
# 复制示例配置到 ZIMA_HOME（默认 ~/.zima，可用 ZIMA_HOME 环境变量覆盖）
ZIMA_HOME="${ZIMA_HOME:-$HOME/.zima}"
mkdir -p "$ZIMA_HOME/configs/"
cp -r examples/webhook/agents examples/webhook/workflows examples/webhook/variables \
      examples/webhook/envs examples/webhook/pjobs "$ZIMA_HOME/configs/"
```

```bash
# 启动 webhook server。secret 走环境变量，避免出现在 `ps` / /proc 里。
export ZIMA_WEBHOOK_SECRET=your-webhook-secret
zima webhook-server \
  --smee-url https://smee.io/YOUR_CHANNEL \
  --pjob claude-cr \
  --pjob kimi-cr
```

## 使用说明

1. **目标 PR 必须带有 `zima:needs-review` 标签**
   - 本示例中的 `scan_pr` action 会按该标签查找仓库中待审查的 PR。
   - Webhook 收到 GitHub 的 `labeled` 事件后，即认为被标记的 PR 就是需要审查的目标 PR。

2. **GitHub Webhook 配置**

   在目标仓库 Settings > Webhooks 添加：
   - Payload URL: `https://smee.io/YOUR_CHANNEL`
   - Content type: `application/json`
   - Secret: 同上
   - Events: **Pull requests**（至少要勾选 `labeled` action，否则无法触发 review）

3. **流程**
   - 给目标 PR 添加 `zima:needs-review` 标签。
   - GitHub 发送 `pull_request` 事件，action 为 `labeled`。
   - Zima 启动对应的 PJob，执行代码审查。
   - 审查成功后，PJob 会在 PR 下评论 "Code review completed by ..."。
