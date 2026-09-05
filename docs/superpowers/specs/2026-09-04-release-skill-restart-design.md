# Spec: release skill 追加"本机升级+重启"步骤（issue #222 · v2 简化版）

日期：2026-09-04 · 状态：draft 待用户确认 · 前版（watcher 方案）已被用户否决：范围过大

## 1. 目标

修改 `.pi/skills/release/SKILL.md`：在 Step 10（PyPI 验证）之后追加 **Step 11 本机服务升级与重启**，把"发版后手动更新本机并重启常驻服务"固化为 skill 步骤。下次任何 agent 跑发版 skill 时自动执行到生效闭环。

## 2. 非目标

- 不加定时任务 / watcher / 任何新代码
- 不做 daemon systemd 化
- 不改 release_helper.py（脚本不动，纯 SKILL.md 文档改动）

## 3. 改动内容

### 3.1 SKILL.md 追加 Step 11

内容 = 固化 2026-09-04 v0.8.2 发版后的实际手动操作（08:03-08:07 实测验证过）：

```
### Step 11: 本机服务升级与重启（发版闭环）

PyPI 验证通过后，更新本机安装并重启常驻服务，让新版本立即生效。
仅当发版机运行着 zima 服务时执行；纯 CI 环境跳过。

(a) 更新本机安装
    uv tool update zima-blue-cli

(b) 排空 in-flight PJob（必须）
    pgrep -f "[z]ima.execution.background_runner" || echo "no inflight"
    有运行中的 CR job 时必须等它结束——systemctl restart 默认 KillMode=control-group，
    会连坐 cgroup 内正在执行的 CR PJob（单轮约 8-10 分钟）。
    轮询直至进程消失（每 30s 一次，超时上限 15 分钟；超时询问用户是否继续）。

(c) 重启 webhook-server
    systemctl --user restart zima-webhook
    验证：is-active == active，且 journalctl --user -u zima-webhook（重启时刻起）
    含 "Connected to smee.io" 和 "Webhook server listening"。
    注：smee DNS 抖动为已知自愈项（重启后 ~10 分钟内恢复），缺失仅作 warning 不算失败。

(d) 重启 daemon（如本机在跑）
    ~/.local/bin/zima daemon status 检查；运行中则记录当前 schedule 名后：
    zima daemon stop && zima daemon start --schedule <schedule>
    验证：zima daemon status 显示 running。
    若 status 显示 not running 但进程存在（游离态），kill PID 后用 start 拉起。

(e) 版本确认
    zima --version == {new_version}，告知用户发版+生效全部完成。
```

### 3.2 错误处理小节补充

- Step 11 各步失败 → 展示错误并停止，不回滚（人工路径：`uv tool install zima-blue-cli==<old>` + 手动重启）
- 排空超时 → 询问用户：继续重启（中断 in-flight）或放弃本轮（服务跑旧版，下次手动）

### 3.3 注意事项小节补充

- webhook 服务形态（systemd user service `zima-webhook.service`）是本机部署事实，非产品默认；非 systemd 部署的机器按实际方式重启
- daemon 的 schedule 名机器相关，从 status / ps 中读取，不硬编码

## 4. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | SKILL.md 含完整 Step 11（a-e 五步） | 自动化验证（static） | grep 断言：uv tool update / pgrep 排空 / systemctl restart zima-webhook / daemon stop+start / zima --version 五要素齐全 | 五要素全部存在，步骤顺序正确 |
| A2 | 错误处理与注意事项同步更新 | 自动化验证（static） | grep 断言"排空超时"与"回滚"路径存在 | 两处均有 |
| U1 | 下次发版真实走一遍 | 用户实测 | 下次 /skill:release 发版观察 Step 11 执行 | 服务自动跑新版，in-flight 未被中断 |

## 5. 实现形态

- 单文件改动：`.pi/skills/release/SKILL.md`
- 不新增代码 / 不新增脚本；worktree 流程照走（纪律），plan 极简
