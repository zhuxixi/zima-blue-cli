# Issue #225 设计规格：合并双 CLAUDE checker 为单 checker 两阶段

- **Issue**：#225
- **类型**：refactor / workflow prompt redesign
- **日期**：2026-09-08
- **状态**：待用户 review
- **基线**：`2e3a8a320f9db7319d395328831d5269c13f0e04`（#224 模型分档已合并）

## 1. 目标与边界

### 1.1 目标

将 Round-1 Step 4 中两个独立的 `claude-compliance-checker` 调用合并为一个调用；在同一份 prompt 内按顺序执行两个审查阶段：

1. **Phase 1：显式规则违反**——逐条核对 CLAUDE.md 的明文规则。
2. **Phase 2：隐含约定 / 反模式**——切换到意图和约定视角，检查变更是否破坏 CLAUDE.md 表达的设计意图。

合并后仍输出一个扁平 JSON finding 数组，保持下游 issue-validator、Step 6 去重排序和评论构建器的输入契约不变。Round-1 Step 4 的 LLM fanout 从 5 个降为 4 个，checker 继续使用 fast 模型档位。

### 1.2 非目标

本 issue 不做以下改动：

- 不修改 `issue-validator`、`delta-reviewer`、`build_review_body.py`、`render_status_report.py` 或其他运行脚本。
- 不修改 finding 的字段名、`reason` 值、severity/blocking 规则、metadata、Status 三态或 XML trailer。
- 不修改增量审查的 `delta-reviewer + Δ2a` 派发结构；只更新其中用于描述完整流程数量的对照表。
- 不新增 MCP 依赖，不改变 pi 与 cc 两种 harness 的派发工具。
- 不把两个阶段变成两次 subagent 调用；两次调用会失去节省一个 agent 的目标。
- 不输出 `phase1_findings` / `phase2_findings` 两个数组，不增加 `phase` 字段。

## 2. 背景与设计依据

#122（PR #129，`fbeedbc`）已经把原先的同 prompt 复跑改成了两个不同 framing：显式规则视角与隐含约定视角。#225 要保留这两个视角的覆盖意图，但把它们放进同一个 checker，省掉一个独立调用。

合并后的主要风险是上下文锚定：Phase 2 可能沿用 Phase 1 的逐条规则思路，导致隐含约定视角变弱。因此 prompt 必须在阶段边界明确要求切换审查镜头、暂时搁置 Phase 1 的结论，并要求 Phase 2 不重复 Phase 1 已发现的问题。最终是否接受该风险不能只由文档静态检查判断，必须在同一个真实 PR 上执行新旧对比。

## 3. 方案选择

### 3.1 采用方案：单 checker、单 prompt、两阶段顺序执行

一个 checker 接收一次输入包，在一个 prompt 内先执行 Phase 1，再执行 Phase 2，最后把两阶段结果汇总为一个 JSON 数组。

**优点**：

- 完全符合 #225 的目标，Round-1 从 5 个 LLM agent 降为 4 个。
- 保留显式规则和隐含约定两个覆盖角度。
- 不改变下游 schema，改动集中在 prompt 和派发文档。
- 通过“切换视角 + 不重复”指令降低同上下文锚定风险。

**代价**：

- 两个阶段不再拥有两个独立上下文，视角互补可能弱于 #122 的双调用设计。
- 单个 checker 失败会同时影响两个阶段；这是节省调用换取的可接受风险，由真实 PR 对比验证兜底。

### 3.2 不采用：两个输出数组

让 checker 输出 `phase1_findings` 和 `phase2_findings` 可以增强观测性，但会破坏现有消费者期望的扁平数组 schema，并迫使 issue-validator、Step 6 和构建器联动修改，超出本 issue 范围。

### 3.3 不采用：两个顺序 subagent 调用

先调用显式规则 checker，再把结果传给隐含约定 checker，虽然上下文可以分离，但仍然消耗两个调用，不能实现本 issue 的成本目标；同时还会让第二个 checker 被第一个结果显式引导。

### 3.4 历史基线的保留方式

