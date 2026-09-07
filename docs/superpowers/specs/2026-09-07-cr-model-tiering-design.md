# Issue #224：cr-batch 模型分档落地（PI_CR_FAST_MODEL / PI_CR_STRONG_MODEL 环境变量注入）— 设计 Spec

- 状态：**修订版，待用户批准**
- 日期：2026-09-07
- 范围：zima-blue-cli 仓内 `pi/github-code-review-batch` skill 包（references 文档 + 契约测试）
- 上游：#212 优化点 2（tracking issue）
- 关联：#170（模型分档文档建议）、#207/#216（modelScope 冲突与文档修复）

> 本文是设计 spec，不是实现计划；获得确认后才可进入 worktree 和 `writing-plans`。

## 1. 背景与问题

flow.md Step 4 的主派发示例在 #216 之后默认不传 `model`，审查 subagent 沿用 Pi 的正常 model resolution chain。结果是规范 checker、bug scanner、finding validator、逻辑分析和增量修复对比都使用同一模型档位，无法针对机械职责降低额度消耗。

CR provider 已从 deepseek 按量切到 zai/ollama plan，优化目标从「省现金」变为「省额度、防 5 小时窗口被打爆」。#170 只完成了模型分档建议；#207 又证明把具体模型名硬编码进 skill 会与用户的 `modelScope` 白名单冲突，#216 已移除硬编码建议。

本 issue 不把具体模型名重新写回 skill，而是增加两个部署侧环境变量：

- `PI_CR_FAST_MODEL`：机械职责使用的模型选择器；
- `PI_CR_STRONG_MODEL`：逻辑/修复对比职责使用的模型选择器。

**重要边界**：当前 skill 是 Markdown 流程规范，不是实际的 subagent runtime。父 Pi agent 负责读取环境变量、调用当前 `subagent({action:"models"})` 获取 registry、读取有效 modelScope 并生成派发项。因此本 spec 不宣称 Markdown 契约能够强制父 agent 的每一步执行，也不把“省略 `model`”夸大为任何环境下都保证 child 启动成功。

**可验证的 fail-safe 定义**：环境变量候选值只要无法同时通过格式、当前 registry 和有效 modelScope 的确认，父 agent 就不得把该候选值作为显式 `model` 传给 child。这样可以避免由本次环境变量直接触发显式 modelScope 错误。只要现有的 inherited resolution chain 本身有效，child 继续沿用该链路运行；如果现有继承链本来就违反 `strict` modelScope，则属于既有部署配置错误，不由本 issue 修复。

**issue 描述勘误**：issue 正文引用 `docs/superpowers/specs/2026-08-31-cr-failure-guard-design.md` §4.4，但该文档没有 §4.4，且其 §3 明确把模型分级列为非目标。本 spec 的依据是本次调研、#216 的已落地 modelScope 规则以及当前 pi-subagents 的实际模型解析行为。

## 2. 目标

1. 定义 `PI_CR_FAST_MODEL` / `PI_CR_STRONG_MODEL` 两个环境变量，值为当前 Pi registry 中可确认的完整 `provider/id` 选择器；可选保留 Pi 支持的已知 thinking 后缀，但本 issue 不新增独立 thinking 配置。
2. 覆盖全流程派发点：Step 4 checker/scanner/logic-analyzer、Step 5 issue-validator、Round-2 delta-reviewer 和 Δ2a scanner/analyzer。
3. 对每个档位执行统一的父 agent preflight：读取环境变量 → 校验格式 → registry 可用性确认 → 有效 modelScope 确认；任何一步无法确认时省略该档的 `model` 属性。
4. fast / strong 两档独立解析、独立 fallback；只配置一档不会影响另一档。
5. 正常未配置状态保持静默；只有“用户配置了候选值但该候选值没有生效”时，通过固定格式的状态报告 `Note:` 披露 fallback 原因。
6. 通过契约测试锁定模型来源、解析顺序、档位映射、fallback 语义和既有 #216 文档约束。

## 3. 非目标与保证边界

