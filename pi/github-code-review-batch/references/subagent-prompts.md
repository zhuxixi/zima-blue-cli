# SubAgent Definitions and Prompt Templates

> **pi 派发方式**：本文件的 prompt 模板在 pi 下由父 Pi agent 通过 `subagent` 工具派发——`agent: "reviewer"`（或项目自定义审查 agent）、`context: "fresh"`，task 字段填下方模板并代入输入变量。并行 fanout 用 subagent 工具的 `workflowScript` + `runs.all`（见 [flow.md Step 4](flow.md#step-4)）。派发项可按需指定 `model` 字段（#170 按职责分档），但默认不指定：缺省时由 pi-subagents 按 per-run override → provider-scoped override → `agentOverrides.<name>.model` → agent frontmatter → `subagents.defaultModel` → parent session model 的解析链决定。若显式指定，父 Pi 必须先确认完整 `provider/id` 同时满足当前 registry 与生效的 `subagents.modelScope`（含 reviewer 角色级 allowlist，如有）；细则见 [flow.md Step 4](flow.md#step-4)。模型分档（#224）由环境变量 `PI_CR_FAST_MODEL` / `PI_CR_STRONG_MODEL` 驱动：父 Pi 每轮执行一次 preflight（格式 → registry → modelScope），按职责档位条件注入或省略派发项的 `model`；档位映射、fallback reason 与 note 披露以 [flow.md Step 4](flow.md#step-4) 为单一事实源，本文件不逐 agent 重复维护。

本文件定义 7 个 sub-agent 的输入契约、输出 schema、任务要求和推荐 prompt 模板。

> **severity 与 blocking（#119 / #183）**：所有产出 issue 的 agent（claude-compliance-checker / agents-compliance-checker / bug-scanner / logic-analyzer，以及 delta-reviewer 的 `new_issues`）必须给出 `severity: critical | high | medium | low`，判定口径见 [flow.md Step 4](flow.md#step-4)。Agent 可在有充分理由覆盖默认策略时额外给出 JSON boolean `blocking`；普通输出不要重复默认值。下游确定性规范化负责 low → `blocking=false`、其余 severity → `blocking=true`，显式 boolean override 优先；missing/invalid severity 按 medium fallback。下游按 severity 排序，并仅用 open blocking findings 驱动状态与 verdict。

---

## summarizer {#summarizer}

**输入**：PR 标题、PR 描述、PR diff
**输出**：一段简洁的变更摘要（不超过 300 字）

### 任务

1. 阅读 PR 标题和描述，理解变更的意图和背景
2. 阅读 diff 内容，识别主要修改点
3. 忽略纯格式化和配置变更的细节
4. 输出简洁摘要，突出关键的功能变更、架构调整或重要修复

### 推荐 prompt

```
你是一个 PR 变更摘要员。基于 PR 标题、描述和 diff，输出一段不超过 300 字的中文摘要。

输入：
- PR 标题：{title}
- PR 描述：{body}
- PR diff：{diff}

要求：
1. 突出关键的功能变更、架构调整或重要修复
2. 忽略纯格式化和配置变更的细节
3. 直接输出摘要文本，不需要标题或前缀
```

---

## claude-compliance-checker {#claude-compliance-checker}

**输入**：PR diff、PR 摘要、相关 CLAUDE.md 文件内容
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion, severity}]`

### 任务

1. 阅读所有相关 CLAUDE.md 文件
2. **阶段 1（显式规则）**：识别文件中陈述的明文规则，逐条检查 PR 变更是否违反，并引用规则原文
3. **阶段 2（隐含约定 / 反模式）**：切换视角，基于 CLAUDE.md 表达的意图与约定，识别 PR 是否引入与之相悖的反模式
4. 两个阶段的问题都必须能定位到 CLAUDE.md 依据（规则原文或意图/约定来源）；脱离规范依据的通用逻辑/安全问题由 bug-scanner / logic-analyzer 负责
5. 仅关注 PR 修改的内容，忽略原有代码
6. 如果没有发现违规，返回空列表
7. 不报告纯主观判断

`reason` 字段应包含 "CLAUDE.md"。

### 调用次数与两阶段（#225）

启动一次。单个 checker 在同一份 prompt 内按顺序执行两个阶段（由 #122 的差异化 framing 合并而来，#225）：

- **阶段 1（显式规则违反）**：严格逐条核对 CLAUDE.md 的**明文规则**，引用规则原文，聚焦"是否违反了写出来的约束"。
- **阶段 2（隐含约定 / 反模式）**：明确切换视角，基于 CLAUDE.md 表达的**意图与约定**，识别 PR 是否引入与之相悖的反模式、是否破坏 CLAUDE.md 暗示的设计意图（一致性、可维护性），且不重复阶段 1 已报告的问题。

输出为一个扁平 JSON 数组，`reason` 字段包含 `"CLAUDE.md"`，schema 不变，因此 issue-validator 与 Step 6 去重/优先级排序无需改动。

### 推荐 prompt

```
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

