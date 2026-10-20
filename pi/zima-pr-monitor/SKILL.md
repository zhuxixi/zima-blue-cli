---
name: zima-pr-monitor
description: Use when monitoring a PR under Zima Blue code review — after creating a PR and adding zima:needs-review, when polling or babysitting CR results, parsing cc-cr-meta/pi-cr-meta review bodies, or deciding if a PR has converged and is mergeable.
---

# Zima PR Monitor

盯一个走 Zima CR 的 PR，直到收敛 + CI 全绿 → 合并。是 github-issue-driven 流程的步 8-9。

> 体系沿革：曾为 cc + kimi 双 bot 交叉验证，kimi 因调用成本过高已移除（单 bot 化）；现主力切换中——cc 版（`cc-cr-meta`）与 pi 版（`pi-cr-meta`，github-code-review-batch 已 pi 适配）共存，同一 PR 由哪个 bot 审，看 review meta 前缀。

## 触发与机制

开 PR + 打标签触发：

```bash
gh pr create --base main --title "..." --body "..."
gh pr edit <N> --add-label zima:needs-review   # webhook 扫到 → 触发该仓库绑定的 CR PJob
```

- webhook 事件驱动触发（smee → webhook-server → PJob），是当前唯一实际运行的路径；Zima daemon ~45min 轮询仅为历史兜底设计（未必启用）。
- 同账号发 review，区分靠 body 的 HTML meta：`<!-- cc-cr-meta {...} -->`（cc 版） / `<!-- pi-cr-meta {...} -->`（pi 版，主力），字段含 `round` / `new_count` / `resolved_count` / `issues[]`（每条 status: resolved/acknowledged/open）。新 pi metadata 还含每条 finding 的 boolean `blocking`，以及 `blocking_open_count` / `blocking_new_count` / advisory counts；`new_count` / `total_issues` 仍是包含 advisory 的事实计数。历史 kimi 版评论（`kimi-cr-meta`）直接忽略；**kimi 未出现 = 正常态，不是未收敛信号**。

## 等待节律（webhook 锚定 + 前台阻塞等待）

**提交 PR + 打 `zima:needs-review` 后，同 turn 立即进入等待，禁止结束 turn。**
zima PJob 是外部进程：turn 一结束 session 不会再被唤醒（`subagent_wait` 只认 pi 自己的 async run，管不到它），后台/异步监听必然错过完成时机——唯一可靠原语是前台阻塞调用。

### 先按本机有没有 zima 运行态选模式

| 本机 `$ZIMA_HOME/history/pjobs` | 模式 | 阻塞命令 |
|---|---|---|
| 存在 | 本地模式 | `wait-cr.py <pjob-code> --since-minutes 10` |
| 不存在（CR 在另一台机器上执行） | `--pr` 模式 | `wait-cr.py --pr 'owner/repo#N' --since-minutes 10` |

**这是启发式，不是判据**：已知本轮 CR 由另一台机器 / 另一个 session 触发时，即使本机有运行态也直接用 `--pr`。选错模式不会等错结果，但会白耗一轮超时。

### 本地模式（CR 与等待会话同机）

1. 确认 spawn：`zima pjob ps`（本地模式专属；webhook 秒级触发，~1min 内应出现本仓库的 CR job；90s 没出现 → 兜底手动 `zima pjob run <code> --set-var=repo=... --set-var=pr_number=...`）。
2. 阻塞等待（helper 只读盯 zima runtime state 文件；终态在 postExec 发完 review 之后才写，等到即「review 已发出」）：

```bash
python3 pi/zima-pr-monitor/scripts/wait-cr.py <pjob-code> --since-minutes 10
```

（脚本路径按仓库根目录解析，需在仓库根 / worktree 根运行。）

3. 多执行流：helper 自动等「所有 running execution」离开 running；退出时打印每个 execution 的 status/duration/returncode/repo#pr 与 log_tail 摘要，按摘要里的 repo#pr 识别无关执行。等完仍按「多执行流陷阱」一节做收敛判定。

### `--pr` 模式（触发机与执行机分离）

```bash
python3 pi/zima-pr-monitor/scripts/wait-cr.py --pr 'owner/repo#N' --since-minutes 10
```

