# Spec: pi skill 文档从 daemon 45min 轮询主叙事迁移到 webhook 事件驱动叙事

Issue: #186
日期: 2026-08-21

## 背景

Zima CR 触发机制已以 webhook 事件驱动为主（smee → webhook-server → PJob，本机 8 仓库运行中），daemon 45min 轮询为兜底且实际未运行（无 daemon 进程）。但 `pi/` 目录下 skill 文档仍以 daemon 45min 轮询为主角描述触发与等待节律，导致 agent 按旧节律空等。

## 决策

不改任何运行时代码（daemon_scheduler.py 保留，兜底语义不变），只改 pi skill 文档措辞，使文档描述的触发/等待模型与实际架构一致。

## 改动清单

### 文件 1: `pi/zima-pr-monitor/SKILL.md`（主要）

| 位置 | 现在 | 改为 |
|---|---|---|
| 「触发与机制」触发行（~L21） | "webhook 事件驱动触发（smee → webhook-server → PJob）；Zima daemon ~45min 轮询为备用路径。" | 保留 webhook 主线；备用路径措辞弱化（daemon 未必启用） |
| 「轮询节律」整节（~L24-26） | 以 ~45min cycle 为锚：惰性 30min / 激进 5-10min | 改为 webhook 锚定：打标签后 ~5-10min 内应出 review；超时用 `zima pjob ps` 排查 |
| 「多执行流陷阱」（~L52） | "daemon 45min 轮询为第三路" | 删掉第三路，仅保留 webhook 流 + 手动 run 流两路 |
| 「触发纪律」（~L59） | "要么纯标签驱动（等 webhook/daemon）" | 收敛为 webhook |

### 文件 2: `pi/github-code-review-batch/SKILL.md`（次要）

- L7 / L29：外部调度器措辞 "zima daemon" → "PJob 调度器（daemon 或 webhook-server）"（字面触发短语契约保留）。
- L96：daemon grep Status 行 → 同上措辞。

### 文件 3: `pi/github-code-review-batch/references/flow.md`（次要）

- L400 / L432 / L453："zima daemon" 调度器措辞 → "PJob 调度器（daemon 或 webhook-server）"；`Status:` 行与 `<zima-review>` trailer 契约不变（PJob 无论谁触发都消费）。

### 不改

- `pi/github-issue-driven/SKILL.md`（"轮询"是 agent 自身 `gh pr view` 动作，与 daemon 无关）。
- 运行时代码、README、docs。

## 非目标

- 不删除 daemon_scheduler.py，不改变任何运行时行为。
- 不重写 skill 结构，只做措辞级修正。

## 验证

- `git diff` 仅限上述 3 个文件。
- grep 确认 `pi/` 下不再有以 45min cycle 为等待锚的表述。
