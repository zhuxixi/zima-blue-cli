# Spec: zima-pr-monitor 监听机制升级（issue #189）

状态：**approved**（2026-08-22 用户确认设计，实现见 PR #190）· 作者：pi coding agent session（2026-08-22）

## 1. 问题与目标

github-issue-driven 步 9 开 PR + 触发 Zima CR 之后，session 不知道「怎么等、等多久、等到什么」：
后台监听会错过（turn 结束后无事件唤醒 session），前台轮询方式各异且无时长预期。
本 spec 把监听环节升级为：**提交 PR 后自动进入、前台阻塞等到 CR job 全部完成、完成后无缝衔接现有决策树**。

## 2. 约束与事实（调研结论摘要，完整调研见 `~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-189/research/listening-patterns.md`）

- **F1** 完成信号：`~/.zima/history/pjobs/<code>/<eid>.json` 的 `status` 在 postExec（发 review/摘标签）**之后**才写终态 → `status != running` 即「review 已发出」。
- **F2** 唯一可靠原语：前台阻塞 bash（sleep loop）。`subagent_wait` 只管 pi 自己的 async run，管不到外部 zima 进程；结束 turn = 失联。
- **F3** 时长：首轮全量 ~1200s（长尾 24min），增量轮 ~500-800s；PJob timeout=1800s 是硬上界。
- **F4** 触发：webhook 秒级 spawn，打标签 ~1min 内可见新 execution；同 PR 同 head 可能多执行流并存（等待期新 spawn 的也要等）。
- **F5** 范围纪律：只改 `pi/zima-pr-monitor/`（skill + scripts），不动 zima CLI 代码。

## 2.5 基线对齐（2026-08-22 00:22 更新）

另一个 session 已合并 PR #187（issue #186，commit `19d09df`），zima-pr-monitor SKILL.md 现状：
- 触发叙事已 webhook 锚定（daemon 45min 轮询降为历史兜底）；
- 多执行流已删 daemon 第三路（只剩 webhook 流 + 手动 run 流）；
- 「轮询节律」章节已改为「等待节律（webhook 锚定）」：打标签后 ~5-10min 应出 review，超 ~15min → `zima pjob ps` 查状态。

**#187 未覆盖的缺口（#189 的增量）**：
1. 「等待节律」只说了「多久该出结果」，没说 session **怎么等**——前台阻塞原语（防后台监听错过）与可靠完成信号（state 文件）都缺失；
2. 「~5-10min」是单一时长估计，与实测不符：首轮全量 10-24min、增量轮 2-11min，需要分轮次时长模型；
3. 自动进入契约（开 PR 后同 turn 进入监听、禁止结束 turn）没有落在任何文档里。

## 3. 设计

### 3.1 流程契约：自动进入监听（改 github-issue-driven 步 9 + zima-pr-monitor）

开 PR + 打 `zima:needs-review`（或手动 `zima pjob run`）后：

1. **同 turn 内**立即进入监听等待，**禁止结束 turn**（F2）。等待期间不轮询 PR、不做别的；
2. 先确认 job 已 spawn：`zima pjob ps`（webhook 触发，~1min 内出现；90s 不出现 → 兜底手动 `zima pjob run <code> --set-var=...`）；
3. 调 `wait-cr` helper 阻塞等待；
4. 返回后走现有决策树（读 pi-cr-meta、收敛判定、多流检查、修复循环）。
   修复循环的每一轮（重打标签）重复 1-4，同样不结束 turn。

### 3.2 新增 helper：`pi/zima-pr-monitor/scripts/wait-cr.py`

```
usage: wait-cr.py <pjob_code> [--since-minutes <minutes>] [--timeout <seconds>]
```
行为：
- 每 30s 扫 `~/.zima/history/pjobs/<code>/*.json`；
- 活跃集 = `started_at >= since` 且 `status == running` 的 execution；
- **全部**活跃 execution 离开 running（terminal）→ 退出 0；期间新 spawn 的 execution 自动并入活跃集（F4 多流）；
- pid 已死但 status 仍 running（状态未刷新）→ 视为 finished 并在输出中标注 `stale`；
- 总上限 `--timeout`（默认 2100 = PJob 1800 + 300 slack）；超时退出非 0，提示 `zima pjob ps` 人工介入；
- 退出时打印每个 execution：eid / status / duration / returncode / repo#pr / stdout_preview 头部预览 / log_tail
  （state 的 log_path 日志尾部，含 `<zima-review>` verdict 尾部；stdout_preview 是 stdout 头部 500 字符，不含 verdict）。
  最终收敛判定仍以 `gh pr view <N> --json reviews` 读 pi-cr-meta 为准。

