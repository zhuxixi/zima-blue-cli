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

### Step Δ2a: 并行扫描新增 hunk（#123，防回归）

delta-reviewer 专注旧 issues 的 resolved / acknowledged / unresolved 对比（需连贯上下文）；但**修复 commit 是回归高发区**，单 agent 易因"确认偏误"漏报新引入的问题。因此对本次新增/修改的 hunk 额外**并行**启动 bug-scanner + logic-analyzer 各 1 个（复用 [subagent-prompts.md](subagent-prompts.md) 的现成 prompt）：

使用 `Bash` 取增量 diff（`previous_head_sha..current_head_sha`）：
```bash
git -C <repo> diff <previous_head_sha> <current_head_sha> -- . ':(exclude)tests' ':(exclude)test'
# 或 gh api repos/{owner}/{repo}/compare/{previous}...{current}
```

把该 delta-diff（经 [Step 3.5](flow.md#step-3-5) 的 `compress_diff.py --filter-tests` 预处理）分别喂给 bug-scanner 与 logic-analyzer。它们产出的 issue 与 delta-reviewer 自身的 `new_issues` 合并（见 [Step Δ4](#step-Δ4)）。新增 hunk 为空（纯删除/revert）时返回空列表，优雅降级。

> delta-reviewer 仍保留"扫新问题"职责：它对比旧 issue 修复状态时本就读新代码，顺手报告明显新问题仍有价值；Δ2a 的并行 scanner 是**补充**（多视角防回归），不是替代。

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
- `new_issues` → 合并 [Step Δ2a](#step-Δ2a) 的 bug-scanner / logic-analyzer 结果（沿用 [Step 6](flow.md#step-6) 去重：相同 file+lines+reason 合并），统一生成新 `id`（如 `"issue-{max_id+1}"`），标记 `status="open"`，`first_round = current_round`

### Step Δ5: 继续至 Step 6

将汇总后的问题列表传入 [Step 6](flow.md#step-6)，继续执行 Step 6-9-10 的标准流程。

注意：[Step 10](flow.md#step-10) 输出状态报告时，`Status` 为 `PASS` 的条件是不存在 `status="open"` 且 `resolution != "acknowledged"` 的 issues。

---

## 与完整流程的区别

| 步骤 | 完整流程 | 增量流程 |
|------|---------|---------|
| Step 3 | summarizer + 5 个审查 Agent | delta-reviewer 1 个 Agent |
| Step 4 | 5 个并行审查 Agent | delta-reviewer（旧 issue 对比）+ Δ2a 并行 bug/logic scanner（新 hunk，#123） |
| Step 5 | 每个 issue 单独验证 | 由 delta-reviewer 内部完成对比验证 |
| 输出 | 全新问题列表 | resolved + acknowledged + new + unresolved 分类 |

**为什么增量轮仍用多 agent（#123）**：旧 issues 的 resolved/acknowledged/unresolved 对比需要连贯上下文 → 仍由 delta-reviewer 单 agent 完成（它不可替代的部分）。但**修复 commit 是回归高发区**，单 agent 易因"确认偏误"漏报新引入的问题 → 对新增 hunk 额外并行 bug-scanner + logic-analyzer（[Step Δ2a](#step-Δ2a)）。这消除了"最高风险阶段反而审查最弱"的矛盾（原先增量轮从 5 agent 坍缩为 1）。
