# pi-cr-batch-adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `pi/github-code-review-batch/` skill 从 Claude Code 端适配为 pi-coding-agent 可直接触发的 skill（工具、派发、metadata 契约、单 bot 表述），不动评审规则与 zima 核心。

**Architecture:** 纯 skill 层改造——文档文本 pi 化 + 2 个 python 脚本常量替换 + 单测路径/断言同步 + monitor 解析描述配套。7 个 scripts 平台无关，除身份常量外全部保留。

**Tech Stack:** Markdown skill 文档、Python 3 stdlib、pytest、gh CLI。

## Global Constraints

- 所有改动只落在 `pi/` 目录 + `tests/unit/test_cr_batch_*.py`；**不动** `plugins/pr-automation/`（CC 版保留字节不变）、不动 `zima/` 核心代码。
- metadata 标签统一 `pi-cr-meta`；机器人签名统一 `🤖 Generated with pi-coding-agent`。
- 触发词原文保留：`"batch review pr"` / `"review pr batch"` / `"scheduled review pr"`（外部调度契约）。
- 评审规则、severity 口径、状态报告三态、Verdict 派生、issues[] schema **不得改变**。
- 不做 zima-pr-monitor 的 kimi 清理（#154 范围）；monitor 只加 pi-cr-meta 识别。
- commit message 用 conventional commits，一次 commit 一个 task。
- 工作目录：`/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-161-pi-cr-batch-adapter`（本文件所有相对路径相对此目录）。

---

### Task 1: scripts 身份常量 pi 化 + 测试同步（TDD）

**Files:**
- Modify: `pi/github-code-review-batch/scripts/build_review_body.py`（2 处）
- Modify: `pi/github-code-review-batch/scripts/parse_metadata.py`（常量 + docstring）
- Modify: `tests/unit/test_cr_batch_contracts.py`（路径 + 断言）
- Modify: `tests/unit/test_cr_batch_parse_metadata.py`（路径 + 断言）

**Interfaces:**
- Consumes: 无（第一个 task）。
- Produces: `build_review_body.py` 输出 `<!-- pi-cr-meta\n{json}\n-->` + `🤖 Generated with pi-coding-agent`；`parse_metadata.py` 常量 `PI_MARKER = "Generated with pi-coding-agent"`、`META_MARKER = "<!-- pi-cr-meta"`、`META_RE = re.compile(r"<!--\s*pi-cr-meta\s*\n(.*?)\n\s*-->", re.DOTALL)`。后续 task 的文档文本引用这些字符串。

- [ ] **Step 1: 改测试断言为 pi 常量（先写失败测试）**

`tests/unit/test_cr_batch_contracts.py`：
- L258: `assert "<!-- cc-cr-meta" in out` → `assert "<!-- pi-cr-meta" in out`
- L261: `assert "🤖 Generated with Claude Code" in out` → `assert "🤖 Generated with pi-coding-agent" in out`
- L270: `out.index("<!-- cc-cr-meta")` → `out.index("<!-- pi-cr-meta")`
- L272: `start + len("<!-- cc-cr-meta")` → `start + len("<!-- pi-cr-meta")`
- L286 注释里 "latest cc-cr-meta" → "latest pi-cr-meta"（注释，不影响断言）

