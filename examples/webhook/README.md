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

## 多仓库路由（单实例服务多仓库）

`--repo`（可重复）按出现顺序与 `--pjob` 1:1 配对，把每个 PJob 绑定到指定仓库。事件到来时，**只触发 `repo` 匹配的 PJob**（大小写不敏感）；不在任何绑定里的仓库事件会被忽略（记日志），不会广播。如此一个 smee channel + 一个 server + 一个 systemd unit 即可服务多个仓库，各仓库的 GitHub webhook 都指向同一个 channel。

```bash
export ZIMA_WEBHOOK_SECRET=your-webhook-secret
zima webhook-server \
  --smee-url https://smee.io/YOUR_SHARED_CHANNEL \
  --pjob zima-zc-cr-job        --repo zhuxixi/zima-blue-cli \
  --pjob jfox-zc-code-review-job --repo zhuxixi/jfox
```

规则：
- `--repo` 数量必须等于 `--pjob` 数量，否则报错退出（按序配对，与书写交错无关）。
- **完全不传 `--repo`** → 保留旧行为（广播模式：任意仓库的事件都触发全部 PJob），向后兼容。
- 一旦传了任何 `--repo`，即进入路由模式（不会对未绑定仓库广播）。

各仓库在 GitHub 侧 Settings > Webhooks 都指向同一个 `https://smee.io/YOUR_SHARED_CHANNEL`，并用同一个 Secret。

