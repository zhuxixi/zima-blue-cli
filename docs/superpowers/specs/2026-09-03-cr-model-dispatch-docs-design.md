# Spec: 修正 CR skill 的 subagent 模型派发文档（issue #207）

日期：2026-09-03 · 状态：draft（等用户确认）

## 背景 / 根因

完整调研见 `research/root-cause-and-fix-surface.md`，并结合 2026-09-02 对当前 Pi / pi-subagents 实现的复核。

当前文档有三类问题：

1. `flow.md` Step 4 的示例和分档说明建议 `deepseek-v4-pro`。当执行 skill 的父 Pi 配置了 `subagents.modelScope.enforce: true`，且 allowlist 不含该模型时，显式传入的 child model 会在启动前被拒绝。`runs.all` 的聚合结果随之失败；如果父流程未单独处理该错误，通常无法完成本轮报告和 verdict，用户侧可能表现为 CR 静默失败。
2. `flow.md` 与 `subagent-prompts.md` 都把模型分档写成可直接照抄的指导；当前 `subagent-prompts.md:3` 还写着「缺省继承当前模型」。这没有说明 agent override、frontmatter、`subagents.defaultModel`、provider-scoped override 等配置层级，也没有说明模型选择由父 Pi 完成。
3. `flow.md` 原文写「模型名以 `enabledModels` 为准」。Pi 官方文档定义 `enabledModels` 为主会话 Ctrl+P 模型循环的候选范围；它不是 subagent 的 modelScope allowlist。它可能间接影响父会话模型，从而影响 child 的继承结果，但不能用来判断 child 是否被允许派发。

## 已确认的配置语义

| 用途 | 配置位置 | 语义 |
|---|---|---|
| 主会话模型范围 | `~/.pi/agent/settings.json` 顶层 `enabledModels`；项目级 `.pi/settings.json` 也可配置 | 主会话 `--models` / Ctrl+P 循环候选，不是 subagent 授权名单 |
| 主会话默认模型 | settings 顶层 `defaultModel` / `defaultProvider` | 主 Pi 会话启动模型；不等同于 `subagents.defaultModel` |
| subagent 默认与角色模型 | settings 的 `subagents.defaultModel`、`agentOverrides`、`agentOverridesByProvider` | child 模型选型配置 |
| subagent 模型政策 | settings 的 `subagents.modelScope` | 对 resolved `provider/id` 做 allowlist 校验；必要时 fail-closed |
| 自定义模型注册 | `~/.pi/agent/models.json` | 注册 custom provider/model 到 Pi registry；不是 modelScope 白名单 |
| 项目级覆盖 | 当前项目 `.pi/settings.json` | 项目配置在被 Pi 信任并加载时优先；项目级 `modelScope` 整体替换用户级 `modelScope`，不是逐字段合并 |

来源：

- Pi `docs/settings.md:1-16, 258-266, 348-365`
- pi-subagents `docs/models.md:5-16, 174-230`
- pi-subagents `src/runs/shared/model-scope.ts:4-13, 76-97, 143-168`
- pi-subagents `src/runs/shared/model-fallback.ts:295-371, 412-465`

## 决策表

| # | 决策点 | 方案 | 理由 |
|---|--------|------|------|
| D1 | Step 4 主派发示例 | 5 个 `runs.all` child 均不显式传 `model` | skill 应适配不同 provider、认证和用户政策；避免把某个用户的模型选择写成通用默认值 |
| D2 | 显式模型分档 | 保留为可选能力，不保留固定模型推荐；要求使用准确的完整 `provider/id`，并同时通过 active registry 与 effective modelScope | #170 的分档能力仍可用，但模型名称是部署策略，不应硬编码在通用 skill 文档里 |
| D3 | 显式模型的确认者 | 由**执行 skill 的父 Pi agent**在调用 `runs.all` 前确认；child reviewer 不负责确认 | model 在 child 启动前已被解析和校验；child 启动后再检查已经太晚 |
| D4 | canonical model ID 查询 | `subagent({action:"models"})` 可以用于查 canonical `provider/id`；但它的 registry 列表不能代替 modelScope 校验 | 官方工具支持该 action；registry 中可能有 allowlist 禁止的模型，不能把「已注册」误认为「获准派发」 |
| D5 | modelScope 检查 | 检查当前有效的 `subagents.modelScope`：全局 `allow` 与 `modelScope.agents.reviewer.allow`（若存在）都必须通过；项目级配置在实际被加载时替换用户级配置 | `agent: "reviewer"` 可能受到全局和角色级两层约束；只看一个 allow 字段不完整 |
| D6 | `enabledModels` 说明 | 明确它是主会话模型范围/循环候选，不是 subagent allowlist；允许说明其可能通过 parent-model inheritance 产生间接影响 | 准确区分选择范围、registry 和政策 allowlist 三种概念 |
| D7 | 缺省模型说明 | 不传 `model` 通常更稳，但不保证一定通过；最终 resolved model 仍受 agent 配置、parent model 和 modelScope 影响 | `strict: true` 会拒绝继承、default、frontmatter 和 fallback 中的越界模型 |
| D8 | `enforce` / `strict` 说明 | `enforce: true` 时显式越界模型报错；`strict: true` 进一步让 inherited/default/fallback 越界模型报错 | `strict` 不是显式 model 报错的必要条件 |
| D9 | model ID 格式 | 显式传 model 时优先使用完整 `provider/id`；不使用 bare `deepseek-v4-flash` 这类可能跨 provider 歧义的 ID | 当前 registry 中多个 provider 暴露相同 bare ID；无法消歧时会在 modelScope 检查前解析失败 |
| D10 | thinking 后缀 | 说明 `:max` 等已知 thinking 后缀在 modelScope 匹配时会被剥离 | `provider/id` 的 allow 条目无需为每个 thinking 后缀重复配置 |
| D11 | 文档修复面 | 修改 `flow.md` 与 `subagent-prompts.md`；不修改 pi-subagents 或用户 settings | 两个文档都有模型派发指导；实现代码不在本仓库 |