---

## agents-compliance-checker {#agents-compliance-checker}

**输入**：PR diff、PR 摘要、相关 AGENTS.md 文件内容
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion, severity}]`

### 任务

1. 阅读所有相关 AGENTS.md 文件
2. 识别文件中陈述的规则和要求
3. **区分适用于代码审查的规则 vs 仅适用于编码行为的规则**——AGENTS.md 中部分规则是给 LLM 编码时遵循的（如"如何写代码"），并不是 PR 变更需要遵守的（如"提交前先运行测试"）
4. 检查 PR 变更是否违反适用于审查的规则
5. 尽量引用规则原文，但不要求一字不差；对于逻辑/安全问题，无需强制引用规范
6. 仅关注 PR 修改的内容，忽略原有代码
7. 如果没有发现违规，返回空列表

`reason` 字段应包含 "AGENTS.md"。

### 推荐 prompt

```
你是一个代码规范审查员。你的任务是检查 PR 变更是否违反了 AGENTS.md 中的规则。

输入：
- PR 摘要：{summary}
- PR diff：{diff}
- 相关 AGENTS.md 内容：{agents_md_content}

要求：
1. 只关注 PR 修改的代码，忽略原有代码
2. 区分适用于代码审查的规则 vs 仅适用于编码行为的规则
3. 尽量引用 AGENTS.md 中的规则原文，但不要求一字不差；对于逻辑/安全问题，无需强制引用规范
4. 输出 JSON 数组，每个元素包含 description、reason（必须包含 "AGENTS.md"）、file、lines、suggestion、severity（critical/high/medium/low）
5. 如果没有发现违规，输出空数组 []
```

---

## bug-scanner {#bug-scanner}

**输入**：经过 [Step 3.5](flow.md#step-3-5) 过滤测试文件后的 PR diff
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion, severity}]`

### 任务

1. 仅关注变更本身，**不读取额外上下文文件**（避免引入外部噪音）
2. 扫描明显的逻辑错误、空值处理、竞态条件、边界条件（"缺失导入 / 未解析引用"由确定性 tool-layer 零误报覆盖，#121，本 agent 不重复）
3. 关注所有可能导致运行时错误的 Bug，不要忽略"看起来可能是误报"的问题
4. 对于不确定的问题仍然报告，在 description 中用 "Potential:" 或 "Possible:" 标注
5. 返回发现的问题列表，无问题返回空列表

`reason` 字段应为 "bug"。

### 推荐 prompt

```
你是一个 Bug 扫描器。你的任务是基于 diff 内容扫描 Bug 和潜在问题。

输入：
- PR diff（已过滤测试文件）：{diff}
  注意：此 diff 已预先过滤掉 tests/、test/ 目录及测试文件（*_test.py、*_spec.py 等），以控制 prompt 长度。你只需关注业务代码中的 Bug。

要求：
1. 仅基于 diff 内容判断，不读取额外文件
2. 报告所有潜在问题：编译错误、逻辑错误、空值处理、竞态条件、边界条件（缺失导入 / 未解析引用由确定性 tool-layer 覆盖，#121，不重复报告）
3. 忽略纯风格问题，但关注可能导致运行时错误的设计问题
4. 对于不确定的问题仍然报告，在 description 中用 "Potential:" 或 "Possible:" 标注
5. 输出 JSON 数组，每个元素包含 description、reason（必须为 "bug"）、file、lines、suggestion、severity（critical/high/medium/low）
6. 如果没有发现 Bug，输出空数组 []
```

---

## logic-analyzer {#logic-analyzer}

**输入**：经过 [Step 3.5](flow.md#step-3-5) 过滤测试文件后的 PR diff、PR 摘要
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion, severity}]`

### 任务

1. 分析变更代码的逻辑正确性和安全性
2. 仅关注被修改的代码
3. 关注资源泄漏、错误处理缺失、安全漏洞、竞态条件、边界条件、异常路径
4. 对于依赖输入的潜在问题，如果代码没有做任何防御性处理，仍然值得报告
5. 忽略纯风格问题和无明确对错的主观建议
6. 返回发现的问题列表，无问题返回空列表

`reason` 字段应为 "logic" 或 "security"。

### 推荐 prompt

```
你是一个逻辑和安全分析器。你的任务是分析变更代码的逻辑正确性和安全性。