实现后的 skill 文档不再保留旧的“双 checker 调用”执行说明，但 U1 的旧方案输入仍从基线 commit `2e3a8a3` 的 prompt 文件提取并存入调研目录。这样运行文档只有一个事实源，验证仍能复现改动前的两个 framing。

## 4. 组件契约与数据流

### 4.1 输入契约

单 checker 的输入保持现状：

- PR 摘要：`summary`
- PR diff：`diff`
- 相关 CLAUDE.md 内容：`claude_md_content`

pi 版和 cc 插件版使用相同的 checker prompt 正文；两版仅保留各自的派发说明：pi 使用 `subagent` 的 `workflowScript + runs.all`，cc 使用 Claude Code 的 `Agent` 工具。

### 4.2 Prompt 内部数据流

```text
summary + diff + claude_md_content
                  │
                  ▼
       Phase 1：明文规则逐条核对
                  │
                  ▼
       明确切换视角，不沿用逐条核对框架
                  │
                  ▼
       Phase 2：意图/约定/反模式检查
                  │
                  ▼
       内部去重并合并为一个 JSON 数组
                  │
                  ▼
[{description, reason, file, lines, suggestion, severity}]
```

### 4.3 输出契约

最终输出必须是一个 JSON 数组。每个 finding 延续现有六字段契约：`description`、`reason`、`file`、`lines`、`suggestion`、`severity`。六个 key 都继续保留；`suggestion` 的内容可以表达“无具体建议”，但本 issue 不改变 key 是否存在。`severity` 仍必须是 `critical | high | medium | low`。

示例：

```json
{
  "description": "问题描述",
  "reason": "CLAUDE.md",
  "file": "相对仓库根目录的文件路径",
  "lines": "行号范围",
  "suggestion": "可选修复建议",
  "severity": "critical | high | medium | low"
}
```

具体约束如下：

1. 两个阶段的 `reason` 都必须包含 `"CLAUDE.md"`，canonical 值继续使用 `"CLAUDE.md"`；不新增 Phase-2 reason 枚举，不把既有“包含”契约收紧成新的完全相等校验。
2. 不增加 `phase` 或其他新必填字段；现有可选 `blocking` 规则保持不变。
3. Phase 1 的 finding 必须在 `description` 中引用对应的 CLAUDE.md 明文规则原文或明确规则位置。
4. Phase 2 的 finding 也必须在 `description` 中指出对应的 CLAUDE.md 意图、约定、章节或规则来源；不能把没有 CLAUDE.md 依据的普通工程偏好包装成规范违规。
5. 不报告纯主观判断、纯风格 nit 或“我认为更好”的建议。
6. 两阶段内部重复的问题只保留一个 finding；跨 agent 的最终去重仍由原 Step 6 执行。
7. 没有 finding 时输出 `[]`，不输出解释文字或 Markdown 围栏。

## 5. Prompt 设计

`references/subagent-prompts.md` 的 `claude-compliance-checker` 小节改为一份 prompt，不再写“启动两次”、`Checker-1`、`Checker-2` 或“两个独立 checker”。该小节的“任务”列表也同步为两阶段职责：逻辑/安全问题只有在同时能定位到 CLAUDE.md 依据时才由 compliance checker 报告；脱离规范依据的通用逻辑/安全问题继续由 bug-scanner / logic-analyzer 负责。这样消除当前“任务”总述与两份具体 prompt、#124 validator 之间的冲突，不扩大 reason 分类。推荐正文如下，pi 与 cc 两份副本保持语义等价。

