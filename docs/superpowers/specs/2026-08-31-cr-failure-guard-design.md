# Issue #202：CR 成本优化——单一改动 Spec

- 状态：**用户已批准（2026-08-31）**
- 日期：2026-08-31
- 范围：zima-blue-cli 的 pi CR PJob 启动保护
- 本版设计只包含一个改动：**在启动 pi CR agent 前，对同一 `(pjob, repo, pr_number, head_sha)` 的连续无效执行做失败熔断**。

> 本文是设计 spec，不是实现计划；获得确认后才可进入 worktree 和 `writing-plans`。

## 1. 为什么只改这一项

已经实证的成本浪费中，最直接的是“失败重试空烧”：2026-08-29 至 08-30 的 incident window 里，pi-agent-board PR #43 在同一目标上连续产生约 13 秒、736 秒、466 秒三次无有效 review 的失败，随后又继续执行了两轮。这个模式说明现有保护并不能稳定阻止同一目标反复消耗付费模型。

目前其他候选方向（模型分级、PR profile、usage 采集）都有收益，但都要求更多配置、观测和对照评估；如果先混在一起实现，失败回退和质量风险难归因。因此首版只做 FailureGuard，先消除已经明确的浪费来源。

## 2. 目标

1. 对同一 `(pjob, repo, pr_number, head_sha)` 目标，连续两次“无有效 review 产出”的执行后进入 cooldown；冷却期内不再启动 pi agent。
2. 冷却命中返回 `SKIPPED`，不调用模型、不执行 postExec 标签动作，且能清楚看到到期时间与下一次允许执行时间。
3. 新 head 使用独立的失败预算；有效 review（包括 `NEEDS_FIX`）不能计入失败，有效 review 后要清掉该目标的失败状态。
4. 所有行为可解释、可测试、可关闭；默认保护有效，显式人工突破必须单独选择并留下日志。

## 3. 非目标

本版 spec 明确不做以下事项：

- 不做模型分级或按 agent 职责切分 flash/pro；
- 不新增 `full/standard/light` 等 PR profile；
- 不改 `pi/github-code-review-batch` 的 checker 数量、Round-1/Round-N 审查流程、prompt 或 `pi-cr-meta` finding 结构；
- 不采集或计费 token usage；
- 不改变 `Status:`、`Verdict:`、`<zima-review>` 或 ReviewParser 的文本契约；
- 不处理 #201 的 E2BIG 根治方案；但该类启动错误应按本 spec 计为无效失败，避免反复空烧。

## 4. 当前基线与问题

- `ActionsRunner._select_pr()` 对轮询路径已有 90 分钟 failed skip-set，但 pinned webhook/manual path 不经过该选择器，不能覆盖本 issue 的连续失败场景。
- `ExecutionHistory.find_recent_duplicate()` 已经存在共享 state 与 `(repo, pr_number, head_sha)` 的判定基础，但它是“重复审查去重”，不是“连续失败熔断”。
- pi 型 agent 正常结束通常 returncode=0，因此不能简单用“非零退出”判断是否需要熔断；必须区分“有效 review 结果”和“执行无效”。

## 5. 设计：FailureGuard

### 5.1 判定规则

把一次执行结果分为两类：

- **有效 review**：有明确 verdict/status 输出（例如 `PASS`、`NEEDS_FIX`、`NO_NEW_COMMITS`），或有可验证的 `pi-cr-meta`/`zima-review` 结果；
- **无效失败**：启动错误、timeout、进程异常终止、或 stdout 没有可证明的有效 review 产出。

默认把以下状态视为“计入失败 streak”：

- pi 未启动或启动失败（如 FileNotFoundError、E2BIG、配置/auth 错误）；
- timeout、被外部终止、崩溃；
- 进程运行但没有产生有效 review 输出；
- postExec 的动作错误不改变“有效 review”的判定，但保留 action error；如果有效 review 已经产出，则不把该次执行计入 failure streak。

默认不计入：

- 没有扫描到满足标签的 PR、重复执行 dedup、skill 合法 skip；
- `NEEDS_FIX`、`PASS`、`NO_NEW_COMMITS`；
- 尚未产生付费模型调用的普通 `SKIPPED`。

### 5.2 状态文件

每个目标使用独立 JSON 记录，放在 zima 的共享 state 目录（建议 `~/.zima/state/failure-guard/<safe-key>.json`；最终以实现时现有 `ExecutionHistory`/`get_zima_home()` 目录规范为准）：

```json
{
  "target": {
    "pjob": "zima-pi-cr-job",
    "repo": "owner/repo",
    "pr_number": "43",
    "head_sha": "..."
  },
  "failure_streak": 2,
  "last_failure_at": "2026-08-30T03:04:58Z",
  "cooldown_until": "2026-08-30T04:04:58Z",
  "last_failure_kind": "process_exit",
  "last_execution_id": "a51d14cf"
}
```

字段要求：

- `repo` 和 `pr_number` 使用与现有 scan/pinned path 相同的 normalization；
- `head_sha` 已知时使用小写规范化后的值；未知时仍保护该目标，但不得把两个已知不同的 head 合并；
- `failure_streak` 只表示当前 head 的连续无效失败次数；
- 状态必须原子写，避免两个并发 execution 同时读到旧状态后放行；
- 文件损坏或字段非法时 fail closed，记录 `guard_error` 并要求人工处理，不能静默重置为 0。

### 5.3 冷却与清除

- 默认 `failure_threshold=2`、`cooldown_minutes=60`；
- 达到阈值的执行结束后写入 `cooldown_until = last_failure_at + cooldown_minutes`；
- cooldown 内的下一次执行在启动 agent 前直接 `SKIPPED`；
- 冷却到期后允许下一次尝试；若这次仍是无效失败，则再次累加并延长 cooldown；
- 一旦产生有效 review（包括 `NEEDS_FIX`），删除该目标的失败记录，或写入清零状态；下一次同 head 从 0 开始。