- 收敛信号：目标 head 上出现带 `pi-cr-meta` / `cc-cr-meta` 的 review（`reviews[].commit.oid == headRefOid`），且 `submittedAt` 不早于「等待开始 − `--since-minutes`」。`kimi-cr-meta` 不计（已废弃）。
- 本机没有 zima runtime，因此**没有** spawn 确认、也没有执行状态可见性：等不到时它只能说「超时」，说不了「卡在哪」。确诊仍需去执行机查 `zima pjob ps` / 日志。
- CR 在等待开始前就已结束、且距今超过 `--since-minutes` 时，helper 会把它当旧轮次并等到超时（exit 1）：这时直接 `gh pr view <N> --json reviews` 读结果，或调大 `--since-minutes` 重跑。
- 同一 head 上重打标签（没有 push）时，上一轮的 review 可能仍在窗口内，helper 会立刻返回 0：看 summary 行的 `round=` 是否前进，没前进说明新流还没出结果，别把它当本轮结论。

### helper 退出码与处置

| 码 | 含义 | 处置 |
|---|---|---|
| 0 | 本轮 review 已到（本地模式：执行全部终态） | 进「每轮」决策树 |
| 1 | 超时 | 去执行机查；**不要**据此判定「未触发」 |
| 2 | 本地模式：宽限期内没有执行出现 | 确认 spawn；仍无 → 手动 `zima pjob run` |
| 3 | 本地模式：本机没有 zima 运行态 | 改用 `--pr 'owner/repo#N'` |
| 4 | `--pr` 模式：等待期 head 变更 | 本轮作废，重新打标签触发新一轮 |
| 5 | `--pr` 模式：PR 已合并 / 关闭 | 结束 |
| 6 | `--pr` 模式：启动期 gh 查询失败 | 检查 `gh auth status` / 仓库名后重跑 |
| 64 | 用法错误（两模式都给 / 都不给 / 远程模式带本地参数） | 按提示改参数 |

### 时长预期（两模式通用，决定 bash timeout 上限）

- 首轮全量 ~1200s（实测 10-24min）→ bash timeout 1500s，超时后续等一次 900s；
- 增量轮 ~800s（实测 2-11min）→ bash timeout 1100s；
- PJob 自身 timeout=1800s 是硬上界；helper 默认总上限 2100s，超时退出码 1。

### 等完之后

接「每轮」决策树：本地模式先读 helper 输出的 status/returncode 与 log_tail（含 `<zima-review>` verdict 尾部；stdout_preview 只是输出头部，不含 verdict）；`--pr` 模式读 helper 打印的 summary 行（review id / head / round / blocking counts）。两模式最终都以 `gh pr view <N> --json reviews` 读 pi-cr-meta 为准。

## 每轮

```bash
gh pr view <N> --json state,labels,statusCheckRollup,reviews
```

决策树（**用 state 判终态，不用 label**）：

- `MERGED/CLOSED` → 结束。
- 有 effective blocking 的 open finding → 读 finding → **worktree** 修 → push → `gh pr edit <N> --add-label zima:needs-review`（重打触发下轮）；仅 advisory open findings 不进入 fix 循环。
- 仍 needs-review / CI pending → 等。

## ⚠️ 收敛判定（最易踩坑）

**`blocking_new_count == 0` 仍不单独等于可合并！** 它只计本轮新发现的 blocking findings，不带历史 carried open。真正可合并 = 该 PR 的 CR bot（cc 或 pi，看 meta 前缀）最新 round 同时满足：

- `blocking_new_count == 0`，**且**
- **无 carried actionable open finding**：逐条检查 `issues[]`，不存在未 acknowledged/wontfix、`status: open` 且 effective `blocking=true` 的 finding。

Effective blocking fallback 必须统一：finding 的 `blocking` 是 JSON boolean 时直接使用；旧 metadata 缺少 boolean（或值非法）时由 severity 派生——`low` → false，`medium` / `high` / `critical` → true；severity 缺失或非法按 `medium`，因此 true。旧 metadata 缺少 top-level blocking counts 时，从 `issues[]` 逐条派生：`blocking_open_count` 统计所有 actionable `status: open` findings，`blocking_new_count` 统计其中 `first_round == round` 的 findings；两者都使用相同 effective blocking 规则。全量 `new_count==0` 不是新契约，open low finding 可继续作为 advisory 历史而不阻塞。