```text
你是一个代码规范审查员。请使用同一份输入执行两个连续但视角不同的审查阶段，最后把两阶段发现合并为一个 JSON 数组。

输入：
- PR 摘要：{summary}
- PR diff：{diff}
- 相关 CLAUDE.md 内容：{claude_md_content}

阶段 1：显式规则违反
1. 通读相关 CLAUDE.md，识别其中适用于本次变更的明文规则。
2. 逐条核对 PR 修改的代码是否违反这些明文规则。
3. 只报告能够由 CLAUDE.md 明文规则支持的问题，并在 `description` 中引用规则原文或明确规则位置。

阶段 2：隐含约定与反模式（切换视角）
现在暂时搁置阶段 1 的逐条规则核对结果，明确切换到“意图与约定”视角。审视 CLAUDE.md 表达的设计意图和项目约定，例如分层、命名一致性、错误处理风格和可维护性边界。
1. 检查 PR 修改是否破坏了这些由 CLAUDE.md 表达或明确暗示的意图与约定。
2. 每个问题都在 `description` 中说明它与 CLAUDE.md 的哪条意图、约定、章节或规则来源相悖。
3. 不重复报告阶段 1 已经发现的同一问题。
4. 没有 CLAUDE.md 依据的普通工程偏好、纯风格 nit 或“我认为更好”的建议不要报告；一般逻辑/安全问题应由其他 checker 负责。

共同要求：
1. 只关注 PR 修改的代码，忽略原有代码。
2. 不报告纯主观判断；规范 finding 必须能同时定位到变更内容和 CLAUDE.md 依据。
3. 汇总两个阶段的发现，输出一个扁平 JSON 数组；不要输出两个数组，不要增加 phase 字段。
4. 每个元素必须包含 description、reason（必须包含 "CLAUDE.md"，canonical 值为 "CLAUDE.md"）、file、lines、suggestion、severity（critical/high/medium/low）；六个 key 均保留。
5. 不要输出 Markdown 代码围栏、标题或 JSON 之外的解释文字。
6. 如果两个阶段都没有发现问题，输出空数组 []。
```

这里的“阶段 2 也必须有 CLAUDE.md 依据”是对 #124 规范类 validator 收紧规则的前置约束：checker 可以从意图推导反模式，但不能脱离 CLAUDE.md 自行扩张规范边界。

## 6. 文件级改动范围

### 6.1 pi 主版

修改：

- `pi/github-code-review-batch/SKILL.md`
  - Step 4 总览：5 个 → 4 个
  - SubAgent 表：checker 并发数 2 → 1，职责改为“两阶段”
  - 设计原理 #2：从“双 checker 不同 framing”改为“单 checker 内两阶段互补”
- `pi/github-code-review-batch/references/subagent-prompts.md`
  - checker “任务”列表同步为两阶段且要求 CLAUDE.md 依据
  - 双 checker 的调用次数说明改为单 checker 两阶段
  - 两份 prompt 合并为第 5 节的一份 prompt
- `pi/github-code-review-batch/references/flow.md`
  - Step 3.5 完整 diff 的 checker 数量说明去掉 `×2`
  - Step 4 标题、fanout 数量和职责列表 5 → 4
  - `claude-checker-1` / `claude-checker-2` 合并为一个 `claude-checker`
  - fast 档位映射去掉 `×2`，checker 继续属于 fast
  - 删除 #224 预留的“#225 落地后再更新”说明
  - 将“为什么 CLAUDE.md checker 跑两次”改为“为什么单 checker 使用两阶段”
- `pi/github-code-review-batch/references/delta-review.md`
  - 仅更新完整流程对照表中的 5 个审查 subagent → 4 个

不修改：`delta-review.md` 的增量派发逻辑和 `Δ2a` 逻辑；它仍然是 delta-reviewer 加 bug/logic scanner。

### 6.2 cc 插件同步版

修改：

- `plugins/pr-automation/skills/github-code-review-batch/SKILL.md`
- `plugins/pr-automation/skills/github-code-review-batch/references/subagent-prompts.md`
- `plugins/pr-automation/skills/github-code-review-batch/references/flow.md`
- `plugins/pr-automation/skills/github-code-review-batch/references/delta-review.md`

cc 版与 pi 版共享 prompt 语义和数量说明，但保留 cc 版的 `Agent` 工具派发写法；不能把 pi 版的 `runs.all` 或 #224 的 `PI_CR_FAST_MODEL` preflight 机械复制到 cc 版。

### 6.3 Contract 测试

修改：

- `tests/unit/test_cr_batch_contracts.py`
- `tests/unit/test_cr_batch_plugin_contracts.py`