### 5.4 人工突破

`--dedup-off` 只表示强制重复审查，不表示突破失败熔断。

本设计需要一个独立、显式的人工开关（建议 CLI/PJob 参数为 `--failure-guard-off`，内部字段保持中性命名，如 `failureGuardOff`），默认关闭。开启时：

- 不读取 cooldown；
- 执行仍记录结果；
- 若继续失败，仍更新 streak；
- 日志/state 必须写明这是 operator override。

## 6. 集成点与可测性拆分

### 6.1 集成点

以 `zima/execution` 为唯一代码层：

1. **启动前检查**：executor 在完成 preExec 并得到 `repo`、`pr_number`、`head_sha` 后，但在调用 pi agent 前检查 guard；
2. **结束后更新**：executor/background runner 在确定执行结果后，按“有效 review / 无效失败”写入 guard；
3. **可观测输出**：guard 的命中、记录、清除、错误都写入日志与 runtime state 的非敏感字段。

不从 skill 内部实现 guard。skill 启动后才看到具体执行，无法在启动前阻止一次付费 PJob。

### 6.2 拆分边界

为实现和测试分离，代码应按以下边界拆分：

- `normalize_failure_target(...)`：纯函数，规范化 repo/pr/head；
- `classify_execution_result(result, stdout_preview) -> GuardOutcome`：纯函数，区分有效 review 与无效失败；
- `FailureGuardState`：状态 dataclass/dict 的 schema 和默认值；
- `FailureGuardStore`：负责原子读、写、更新；不决定业务规则；
- `FailureGuard`：组合 store + policy，提供 `should_skip(target, now)` 与 `record_result(target, outcome, now)`；
- executor 只负责接线与日志，不把 cooldown 计算散落在执行流程里。

测试边界：

- 纯规则（阈值、到期、清零、新 head 隔离、无效配置）全部 unit；
- 状态读写的原子性、损坏处理、并发竞争用带临时目录的 unit/integration；
- executor 的“启动前不调用 pi”和“结束后正确写入”用 fake agent/integration 验证；
- 真实 webhook/CR 链路只作为用户实测，不让测试依赖 GitHub 或 DeepSeek。

## 7. 兼容性

- 不改变 PJob YAML 的现有结构；如果没有新增配置，使用默认 guard 行为；
- 不改变 `pi-cr-meta`、`<zima-review>`、`Status:` 或 review 文本输出；
- cooldown 命中不执行 postExec，不改变 PR 标签；
- 失效时优先 fail closed：无法证明可以安全启动时，不要自动启动可能重复付费的执行；
- 非 CR PJob 也应可复用同一 guard，但本版验收只要求 pi CR 链路。

## 8. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|---|---|---|---|---|
| A1 | 目标规范化 | 自动化验证（unit） | `uv run pytest tests/unit/test_failure_guard.py -q` | repo/pr/head 大小写、别名、缺失值按规则规范化；不同已知 head 不合并 |
| A2 | 有效/无效结果分类 | 自动化验证（unit） | 同上 | `NEEDS_FIX`/`PASS` 不计失败；启动错误、timeout、无有效 review 输出计失败 |
| A3 | streak/cooldown 规则 | 自动化验证（unit） | 同上 | 达到阈值写 cooldown；到期允许重试；有效 review 清零；非法配置回退默认值 |
| A4 | 状态持久化与并发 | 自动化验证（unit/integration） | 临时目录 + 并发/损坏用例 | 原子写；损坏 fail closed；并发更新不丢计数 |
| A5 | executor 启动前拦截 | 自动化验证（integration） | fake pi + pinned target 测试 | cooldown 内不启动 pi、不跑 postExec，输出含到期时间与原因 |
| A6 | executor 结束后更新 | 自动化验证（integration） | fake pi 分别模拟有效/无效结果 | 无效结果增加 streak；有效 review 清零；新 head 独立 |
| A7 | 人工突破开关 | 自动化验证（integration） | CLI/PJob override 用例 | `--dedup-off` 不绕过 guard；`--failure-guard-off` 绕过且留痕 |
| A8 | 兼容性回归 | 自动化验证（integration） | 现有 pjob lifecycle、CR contracts 测试 | 不带 guard 配置的旧执行路径仍正常，Status/XML 契约不变 |
| U1 | 真实失败场景 | 用户实测 | 在测试 PR/head 上制造两次无有效 review 的失败，观察第三次被跳过；再推新 head 验证可执行 | 第三次不启动 pi、不改标签；新 head 恢复；日志/state 清楚说明原因 |

## 9. 预期收益与限制

- 在 #43 类场景中，第三次及之后的重复无效付费执行应被直接阻止；
- 该改动不会提高或降低单次有效审查的质量，只消除无效重试的现金消耗；
- 由于当前没有 token/cost 落盘，预期节省只能按被阻止的执行数量与预估单次成本计算；usage 可观测性保留给后续独立 issue；
- 它不能解决“文档类 PR 满配”或“模型分级”，这些必须在后续单独设计和验证。

## 10. 待确认

1. 是否确认本版只做“启动前失败熔断”，暂不做模型分级、PR profile、usage 采集？推荐确认。
2. 是否接受默认 `failure_threshold=2`、`cooldown_minutes=60`？推荐接受，兼顾瞬时空烧与连续失败止损。
3. 是否接受独立的 `--failure-guard-off` 人工突破开关，且不允许 `--dedup-off` 顺带绕过？推荐接受。

确认后下一步才进入 worktree、提交 spec，并按 `writing-plans` 编写可追溯 A1–U1 的 implementation plan。