- **不新增 zima 或 pi-subagents 运行时代码**：本 issue 修改 skill 文档和契约测试；模型 preflight 由父 Pi agent 按文档执行。
- **不改动 zima executor / PJob / EnvConfig**：环境变量由用户通过现有部署环境或 CR agent 的 env 配置提供。
- **不保证 Markdown 流程对父 agent 的执行具有运行时强制性**：契约测试只能验证文档，没有办法静态证明父 agent 没有忘记读取变量或错误生成派发项。
- **不把 `provider/id` 外形当作模型可用性证明**：候选值还必须出现在当前 `subagent({action:"models"})` registry 中。
- **不把省略 `model` 当作无条件启动保证**：省略后由 Pi 执行正常 resolution chain；如果该链路最终得到的 inherited/default/agent override 模型本身不满足 `strict` modelScope，child 仍可能被 Pi 拒绝，这种既有配置错误不在本 issue 范围。
- **不改变 Pi 的 resolution chain**：不传 per-run `model` 只表示不覆盖现有链路，不保证最终模型一定等于父 session 模型。
- **不新增独立 thinking 档位变量**：如果环境变量带 Pi 已知 thinking 后缀，后缀只作为用户提供的 selector 透传；本 issue 不负责选择、验证或改变 thinking policy。
- **不给 summarizer 建立 subagent 派发点**：Step 3 summarizer 当前由 parent 直接生成；#212 优化点 5 暂缓。
- **不改 cc 版 skill**：只改本仓 `pi/` 包。
- **不新增 `profile_fallback` 状态字段**：Pi 工具没有该参数，状态报告 renderer 也不新增 schema；它在本 spec 中是父 agent 的临时决策状态，最终只通过固定 `Note:` 文本披露。
- **不动 `Status` / `Verdict` / `<zima-review>` 契约**：模型 fallback note 是附加说明，不改变调度器的三态和 XML trailer。

## 4. 总体设计

### 4.1 改动面

| 改动点 | 文件 | 性质 |
|---|---|---|
| Step 4 模型 preflight、派发示例和档位说明 | `pi/github-code-review-batch/references/flow.md` | 将 #216 的可选自选模型指导改为环境变量候选 + preflight + 条件注入 |
| Step 5 validator 派发 | `pi/github-code-review-batch/references/flow.md` | 标明 validator 使用 fast profile，并复用本轮 preflight 结果 |
| Step 10 fallback 披露 | `pi/github-code-review-batch/references/flow.md` | 定义何时向 `render_status_report.py` 传 `note`，以及固定 note 文案 |
| Round-2 派发 | `pi/github-code-review-batch/references/delta-review.md` | delta-reviewer/Δ2a 各自使用 strong/fast profile，复用本轮结果 |
| 档位和 resolution chain 摘要 | `pi/github-code-review-batch/references/subagent-prompts.md` | 指向 flow.md 的单一事实源，不重复维护完整规则 |
| 边界行为 | `pi/github-code-review-batch/references/edge-cases.md` | 记录 unset、invalid、registry-unavailable、scope-unverified/rejected 等行为 |
| 契约测试 | `tests/unit/test_cr_batch_contracts.py` | 新增 `TestModelTieringDocs`，并改写与 #216 冲突的旧断言 |

本 issue 不新增 `resolve_model_profile.py`。原因是当前 skill 文档层没有直接获得 Pi registry 和有效配置快照的 runtime API；父 agent 必须先调用 Pi 的 `subagent({action:"models"})`，再结合当前进程实际加载的 settings 判断。把 shell 脚本伪装成完整 resolver 反而会制造“脚本已经能证明运行时安全”的错误保证。

### 4.2 每轮模型 preflight（父 agent 执行一次、该轮复用）

父 agent 在本轮首次派发 subagent 前执行一次 preflight。首轮在 Step 4 前执行；增量轮在进入 `delta-review.md` 前执行。Step 4、Step 5 和 Round-2 的所有派发项复用同一个结果，不在每个 child 前重复解析。