新增文档契约测试，不调用 LLM，不改变生产逻辑。加入测试是用户已确认的设计选择：通过 `.py` 变更避免纯 docs-only trivial 路径，并为两份 skill 副本锁定新的单 checker 两阶段结构。

### 6.4 明确不修改的文件

以下文件不属于本 issue：

- `pi/github-code-review-batch/scripts/**`
- `plugins/pr-automation/skills/github-code-review-batch/scripts/**`
- `zima/**`
- `issue-validator`、`build_review_body.py`、`render_status_report.py` 的实现或 prompt
- 触发短语、PR 评论 metadata、状态报告和三态 Status 相关文档契约

## 7. 测试与可测性拆分设计

所有自动化验收都使用纯文本读取和局部 section 提取，不启动 subagent、不访问 GitHub、不依赖模型。这样测试边界只覆盖“文档是否描述并派发了正确的结构”，不把随机的 LLM 召回行为伪装成 unit 测试；LLM 召回由 U1 真实 PR 对比覆盖。

### 7.1 测试单元与边界

| 测试单元 | 独立职责 | 测试边界 |
|---|---|---|
| pi Step 4 section extractor | 读取 pi flow.md 的 Step 4 并提取第一个 `runs.all` JS 块 | 只验证文档示例的 4 个 lane，不验证 subagent 工具运行时 |
| cc Step 4 section extractor | 读取 cc flow.md 的 Step 4 并提取 Agent 派发清单 | 只验证 cc 文档的 4 个角色，不验证 Claude Code Agent 工具 |
| checker prompt extractor | 提取两份 `claude-compliance-checker` section | 验证两阶段内容、flat schema 和 CLAUDE.md 依据，不评价 prompt 的实际模型效果 |
| legacy residue scanner | 扫描 pi/cc skill 目录下相关 Markdown | 只禁止旧执行语义；不禁止历史 issue 编号或普通单词 checker |
| tier mapping assertion | 检查 pi Step 4 fast 映射行 | 验证 checker 仍为 fast；不测试 preflight 解析和 modelScope |
| existing external-contract suite | 运行已有两个 contract 测试文件 | 验证触发词、metadata、状态报告、模型分档等已有契约没有回归 |

### 7.2 新增断言

`test_cr_batch_contracts.py` 新增 `TestCheckerMergeDocs`，使用现有 `SKILL_DIR`、`re` 和局部 section 提取模式：

1. `test_pi_step4_dispatch_has_four_lanes`
   - 从 Step 4 的首个 `js` 代码块提取所有 `key`。
   - 断言集合恰为 `claude-checker`、`agents-checker`、`bug-scanner`、`logic-analyzer`，数量恰为 4。
2. `test_pi_checker_task_uses_two_phase_prompt`
   - 断言唯一 CLAUDE lane 的 task 指向“两阶段 prompt”，Step 4 同时写明“显式规则”和“隐含约定 / 反模式”。
3. `test_pi_checker_fast_mapping_is_preserved`
   - 断言 fast 映射表同一行包含 `CLAUDE.md checker`、`bug-scanner` 和 `PI_CR_FAST_MODEL`；现有 `TestModelDispatchDocs` 继续检查条件 spread、preflight 与 fallback。
4. `test_pi_checker_prompt_preserves_flat_schema`
   - 从 `subagent-prompts.md` 提取 checker section，断言包含“一个扁平 JSON 数组”、`description`、`reason`、`file`、`lines`、`suggestion`、`severity`，并要求 `reason` 包含 `CLAUDE.md`。
   - 断言不存在 `phase1_findings`、`phase2_findings` 或新增 `phase` 字段契约。
5. `test_pi_checker_prompt_switches_view_and_requires_guideline_basis`
   - 断言存在“阶段 1”“阶段 2”“切换视角”“不重复”，且 Phase 2 要求在 `description` 中关联 CLAUDE.md 意图、约定、章节或规则来源。
6. `test_pi_round1_agent_count_docs_are_consistent`
   - 断言 `SKILL.md` Step 4 总览、`flow.md` Step 4 标题/正文和 `delta-review.md` 完整流程对照表都写 4 个审查 agent。