## 文案变更设计

### 变更 1：`flow.md` Step 4 派发示例

删除两个显式模型字段：

```diff
 await runs.all([
   { key: "claude-checker-1", agent: "reviewer", context: "fresh", task: "<claude-compliance-checker prompt，显式规则 framing>" },
   { key: "claude-checker-2", agent: "reviewer", context: "fresh", task: "<claude-compliance-checker prompt，隐含约定 framing>" },
   { key: "agents-checker",    agent: "reviewer", context: "fresh", task: "<agents-compliance-checker prompt>" },
-  { key: "bug-scanner",       agent: "reviewer", context: "fresh", model: "<便宜快模型，如 deepseek-v4-flash>", task: "<bug-scanner prompt>" },
-  { key: "logic-analyzer",    agent: "reviewer", context: "fresh", model: "<强模型，如 deepseek-v4-pro>", task: "<logic-analyzer prompt>" },
+  { key: "bug-scanner",       agent: "reviewer", context: "fresh", task: "<bug-scanner prompt>" },
+  { key: "logic-analyzer",    agent: "reviewer", context: "fresh", task: "<logic-analyzer prompt>" },
 ])
 ```

这段示例只表达职责与并发关系，不替用户决定 provider/model。child 的有效模型由父 Pi 根据 `reviewer` 的 agent 配置和当前 settings 解析。

### 变更 2：`flow.md` 模型选择说明

将现有「按职责差异化指定模型」段落改为以下语义：

```text
**按 agent 职责差异化指定模型（#170，可选）**：subagent 工具的派发项支持 `model` 字段，但主派发示例默认不指定它。若确实需要按职责分档，模型由执行本 skill 的父 Pi agent 选择：

1. 用 `subagent({action:"models"})` 查询当前 registry 中准确的 `provider/id`；该列表只用于确认 canonical ID，不代表模型通过了 modelScope 政策。
2. 读取当前实际生效的 settings，检查 `subagents.modelScope.allow`；由于本流程使用 `agent: "reviewer"`，如果存在 `subagents.modelScope.agents.reviewer.allow`，还必须同时通过该角色级 allowlist。
3. 项目级 `.pi/settings.json` 只有在当前非交互 Pi 进程信任并加载时才生效；生效时项目级 `subagents.modelScope` 整体替换用户级同名配置。
4. 显式传入时使用完整的 `provider/id`，不要使用可能跨 provider 歧义的 bare model ID。无法确认有效 modelScope 时，省略 `model`，不要猜测或按 registry 列表直接选择。

`subagents.modelScope` 是模型范围政策，不负责选择便宜模型。`enforce: true` 时，显式传入的越界模型会在 child 启动前报错；`strict: true` 还会拒绝从 agent frontmatter、`subagents.defaultModel`、父 session 或 fallback 链解析出的越界模型。`allow` 按 resolved `provider/id` 匹配，已知 thinking 后缀（如 `:max`）会在匹配时剥离。

注意：`enabledModels` 是 settings 顶层的主会话模型范围/模型循环候选，不是 subagent 的 modelScope allowlist。它可能间接影响继承父 session 模型的 child，但不能用来判断 child 是否获准派发。
```

其中「读取 settings」的动作由父 Pi agent 执行，不要求被派出的 reviewer child 自己运行 slash command。`/subagents-models` 是交互式 slash command，不能作为非交互 CR 进程的确认步骤；工具形式的 `subagent({action:"models"})` 可以在非交互父进程中调用，但不展示 allowlist。

### 变更 3：`subagent-prompts.md` 顶部说明

同步删除当前的固定模型分档和「缺省继承当前模型」表述，改为：

```text
本文件的 prompt 模板在 pi 下由父 Pi agent 通过 `subagent` 工具派发。并行 fanout 使用 `workflowScript` + `runs.all`。派发项可以按需指定 `model`，但默认不指定；缺省时由 pi-subagents 按 per-run override、provider-scoped override、agent override、agent frontmatter、`subagents.defaultModel`、parent session model 的解析链决定。若显式指定，父 Pi 必须先确认完整 `provider/id` 同时满足当前 registry 与 effective `subagents.modelScope`（包括 reviewer 角色级限制，如有）。
```