对 `fast` 和 `strong` 两个 profile 分别执行以下过程：

```text
输入：PI_CR_FAST_MODEL 或 PI_CR_STRONG_MODEL
输出：disabled | enabled(model_selector) | fallback(reason)

1. 读取并 trim 环境变量
   - 空字符串或仅空白：disabled（该 profile 未启用，不记 fallback note）
   - 非空：进入下一步

2. 校验 selector 外形
   - 必须是完整 provider/id 形态
   - 不得包含换行、控制字符或未闭合引号等不能安全成为 JS 字符串的内容
   - 可选的 thinking 后缀只能是 Pi 已知后缀（off/minimal/low/medium/high/xhigh/max）
   - 失败：fallback(reason=invalid)

3. 查询当前 Pi registry
   - 父 agent 调用 subagent({action:"models"})
   - 去掉已知 thinking 后缀后，候选 base selector 必须能在当前 registry 中确认
   - 只使用 registry 确认过的完整 provider/id，不按 bare id 猜测，不把“看起来像 provider/id”当作存在证明
   - registry 查询失败、候选不存在或无法唯一确认：fallback(reason=registry-unavailable)

4. 检查当前有效 modelScope
   - 读取当前 Pi 进程实际生效的 settings，而不是只看 enabledModels
   - 如果项目级 .pi/settings.json 被当前进程信任并加载，它整体替换用户级同名 modelScope；无法判断哪份配置有效时，按 scope-unverified 处理
   - 本流程所有 child 的 agent 名都是 reviewer；全局 modelScope 和
     modelScope.agents.reviewer.allow 中所有“已启用的限制规则”都必须通过
   - allow 按 resolved provider/id 做 glob 匹配；匹配前剥离已知 thinking 后缀
   - modelScope 缺失，或有效配置没有启用任何限制（例如 enforce=false）：视为无范围限制，继续注入
   - 已启用限制且候选不匹配：fallback(reason=scope-rejected)
   - modelScope 存在但无法可靠读取、解析或判断有效规则：fallback(reason=scope-unverified)

5. 生成派发覆盖
   - enabled：只把已经确认的完整 selector 安全写入该 profile 对应派发项的 model 属性
   - fallback/disabled：派发项完全省略 model 属性，不写空字符串、null 或未经确认的候选值
```

**关于 modelScope 与 `strict`**：环境变量候选一旦作为派发项的 `model` 传入，就是 explicit model。它必须在 preflight 阶段通过所有有效 allowlist；`strict` 不会把一个已通过 allowlist 的 explicit 候选变成失败。fallback 时省略 `model` 后，Pi 仍按 inherited/default/agent override/parent resolution chain 解析；`strict` 对该既有链路的检查继续由 Pi 负责，本 issue 不声称能够修复链路自身的越界配置。

**关于无 modelScope**：没有有效 modelScope 不代表候选模型非法，而是表示当前没有 modelScope 范围限制。候选仍必须先通过 registry 确认；如果 settings 文件存在但无法确定其是否生效，则不能把“不确定”误判成“没有限制”，必须 fallback。

**关于安全写入**：环境变量只是候选输入，不能直接拼接进 workflowScript。父 agent 应从 registry 确认结果中复制 canonical provider/id，并以安全的 JS/JSON 字符串字面量生成派发项；fallback 时省略整个属性。这样可以避免引号、换行和任意 shell 内容进入脚本。

### 4.3 档位映射

| 派发点 | 位置 | profile |
|---|---|---|
| claude-checker ×2、agents-checker、bug-scanner | flow.md Step 4 | `PI_CR_FAST_MODEL` |
| logic-analyzer | flow.md Step 4 | `PI_CR_STRONG_MODEL` |
| issue-validator ×N | flow.md Step 5 | `PI_CR_FAST_MODEL` |
| delta-reviewer | delta-review.md Round-2 | `PI_CR_STRONG_MODEL` |
| Δ2a bug-scanner | delta-review.md Round-2 | `PI_CR_FAST_MODEL` |
| Δ2a logic-analyzer | delta-review.md Round-2 | `PI_CR_STRONG_MODEL` |