7. `test_pi_no_legacy_dual_checker_execution_text`
   - 扫描 pi skill Markdown，断言不存在这些明确的旧执行 token：`启动两次`、`claude-checker-1`、`claude-checker-2`、`CLAUDE.md checker ×2`。
   - 不禁止 #122 历史背景或一般性的“checker”单词，避免把设计缘由误判成当前执行说明。

`test_cr_batch_plugin_contracts.py` 在 `TestCcPluginContracts` 或独立文档测试类中新增：

1. `test_cc_step4_dispatch_has_four_agents`
   - 只提取 cc flow.md 中“派发结构”到“task 的 prompt 模板见”之间的 bullet key。
   - 断言集合恰为 `claude-checker`、`agents-checker`、`bug-scanner`、`logic-analyzer`，数量恰为 4。
   - 断言该派发 section 不含 pi 的 `runs.all`、`FAST_OVERRIDE` 或 `PI_CR_FAST_MODEL`。
2. `test_cc_round1_agent_count_docs_are_consistent`
   - 对 cc 的 `SKILL.md`、`flow.md` 和 `delta-review.md` 执行与 pi 相同的 4-agent 数量一致性检查。
3. `test_cc_no_legacy_dual_checker_execution_text`
   - 扫描 cc skill Markdown，使用与 pi 相同的旧执行 token 集合。
4. `test_pi_and_cc_checker_prompt_sections_are_identical`
   - 分别提取两份 `subagent-prompts.md` 的 `claude-compliance-checker` section，断言正文完全相等；两版不同的派发头位于该 section 之外，不影响比较。

这些是实现要求，不是建议性名称；plan 必须把每个测试绑定回 A2–A7。

### 7.3 自动化验证命令

最低验证命令为：

```bash
uv run pytest tests/unit/test_cr_batch_contracts.py \
  tests/unit/test_cr_batch_plugin_contracts.py -q
uv run ruff check tests/unit/test_cr_batch_contracts.py \
  tests/unit/test_cr_batch_plugin_contracts.py
uv run black --check tests/unit/test_cr_batch_contracts.py \
  tests/unit/test_cr_batch_plugin_contracts.py --line-length 100
```

如果测试改动影响共享 contract 或全套单测，再追加：

```bash
uv run pytest tests/unit/ -q
```

## 8. 验收矩阵

下表把每个功能点绑定到稳定 ID、验证层级、命令和通过标准；U1 不能被自动化单测替代。

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|---|---|---|---|---|
| A1 | 既有外部契约不回归 | 自动化验证（unit） | `uv run pytest tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py -q` | 两个 contract 测试文件全部通过；触发短语、metadata、状态报告和模型分档断言均保持通过 |
| A2 | pi Step 4 从 5 个降为 4 个，且只保留一个 checker | 自动化验证（unit/static） | `TestCheckerMergeDocs.test_pi_step4_dispatch_has_four_lanes`、`test_pi_round1_agent_count_docs_are_consistent` | `runs.all` 恰有 4 个 lane，唯一 CLAUDE lane 为 `claude-checker`；SKILL/flow/delta 数量一致 |
| A3 | cc Step 4 从 5 个降为 4 个，且保留 cc 派发方式 | 自动化验证（unit/static） | `test_cc_step4_dispatch_has_four_agents`、`test_cc_round1_agent_count_docs_are_consistent` | Agent 清单恰有 4 个职责；cc 派发段不含 pi 的 `runs.all`、模型 override 或模型分档内容 |
| A4 | 单 checker 两阶段 prompt 保留两个覆盖角度 | 自动化验证（unit/static） | `test_pi_checker_task_uses_two_phase_prompt`、`test_pi_checker_prompt_switches_view_and_requires_guideline_basis`、`test_pi_and_cc_checker_prompt_sections_are_identical` | 两份副本有相同 prompt 正文，且包含 Phase 1 显式规则、Phase 2 隐含约定/反模式、视角切换、不重复和 CLAUDE.md 依据要求 |
| A5 | 输出 schema 和下游契约不变 | 自动化验证（unit/static） | `test_pi_checker_prompt_preserves_flat_schema` + 既有 contract suite | 输出为一个扁平 JSON 数组；保留六个既有 key 和可选 `blocking`；reason 仍包含 `CLAUDE.md`，canonical 值不变；没有 phase 双数组或 phase 字段 |
| A6 | 旧双 checker 执行语义清零 | 自动化验证（unit/static） | `test_pi_no_legacy_dual_checker_execution_text`、`test_cc_no_legacy_dual_checker_execution_text` | pi/cc 运行文档不再声明启动两次、两个旧 lane key 或 `CLAUDE.md checker ×2` |
| A7 | fast 档位归属不变 | 自动化验证（unit/static） | `test_pi_checker_fast_mapping_is_preserved` + 现有 `TestModelDispatchDocs` | checker 仍在 `PI_CR_FAST_MODEL` 映射中；条件 model spread、fallback 和 Step 5 fast 映射不受影响 |
| A8 | 测试代码质量 | 自动化验证（static） | `uv run ruff check tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py`；`uv run black --check tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py --line-length 100` | 两条命令都成功退出，无新增 lint/format 问题 |
| U1 | 同一真实 PR 的新旧召回对比 | 用户实测 | 按第 9 节固定输入和步骤，比较旧双 checker 与新两阶段 checker | 新方案必须召回已知 CLAUDE.md 哨兵 finding，并保留旧方案本轮产出的每个有效 finding；用户确认后才可定稿 |

