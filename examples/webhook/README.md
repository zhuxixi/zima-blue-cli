# Webhook 触发 Code Review 示例配置

## 安装配置

```bash
# 确保 ZIMA_HOME 配置目录存在
mkdir -p ~/.zima/configs/

# 从仓库根目录进入示例目录，并复制配置到 ZIMA_HOME
#（以下命令使用绝对路径，可直接从任意目录执行）
cd examples/webhook
cp -r agents workflows variables envs pjobs ~/.zima/configs/
```

> 如果 `~/.zima` 不是默认位置，请确保已正确设置 `ZIMA_HOME` 环境变量。

```bash
# 启动 webhook server
zima webhook-server \
  --smee-url https://smee.io/YOUR_CHANNEL \
  --pjob claude-cr \
  --pjob kimi-cr \
  --secret YOUR_WEBHOOK_SECRET
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