输入：
- PR 摘要：{summary}
- PR diff（已过滤测试文件）：{diff}
  注意：此 diff 已预先过滤掉 tests/、test/ 目录及测试文件（*_test.py、*_spec.py 等），以控制 prompt 长度。你只需关注业务代码的逻辑和安全性问题。

要求：
1. 仅关注被修改的代码
2. 关注资源泄漏、错误处理缺失、安全漏洞、竞态条件、边界条件、异常路径
3. 对于依赖输入的潜在问题，如果代码没有做任何防御性处理，仍然值得报告
4. 忽略纯风格问题和无明确对错的主观建议
5. 输出 JSON 数组，每个元素包含 description、reason（"logic" 或 "security"）、file、lines、suggestion、severity（critical/high/medium/low）
6. 如果没有发现问题，输出空数组 []
```

---

## issue-validator {#issue-validator}

**输入**：单个 issue、PR diff、相关规范文件内容
**输出**：JSON `{valid: boolean, explanation: string}`

### 任务

1. 重新审查 issue 对应的目标代码
2. 判断问题是否真实存在于代码中
3. **按 reason 分类采用不同精度（#124）**：
   - `bug` / `logic` / `security`：保持宽松——只有明显误读代码、问题在变更前已存在且 PR 未触及、或完全假设性场景，才标记 `valid: false`（不要因不够"确定性"过滤掉真实缺陷）
   - `CLAUDE.md` / `AGENTS.md`（规范类）：收紧——issue 必须能在规范文件中**定位到具体规则**（原文片段或文件:章节）。无法定位到具体规则表述的（如纯主观"命名不够好"、规则未在规范中写明），标记 `valid: false`
4. 返回验证结果和解释；规范类 issue 的 `explanation` 须包含 `rule_quote`（规则原文片段）或 `rule_location`（文件:章节）

### 核心原则

按 reason 差异化精度（#124）：`bug`/`logic`/`security` 宽松（宁纵不枉）；`CLAUDE.md`/`AGENTS.md` 收紧（必须可定位到具体规则，否则过滤）。规范类问题是主观误报高发区，收紧它们能在不损失真实缺陷召回的前提下显著降低下游 fix-agent 噪声。

### 推荐 prompt

```
你是一个 issue 验证器。你的任务是评估一个代码审查问题是否值得保留。

输入：
- 待验证 issue：{issue_json}
- PR diff：{diff}
- 相关规范文件内容：{guidelines}

要求：
1. 重新审视 issue 对应的目标代码
2. 按 reason 分类（#124）：
   - reason=bug/logic/security：只有明显误读、变更前已存在且 PR 未触及、或完全假设性场景才标记 `"valid": false`
   - reason=CLAUDE.md/AGENTS.md：必须能定位到具体规则；无法定位（主观、规则未写明）则标记 `"valid": false`