## 9. U1 真实 PR 对比验证协议

### 9.1 固定样本、PR 内 commit 快照和哨兵 finding

为避免“换一个更容易的 PR”造成选择偏差，固定使用已合并真实 PR #205 内引入主流程的 commit 快照：

- **PR**：`zhuxixi/zima-blue-cli#205`
- **标题**：`feat(auto-merge): auto approve + squash merge after CR convergence (#204)`
- **base SHA**：`bb7b5138d32f4533b05d1971812e2507a74bfb7f`
- **head SHA**：`7b23046c5c49b88cbba6a9c44dae358d5caf6366`
- **commit**：`feat(auto-merge): main flow — orchestration, CLI, flock, gh client`
- **选择理由**：这是 PR #205 的真实 commit，只包含 Python 实现和测试；它引入了受 CLAUDE.md 明文约束的运行时路径。固定 diff 为 16,996 字符，小于 checker 的 20K 预算，`compress_diff.py` 预检为 `diff_truncated=false`、`Coverage: 2/2 files`，不会因截断制造假失败。

U1 设置一个已知哨兵 finding，防止本次旧双 checker 和新 checker 因采样随机性同时漏报后得到“0 对 0，因此通过”的虚假结论：

- **规则依据**：head SHA 对应的 CLAUDE.md 明文要求“新增运行时路径必须用 `get_zima_home()`，不能使用 `Path.home() / ".zima"`”，并说明运行时目录受 `ZIMA_HOME` 定制。
- **目标变更**：`examples/auto-merge/auto-merge-guarded.py` 新增 `DEFAULT_CONFIG = "~/.zima/configs/auto-merge.yaml"` 和 `DEFAULT_LOG = "~/.zima/logs/auto-merge.log"`，绕开 `ZIMA_HOME`。
- **历史依据**：PR #205 后续 Round-1 review 对同一目标变更产生了 `reason="CLAUDE.md"`、`severity="medium"` 的有效 finding；本快照把输入收窄到引入该问题的原始 commit，且目标 hunk 未被截断。
- **输入覆盖预检**：固定 base...head diff 经生产命令 `compress_diff.py --max-len 20000` 后必须仍包含两个常量，并记录 `diff_truncated=false`、`covered_files=2`、`total_files=2`。

如果固定 commit、规范文件或 GitHub PR 元数据发生不可恢复的读取失败，U1 状态必须记录为 `blocked`，不能私自改换 PR 后宣称通过；下一步输入需要用户明确指定替代样本及 SHA。

### 9.2 冻结输入包

