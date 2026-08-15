# Flow: github-code-review-batch

本文件包含 SKILL.md 主流程总览中各 Step 的详细规则。SKILL.md 通过锚点引用本文件具体小节。

---

## Step 0: 审查类型判断 {#step-0}

本 Skill 为非监听模式，每次调用都是独立短会话。状态完全通过 PR 评论中的 metadata 持久化。在正式审查之前，判断本次审查的类型：首次完整审查，还是基于前一轮 metadata 的增量审查。

### 0.1 检测 previous review metadata {#step-0-1}

使用 `Bash` 执行：
```bash
gh pr view <PR> --json reviews --jq '.reviews[] | {body: .body, submitted_at: .submittedAt}'
```

把 JSON 通过 stdin 传给 `scripts/parse_metadata.py`，脚本返回最新一条 Claude Code 评论的 cc-cr-meta JSON（无则返回 `{}`）。详见 [scripts/parse_metadata.py](../scripts/parse_metadata.py)。

脚本内部规则：
1. 评论 body 包含 `"Generated with Claude Code"`
2. 评论 body 包含 `"<!-- cc-cr-meta"`
3. 按 `submitted_at` 排序，取最新一条
4. 用正则 `<!-- cc-cr-meta\n(.*?)\n-->` 提取 JSON

得到 metadata 字段：`round`, `head_sha`, `previous_head_sha`, `issues` 等。

### 0.2a 读取并解析 committer 回应 {#step-0-2a}

对于增量审查，在提取 previous_issues 后，需要读取 committer 对上一轮 issues 的回应，避免重复标记已解释/已拒绝修复的问题。

**执行步骤：**

1. 使用 `Bash` 执行 `gh pr view <PR> --comments` 获取所有 PR 评论
2. 过滤掉所有 AI CR 评论（Claude Code 评论 body 包含 `"Generated with Claude Code"`，Kimi CLI 评论 body 包含 `"<!-- kimi-cr-meta"`），保留 committer / human reviewer 的评论。两个 Agent 的审查结论互不参考，保证交叉验证的独立性
3. 对每个 `status="open"` 的 previous issue，检查 committer 评论中是否提及该 issue：
   - 匹配方式：issue 描述前 10 个单词、或 `file:lines` 组合、或 `"issue-{id}"` 引用
4. **分类 committer 回应**（关键词匹配，不区分大小写）：

| 信号关键词 | 分类 (`resolution`) | 处理方式 |
|-----------|---------------------|---------|
| "wontfix", "won't fix", "by design", "intentional", "not a bug", "不需要修复", "不修复", "设计如此" | `wontfix` | 标记为 acknowledged，不列入 "Still open" |
| "fixed", "已修复", "done", "resolved", "addressed" | `resolved` | 标记 `status="resolved"`（delta-reviewer 再验证） |
| "clarify", "说明", "actually", "context:", "returns", "只返回", "strictly" | `clarified` | 添加 `committer_note`，传递给 delta-reviewer |
| 无明确信号 | `null` | 无变化，按原有流程处理 |

5. 当分类为 `wontfix` 或 `clarified` 时，在对应 issue 上增加字段：
   - `resolution`: `"acknowledged"` / `"wontfix"` / `"resolved"` / `null`
   - `committer_note`: committer 评论中的相关原文片段

**为什么不完全脚本化这一步**：分类是启发式的，"前 10 个单词"匹配本身需要 NLP 直觉，完全脚本化容易因边界情况失真。不确定时，优先分类为 `clarified` 而非 `wontfix`，以保留人工判断空间。

**可脚本化的核心（#125）**：关键词表与三种匹配键（`issue-{id}` / `file:lines` / 描述前若干 token）已固化在 [scripts/match_committer_response.py](../scripts/match_committer_response.py)，作为可单测的确定性参考实现（优先级 resolved > clarified > wontfix）。LLM 可把它当作"候选匹配 + 初步分类"的预筛，再对歧义做最终裁决；该脚本的关键词表是单一事实来源，本节表格与之保持一致。

### 0.3 判断分支 {#step-0-3}