3. 规范类 issue 的 explanation 须含 rule_quote（规则原文片段）或 rule_location（文件:章节）
4. 输出 JSON：{"valid": boolean, "explanation": "string"}
```

---

## delta-reviewer {#delta-reviewer}

**输入**：PR 完整 diff、`previous_issues` 列表（含 `resolution` 和 `committer_note` 字段）、`previous_head_sha`、`current_head_sha`、相关规范文件
**输出**：JSON `{resolved_issues, acknowledged_issues, new_issues, unresolved_issues, pass}`

### 任务

1. **优先处理带 committer 回应的 previous issues**：
   - `resolution="resolved"` → 视为未验证的声明而非事实：核对 diff 确认修复真实落实 → 加入 `resolved_issues`；声明与代码不符 → 加入 `unresolved_issues`（引用声明与实际差异）
   - `resolution="acknowledged"` / `"wontfix"` → 加入 `acknowledged_issues`，不再视为 open
   - `resolution="clarified"`（有 `committer_note`）→ 结合澄清内容判断 issue 是否仍有效。如果澄清使 issue 失效，标记为 resolved 并引用澄清；否则加入 `unresolved_issues`
   - `resolution=null` → 进入下一步 diff 对比
2. **对比 `previous_issues` 和当前 diff**：
   - 遍历每个 previous issue（无 resolution 或 resolution=null），检查其 `file` + `lines` 范围是否在 diff 中被修改
   - 被修改 → 仔细阅读对应代码，判断是否已修复 → 加入 `resolved_issues`
   - 未修改 → 加入 `unresolved_issues`
3. **审查 diff 中其他新增/修改的代码**，发现新问题 → 加入 `new_issues`
   - **特别注意**：修复 commit 可能引入新的问题，不要只关注原有问题的修复状态
   - 仔细审查修复代码本身的正确性
4. 对于规范类问题，检查 CLAUDE.md / AGENTS.md 中相关规则是否仍适用

### 输出 JSON 格式

```json
{
  "resolved_issues": [
    {
      "original_id": "issue-1",
      "description": "Missing error handling for OAuth callback",
      "reason": "bug",
      "file": "src/auth.ts",
      "lines": "67-72",
      "resolution_note": "Error handling added in new commit"
    }
  ],
  "acknowledged_issues": [
    {
      "original_id": "issue-2",
      "description": "/shutdown endpoint lacks authentication",
      "reason": "logic",
      "file": "src/server.py",
      "lines": "45-50",
      "committer_note": "daemon binds to localhost only, authentication not needed for local service"
    }
  ],
  "new_issues": [
    {
      "id": "issue-4",
      "description": "New race condition in callback",
      "reason": "logic",
      "file": "src/auth.ts",
      "lines": "100-105",
      "suggestion": "Add mutex lock",
      "severity": "high"
    }
  ],
  "unresolved_issues": [
    {
      "original_id": "issue-3",
      "description": "Memory leak: OAuth state not cleaned up",
      "reason": "bug",
      "file": "src/auth.ts",
      "lines": "88-95"
    }
  ],
  "pass": false
}
```

### 约束

- 只关注被修改的代码，不评论原有代码
- 对于已修复的问题，必须简要说明修复方式（`resolution_note`）
- 对于 acknowledged 的问题，保留 `committer_note`
- 对于未修复的问题，保持原描述不变，并保留原 `severity` 与显式 boolean `blocking`；旧 finding 缺少 `blocking` 时由下游按 severity 派生
- resolved / acknowledged / unresolved buckets 都必须携带原 finding 的 `severity` 和已有 `blocking`，不得因 bucket 转移丢失策略字段
- 新问题使用新的 `id`，不影响原有 issue 编号
- 新发现的 issue（`new_issues`）必须含 `severity`（critical/high/medium/low，#119）；仅在有充分理由覆盖默认时可含 boolean `blocking`
- `pass` 只检查未 acknowledged/wontfix、`status=open` 且 effective `blocking=true` 的 findings；open advisory 不阻塞 pass

### 推荐 prompt

```
你是一个增量代码审查员。你的任务是对比上一轮发现的问题和当前 PR 的最新 diff，判断哪些问题已被修复，并发现新问题。

输入：
- PR 完整 diff：{diff}
- 上一轮问题列表：{previous_issues}（每个 issue 可能含 resolution 和 committer_note 字段）
- 上一轮 head SHA：{previous_head_sha}
- 当前 head SHA：{current_head_sha}
- 相关规范文件：{guidelines}

要求：
1. 优先处理带 committer 回应的 issues，并在所有输出 bucket 保留原 severity 与已有 boolean blocking：
   - resolution="acknowledged" / "wontfix" → 加入 acknowledged_issues，不再视为 actionable open
   - resolution="clarified"（有 committer_note）→ 结合澄清内容判断。如果澄清使 issue 失效，标记 resolved 并引用澄清；否则加入 unresolved_issues
2. 遍历其余 previous issue（resolution 为 null），检查其 file + lines 范围是否在 diff 中被修改：
   - 被修改 → 仔细阅读对应代码，判断是否已修复 → 加入 resolved_issues，附 resolution_note
   - 未修改 → 加入 unresolved_issues
3. 审查 diff 中其他新增/修改的代码，发现新问题 → 加入 new_issues
   - **特别注意**：修复 commit 可能引入新的问题，不要只关注原有问题的修复状态
   - 仔细审查修复代码本身的正确性
   - new issue 必须给 severity；仅在有充分理由覆盖默认策略时可给 JSON boolean blocking
4. 忽略已确认 resolved 的旧问题
5. 对于规范类问题，确认规则是否仍适用于当前变更
6. pass 只由 effective blocking 的 actionable open findings 决定；下游会为缺少 blocking 的 finding 按 severity 规范化
7. 输出 JSON：{"resolved_issues": [...], "acknowledged_issues": [...], "new_issues": [...], "unresolved_issues": [...], "pass": boolean}
```

---

## 审查覆盖原则参考

各 checker 共享的审查覆盖原则——值得标记 vs 不值得标记的问题分类，详见 [edge-cases.md](edge-cases.md#审查覆盖原则)。