`summarizer` 不在表中，因为它当前由 parent 直接执行。logic-analyzer 保守归 strong：虽然 prompt 要求“仅关注被修改代码”，但它承担逻辑/安全缺陷召回；delta-reviewer 需要连续对比旧 finding 的修复声明与代码事实，#170 明确提示 flash 可能漏判。部署时两个变量可以填同一个模型，等效为单档；映射不因此改变。

### 4.4 fallback 语义与披露

父 agent 在内存中维护每档一个临时 profile 状态：

```text
state = disabled | enabled | fallback
reason = unset | invalid | registry-unavailable | scope-unverified | scope-rejected
```

`profile_fallback=true` 只表示某个**已配置的非空候选**经过 preflight 后没有生效；它不是 subagent 工具参数，也不是持久化状态字段。

| 场景 | profile 状态 | 状态报告 |
|---|---|---|
| 环境变量未设置或为空 | disabled | 静默，不记 fallback |
| 环境变量已设置且 registry/scope 均通过 | enabled | 静默 |
| 非空候选格式非法 | fallback | 披露 `model profile fallback: <tier>=resolution-chain (<reason>)` |
| 非空候选不在当前 registry | fallback | 披露 `registry-unavailable` |
| 非空候选超出有效 allowlist | fallback | 披露 `scope-rejected` |
| modelScope 存在但无法可靠确认 | fallback | 披露 `scope-unverified` |

同一轮如果两档都 fallback，合并为一条 note；未配置的档不出现在 note 中。例如：

```text
Note: model profile fallback: fast=resolution-chain (invalid); strong=resolution-chain (scope-rejected)
```

其中 `resolution-chain` 只表示派发项省略了 per-run `model` 属性，不表示最终模型一定是父 session 模型。

Step 10 调用 `render_status_report.py` 时，只有存在至少一个 `fallback` profile 才传入该 note。正常 enabled/disabled 组合不传模型 note；允许同时存在与模型无关的 `Diff truncated` / `Coverage` 说明。

这样，“未启用功能的存量用户”与“用户配置了但配置没有生效”被明确区分，避免每轮报告持续出现无意义的 fallback 噪音。

### 4.5 派发示例形态

示例必须表达“enabled 时有 `model` 属性、disabled/fallback 时省略整个属性”，不能用 `model: null` 或 `model: ""` 伪装省略：

```js
// Parent resolves each profile before building this script.
// Enabled:  FAST_OVERRIDE = { model: "<canonical fast provider/id>" }
// Fallback: FAST_OVERRIDE = {}
// Enabled:  STRONG_OVERRIDE = { model: "<canonical strong provider/id>" }
// Fallback: STRONG_OVERRIDE = {}
await runs.all([
  { key: "claude-checker-1", agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "..." },
  { key: "claude-checker-2", agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "..." },
  { key: "agents-checker",   agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "..." },
  { key: "bug-scanner",      agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "..." },
  { key: "logic-analyzer",   agent: "reviewer", context: "fresh", ...STRONG_OVERRIDE, task: "..." },
])
```

`<canonical ...>` 仅是文档占位符，实际运行时必须替换为 preflight 从当前 registry 确认的安全字面量；它不是可直接传给 subagent 的模型值。#225 若先合并 checker，后落地者按实际 agent 数量更新示例；契约测试不锁 checker 数量和 key 名，只锁 profile 归属与条件省略语义。

## 5. 组件设计

### 5.1 flow.md