`tests/unit/test_cr_batch_parse_metadata.py`：
- L29-31: `SCRIPTS = _REPO_ROOT / "plugins" / "pr-automation" / "skills" / "github-code-review-batch" / "scripts"` → `_REPO_ROOT / "pi" / "github-code-review-batch" / "scripts"`
- L57 注释 "cc-cr-meta" → "pi-cr-meta"；L68 `f"<!-- cc-cr-meta\n..."` → `f"<!-- pi-cr-meta\n..."`
- L69 `"🤖 Generated with Claude Code"` → `"🤖 Generated with pi-coding-agent"`
- L74 注释 "no CC signature" → "no pi signature"；L80 注释 "multiple cc-cr-meta" → "multiple pi-cr-meta"
- `_kimi_body` 测试保留不变（kimi-cr-meta 评论仍须被忽略——行为未变）

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-161-pi-cr-batch-adapter
uv run pytest tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_parse_metadata.py -x
```
Expected: FAIL（脚本仍输出 cc-cr-meta，断言不匹配；SCRIPTS 路径已切到 pi/ 版脚本）

- [ ] **Step 3: 改脚本常量**

`pi/github-code-review-batch/scripts/build_review_body.py`：
- L83: `return f"<!-- cc-cr-meta\n{json.dumps(payload, ensure_ascii=False)}\n-->"` → `"<!-- pi-cr-meta\n..."`
- L176: `return f"{metadata}\n\n{body}\n\n🤖 Generated with Claude Code\n"` → `"🤖 Generated with pi-coding-agent"`

`pi/github-code-review-batch/scripts/parse_metadata.py`：
- docstring L1-3 的 "cc-cr-meta" → "pi-cr-meta"
- L21: `CC_MARKER = "Generated with Claude Code"` → `PI_MARKER = "Generated with pi-coding-agent"`
- L22: `META_MARKER = "<!-- cc-cr-meta"` → `META_MARKER = "<!-- pi-cr-meta"`
- L23: `META_RE = re.compile(r"<!--\s*cc-cr-meta\s*\n(.*?)\n\s*-->", re.DOTALL)` → `pi-cr-meta`
- L47-48 `extract_latest_meta` 里 `CC_MARKER in r["body"]` → `PI_MARKER in r["body"]`

- [ ] **Step 4: 跑测试确认通过**

```bash
uv run pytest tests/unit/test_cr_batch_*.py -v
```
Expected: PASS（5 个 cr_batch 测试文件全绿；suppressions/tool_layer/committer_match 三个文件不受影响但也跑一遍）

- [ ] **Step 5: Commit**

```bash
git add pi/github-code-review-batch/scripts/build_review_body.py pi/github-code-review-batch/scripts/parse_metadata.py tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_parse_metadata.py
git commit -m "refactor(cr-batch): pi identity constants in build/parse scripts (pi-cr-meta)"
```

---

### Task 2: SKILL.md pi 化

**Files:**
- Modify: `pi/github-code-review-batch/SKILL.md`

**Interfaces:**
- Consumes: Task 1 的常量（pi-cr-meta、Generated with pi-coding-agent）。
- Produces: pi 可加载的 skill frontmatter（触发词保留）、工具名全 pi 化、单 bot 表述。Task 3 的 references 与本文件表述一致。

- [ ] **Step 1: frontmatter description 改 pi 表述（触发词原文不动）**

description 第 2 行 `Claude Code 端` → `pi-coding-agent 端`；第 3 行 "多 Agent 并行检查" 保留。触发词三行保留原样。

- [ ] **Step 2: 标题与双 bot 表述单 bot 化**

L4 标题 `# GitHub Code Review Batch (Claude Code)` → `# GitHub Code Review Batch (pi-coding-agent)`。
L19 段 "本 Skill 是**双 CR Agent 交叉验证体系**的一部分：Claude Code 和 Kimi CLI 分别独立审查同一 PR……（`cc-cr-meta` / `kimi-cr-meta`）……互不干扰——两边读取评论流时严格忽略对方的 metadata 评论" 整段改写为：
"本 Skill 是 **pi-coding-agent 单 agent 审查**：每次调用独立审查 PR，结论通过 `<!-- pi-cr-meta -->` HTML metadata 持久化。历史 cc 版评论（`cc-cr-meta` / `Generated with Claude Code`）与 kimi 版评论（`kimi-cr-meta`）在增量解析时严格忽略——各 harness 的审查历史互不干扰。"

- [ ] **Step 3: 工具名与派发约束 pi 化**

- L44 `Bash` → `bash`（PR 编号提取段："都未提供 → 使用 `bash` 执行……"）
- "关键约束" 段 3 条改写：
  - "**`Bash` 执行所有 `gh` 和 `git` 命令**" → "**`bash` 执行所有 `gh` 和 `git` 命令**"
  - "**`Agent` 启动所有审查/验证 sub-agent**：本 skill 需要的并行+独立上下文执行语义，其他工具（如内联 LLM 调用）保证不了" → "**`subagent` 启动所有审查/验证 subagent**：用 subagent 工具的 `workflowScript` + `runs.all` 并行 fanout（`agent: "reviewer"` + `context: "fresh"`），获得与独立上下文执行等价的语义"
  - "不依赖任何 MCP 工具" 条保留
