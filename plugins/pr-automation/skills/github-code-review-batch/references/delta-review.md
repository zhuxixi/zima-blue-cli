# Delta Review Flow

当 [Step 0](flow.md#step-0-3) 检测到 PR 有新的 commit（相对于上一轮 review）时，执行**增量审查**而非完整审查。本流程替代完整流程中的 [Step 3](flow.md#step-3) – [Step 5](flow.md#step-5)。

---

## 适用场景

- [Step 0](flow.md#step-0-3) 检测到 previous review metadata 且当前 head SHA != `previous_head_sha`

---

## 输入

- `previous_issues`：从上一轮 metadata 提取的问题列表（含 `id`, `description`, `reason`, `file`, `lines`, `status`, `first_round`），可能含 `resolution` 和 `committer_note` 字段（由 [Step 0.2a](flow.md#step-0-2a) 填充）
- `previous_head_sha`：上一轮 review 时的 head SHA
- `current_head_sha`：当前 PR head SHA
- PR 完整 diff（`gh pr diff` 输出）
- 相关规范文件（CLAUDE.md / AGENTS.md）

---

## 执行步骤

### Step Δ1: 获取完整 diff

使用 `Bash` 执行 `gh pr diff <PR>` 获取完整 diff。

### Step Δ2: 启动 delta-reviewer Agent

使用 `Agent` 启动 [delta-reviewer](subagent-prompts.md#delta-reviewer)（前台，1 个 Agent），输入：
- PR 完整 diff
- `previous_issues` 列表
- `previous_head_sha`
- `current_head_sha`
- 相关规范文件内容

### Step Δ3: 收集 delta-reviewer 结果

delta-reviewer 输出 JSON：

```json
{
  "resolved_issues": [
    {
      "original_id": "issue-1",
      "description": "...",
      "reason": "bug",
      "file": "src/auth.ts",
      "lines": "67-72",
      "resolution_note": "Error handling added in new commit"
    }
  ],
  "acknowledged_issues": [
    {
      "original_id": "issue-2",
      "description": "...",
      "reason": "logic",
      "file": "src/server.py",
      "lines": "45-50",
      "committer_note": "..."
    }
  ],
  "new_issues": [
    {
      "id": "issue-4",
      "description": "...",
      "reason": "logic",
      "file": "src/auth.ts",
      "lines": "100-105",
      "suggestion": "..."
    }
  ],
  "unresolved_issues": [
    {
      "original_id": "issue-3",
      "description": "...",
      "reason": "bug",
      "file": "src/auth.ts",
      "lines": "88-95"
    }
  ],
  "pass": false
}
```

### Step Δ4: 汇总问题列表

构建当前轮次的完整 issues 列表：
- `resolved_issues` → 保留原 `id`，标记 `status="resolved"`，`resolution="resolved"`
- `acknowledged_issues` → 保留原 `id`，标记 `status="open"`，`resolution="acknowledged"`，保留 `committer_note`
- `unresolved_issues` → 保留原 `id`，标记 `status="open"`，`resolution=null`
- `new_issues` → 生成新 `id`（如 `"issue-{max_id+1}"`），标记 `status="open"`，`first_round = current_round`

### Step Δ5: 继续至 Step 6

将汇总后的问题列表传入 [Step 6](flow.md#step-6)，继续执行 Step 6-9-10 的标准流程。

注意：[Step 10](flow.md#step-10) 输出状态报告时，`Status` 为 `PASS` 的条件是不存在 `status="open"` 且 `resolution != "acknowledged"` 的 issues。

---

## 与完整流程的区别

| 步骤 | 完整流程 | 增量流程 |
|------|---------|---------|
| Step 3 | summarizer + 5 个审查 Agent | delta-reviewer 1 个 Agent |
| Step 4 | 5 个并行审查 Agent | 由 delta-reviewer 替代 |
| Step 5 | 每个 issue 单独验证 | 由 delta-reviewer 内部完成对比验证 |
| 输出 | 全新问题列表 | resolved + acknowledged + new + unresolved 分类 |

**为什么用单 agent 替代 5 agent**：增量审查需要在"对比上一轮 issues 与新 diff"和"扫描新 commit 中的新问题"两件事之间做交叉判断，分散到多个独立 agent 后再合并会丢失上下文。delta-reviewer 在一个 agent 内完成这两件事，更连贯。
