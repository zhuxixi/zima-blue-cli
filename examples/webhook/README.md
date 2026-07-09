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