- "常用 gh 命令" 段无工具名，不动。

- [ ] **Step 4: 输出契约与 metadata 描述同步**

L96-98 处 "包含 `<!-- cc-cr-meta ... -->` 机器可读 header" → `<!-- pi-cr-meta ... -->`。状态报告三态与 Verdict 描述不动。

- [ ] **Step 5: 验证 grep**

```bash
grep -n "Claude Code\|cc-cr-meta\|kimi-cr-meta\|`Bash`\|`Agent`" pi/github-code-review-batch/SKILL.md
```
Expected: 仅 L19 改写段中作为"历史忽略对象"出现的 `cc-cr-meta`/`kimi-cr-meta`/`Generated with Claude Code` 字样（有意保留）；无 `Bash`/`Agent` 工具名。

- [ ] **Step 6: Commit**

```bash
git add pi/github-code-review-batch/SKILL.md
git commit -m "docs(cr-batch): pi-ify SKILL.md (tools, dispatch, single-bot wording)"
```

---

### Task 3: references/ pi 化

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md`
- Modify: `pi/github-code-review-batch/references/delta-review.md`
- Modify: `pi/github-code-review-batch/references/output-examples.md`
- Modify: `pi/github-code-review-batch/references/subagent-prompts.md`（仅派发说明，prompt 模板不动）

**Interfaces:**
- Consumes: Task 1 常量、Task 2 的表述基调。
- Produces: 全部 references 与 SKILL.md 一致；subagent 派发描述统一为 `subagent` + `runs.all`。

- [ ] **Step 1: flow.md 机械替换工具名**

全文件（13 处 `Bash` → `bash`、1 处 `Read` → `read`）：
```bash
sed -i 's/`Bash`/`bash`/g; s/`Read`/`read`/g' pi/github-code-review-batch/references/flow.md
```
Expected: `grep -c '`Bash`\|`Read`'` = 0。

- [ ] **Step 2: flow.md 派发段改写（3 处 `Agent`）**

- Step 3（L168 附近）"使用 `Agent` 启动 summarizer subagent" → "由 parent 直接完成（300 字摘要成本低，无需派 subagent；如需隔离上下文，用 `subagent` 单发）"
- Step 4（L212 附近）"启动 5 个并行 `Agent`" → 改写为：

```
启动 5 个并行 `subagent`（subagent 工具 `workflowScript` + `runs.all`，每个 `agent: "reviewer"`、`context: "fresh"`）：