- Step 4 的旧“父 agent 自选模型（可选）”段改为 §4.2 的标准 preflight。
- 保留 `subagent({action:"models"})`，但用途改为：确认环境变量候选的当前 registry 可用性，而不是让父 agent 自行猜模型名。
- 保留 #216 关于 effective modelScope 的语义：`enforce` / `strict`、全局与 reviewer 级 allow、项目级替换、thinking 后缀匹配规则、`enabledModels` 与 modelScope 的区别。
- 明确没有 modelScope 时表示“没有范围限制”，但 registry 确认仍然必需。
- Step 4 派发示例使用 `FAST_OVERRIDE` / `STRONG_OVERRIDE` 的条件 spread；fallback 时不出现 `model` 属性。
- Step 5 明确 issue-validator 使用 fast profile，并复用本轮 preflight 结果。
- Step 10 增加 note 规则：只在已配置 profile fallback 时传 `note`；note 固定为单行、合并两档 reason，不影响其他 coverage note。

### 5.2 delta-review.md

- Step Δ2 的 delta-reviewer 使用 strong profile。
- Step Δ2a 的 bug-scanner 使用 fast profile，logic-analyzer 使用 strong profile。
- 首轮入口在进入 Step 4 前执行一次 preflight，Step 4 与 Step 5 的所有 child 复用结果；首轮没有 Round-2 派发。
- 增量轮入口在进入 delta-review 前执行一次 preflight，delta-reviewer 与 Δ2a child 复用结果；增量轮不重复执行首轮 Step 4/5。
- 不因“这是增量轮”而重新读取或猜测另一套模型；模型 profile 只由本轮入口结果决定。

### 5.3 subagent-prompts.md

在 header 的 resolution-chain 说明后增加一条单一事实源说明：模型 profile 的环境变量、preflight、档位映射和 fallback note 以 `flow.md` 为准；本文件只描述各 agent 的任务和输出 schema，不重复维护模型选择规则。

### 5.4 edge-cases.md

新增以下边界条目：

- 两个环境变量都未设置：两个 profile 均 disabled，保持现有派发行为，报告不出现模型 fallback note。
- 只设置一个变量：只解析对应 profile；另一 profile 继续沿用 resolution chain且不记 fallback。
- 空白值：按 unset 处理，不记 fallback。
- 非空但格式非法：对应 profile fallback，省略 `model`，note 记录 `tier=resolution-chain (invalid)`。
- 格式正确但 registry 不存在/查询失败/无法唯一确认：对应 profile fallback，note 记录 `tier=resolution-chain (registry-unavailable)`。
- registry 存在但有效 modelScope 不允许：对应 profile fallback，note 记录 `tier=resolution-chain (scope-rejected)`。
- modelScope 文件存在但有效配置无法判断：对应 profile fallback，note 记录 `tier=resolution-chain (scope-unverified)`，不能按“无 modelScope”处理。
- 没有有效 modelScope 或限制未启用：不构成 scope 拒绝；候选仍需通过 registry。
- 两变量配置相同 selector：合法，两个 profile 独立 enabled，等效单档。
- fallback 后的 inherited/default/agent override 模型：由 Pi 的正常 resolution chain 解析；本 issue 不保证它一定等于父 session 模型，也不修复该链路已有的 strict scope 冲突。
- thinking 后缀：只接受 Pi 已知后缀；匹配 registry 和 allowlist 时剥离后缀，派发时保留用户确认过的 selector；本 issue 不新增 thinking policy。
- checker 合并后：#225 改变 checker 数量不改变 checker 的 fast profile 归属。

### 5.5 契约测试（`TestModelTieringDocs`）

测试以局部章节/代码块为边界，不靠全文件任意 substring 判断映射。需要新增或改写以下契约：

