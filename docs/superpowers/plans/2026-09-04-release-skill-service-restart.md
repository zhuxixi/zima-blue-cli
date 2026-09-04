# Release Skill Service-Restart Step Implementation Plan (issue #222)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.pi/skills/release/SKILL.md` 追加 Step 11「本机服务升级与重启」，把发版后的本机 uv tool 升级 + 排空 in-flight PJob + 重启 webhook/daemon 固化为 skill 步骤。

**Architecture:** 纯文档改动，单文件（`.pi/skills/release/SKILL.md`）。在现有 Step 10（PyPI 验证）之后插入 Step 11，同步补「错误处理」与「注意事项」小节。不加代码、不加脚本、不改 release_helper.py。

**Tech Stack:** Markdown skill 文档；static 验收用 grep 断言。

**Spec:** `docs/superpowers/specs/2026-09-04-release-skill-restart-design.md`（worktree 内）

## Global Constraints

- 只改 `.pi/skills/release/SKILL.md` 一个文件
- Step 11 内容固化 2026-09-04 v0.8.2 发版后实测验证过的操作序列（uv tool update → 排空 → systemctl restart → daemon stop/start → 版本确认）
- daemon schedule 名不硬编码（从 status/ps 读取）
- 排空超时上限 15 分钟，超时询问用户；失败不回滚，人工回滚路径（`uv tool install zima-blue-cli==<old>`）写入文档
- 涉及多行 shell 命令的步骤保持 SKILL.md 现有代码块风格

---

### Task 1: SKILL.md 追加 Step 11 + 补错误处理/注意事项

**Files:**
- Modify: `.pi/skills/release/SKILL.md`（Step 10 末尾与「## 错误处理」之间插入 Step 11；「## 错误处理」「## 注意事项」小节各补条目）

**Interfaces:**
- Consumes: spec §3.1（Step 11 五步文本）、§3.2（错误处理两条）、§3.3（注意事项两条）
- Produces: 无代码接口；验收锚点 = 五个 grep 要素（见 Step 2）

- [ ] **Step 1: 编辑 SKILL.md —— 插入 Step 11**

在「### Step 10: 验证 PyPI 发布」小节末尾（即「成功后告知用户」代码块之后）与「## 错误处理」之间插入以下文本（原样）：

````markdown
### Step 11: 本机服务升级与重启（发版闭环）

PyPI 验证通过后，更新本机安装并重启常驻服务，让新版本立即生效。
仅当发版机运行着 zima 服务时执行；纯 CI / 无本机服务的环境跳过本步。

**(a) 更新本机安装**

```bash
uv tool update zima-blue-cli
```

**(b) 排空 in-flight PJob（必须）**

systemd restart 默认 KillMode=control-group，会连坐 cgroup 内正在执行的
CR PJob（单轮约 8-10 分钟）。重启前必须等运行中的 CR job 结束：

```bash
pgrep -f "zima.execution.background_runner" || echo "no inflight"
```

有输出（存在 in-flight）则每 30s 轮询一次直至进程消失；超时上限 15 分钟。
超时仍忙 → 询问用户：继续重启（会中断该 CR job）或放弃本轮（服务跑旧版，下次手动重启）。

**(c) 重启 webhook-server**

```bash
systemctl --user restart zima-webhook
systemctl --user is-active zima-webhook   # 期望 active
journalctl --user -u zima-webhook --since "<重启时刻>" --no-pager | tail -8
```

验证：日志含 `Connected to smee.io` 与 `Webhook server listening`。
注：smee DNS 抖动为已知自愈项（重启后 ~10 分钟内自动恢复），此时缺
`Connected to smee.io` 仅作 warning，不算失败。

**(d) 重启 daemon（如本机在跑）**

```bash
~/.local/bin/zima daemon status
```

- 显示 running：从输出/`ps` 记录当前 schedule 名，然后

```bash
zima daemon stop && zima daemon start --schedule <schedule>
```

- 显示 not running 但 `ps` 里存在进程（游离态，daemon.pid 丢失）：
  先 `kill <PID>` 再用上面同款 `zima daemon start --schedule <schedule>` 正规拉起。