await runs.all([
  { key: "claude-checker-1", agent: "reviewer", context: "fresh", task: "<claude-compliance-checker prompt，显式规则 framing>" },
  { key: "claude-checker-2", agent: "reviewer", context: "fresh", task: "<claude-compliance-checker prompt，隐含约定 framing>" },
  { key: "agents-checker",    agent: "reviewer", context: "fresh", task: "<agents-compliance-checker prompt>" },
  { key: "bug-scanner",       agent: "reviewer", context: "fresh", task: "<bug-scanner prompt>" },
  { key: "logic-analyzer",    agent: "reviewer", context: "fresh", task: "<logic-analyzer prompt>" },
])
```

每个 task 的 prompt 模板见 subagent-prompts.md 对应小节，输入包（diff 文件路径 /tmp/pi-cr-diff.txt 等）以模板变量方式填入。

- Step 5（L292 附近）"启动一个并行 `Agent` 进行验证" → "启动一个并行 `subagent`（`agent: "reviewer"`、`context: "fresh"`、task 为 issue-validator prompt 模板 + 单个 issue 信息），N 个候选 issue 用 `runs.all` 一并 fanout"。

- [ ] **Step 3: flow.md 身份与路径文本**

- L18-24 parse_metadata 描述："最新一条 Claude Code 评论的 cc-cr-meta JSON" + 4 条内部规则（"Generated with Claude Code" / `<!-- cc-cr-meta` / 正则）→ 同步为 pi 版（"Generated with pi-coding-agent" / `<!-- pi-cr-meta`）。
- Step 0.2a 第 2 条："过滤掉所有 AI CR 评论（Claude Code 评论 body 包含 `"Generated with Claude Code"`，Kimi CLI 评论 body 包含 `"<!-- kimi-cr-meta"`），保留 committer / human reviewer 的评论。两个 Agent 的审查结论互不参考……" → "过滤掉所有 AI CR 评论（pi 版包含 `"Generated with pi-coding-agent"`，cc 版包含 `"Generated with Claude Code"`，kimi 版包含 `"<!-- kimi-cr-meta"`），保留 committer / human reviewer 的评论。各 harness 的审查结论互不参考"
- 临时文件路径 `/tmp/cc-cr-diff.txt`、`/tmp/cc-cr-diff-meta.json`（Step 3.5）→ `/tmp/pi-cr-diff.txt`、`/tmp/pi-cr-diff-meta.json`
- Step 6 suppress 段：仓库根 `.claude/cr-suppressions.json` → `.pi/cr-suppressions.json`（CC 兼容读取说明保留一句："历史 `.claude/cr-suppressions.json` 仍可读，双路径兼容"）
- Step 9.2：`/tmp/cc-cr-{pr_number}.md` → `/tmp/pi-cr-{pr_number}.md`；"必须包含 `"🤖 Generated with Claude Code"` 标识（脚本已固化）" → pi 版标识
- Part A 示例 `<!-- cc-cr-meta\n{...}\n-->` → `<!-- pi-cr-meta\n{...}\n-->`

- [ ] **Step 4: delta-review.md**

- L27 `Bash` → `bash`；L42 `Bash` → `bash`
- L29-31 "启动 delta-reviewer Agent" → "启动 delta-reviewer（`subagent`、`agent: "reviewer"`、`context: "fresh"`，前台 1 个）"
- L121-122 表格 "5 个并行审查 Agent" / "delta-reviewer 1 个 Agent" → "5 个并行审查 subagent" / "delta-reviewer 1 个 subagent"

- [ ] **Step 5: output-examples.md**

全文件 4 处 `<!-- cc-cr-meta` → `<!-- pi-cr-meta`、4 处 `🤖 Generated with Claude Code` → `🤖 Generated with pi-coding-agent`：
```bash
sed -i 's/<!-- cc-cr-meta/<!-- pi-cr-meta/g; s/Generated with Claude Code/Generated with pi-coding-agent/g' pi/github-code-review-batch/references/output-examples.md
```

- [ ] **Step 6: subagent-prompts.md**

L1 标题下加一段派发说明（prompt 模板本身不动）：
"本文件的 prompt 模板在 pi 下通过 `subagent` 工具派发：`agent: "reviewer"`（或项目自定义审查 agent）、`context: "fresh"`，task 字段填下方模板并代入输入变量。并行 fanout 用 subagent 工具的 `workflowScript` `runs.all`。"

- [ ] **Step 7: 验证 grep**

```bash
grep -rn '`Bash`\|`Read`\|`Agent`\|cc-cr-meta\|Generated with Claude Code\|cc-cr-diff' pi/github-code-review-batch/references/
```
Expected: 仅 Step 0.2a 与 SKILL.md 对应的"历史忽略对象"描述中允许出现 `cc-cr-meta`/`Generated with Claude Code`（作为被过滤的历史评论特征）；无工具名残留；`cc-cr-diff` 路径已清空。

- [ ] **Step 8: Commit**

```bash
git add pi/github-code-review-batch/references/
git commit -m "docs(cr-batch): pi-ify references (flow/delta/examples/prompts)"
```

---

### Task 4: zima-pr-monitor 认 pi-cr-meta（最小配套）

**Files:**
- Modify: `pi/zima-pr-monitor/SKILL.md`

**Interfaces:**
- Consumes: Task 1 的 `pi-cr-meta` 标签。
- Produces: monitor 收敛判定能解析 pi 版 review。不做 kimi 清理（#154）。

- [ ] **Step 1: 解析规则加 pi-cr-meta**

L17 "区分靠 body 的 HTML meta：`<!-- cc-cr-meta {...} -->` / `<!-- kimi-cr-meta {...} -->`，字段含 `round` / `new_count` / `resolved_count` / `issues[]`（每条 status: resolved/acknowledged/open）" → 改为：
"区分靠 body 的 HTML meta：`<!-- cc-cr-meta {...} -->`（cc 版） / `<!-- pi-cr-meta {...} -->`（pi 版） / `<!-- kimi-cr-meta {...} -->`（kimi 版，已停用），字段含 `round` / `new_count` / `resolved_count` / `issues[]`（每条 status: resolved/acknowledged/open）"

- [ ] **Step 2: 收敛判定说明同步**

L33/L37/L45 里涉及 "双 bot（cc AND kimi）" 的表述**不动**（kimi 清理属 #154）；仅在描述 metadata 时确保 pi-cr-meta 是合法解析对象。

- [ ] **Step 3: 验证**

```bash
grep -n "pi-cr-meta" pi/zima-pr-monitor/SKILL.md
```
Expected: ≥2 处（description + 解析规则）。

- [ ] **Step 4: Commit**

```bash
git add pi/zima-pr-monitor/SKILL.md
git commit -m "docs(pr-monitor): recognize pi-cr-meta review metadata"
```

---

### Task 5: 全量验证收尾

**Files:** 无新增。

- [ ] **Step 1: 全仓 grep 收尾**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-161-pi-cr-batch-adapter
grep -rn '`Bash`\|`Read`\|`Agent`' pi/github-code-review-batch/        # 期望 0
grep -rn "cc-cr-meta" pi/github-code-review-batch/                     # 期望：仅"历史忽略对象"语境
grep -rn "Claude Code 端" pi/github-code-review-batch/                 # 期望 0
```

