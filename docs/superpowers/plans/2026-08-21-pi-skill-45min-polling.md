# Plan: pi skill 文档 webhook 化（issue #186）

日期: 2026-08-21
Spec: [2026-08-21-pi-skill-45min-polling-design.md](../specs/2026-08-21-pi-skill-45min-polling-design.md)

## 任务

### Task 1: `pi/zima-pr-monitor/SKILL.md`（主要）

- T1.1 「触发与机制」：备用路径措辞弱化——daemon ~45min 轮询注明"未必启用"。
- T1.2 「轮询节律」整节 → 「等待节律」，webhook 锚定（打标签后 ~5-10min 出 review；超 15min 查 `zima pjob ps`）。
- T1.3 「多执行流陷阱」：删 "daemon 45min 轮询为第三路"，只留 webhook 流 + 手动 run 流。
- T1.4 「触发纪律」："等 webhook/daemon" → "等 webhook"。
- T1.5 babysit stuck 检测："~3 轮 / 90min" → 与 webhook 节律一致（~3 轮 / 45-60min）。

### Task 2: `pi/github-code-review-batch/SKILL.md`（次要）

- T2.1 description：`外部调度器（如 zima daemon）` → `PJob 调度器（zima daemon 或 webhook-server）`。
- T2.2 触发短语警告：`调度器（zima daemon）` → 同上。
- T2.3 输出契约末尾：`zima daemon 通过 grep Status: 行` → 同上措辞。

### Task 3: `pi/github-code-review-batch/references/flow.md`（次要）

- T3.1 L400：`供外部调度器（如 zima daemon）` → `供 PJob 调度器（zima daemon 或 webhook-server）`。
- T3.2 L432：`（不变，zima daemon 仍 grep 此行）` → `（不变，PJob 调度器仍 grep 此行）`。
- T3.3 L453：`daemon 的 grep 契约不受影响` → `PJob 调度器的 grep 契约不受影响`。

### Task 4: 验证

- `git diff` 仅含上述 3 个文件 + spec/plan。
- grep 确认 `pi/` 下不再有以 45min cycle 为等待锚的表述（允许"未必启用/兜底设计"类说明）。
- markdown 语法检查（重点表格与代码块完整性）。

## 不做

- 不改运行时代码、README、docs/ 其他文件。
- 不删除 daemon_scheduler.py。
- 不改 github-issue-driven/SKILL.md（agent 自身轮询，与 daemon 无关）。