在实现完成、执行 U1 前创建 `research/validation/pr-205-7b23046/`，并冻结以下输入。PR 元数据可以用 `gh pr view 205` 获取，但代码 diff 和规范文件必须从固定 commit SHA 读取，不能使用 PR 最终 head 或当前 main：

```bash
VALIDATION_DIR="$HOME/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-225/research/validation/pr-205-7b23046"
mkdir -p "$VALIDATION_DIR"

gh pr view 205 --repo zhuxixi/zima-blue-cli \
  --json number,title,body,reviews \
  > "$VALIDATION_DIR/pr-and-reviews.json"

git diff bb7b5138d32f4533b05d1971812e2507a74bfb7f...7b23046c5c49b88cbba6a9c44dae358d5caf6366 \
  > "$VALIDATION_DIR/diff.patch"

git show 7b23046c5c49b88cbba6a9c44dae358d5caf6366:CLAUDE.md \
  > "$VALIDATION_DIR/CLAUDE.md"

python pi/github-code-review-batch/scripts/compress_diff.py \
  --max-len 20000 \
  --meta-file "$VALIDATION_DIR/diff-meta.json" \
  < "$VALIDATION_DIR/diff.patch" \
  > "$VALIDATION_DIR/diff-20k.patch"
```

parent 基于固定 PR 标题、描述和 `diff.patch` 生成一次不超过 300 字的摘要，保存为 `summary.md`，三次 checker 调用复用该文件。执行前断言 `diff-meta.json` 为 `diff_truncated=false`、`covered_files=2`、`total_files=2`，并确认 `diff-20k.patch` 仍包含 `DEFAULT_CONFIG` / `DEFAULT_LOG` 目标 hunk；任何条件不满足都把 U1 标记为 blocked，不得给新旧方案使用不同输入。

三次调用必须使用完全相同的：

- PR 标题、描述和已冻结摘要；
- `diff-20k.patch`；
- 固定 head SHA 的 `CLAUDE.md`；
- `agent: "reviewer"`、`context: "fresh"`、provider/id、thinking level 和其他派发配置。

模型档位只做一次 #224 preflight：fast 档通过时，三项都显式使用同一个 canonical model override；fast 档未启用或 fallback 时，三项都省略 `model` 属性。将每个 child 实际报告的模型身份写入比较记录；如果三项实际模型或 thinking level 不一致，本轮 U1 无效并标记 blocked。

### 9.3 新旧方案运行

旧方案 prompt 固定取基线 commit `2e3a8a3` 的 `subagent-prompts.md`：

- `old-explicit`：基线 Checker-1/显式规则 prompt；
- `old-implicit`：基线 Checker-2/隐含约定 prompt。

新方案 prompt 取实现 worktree 的 checker section：

- `new-two-phase`：单 checker 两阶段 prompt。

在同一个 `runs.all` 中并行启动三个 fresh reviewer，以减少运行时环境漂移；每项只执行对应 checker prompt，不执行完整 CR skill。验证运行是只读实验，禁止发 PR 评论、改标签、push、触发 fix agent 或执行 Step 7–10。分别保存原始输出：

```text
old-explicit.json
old-implicit.json
new-two-phase.json
```

旧方案联合 finding 集合定义为两个旧输出的并集；只在 `comparison.md` 中做语义去重，不修改原始输出。三个 child 均只运行一次；若某项因基础设施失败没有返回可用结果，整轮标记 blocked，不单独重跑造成样本条件不一致。

### 9.4 Schema 检查

比较召回前，逐份验证：

1. 根节点是 JSON 数组，且没有 Markdown 围栏或数组外文字；
2. 每项是对象，包含非空 string `description`、`reason`、`file`、`lines` 和合法 `severity`；
3. `reason` 必须是包含 `"CLAUDE.md"` 的 string；
4. `suggestion` 必须存在且是 string，`blocking` 若存在必须是 boolean；
5. `severity` 必须属于 `critical/high/medium/low`。

任一输出 schema 失败时 U1 失败，不进入召回比较。

### 9.5 Finding 匹配与人工裁决