- [ ] **Step 2: 全量测试**

```bash
uv run pytest tests/unit/ -q
```
Expected: PASS（cr_batch 5 个文件 + 其余全部；注意 worktree 无 .venv，uv 会自动 sync——如失败用 `uv sync` 后重跑）

- [ ] **Step 3: plugins 版字节不变验证**

```bash
git diff --stat plugins/   # 期望空
```

- [ ] **Step 4: spec/plan 文件 commit（流程产物落仓）**

```bash
git add docs/superpowers/specs/2026-08-19-pi-cr-batch-adapter-design.md docs/superpowers/plans/2026-08-19-pi-cr-batch-adapter.md
git commit -m "docs: spec + plan for pi cr-batch adapter (#161)"
```

- [ ] **Step 5: push + PR**

```bash
git push -u origin issue-161-pi-cr-batch-adapter
gh pr create --base main --title "feat(skill): adapt github-code-review-batch to pi-coding-agent" --body-file <(cat <<'EOF'
## Summary

Closes #161. 把 `pi/github-code-review-batch/` 从 Claude Code 端 skill 适配为 pi 端：工具调用、subagent 派发、metadata 契约、单 bot 表述。

## Changes

- scripts 身份常量 pi 化：`cc-cr-meta` → `pi-cr-meta`、`Generated with pi-coding-agent`；tests 路径 plugins→pi + 断言同步
- SKILL.md / references 工具名 pi 化（bash/read/subagent + runs.all 并行 fanout），删除 kimi 双 bot 表述（顺带覆盖 #154 对 github-code-review-batch 的要求）
- `pi/zima-pr-monitor` 认 `pi-cr-meta`（最小配套；monitor 的 kimi 清理留给 #154）
- plugins/ CC 版保持字节不变

## Test

- `uv run pytest tests/unit/ -q` 全绿
- build/parse 往返一致性由 test_cr_batch_contracts.py 覆盖

## Notes

- 本机 pi 会话内触发词 `batch review pr <N>` 可直接跑；端到端冒烟在合并后于本机验证（不阻塞本 PR）
- 决策依据见 issue #161 调研评论（3 轮）与 spec 文档
EOF
)
```