## 错误语义边界

文档不得把「静默失败」写成 Pi runtime 一定不会输出任何错误。准确描述是：

- 显式越界模型在 child 启动前被 `modelScope` 拒绝，并抛出包含 allow patterns 的错误；
- `runs.all` 使用 `Promise.all` 聚合 child 结果，单个 child 的启动失败会使聚合结果失败；
- 如果父流程没有捕获并转换该错误，skill 可能无法继续生成正常 review 报告、PR 评论或 `<zima-review>` trailer；
- 错误可能存在于父 Pi transcript / zima 日志中，因此「静默」描述限定为「没有正常 CR 产物」，不宣称底层完全无错误输出。

## 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | 主派发示例不再硬编码模型 | 自动化验证（unit/static） | `uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs` | Step 4 的 `runs.all` 示例中不存在 `model` 字段，且 `flow.md` / `subagent-prompts.md` 不再把具体模型写成通用推荐 |
| A2 | 显式模型确认流程准确 | 自动化验证（unit/static） | 同上 | 文档明确父 Pi 负责确认、完整 `provider/id`、registry 与 effective modelScope 分开检查；无法确认时省略 `model` |
| A3 | modelScope 语义准确 | 自动化验证（unit/static） | 同上 | 文档涵盖 global allow、`agents.reviewer.allow`、`enforce`、`strict`、thinking suffix 和项目级替换规则 |
| A4 | enabledModels 语义准确 | 自动化验证（unit/static） | 同上 | 文档明确 `enabledModels` 只定义主会话范围/循环候选，不是 subagent allowlist，并说明可能的 parent inheritance 间接影响 |
| A5 | 两份文档没有过时说明 | 自动化验证（static） | `grep -Rni --include='*.md' -E 'deepseek-v4-pro|模型名以.*enabledModels|缺省继承当前模型' pi/github-code-review-batch` | 无旧模型建议、旧约束源或不完整继承说明残留；允许 issue/spec 调研文件之外的正文不出现这些过时表述 |
| A6 | 现有 skill 契约未破坏 | 自动化验证（unit/static） | `uv run pytest tests/unit/test_cr_batch_contracts.py`；`git diff --check` | 既有触发短语、状态报告、metadata、交叉引用契约继续通过，diff 无 whitespace error |
| U1 | Full Round-1 在白名单环境成功 | 用户实测 | 使用当前有效 modelScope 配置，对一个无 previous metadata 的真实 PR 触发 `batch review pr`；观察 Step 4 和产物 | 5 个 reviewer child 均成功启动，未出现 out-of-scope 或 ambiguous model 错误，产生正常 review 输出和 `<zima-review>` verdict |
| U2 | Incremental 分支在同一配置下成功 | 用户实测 | 对已有上一轮 metadata 且 head SHA 已变化的 PR 触发一次增量审查；观察 delta-reviewer 与新增 hunk scanner 派发 | delta-reviewer、bug-scanner、logic-analyzer 均能完成；产生正常状态报告和 `<zima-review>` verdict |

### 可测性拆分设计

这是文档契约修复，但需要把容易回归的模型派发规则拆成独立的静态断言，而不是只依赖人工阅读：

- `extractStep4DispatchExample(text)`：从 `flow.md` 定位 Step 4 的 `runs.all` 示例代码块；测试它不包含 `model` 字段、不包含 bare model ID。
- `assertModelScopeGuidance(text)`：检查文档是否同时提到 `subagents.modelScope.allow`、`modelScope.agents.reviewer.allow`、`enforce`、`strict`、完整 `provider/id`、registry 与 allowlist 的区别，以及无法确认时省略 `model`。
- `assertEnabledModelsGuidance(text)`：检查 `enabledModels` 被描述为主会话范围/循环候选，而不是 subagent 派发约束，并保留 parent inheritance 的间接影响说明。
- `assertNoStaleModelGuidance(flowText, promptText)`：检查两个文档没有旧的 `deepseek-v4-pro` 推荐、`enabledModels` 作为派发依据、或「缺省继承当前模型」的过度简化表述。

这些方法应保持纯文本输入/布尔或异常输出，不读取 settings、不调用 Pi、不启动 subagent。这样 unit/static 测试只验证文档契约；U1/U2 负责验证真实 Pi runtime、配置加载和外部 provider 行为。U1/U2 依赖真实 GitHub、Pi registry、认证与 modelScope，不能由文档静态测试替代；无法执行时必须记录为 `pending`。

## 非目标

- 不修改 pi-subagents runtime、model resolver 或 modelScope 实现
- 不自动读取 settings 并在 skill 内实现一套新的 glob 匹配器
- 不做自动 fallback 或把越界模型静默替换成另一个模型
- 不修改用户级或项目级 settings.json
- 不修改 `SKILL.md` 的触发词和执行契约
- 不处理 #202 的成本模型选择，只消除固定模型建议与用户政策之间的文档冲突
- 不把 `/subagents-models` 当成非交互 CR 的必要步骤