| 断言 | 内容 |
|---|---|
| 变量名 | `PI_CR_FAST_MODEL` / `PI_CR_STRONG_MODEL` 精确出现，且没有写入具体模型 ID |
| registry 守门 | 文档要求调用 `subagent({action:"models"})`，并明确 provider/id 外形不等于 registry 可用性 |
| scope 守门 | 文档包含 effective modelScope、reviewer 级 allow、项目级替换、`enabledModels` 区别和“无 modelScope = 无范围限制” |
| 守门顺序 | 格式 → registry → modelScope → 条件注入/省略，顺序在同一 preflight 章节内可验证 |
| fail-safe 边界 | 文档要求 fallback 时省略整个 `model` 属性，不写空字符串/null/未经确认候选；同时不宣称 inherited strict 冲突可被本 issue 修复 |
| 档位映射 | checker/scanner/validator → FAST；logic-analyzer/delta-reviewer → STRONG；Δ2a 两者分别成对出现 |
| 轮次复用 | 首轮或增量轮入口只解析一次，后续派发复用结果 |
| fallback 披露 | unset 静默；已配置但失败才披露；note 固定为 `tier=resolution-chain (reason)` 格式并允许合并两档 reason |
| note 接线 | Step 10 只在存在 profile fallback 时传模型 note，同时允许 coverage note 独立存在 |
| selector 安全性 | 文档要求 trim、拒绝控制字符、使用 registry 确认的 canonical provider/id、安全生成字符串字面量 |
| #216 回归 | 保留 modelScope 层级、`enforce`/`strict`、后缀剥离和 `enabledModels` 非 allowlist 等既有契约 |
| 旧测试迁移 | 删除/改写 `test_step4_example_has_no_model_field` 这条“代码块完全不能有 model”的旧断言；改为验证 enabled/fallback 两种形态及无硬编码模型名 |

自动化测试仍是纯文本契约测试，无副作用。可测性边界明确为：

- `test_preflight_order_and_registry_guard`：只验证文档是否规定格式、registry、scope 的顺序；
- `test_model_tier_mapping`：只验证每个职责在对应局部章节绑定到正确环境变量；
- `test_fallback_omits_model_property`：只验证省略整个属性而非空值/null；
- `test_fallback_note_semantics`：只验证 unset 静默、configured failure 披露和 note 格式；
- `test_resolution_chain_and_strict_boundary`：只验证文档没有把 fallback 误写成“必然继承父模型”或“修复 strict 越界”；
- existing `TestModelDispatchDocs` cases：保留可兼容的 #216 规则，改写与条件注入冲突的断言。

## 6. 兼容性

- **不设置环境变量**：两个 profile 均 disabled；派发继续不传 per-run `model`，报告不增加模型 fallback note，保持现有行为。
- **设置合法且可用的变量**：通过 registry 和有效 modelScope 后，只有对应职责的派发项携带 explicit `model`；另一档独立处理。
- **设置非法变量**：该档不显式传候选值，而是沿用正常 resolution chain；只要该既有链路有效，CR 继续运行并在报告中披露 fallback reason。
- **modelScope 缺失**：不执行 allowlist 拒绝，但 registry 检查仍保留。
- **#216 文档契约**：不重新引入具体模型名；`enabledModels` 仍不是 subagent modelScope allowlist；显式候选必须使用完整 provider/id。
- **#225 串行关系**：两项都修改 Step 4 派发段，禁止并行；本 spec 不锁 checker 数量和 key 名，后落地的 PR 适配实际基线。
- **zima 调度器**：Status/Verdict/XML trailer 不变；note 只作为附加人类可读说明，coverage note 与模型 note 可同时存在。