另：label 消失 ≠ 审完（bot 发完 review 就移标签，但流程可能还在收尾）→ 看 review meta 确认本轮报告存在。kimi 永远不会出现（已移除），不要等它。CI 必须 `gh pr checks` 全绿（Windows fast job ~24-27min 是瓶颈）。

## ⚠️ 多执行流陷阱（jfox #402 教训：合并后迟到流发现 high bug）

同一 PR 同一 head 可能有多条审查流并行（打标签触发 webhook 流 + 手动 `zima pjob run` 流），**各自独立维护 round 计数**——review 的 round 编号会重复，且内容可能一条收敛、一条发现问题。仅看"最新一条 review"判定收敛会在另一条流迟到时被打爆。

判定与合并纪律：

- **识别多流**：同 head 的 `pi-cr-meta` review 超过一条即视为多流嫌疑——单条流对同一 head 不会发多条 review（batch skill Step 0 同 SHA 直接 `NO_NEW_COMMITS`、不发评论），「超过一条」本身就是充分判据。round 相同为确证；round 不同（流间 round 计数错位）仍需逐条核对 meta 并按「所有流收敛」规则判定，不要因此排除多流。按 `(head_sha, submittedAt)` 排序；最新一条不代表全部。
- **收敛要求所有流**：每条活跃流对当前 head 的 review 都满足 `blocking_new_count == 0` 且无 actionable open blocking finding 才算收敛；每条流都使用上节的 legacy severity fallback。Open advisory findings 不阻塞。**活跃流** = 对当前 head 已发布 review 的流 + 距最后触发 <15min 时可能仍在跑的流。
- **合并前 in-flight 检查（必做）**：① 本地模式专属：`zima pjob ps` 确认无该仓库的 running CR job；`--pr` 模式没有这个可见性，只能靠 ② 的触发时钟推断；② 距最后一次触发（打标签或手动 run）不足 ~15min 时，未出 review 的流可能还在跑——等它出结果再判。**取触发时间**：标签触发用 `gh api repos/{owner}/{repo}/issues/{n}/timeline --paginate --jq '[.[] | select(.event=="labeled" and .label.name=="zima:needs-review")] | last | .label.name + " " + .created_at'` 查最近一次 `zima:needs-review` 打标时间（必须 `--paginate` 翻全部分页——默认只返回最旧 30 条，事件多的 PR 上最近打标会被截断；必须过滤 label 名，否则会混入 needs-fix 等其他打标事件）；手动 run 以自己执行 `zima pjob run` 的时刻为准。
- **触发纪律**：一次修复循环只用一条流——要么纯标签驱动（等 webhook），要么接受"打标签即触发 webhook 流"的事实：手动 run 前打了标签就必须**等两条流都出 review**。不要假设"只看到一条 review"= 只有一条流。（根治需调度器去重，见 zima-blue-cli #181）

## babysit 必带 stuck 检测（否则空转数天）

- 每轮存快照，比对进展（新 review / 新 commit / CI 变化 / label 转换）；有进展清零，无进展 +1。
- 连续 K 轮（~3 轮 / 45-60min）零进展 → **停 + 报警**。
- **label 死状态守卫**：`zima:needs-review` 不在 + 无新 review + state OPEN = "CR 不会被触发"的死状态 → 报"需手动重打标签" + 停。（专防"忘打标签空转两天"旧坑。）

## 合并

CR bot 0 actionable open blocking findings + `blocking_new_count == 0` + CI 全绿 + **多流收敛确认与 in-flight 检查通过**（见上节）→ `gh pr merge <N> --squash --delete-branch`。in-flight 检查按模式分叉：本地模式看 `zima pjob ps`；`--pr` 模式只能看触发时钟（≥15min 无新 review 视为静止）。**档位限定**：授权档位为 `auto` / `design-only` 时，合并前需用户明确许可（两档授权的上限是「可合并判定」）；`stepwise` 档行为不变——收敛 + CI 全绿即合并。Advisory / non-blocking findings 可保持 `status: open`，不影响该判定。

## CR 验证纪律

读 **PR HEAD**（`gh pr diff <N>` / `gh pr view <N> --json`），**不读本地工作区**——工作区可能停在别的分支 → 虚假回归。