**有 previous review metadata？**
- 是 → 使用 `Bash` 执行 `gh pr view <PR> --json headRefOid --jq '.headRefOid'` 获取当前 head SHA
  - 当前 SHA == `previous_head_sha` → **无新 commit**
    - 输出：`"No new commits since Round-{round} review. Previous issues may still be open."`
    - 列出仍 open 的 issues（排除已标记 `resolution="acknowledged"` / `"wontfix"` 的）
    - 输出【状态报告】（见 [Step 10](#step-10)），Status: `NO_NEW_COMMITS`
    - 结束
  - 当前 SHA != `previous_head_sha` → **有新 commit**
    - 标记当前为 `Round = round + 1`
    - 提取 `previous_issues = issues`
    - 执行 [Step 0.2a](#step-0-2a)：读取并解析 committer 对上一轮 issues 的回应，更新 `previous_issues` 的 `resolution` 和 `committer_note` 字段
    - 进入【增量审查流程】（见 [delta-review.md](delta-review.md)），跳过 Step 1 之后的 Step 3-5
- 否 → 首次审查 → 走完整流程（Round = 1）

### 0.4 异常情况 {#step-0-4}

- **Metadata 字段部分损坏但能拿到 round**：以读到的 round 为底线，本轮取 `round + 1`，其余字段按 fallback 默认（如 `previous_head_sha=null`，`previous_issues=[]`），输出警告
- **Metadata 完全无法解析（连 round 都拿不到）**：报错并停止执行。**不再静默 fallback 到 Round-1**，因为对已存在 Round-N 历史的 PR 重置 round 会破坏外部调度器的状态机
- `gh pr view --json reviews` 失败 → 视为无 previous review，继续正常 Round-1 流程

---

## Step 1: PR 资格审查 {#step-1}

使用 `Bash` 执行 `gh pr view <PR>` 和 `gh pr view <PR> --comments` 检查 PR 状态。

检查以下任一条件：
- PR 是否已关闭 (state: CLOSED)
- PR 是否为草稿 (isDraft: true)
- PR 是否是 trivial PR（如 dependabot、renovate、纯格式化、仅修改配置文件）
- PR 是否是自动化 PR（PR 标题或描述包含 "automated"、"bot" 等标识）

如果上述任一条件为真，立即停止执行，向用户说明原因，不继续审查。

**为什么不检查"是否已有 bot 评论"**：与监听模式不同，非监听模式下同一 PR 会被外部调度器多次审查（首次 → 增量 → 增量...），这是预期行为。Step 0 会通过 metadata 和 SHA 对比自动判断是首次审查还是增量审查。

**为什么不跳过 AI 生成的 PR**：AI 生成的 PR 也可能存在规范违规或逻辑错误，因此不跳过。

如何判断 trivial PR：
- 标题包含 "bump"、"update"、"dependabot"、"renovate"、"format"、"lint"
- 只修改了配置文件（如 `.github/workflows`、`.prettierrc`、锁文件）
- 变更行数极少且明显无意义

---

## Step 2: 收集项目规范 {#step-2}

使用 `Bash` 执行 `gh pr diff <PR> --name-only` 获取变更文件列表。

根据变更文件路径，读取以下规范文件（使用 `Read` 工具）：
- 根目录的 `CLAUDE.md`
- 根目录的 `AGENTS.md`
- 变更文件所在子目录的 `CLAUDE.md`
- 变更文件所在子目录的 `AGENTS.md`

例如，如果变更文件为 `src/utils/helpers.py`，则需要检查：
- `./CLAUDE.md`
- `./AGENTS.md`
- `./src/CLAUDE.md`
- `./src/AGENTS.md`
- `./src/utils/CLAUDE.md`
- `./src/utils/AGENTS.md`

将读取到的规范文件内容汇总为一个规范上下文字符串，供后续审查 Agent 使用。如果某目录下没有规范文件，则跳过。

**冲突处理**：子目录的规范文件优先于父目录。如果存在冲突，以最深目录的规范为准。

---

## Step 3: 获取 PR 摘要 {#step-3}

使用 `Bash` 执行：
- `gh pr view <PR>` 获取 PR 标题和描述
- `gh pr diff <PR>` 获取完整 diff

使用 `Agent` 启动 summarizer subagent（详见 [subagent-prompts.md#summarizer](subagent-prompts.md#summarizer)），输入包括 PR 标题、PR 描述、PR diff 内容。summarizer 输出一段简洁的变更摘要（不超过 300 字），帮助后续审查 Agent 快速理解变更意图。

---

## Step 3.5: Diff 预处理 {#step-3-5}

在将 diff 传入 sub-agent 之前，进行预处理和长度保护，避免完整 diff 直接嵌入 prompt 导致 JSON 解析失败（参见原 issue #4）。

调用 [scripts/compress_diff.py](../scripts/compress_diff.py) 执行预处理：

**按 agent 类型过滤 diff**：
- CLAUDE.md checker ×2、AGENTS.md checker：接收**完整 diff**（规范检查需要完整上下文），仅应用长度兜底
  ```bash
  gh pr diff <PR> | python scripts/compress_diff.py --max-len 4000 \
      --meta-file /tmp/cc-cr-diff-meta.json > /tmp/cc-cr-diff.txt
  ```
- Bug scanner、Logic analyzer：接收**过滤后的 diff**，排除测试相关文件
  ```bash
  gh pr diff <PR> | python scripts/compress_diff.py --filter-tests --max-len 4000 \
      --meta-file /tmp/cc-cr-diff-meta.json > /tmp/cc-cr-diff.txt
  ```

`--meta-file`（#120）写一份覆盖 meta（`diff_truncated`、`covered_files`/`total_files`、被丢弃文件等）到 sidecar JSON，供 [Step 10](#step-10) 在状态报告中显式提示部分覆盖；各 agent 改为读取 `/tmp/cc-cr-diff.txt` 作为 diff 输入。

**脚本内部规则**：
1. `--filter-tests` 排除：`tests/`、`test/` 目录下的文件；`*_test.py`、`*_spec.py`、`*_tests.py`；`.test.`、`.spec.` 等测试文件
2. `--max-len N`：超长时先压缩为 hunk-only（保留 +/- 行及前后各 2 行上下文）；仍超长则截断至 N 字符并附 `... (diff truncated)`，并在 meta 中置 `diff_truncated: true`（#120）

**效果**：过滤后 diff 长度通常减少 60-70%（测试文件往往占据大比例 diff）。

---

## Step 4: 5 个并行审查 Agent {#step-4}

**确定性 tool-layer（#121）**：启动 LLM agent 之前，先运行 [scripts/run_tool_layer.py](../scripts/run_tool_layer.py)——按仓库 manifest 自动探测并执行 `ruff` / `mypy` / `tsc` / `eslint`（缺失则静默降级，不报错）。它用零误报工具吃掉"缺失导入 / 未解析引用 / 类型错误 / 语法错误"，产出 reason 为 `lint` / `typecheck` 的 issue，与下面 agent 的结果一起进入 [Step 5](#step-5) / [Step 6](#step-6)。bug-scanner 不再重复这些类别。

启动 5 个并行 `Agent`，每个接收经过 [Step 3.5](#step-3-5) 预处理的输入包：
- **CLAUDE.md checker ×2、AGENTS.md checker**：完整 diff（或截断后的）+ 变更摘要 + PR 标题和描述 + 相关规范文件内容
- **Bug scanner、Logic analyzer**：过滤掉测试文件的 diff（或截断后的）+ 变更摘要 + PR 标题和描述

5 个 agent 的具体职责、输入输出契约、prompt 模板见 [subagent-prompts.md](subagent-prompts.md)：
- [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker)（启动两次，独立运行，交叉验证）
- [agents-compliance-checker](subagent-prompts.md#agents-compliance-checker)
- [bug-scanner](subagent-prompts.md#bug-scanner)
- [logic-analyzer](subagent-prompts.md#logic-analyzer)

每个 Agent 输出统一的 JSON 格式问题列表：

```json
[
  {
    "description": "问题描述（1-2 句话）",
    "reason": "问题类别，如 'CLAUDE.md' / 'AGENTS.md' / 'bug' / 'logic' / 'security'",
    "file": "相对仓库根目录的文件路径",
    "lines": "行号范围，格式如 '45-52'",
    "suggestion": "可选的修复建议",
    "severity": "critical | high | medium | low（#119）"
  }
]
```

如果未发现任何问题，输出空列表 `[]`。

**severity 判定口径（#119）**：每个 issue 必须给出 `severity`，供状态报告计算 `Critical issues` 计数与 `Verdict`：

| severity | 适用 |
|----------|------|
| `critical` | 数据损坏、安全漏洞、崩溃/不可恢复错误、阻塞主流程 |
| `high` | 资源泄漏、错误处理缺失、很可能触发的边界 bug |
| `medium` | 偶发边界、逻辑健壮性、规范硬性违规 |
| `low` | 命名/风格类规范、轻微不一致 |

issue-validator 验证时若 agent 未给 severity，按 `medium` 兜底。`build_review_body.py` 渲染时按 severity 降序排列（critical 在前），metadata `issues[]` 保留原始顺序。

**为什么 CLAUDE.md checker 跑两次（#122：差异化而非复跑）**：两个 checker 使用**不同 framing**（Checker-1 显式规则、Checker-2 隐含约定/反模式），让召回增益来自视角互补而非采样噪声。两者的 `reason` 都为 `"CLAUDE.md"`、schema 不变，下游无需改动。这与"双 CR Agent 交叉验证体系"（Claude Code vs Kimi CLI）是两个不同层次的冗余——前者在同一 skill 内部，后者跨 agent。

---

## Step 5: Issue 验证 {#step-5}

对 [Step 4](#step-4) 中发现的每一个 issue，启动一个并行 `Agent` 进行验证。详见 [subagent-prompts.md#issue-validator](subagent-prompts.md#issue-validator)。

验证 agent 输入：
- 单个 issue 的完整信息
- PR diff
- 相关规范文件内容

验证 agent 输出 JSON `{valid: boolean, explanation: string}`。只有 `valid: true` 的 issue 才会进入下一步。`valid: false` 的 issue 被直接丢弃。

**核心原则（#124：按 reason 差异化精度）**：验证 agent 确认问题不是明显误读。对 `bug`/`logic`/`security` 保持宽松（宁纵不枉，只有明显误读/变更前已存在/完全假设性才标 `valid: false`）；对 `CLAUDE.md`/`AGENTS.md`（规范类，主观误报高发区）收紧——必须能在规范中**定位到具体规则**，否则标 `valid: false`，且 explanation 含 `rule_quote`/`rule_location`。这样在不损失真实缺陷召回的前提下降低喂给 fix-agent 的噪声。

---

## Step 6: 过滤与汇总 {#step-6}

对通过验证的 issue 进行后处理：

1. **丢弃无效 issue**：移除所有 `valid: false` 的 issue
2. **去重**：如果多个 issue 的 `file`、`lines`、`reason` 相同或高度相似，合并为一个
3. **排序优先级**（#119：severity 优先）：
   1. 先按 `severity` 降序（critical → high → medium → low）
   2. 再按 reason 类别：CLAUDE.md → AGENTS.md → bug → logic / security

   最终渲染顺序由 `build_review_body.py` 保证（见 [output-examples.md](output-examples.md)）。

去重规则：
- 如果两个 issue 指向同一个文件、同一行范围、且原因相同，视为重复
- 如果描述内容高度相似（超过 80% 相似度），也视为重复
- 合并时保留描述更详细、建议更具体的一个

**可选：跨 PR suppress（#126，默认 off）**：若仓库根存在 `.claude/cr-suppressions.json`，去重后调用 [scripts/apply_suppressions.py](../scripts/apply_suppressions.py) 把命中的 issue 降级为 `suppressed`——不计入 open、不触发 fix-agent，但仍出现在终端输出供人工核验。条目格式：

```json
[
  {"reason": "CLAUDE.md", "pattern": "naming", "expires": "2026-12-31", "rationale": "wontfix on #12,#18"},
  {"pattern": "ci 配置", "expires": null, "rationale": "by design"}
]
```

匹配规则：`reason` 精确匹配 AND `pattern`（描述子串、不区分大小写）命中；`expires` 过期则忽略该条。无文件 = 无抑制。**宁可漏抑不可误抑**：条目应窄；committer 仍可在 PR 评论 override。

---

## Step 7: 最终资格审查 {#step-7}

使用 `Bash` 执行 `gh pr view <PR> --json state` 再次检查 PR 状态。

如果 PR 已关闭 (closed) 或已合并 (merged)，立即停止执行，**不发布评论**。

**为什么需要二次检查**：整个审查流程（特别是并行 Agent 执行）可能需要数分钟时间，在此期间 PR 状态可能发生变化。直接发布评论会污染已关闭 PR 的评论流。

---

## Step 8: 终端输出 {#step-8}

输出 Markdown 格式的审查报告到终端。完整模板与字段拼装由 [scripts/build_review_body.py](../scripts/build_review_body.py) 生成；终端输出可直接用脚本输出的 Part B（Markdown 部分）。

精简模板：

发现问题时：
```markdown
### Code Review

Found N issues:

1. {description} ({reason}, {severity})

https://github.com/owner/repo/blob/{full-sha}/{file}#L{start}-L{end}
```

无问题时：
```markdown
### Code Review

No issues found. Checked for bugs, CLAUDE.md and AGENTS.md compliance.
```

完整 Round-N 多轮格式见 [output-examples.md](output-examples.md)。

代码链接格式要求：
- 使用 `Bash` 执行 `gh pr view <PR> --json headRefOid --jq '.headRefOid'` 获取 PR head SHA（40 字符）
- 链接格式必须严格为：`https://github.com/owner/repo/blob/[sha]/path#L[start]-L[end]`
- 行范围至少包含 1 行上下文（评论目标行的前后至少各 1 行）
- 仓库 owner 和 repo 名通过 `gh pr view --json headRepositoryOwner,headRepository` 获取

行号提取方法：
- 在 diff 中，新增内容以 `+` 开头，对应的行号在 diff hunk 头部标明
- 例如 `@@ -45,7 +67,9 @@` 表示旧文件从第 45 行开始，新文件从第 67 行开始
- 计算目标代码在新文件中的实际行号

---

## Step 9: 构建并发布 PR Review 评论 {#step-9}

此步骤构建包含 metadata 的结构化 review 评论，并发布到 PR。

### 9.1 构建评论 Body

调用 [scripts/build_review_body.py](../scripts/build_review_body.py)，输入 JSON 包括：
- `round`, `pr_number`, `head_sha`, `previous_head_sha`
- `repo_owner`, `repo_name`
- `issues`（含 status / resolution / committer_note / severity）
- 分类计数：`resolved_count`, `acknowledged_count`, `new_count`, `total_issues`
- `timestamp`（ISO 8601）

脚本输出完整 review body，由两部分组成：

**Part A: HTML Comment Metadata（机器可读，GitHub 渲染时隐藏）**

```markdown
<!-- cc-cr-meta
{"round":N,"pr_number":...,"head_sha":"...","previous_head_sha":"...","total_issues":...,"resolved_count":...,"new_count":...,"acknowledged_count":...,"issues":[...],"timestamp":"..."}
-->
```

字段说明：
- `round`: 当前轮次（首次审查为 1，增量审查为 N+1）
- `pr_number`: PR 编号
- `head_sha`: 当前 PR head commit 的完整 SHA（40 字符）
- `previous_head_sha`: 上一轮 review 时的 head SHA（Round-1 为 null）
- `total_issues`: 当前轮次统计的问题总数（不含 acknowledged）
- `resolved_count`: 本轮标记为 resolved 的问题数（Round-1 为 0）
- `new_count`: 本轮新发现的问题数
- `acknowledged_count`: 本轮标记为 acknowledged / wontfix 的问题数
- `issues`: 问题数组，每个元素含 `status`（"open"/"resolved"）、`resolution`（"acknowledged"/"wontfix"/"resolved"/null）、`committer_note`（string 或 null）、`severity`（"critical"/"high"/"medium"/"low"，#119，缺省 medium）
- `timestamp`: ISO 8601 格式时间戳

**Part B: Markdown 人类可读部分**

模板分三种：Round-1、Round-N（增量）、All-resolved。三种完整模板见 [output-examples.md](output-examples.md)。

### 9.2 发布 Review 评论

使用 `Bash` 执行：
```bash
# 将 review body 写入临时文件（避免 shell 转义和长命令问题）
python scripts/build_review_body.py < input.json > /tmp/cc-cr-{pr_number}.md
gh pr review <PR> --comment --body-file /tmp/cc-cr-{pr_number}.md
```

注意：
- 每轮审查都发布**新评论**，不编辑旧评论。原因：metadata 是审查历史的事实记录，覆写会丢失中间状态
- 必须包含 `"🤖 Generated with Claude Code"` 标识，用于后续识别（脚本已固化）
- 必须包含 `"### Code Review | Round-{N}"` 标题（脚本已固化）
- 此步骤必须执行：只要资格审查通过，无论是否发现问题，都必须发布评论
- 如果 `gh pr review` 命令失败，向用户报告错误详情，不重复尝试

---

## Step 10: 状态报告输出 {#step-10}

每次审查结束时，无论发现问题与否，都必须输出状态报告到终端。状态报告是供外部调度器（如 zima daemon）和 fix agent 消费的机器可读摘要。

调用 [scripts/render_status_report.py](../scripts/render_status_report.py) 生成。

### 输出时机

以下情况均须输出状态报告：
- [Step 0](#step-0-3) 检测到无新 commit → 输出当前 open issues 状态，Status: `NO_NEW_COMMITS`
- [Step 6](#step-6) 过滤后存在 open issues → 输出问题统计，Status: `NEEDS_FIX`
- [Step 6](#step-6) 过滤后无 open issues → 输出 "All issues resolved"，Status: `PASS`
- PR 在 [Step 7](#step-7) 被判定为已关闭/已合并 → 已停止，**不输出**状态报告

### 状态报告格式

```
=== CR Batch Status Report ===
PR: #{pr_number} | Round: {round} | Head SHA: {head_sha}
Previous Head SHA: {previous_head_sha}
Total open issues: {open_count}
- New this round: {new_count}
- Still open from previous: {unresolved_count}
- Resolved this round: {resolved_count}
- Acknowledged / Won't Fix: {acknowledged_count}
Status: {status}
Critical issues: {critical_count}
Verdict: {verdict}
================================
```

字段说明：
- `Total open issues`：当前仍 open 的问题总数（不含 acknowledged）
- `Critical issues`：当前 open issues 中 `severity=critical` 的数量（#119，向后兼容：未提供视为 0）
- `Status` 枚举三态（不变，zima daemon 仍 grep 此行）：
  - `NEEDS_FIX` — 仍有 open issues 需要修复
  - `PASS` — 无 open issues（可能仍有 acknowledged）
  - `NO_NEW_COMMITS` — Step 0 检测到无新 commit
- `Verdict`（#119 新增，由 `Status` + `critical_count` + `open_count` 派生，不替换三态）：
  - `SKIP` — NO_NEW_COMMITS
  - `BLOCK_MERGE` — critical_count > 0
  - `READY_TO_MERGE` — open_count == 0
  - `MERGE_WITH_CAUTION` — 其余（有 open 但无 critical）

`critical_count` 由 Step 6 汇总后的 open issues 中 severity=critical 的个数得出，作为 `critical_count` 字段传入 `render_status_report.py`。

**部分覆盖提示（#120）**：若 [Step 3.5](#step-3-5) 的 `--meta-file` 指示 `diff_truncated: true`，把 `diff_truncated` / `covered_files` / `total_files` 传入 `render_status_report.py`，报告会在 `Verdict:` 之后追加：

```
Diff truncated: yes
Coverage: 7/10 files
```

调度器据此识别"本轮 0 issue 但 diff 被截断、覆盖不全"，不会把截断导致的空结果误读为"全量审查通过"。未提供这些字段时省略（向后兼容）。

### 用途

- **zima 调度器**：根据 `Status` 决策是否调度 fix agent
  - `NEEDS_FIX` → 调度 fix agent 修复 open issues
  - `PASS` → 当前 PR 无需进一步 action
  - `NO_NEW_COMMITS` → 本轮跳过，等待下次调度
  - 可选：消费 `Verdict` 行优先处理 `BLOCK_MERGE`（有 critical）的 PR
- **fix agent**：快速获取当前 open issues 列表，无需重新解析 metadata
- **人工查看**：一目了然了解当前审查状态