## 7. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|---|---|---|---|---|
| A1 | 模型 preflight 顺序与 registry 守门 | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_contracts.py -k tiering` | 格式 → registry → modelScope → 注入/省略契约通过 |
| A2 | 全流程档位映射 | 自动化验证（unit） | 同上 | Step 4、Step 5、Round-2/Δ2a 映射完整且无错配 |
| A3 | fallback 与 note 语义 | 自动化验证（unit） | 同上 | unset 静默；已配置但失败披露固定 reason；两档可合并 |
| A4 | #216 文档无回归 | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_contracts.py` | 既有 modelScope、registry、enabledModels、无硬编码模型约束通过 |
| A5 | 文档格式与全套回归 | 自动化验证（static/unit） | `uv run ruff check zima/ tests/`；`uv run black --check zima/ tests/ --line-length 100`；`uv run pytest` | lint、format、全套测试通过 |
| U1a | 合法 profile 的首轮派发 | 用户实测 | 配置两个已在当前 registry 且通过有效 modelScope 的 selector，对没有 previous metadata 的 PR 运行首轮 `batch review pr`；观察 Step 4/5 child 的启动 selector与报告 | checker/scanner/validator 使用 fast selector，logic-analyzer 使用 strong selector；CR 正常产出 verdict；没有 `model profile fallback` note（允许 coverage 等其他 note） |
| U1b | 合法 profile 的增量派发 | 用户实测 | 在 U1a 的 PR 上创建新 head，使其进入增量审查；观察 delta-reviewer 与 Δ2a child 的启动 selector与报告 | delta-reviewer/Δ2a logic-analyzer 使用 strong selector，Δ2a bug-scanner 使用 fast selector；CR 正常产出 verdict；没有 `model profile fallback` note |
| U2 | 未启用 profile 的存量行为 | 用户实测 | 不设置两个环境变量，分别观察首轮和增量轮 | 所有派发项均不带 per-run `model`；正常 resolution chain 生效；没有模型 fallback note；CR 正常产出 verdict |
| U3 | 配置失败的 bounded fail-safe | 用户实测 | 在“父/default/agent resolution chain 本身有效且通过当前 scope”的前提下，分别以独立运行配置格式非法值、registry 不存在值和 scope 不通过值 | 对应档位不把候选值传给 child，改走正常 resolution chain；note 披露准确 reason；CR 正常产出 verdict |

**U3 的前置条件不可省略**：如果测试环境的 inherited/default/agent override 模型本身违反 `strict` modelScope，测试失败不能归因于本 issue；应先修复测试部署配置，或将该结果标记为既有配置阻塞。

**可测性拆分设计**：本 issue 仍无运行时代码，自动化对象是文档契约。registry 查询、scope 判断和 fallback 选择属于父 agent 行为，无法由仓内静态测试证明，因此由 U1-U3 覆盖。契约测试按 preflight 顺序、映射、属性省略、note、resolution chain 边界分别断言，避免一个宽泛 substring 测试同时掩盖多个错误。

## 8. 风险与已处理的审查问题

1. **strict inherited scope**：已收窄保证范围。省略 `model` 只能避免本次候选作为 explicit model 触发错误，不能修复已有 inherited/default 模型越界。
2. **registry 不存在**：已恢复 `subagent({action:"models"})` 守门；`provider/id` 外形不再视为可用性证明。
3. **modelScope 缺失**：已明确“无有效 modelScope = 无范围限制”，但仍需要 registry 证明；无法判断有效 settings 时按 scope-unverified fallback。
4. **resolution chain 误称父模型**：全文统一改为正常 subagent model resolution chain，U1/U2/U3 不再假定最终一定是父 session 模型。
5. **`profile_fallback` 落点**：已明确不是 Pi 参数或报告字段；它是每轮临时状态，固定 `Note:` 是唯一对外披露形式。
6. **未定义 note 接线**：已把 Step 10 纳入改动面，规定模型 note 与 coverage note 独立传递。
7. **环境变量直接进入 JS**：已加入 trim、控制字符、registry canonical selector 和安全字面量要求；fallback 必须省略整个属性。
8. **#216 旧测试冲突**：已明确迁移 `test_step4_example_has_no_model_field`，不再要求含条件注入示例的代码块完全没有 `model`。
9. **#225 串行冲突**：契约不锁 checker 数量和 key 名，两个 PR 仍必须串行落地。

## 9. 设计边界确认记录（2026-09-07）

1. ✅ 已确认：issue 的“完全不启动失败”解释为候选环境变量未通过 preflight 时不显式传入；只要既有 inherited resolution chain 有效，CR 继续运行；既有 strict 配置错误不在本 issue 范围。
2. ✅ 已确认：不新增 `profile_fallback` 结构化字段，固定 `Note:` 是唯一对外披露方式。
3. ✅ 已确认：U1a/U1b/U2/U3 为合并后用户实测项，U3 前置条件（fallback resolution chain 本身有效）不可省略。