- 本机未跑 daemon：跳过。

**(e) 版本确认与收尾**

```bash
zima --version   # 期望 == {new_version}
```

全部通过后告知用户：

```
✅ Release v{new_version} 已发布、上线 PyPI，本机服务已升级重启至新版本。
```
````

同时把 Step 10 原有的收尾段：

```
成功后告知用户：

```
✅ Release v{new_version} 已发布并上线 PyPI。
```
```

替换为：

```
成功后进入 Step 11（本机服务升级与重启）。
```

- [ ] **Step 2: static 验收（A1 + A2）**

Run:

```bash
SKILL=.pi/skills/release/SKILL.md
grep -q "Step 11: 本机服务升级与重启" "$SKILL" &&
grep -q "uv tool update zima-blue-cli" "$SKILL" &&
grep -q "zima.execution.background_runner" "$SKILL" &&
grep -q "systemctl --user restart zima-webhook" "$SKILL" &&
grep -q "zima daemon stop && zima daemon start --schedule" "$SKILL" &&
grep -q "zima --version" "$SKILL" &&
grep -q "超时仍忙" "$SKILL" &&
grep -q "uv tool install zima-blue-cli==" "$SKILL" &&
echo "A1+A2 STATIC PASS"
```

Expected: `A1+A2 STATIC PASS`（五要素 + 排空超时路径 + 回滚路径全部存在）

- [ ] **Step 3: 编辑 SKILL.md —— 补「错误处理」与「注意事项」**

「## 错误处理」小节末尾追加：

```markdown
- Step 11 排空超时 → 询问用户继续（中断 in-flight）或放弃本轮
- Step 11 任一步失败 → 展示错误并停止，不自动回滚；人工回滚路径：
  `uv tool install zima-blue-cli==<old> && systemctl --user restart zima-webhook`，
  daemon 同步 stop/start
```

「## 注意事项」小节末尾追加：

```markdown
- Step 11 的 systemd user service（`zima-webhook.service`）形态是本机部署事实，
  非产品默认；非 systemd 部署的机器按实际方式重启
- daemon 的 schedule 名机器相关（如 cosmobo），从 status/ps 读取，不硬编码
```

- [ ] **Step 4: 重跑 static 验收 + 顺序断言（A1 + A2 收口）**

Run: Step 2 的完整命令，另加顺序检查（Step 11 位于 Step 10 之后、错误处理之前）：

```bash
SKILL=.pi/skills/release/SKILL.md
L10=$(grep -n "^### Step 10" "$SKILL" | head -1 | cut -d: -f1)
L11=$(grep -n "^### Step 11" "$SKILL" | head -1 | cut -d: -f1)
LEH=$(grep -n "^## 错误处理" "$SKILL" | head -1 | cut -d: -f1)
[ -n "$L10" ] && [ -n "$L11" ] && [ -n "$LEH" ] && [ "$L10" -lt "$L11" ] && [ "$L11" -lt "$LEH" ] && echo "ORDER PASS"
```

Expected: `A1+A2 STATIC PASS` 且 `ORDER PASS`

- [ ] **Step 5: Commit**

```bash
git add .pi/skills/release/SKILL.md
git commit -m "docs(skill): release skill Step 11 - local service upgrade and restart (#222)"
```

### Task 2: U1 用户实测（post-implementation，不在本 PR 验收）

U1（下次发版真实走一遍 Step 11）为用户实测项，标记 pending，不阻塞本 PR。
PR 描述中注明：U1 于下次发版时验证（观察服务自动跑新版、in-flight 未被中断）。

---

## Self-Review

- **Spec coverage:** A1 → Task 1 Step 2/4（五要素 + 顺序）；A2 → Task 1 Step 2/4（超时路径 + 回滚路径）；U1 → Task 2（post-implementation）。spec §3.1/3.2/3.3 全部落到 Task 1。✅
- **Placeholder scan:** 插入文本为最终内容，无 TBD/TODO。`<schedule>` / `<old>` 为运行时占位符（skill 读者替换），非 plan 占位符。✅
- **Type consistency:** 纯文档改动，无类型接口；验收锚点均为字面量。✅