调用形态（前台，实证可承受 1200s+）：
- 首轮全量：`bash timeout 1500`（预期 1200 + slack；长尾超时则再续一次 `--since` 缩小后的调用）；
- 增量轮：`bash timeout 1100`（预期 800 + slack）。

### 3.3 时长预期模型（升级 #187 的「等待节律」章节）

| 轮次类型 | 预期 | bash timeout | 兜底 |
|---|---|---|---|
| 首轮全量 | ~1200s（实测范围 10-24min） | 1500s | 超时后续等一次 900s；PJob 自身 1800s 封顶 |
| 增量轮 | ~800s（实测范围 2-11min） | 1100s | 同上 |
| sleep 粒度 | 30s | — | — |

#187 的单一估计「打标签后 ~5-10min 出 review」只适用于增量轮（其数据来自 PR #182 的 R2-R4），首轮全量会到 10-24min——分轮次后不再误导首轮判断。

### 3.4 关键决策表

| 决策点 | 选择 | 理由 |
|---|---|---|
| 完成信号 | state 文件 status | postExec 后写终态（F1），免 PID 管理、免猜 |
| 等待载体 | 前台 bash sleep loop（30s 粒度） | F2 唯一可靠；kill -0 与 gh 轮询作为降级兜底保留 |
| 多执行流 | 等待全部 running→terminal | jfox #402 教训：迟到流会打爆收敛判定 |
| helper 形式 | 仓库内 python 脚本 | 不进 zima CLI（F5）；脚本可单测 |
| 超时策略 | 分档 timeout + 超时可续等 | 首轮长尾 24min 不误杀 |
| 与 #187 的关系 | 基线之上叠加等待原语，不推翻 | #187 已改触发叙事与多流定义，本 spec 只补「怎么等」 |
| zima CLI 新命令 `pjob wait` | **非目标**（本 issue 不做） | skill 侧脚本够用；若实战暴露脆弱性再单开 issue |

### 3.5 非目标

- 不改 zima CLI / webhook / daemon 代码；
- 不解决 #181（调度器侧多流去重）——监听侧按「全等」规避；
- 不做通知推送（飞书等）——session 前台阻塞本身就是结果。

## 4. 落地改动清单

1. `pi/zima-pr-monitor/scripts/wait-cr.py` — 新增（如上述接口）；
2. `pi/zima-pr-monitor/SKILL.md`（基于 #187 之后的最新版）：
   - 「等待节律（webhook 锚定）」章节升级：保留 webhook 锚定，叠加 3.1-3.3 内容（阻塞等待原语、wait-cr 用法、分轮次时长表、禁止结束 turn）；
   - 修正「~5-10min 出 review」为分轮次预期（首轮全量 ~1200s / 增量轮 ~800s）；
   - 决策树前加「等待完成后先读 state stdout_preview + gh pr view」的衔接步骤；
3. `pi/github-issue-driven/SKILL.md` 步 9：明确「开 PR + 打标签后同 turn 进入 zima-pr-monitor 等待，禁止结束 turn」，链接 helper。

## 5. 验证方案（dogfooding）

本 issue 的修复 PR 自身就是首个试验田：走完「开 PR → 打标签 → wait-cr 等待 → 读 review → 判定」全流程（SKILL.md 基线以 #187 后最新版为准，验证的正是 2.5 列出的三个缺口是否被补齐）。
验收标准：
- 首轮等待在 ~20min 内返回且 review 已出现（无「等完才发现没触发」）；
- 多执行流场景（首轮 + 手动 run 并存）能等到全部完成再判定；
- 增量轮（重打标签）等待 ≤15min；
- 全程 session 未结束 turn、无需人工唤醒。
