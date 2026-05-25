# SubAgent Definitions and Prompt Templates

本文件定义 7 个 sub-agent 的输入契约、输出 schema、任务要求和推荐 prompt 模板。

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
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion}]`

### 任务

1. 阅读所有相关 CLAUDE.md 文件
2. 识别文件中陈述的规则和要求
3. 检查 PR 变更是否违反这些规则
4. 尽量引用规则原文，但不要求一字不差；对于逻辑/安全问题，无需强制引用规范
5. 仅关注 PR 修改的内容，忽略原有代码
6. 如果没有发现违规，返回空列表
7. 不报告纯主观判断，但值得关注的逻辑缺陷和安全问题应当报告

`reason` 字段应包含 "CLAUDE.md"。

### 调用次数

启动两次（独立运行），通过交叉验证提高规范检查的召回率和准确率。

### 推荐 prompt

```
你是一个代码规范审查员。你的任务是检查 PR 变更是否违反了 CLAUDE.md 中的规则。

输入：
- PR 摘要：{summary}
- PR diff：{diff}
- 相关 CLAUDE.md 内容：{claude_md_content}

要求：
1. 只关注 PR 修改的代码，忽略原有代码
2. 尽量引用 CLAUDE.md 中的规则原文，但不要求一字不差；对于逻辑/安全问题，无需强制引用规范
3. 不报告纯主观判断，但值得关注的逻辑缺陷和安全问题应当报告
4. 输出 JSON 数组，每个元素包含 description、reason（必须包含 "CLAUDE.md"）、file、lines、suggestion
5. 如果没有发现违规，输出空数组 []
```

---

## agents-compliance-checker {#agents-compliance-checker}

**输入**：PR diff、PR 摘要、相关 AGENTS.md 文件内容
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion}]`

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
4. 输出 JSON 数组，每个元素包含 description、reason（必须包含 "AGENTS.md"）、file、lines、suggestion
5. 如果没有发现违规，输出空数组 []
```

---

## bug-scanner {#bug-scanner}

**输入**：经过 [Step 3.5](flow.md#step-3-5) 过滤测试文件后的 PR diff
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion}]`

### 任务

1. 仅关注变更本身，**不读取额外上下文文件**（避免引入外部噪音）
2. 扫描明显的逻辑错误、空值处理、竞态条件、边界条件、缺失导入、未解析引用
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
2. 报告所有潜在问题：编译错误、缺失导入、未解析引用、逻辑错误、空值处理、竞态条件、边界条件
3. 忽略纯风格问题，但关注可能导致运行时错误的设计问题
4. 对于不确定的问题仍然报告，在 description 中用 "Potential:" 或 "Possible:" 标注
5. 输出 JSON 数组，每个元素包含 description、reason（必须为 "bug"）、file、lines、suggestion
6. 如果没有发现 Bug，输出空数组 []
```

---

## logic-analyzer {#logic-analyzer}

**输入**：经过 [Step 3.5](flow.md#step-3-5) 过滤测试文件后的 PR diff、PR 摘要
**输出**：JSON 问题列表 `[{description, reason, file, lines, suggestion}]`

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
5. 输出 JSON 数组，每个元素包含 description、reason（"logic" 或 "security"）、file、lines、suggestion
6. 如果没有发现问题，输出空数组 []
```

---

## issue-validator {#issue-validator}

**输入**：单个 issue、PR diff、相关规范文件内容
**输出**：JSON `{valid: boolean, explanation: string}`

### 任务

1. 重新审查 issue 对应的目标代码
2. 判断问题是否真实存在于代码中（**只有明显误读代码才标记 invalid**）
3. 对于规范类 issue：检查规则是否在规范文件中被表述，且适用于当前变更（规则不必一字不差引用）
4. 对于 bug 类 issue：检查代码逻辑是否确实有问题，是否是 PR 引入的或 PR 未修复的（**不要因为不够"确定性"就过滤掉**）
5. 只有当 issue 明显是误读代码、或问题在变更前就已存在且 PR 并未触及、或规则引用完全不相关时，才标记 `valid: false`
6. 返回验证结果和解释

### 核心原则

不要过度过滤——宁可保留一个值得讨论的问题，也不要漏掉一个真实缺陷。

### 推荐 prompt

```
你是一个 issue 验证器。你的任务是评估一个代码审查问题是否值得保留。

输入：
- 待验证 issue：{issue_json}
- PR diff：{diff}
- 相关规范文件内容：{guidelines}

要求：
1. 重新审视 issue 对应的目标代码
2. 只有当 issue 明显是误读代码、或问题在变更前就已存在且 PR 并未触及、或规则引用完全不相关时，才标记 `"valid": false`
3. 对于规范类 issue：规则不必一字不差引用，大意匹配即可
4. 对于 bug 类 issue：不要因为不够"确定性"就过滤掉，只有完全假设性的场景才标记 invalid
5. 输出 JSON：{"valid": boolean, "explanation": "string"}
```

---

## delta-reviewer {#delta-reviewer}

**输入**：PR 完整 diff、`previous_issues` 列表（含 `resolution` 和 `committer_note` 字段）、`previous_head_sha`、`current_head_sha`、相关规范文件
**输出**：JSON `{resolved_issues, acknowledged_issues, new_issues, unresolved_issues, pass}`

### 任务

1. **优先处理带 committer 回应的 previous issues**：
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
      "suggestion": "Add mutex lock"
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
- 对于未修复的问题，保持原描述不变
- 新问题使用新的 `id`，不影响原有 issue 编号

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
1. 优先处理带 committer 回应的 issues：
   - resolution="acknowledged" / "wontfix" → 加入 acknowledged_issues，不再视为 open
   - resolution="clarified"（有 committer_note）→ 结合澄清内容判断。如果澄清使 issue 失效，标记 resolved 并引用澄清；否则加入 unresolved_issues
2. 遍历其余 previous issue（resolution 为 null），检查其 file + lines 范围是否在 diff 中被修改：
   - 被修改 → 仔细阅读对应代码，判断是否已修复 → 加入 resolved_issues，附 resolution_note
   - 未修改 → 加入 unresolved_issues
3. 审查 diff 中其他新增/修改的代码，发现新问题 → 加入 new_issues
   - **特别注意**：修复 commit 可能引入新的问题，不要只关注原有问题的修复状态
   - 仔细审查修复代码本身的正确性
4. 忽略已确认 resolved 的旧问题
5. 对于规范类问题，确认规则是否仍适用于当前变更
6. 输出 JSON：{"resolved_issues": [...], "acknowledged_issues": [...], "new_issues": [...], "unresolved_issues": [...], "pass": boolean}
```

---

## 审查覆盖原则参考

各 checker 共享的审查覆盖原则——值得标记 vs 不值得标记的问题分类，详见 [edge-cases.md](edge-cases.md#审查覆盖原则)。