不能用 JSON 文本完全相等判断召回，因为 LLM 输出措辞可能不同。按以下顺序为旧方案去重后的每个 finding 建立匹配：

1. `file` 相同且 `lines` 有重叠或相邻上下文；
2. 问题主张指向同一行为、规则违反或反模式；
3. 新 finding 可以使用不同措辞，但必须覆盖同一风险、CLAUDE.md 依据和修复方向。

对每个旧 finding 在 `comparison.md` 标记以下一种结果：

- `retained`：新输出中存在等价 finding；
- `duplicate`：旧双 checker 的两个输出实际是同一个 finding，只计一次；
- `false-positive`：人工核对 PR diff 和 CLAUDE.md 后确认旧 finding 不成立或没有 CLAUDE.md 依据；
- `lost-valid`：旧 finding 有效，但新输出没有等价 finding。

如果新输出用不同措辞覆盖了同一风险，它属于 `retained`，不能用含糊的“丢失但可解释”分类放宽标准。新方案额外 finding 也要逐项标记 `valid` / `false-positive`；额外 finding 不抵消任何旧方案有效 finding 的丢失。

哨兵 finding 单独标记 `sentinel-retained` 或 `sentinel-missed`，不取决于本次旧方案是否再次发现它。

### 9.6 U1 通过与失败标准

U1 **通过**必须同时满足：

1. 三个 checker 均完成一次，使用相同冻结输入和相同实际模型配置，输出都通过 schema 检查；
2. 新两阶段 checker 召回第 9.1 节的 `ZIMA_HOME` 哨兵 finding；
3. 旧双 checker 本轮产出的每个去重后有效 finding 都在新输出中标为 `retained`，即 `lost-valid=0`，不分 severity 放宽；
4. 新方案的每个额外 finding 都能定位到 diff 和 CLAUDE.md 依据，不存在规范类 false positive；
5. `comparison.md` 记录模型身份、三份 finding 数、旧 finding 去重/有效性、新旧匹配、哨兵结果、新增 finding 有效性和最终结论；
6. 用户查看 `comparison.md` 后明确确认“无明显召回损失”。

U1 **失败或 blocked** 时：

- 不写“验证通过”，不进入合并前最终验收；
- prompt 召回或误报失败时，修改两份副本 prompt 的共同正文后重新执行 9.2–9.6；旧基线 prompt 不得修改，每轮输出保存在独立子目录；
- GitHub、模型、固定 commit 或权限不可用时，记录精确错误、已冻结输入和未完成步骤，标记 `blocked`，等待用户提供下一步输入。

## 10. 故障处理与回退

- **文档契约测试失败**：先定位是数量、旧残留、schema、pi/cc 漂移还是模型映射回归；修正文档或测试后重新运行 A1–A8。
- **pi/cc prompt 语义不一致**：以第 5 节 prompt 为共同正文，保留各自派发头，不接受只修一份的状态。
- **模型分档文档回归**：不得为了合并 checker 删除 `FAST_OVERRIDE`、`STRONG_OVERRIDE`、preflight、fallback note 或 Step 5 fast 复用说明；按 #224 契约修复。
- **U1 发现召回下降**：不通过“增加阈值容忍”掩盖问题；优先强化 Phase-2 的视角切换、CLAUDE.md 依据和不重复指令，按 9.6 重跑。
- **U1 暂时不能运行**：标记 pending/blocked；A1–A8 通过不能替代 U1，也不能据此声称 issue 完成。

## 11. 验收后的交付物

实现完成后，在本 issue 的全局调研目录保留：

```text
~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-225/
├── research/
│   ├── change-inventory.md
│   └── validation/pr-205-7b23046/
│       ├── pr-and-reviews.json
│       ├── diff.patch
│       ├── diff-20k.patch
│       ├── diff-meta.json
│       ├── CLAUDE.md
│       ├── summary.md
│       ├── old-explicit.json
│       ├── old-implicit.json
│       ├── new-two-phase.json
│       └── comparison.md
└── spec.md
```

这些验证产物不进入仓库 commit。仓库 commit 只包含第 6 节列出的 skill 文档和 contract 测试改动。
