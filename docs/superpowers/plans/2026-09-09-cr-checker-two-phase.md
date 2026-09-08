# 合并双 CLAUDE checker 为单 checker 两阶段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 github-code-review-batch 的两个 CLAUDE compliance checker（显式规则 / 隐含约定双 framing，#122）合并为单 checker 两阶段 prompt，Round-1 Step 4 fanout 从 5 降为 4，pi 主版与 cc 插件副本同步。

**Architecture:** 纯文档 + 文档契约测试改动。`subagent-prompts.md` 的 checker 小节由「双 prompt 双派发」改为「单 prompt 内顺序执行两阶段」，输出保持扁平 JSON 数组（六字段 schema 不变）；`flow.md` / `SKILL.md` / `delta-review.md` 的数量与派发描述同步；新增 contract 测试锁定新结构；最后用固定真实 PR 快照做新旧 prompt 召回对比（U1，用户实测）才可定稿。

**Tech Stack:** Markdown skill 文档、pytest（纯文本契约断言，不调用 LLM）、ruff/black、gh/git CLI、pi subagent 工具（仅 U1）。

**Spec:** [`docs/superpowers/specs/2026-09-09-cr-checker-two-phase-design.md`](../specs/2026-09-09-cr-checker-two-phase-design.md)（首个 commit 已落入本 worktree）。验收 ID（A1–A8 / U1）与 U1 完整协议以 spec 第 8、9 节为准。

## Global Constraints

- **Worktree**：`WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-225-merge-claude-checker-two-phase`，分支 `issue-225-merge-claude-checker-two-phase`。所有编辑与命令都在 worktree 内执行；bash 命令以 `cd "$WT" && ...` 前缀运行（子 shell，不切 session），git 操作用 `git -C "$WT"`。**禁止碰主 checkout。**
- **不改**：`scripts/**`、`zima/**`、issue-validator / build_review_body.py / render_status_report.py、触发短语（`"batch review pr"` / `"review pr batch"` / `"scheduled review pr"`）、PR 评论 metadata、状态报告块、三态 Status、XML trailer。
- **输出契约**：checker 输出保持扁平 JSON 数组；六个 key（`description`/`reason`/`file`/`lines`/`suggestion`/`severity`）均保留；`reason` **包含** `"CLAUDE.md"`（canonical 值仍为 `"CLAUDE.md"`，不收紧为完全相等）；不新增 `phase` 字段或双数组；可选 `blocking` 规则不动。
- **两份副本**：pi（`pi/github-code-review-batch/`）与 cc（`plugins/pr-automation/skills/github-code-review-batch/`）的 checker section（`## claude-compliance-checker` 至 `## agents-compliance-checker` 之间）必须**字节一致**；cc 版保留 `Agent` 工具派发形态，不得混入 pi 的 `runs.all` / `FAST_OVERRIDE` / `PI_CR_FAST_MODEL`。
- **模型分档（#224）不回归**：checker 仍 fast 档；`FAST_OVERRIDE` / `STRONG_OVERRIDE` 条件 spread、preflight、fallback note、Step 5 复用说明全部保留；全目录 `.md` 禁止硬编码模型名（`TestModelDispatchDocs` 扫描）。
- **测试不调用 LLM、不访问 GitHub**：纯文本读取 + section 提取；LLM 召回只由 Task 6（U1）覆盖。
- **提交规范**：conventional commits；按文件 `git add <file>`，禁止 `git add -A`；commit message 用英文。
- **遗留 token**：实现后两份副本的 `.md` 中不得出现 `启动两次`、`claude-checker-1`、`claude-checker-2`、`CLAUDE.md checker ×2`（历史 issue 编号 #122 的引用允许，但这些执行 token 不允许）。

## 验收追溯

| 验收 ID | 覆盖 Task |
|---|---|
| A1（既有契约不回归） | Task 5 |
| A2（pi Step 4 四 lane） | Task 1（红）→ Task 2（绿） |
| A3（cc Step 4 四 agent） | Task 3（红）→ Task 4（绿） |
| A4（两阶段 prompt 双视角） | Task 1/2（pi）+ Task 3/4（cc） |
| A5（flat schema 不变） | Task 1（红）→ Task 2（绿） |
| A6（旧双 checker 语义清零） | Task 1/2（pi）+ Task 3/4（cc） |
| A7（fast 档位不变） | Task 1（红）→ Task 2（绿），Task 5 回归 |
| A8（lint/format） | Task 5 |
| U1（真实 PR 召回对比） | Task 6（用户实测，**定稿红线**） |

---

### Task 1: pi 侧 contract 测试（红）

**Files:**
- Test: `tests/unit/test_cr_batch_contracts.py`（文件末尾追加新 class）

**Interfaces:**
- Consumes: 现有 `SKILL_DIR`、`_REPO_ROOT`、`re`、`pytest`（文件头部已导入，无需新增 import）
- Produces: class `TestCheckerMergeDocs`（Task 5 回归用）；helper `_step4_runs_all_keys` / `_checker_section`

- [ ] **Step 1: 在 `tests/unit/test_cr_batch_contracts.py` 末尾追加以下 class**

```python
class TestCheckerMergeDocs:
    """Issue #225: single two-phase claude-compliance-checker contracts (pi copy).

    The two differentiated-framing dispatches (#122) merge into one dispatch
    whose prompt runs Phase-1 (explicit rules) then Phase-2 (implicit
    conventions / anti-patterns) and emits one flat JSON array. These tests
    lock the pi-side docs to that design.
    """

    LEGACY_TOKENS = (
        "启动两次",
        "claude-checker-1",
        "claude-checker-2",
        "CLAUDE.md checker ×2",
    )

    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        docs = {
            "skill": (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"),
            "flow": (SKILL_DIR / "references" / "flow.md").read_text(encoding="utf-8"),
            "delta": (SKILL_DIR / "references" / "delta-review.md").read_text(
                encoding="utf-8"
            ),
            "prompts": (SKILL_DIR / "references" / "subagent-prompts.md").read_text(
                encoding="utf-8"
            ),
        }
        for md_path in sorted(SKILL_DIR.rglob("*.md")):
            docs.setdefault(
                str(md_path.relative_to(SKILL_DIR)),
                md_path.read_text(encoding="utf-8"),
            )
        return docs

    @staticmethod
    def _section(text: str, start: str, end: str) -> str:
        return text.split(start, 1)[1].split(end, 1)[0]

    def _step4_section(self, flow_text: str) -> str:
        return self._section(flow_text, "## Step 4", "## Step 5")

    def _step4_runs_all_keys(self, flow_text: str) -> list[str]:
        step4 = self._step4_section(flow_text)
        blocks = re.findall(r"```js\n(.*?)```", step4, re.DOTALL)
        assert (
            blocks and "runs.all" in blocks[0]
        ), "Step 4 must contain a js code block with the runs.all fanout"
        return re.findall(r'key:\s*"([^"]+)"', blocks[0])

    def _checker_section(self, prompts_text: str) -> str:
        return self._section(
            prompts_text,
            "## claude-compliance-checker",
            "## agents-compliance-checker",
        )

    # --- A2: single checker lane in the Step 4 fanout ---

    def test_pi_step4_dispatch_has_four_lanes(self, texts):
        keys = self._step4_runs_all_keys(texts["flow"])
        assert keys == [
            "claude-checker",
            "agents-checker",
            "bug-scanner",
            "logic-analyzer",
        ], f"Step 4 must fan out to exactly 4 lanes with one claude-checker: {keys}"

    def test_pi_checker_task_uses_two_phase_prompt(self, texts):
        step4 = self._step4_section(texts["flow"])
        assert "两阶段" in step4
        assert "显式规则" in step4
        assert "隐含约定" in step4

    def test_pi_round1_agent_count_docs_are_consistent(self, texts):
        assert "4 个并行审查 Agent" in texts["skill"]
        assert "4 个并行审查 Agent" in texts["flow"]
        assert "4 个并行审查 subagent" in texts["delta"]

    # --- A7: the merged checker stays on the fast tier ---

    def test_pi_checker_fast_mapping_is_preserved(self, texts):
        step4 = self._step4_section(texts["flow"])
        for line in step4.splitlines():
            if "PI_CR_FAST_MODEL" in line and "checker" in line:
                assert "×2" not in line
                assert "bug-scanner" in line
                break
        else:
            pytest.fail("fast mapping line for the checker is missing")

    # --- A4/A5: merged two-phase prompt keeps the flat schema ---

    def test_pi_checker_prompt_preserves_flat_schema(self, texts):
        section = self._checker_section(texts["prompts"])
        for token in (
            "一个扁平 JSON 数组",
            "description",
            "reason",
            "file",
            "lines",
            "suggestion",
            "severity",
            "CLAUDE.md",
        ):
            assert token in section, f"checker prompt missing {token!r}"
        assert "phase1_findings" not in section
        assert "phase2_findings" not in section

    def test_pi_checker_prompt_switches_view_and_requires_guideline_basis(self, texts):
        section = self._checker_section(texts["prompts"])
        for token in ("阶段 1", "阶段 2", "切换视角", "不重复"):
            assert token in section, f"checker prompt missing {token!r}"
        # Phase 2 must stay grounded in CLAUDE.md, not free-floating opinion
        assert "CLAUDE.md" in section.split("阶段 2", 1)[1]

    # --- A6: no legacy dual-checker execution text anywhere in the skill ---

    def test_pi_no_legacy_dual_checker_execution_text(self, texts):
        for name, text in texts.items():
            for token in self.LEGACY_TOKENS:
                assert (
                    token not in text
                ), f"legacy dual-checker token {token!r} remains in {name}"
```

- [ ] **Step 2: 运行新测试类，确认全部失败（红）**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_contracts.py::TestCheckerMergeDocs -q`
Expected: 7 个测试全部 FAIL（当前文档仍是双 checker 形态：lane key 是 `claude-checker-1/2`、数量为 5、prompt 无双阶段结构）

- [ ] **Step 3: 确认既有测试不受影响（改动只追加了 class）**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_contracts.py -q -k "not TestCheckerMergeDocs"`
Expected: 全部 PASS（基线 108 项中本文件的既有断言不变）

**本 task 不 commit**（红测试与 Task 2 的文档改动一起提交）。

---

### Task 2: pi 侧文档改写（转绿 + 提交）

**Files:**
- Modify: `pi/github-code-review-batch/references/subagent-prompts.md`（checker 小节整体替换）
- Modify: `pi/github-code-review-batch/references/flow.md`（11 处）
- Modify: `pi/github-code-review-batch/SKILL.md`（3 处）
- Modify: `pi/github-code-review-batch/references/delta-review.md`（2 处）

**Interfaces:**
- Consumes: Task 1 的 `TestCheckerMergeDocs` 断言
- Produces: pi checker section 最终文本（Task 4 将其字节级复制到 cc 副本；Task 6 从这里取新 prompt）

- [ ] **Step 1: 替换 `subagent-prompts.md` 的 checker 小节**

将 `## claude-compliance-checker {#claude-compliance-checker}` 到 `## agents-compliance-checker` 之前的全部内容（含末尾的 `---` 分隔线之前）替换为：

```markdown
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
```

（替换后保持原有的 `---` 分隔线与 `## agents-compliance-checker` 小节不变。）

- [ ] **Step 2: 修改 `flow.md`（11 处精确替换）**

| # | old | new |
|---|---|---|
| 1 | `- CLAUDE.md checker ×2、AGENTS.md checker：接收**完整 diff**（规范检查需要完整上下文），预算 20K` | `- CLAUDE.md checker、AGENTS.md checker：接收**完整 diff**（规范检查需要完整上下文），预算 20K` |
| 2 | `## Step 4: 5 个并行审查 Agent {#step-4}` | `## Step 4: 4 个并行审查 Agent {#step-4}` |
| 3 | `启动 5 个并行 \`subagent\`（subagent 工具` | `启动 4 个并行 \`subagent\`（subagent 工具` |
| 4 | `  { key: "claude-checker-1", agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "<claude-compliance-checker prompt，显式规则 framing>" },`<br>`  { key: "claude-checker-2", agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "<claude-compliance-checker prompt，隐含约定 framing>" },` | `  { key: "claude-checker", agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "<claude-compliance-checker prompt（两阶段：阶段 1 显式规则 → 阶段 2 隐含约定/反模式）>" },` |
| 5 | `由 Pi 正常 resolution chain 解析。示例按当前双 checker 形态书写，#225（checker 合并）落地后按实际 agent 数量更新，档位归属不变。` | `由 Pi 正常 resolution chain 解析。` |
| 6 | `\| CLAUDE.md checker ×2、AGENTS.md checker、bug-scanner \| fast（\`PI_CR_FAST_MODEL\`） \|` | `\| CLAUDE.md checker、AGENTS.md checker、bug-scanner \| fast（\`PI_CR_FAST_MODEL\`） \|` |
| 7 | `以模板变量方式填入。5 个 subagent 职责：` | `以模板变量方式填入。4 个 subagent 职责：` |
| 8 | `- **CLAUDE.md checker ×2、AGENTS.md checker**：完整 diff` | `- **CLAUDE.md checker、AGENTS.md checker**：完整 diff` |
| 9 | `5 个 agent 的具体职责、输入输出契约、prompt 模板见` | `4 个 agent 的具体职责、输入输出契约、prompt 模板见` |
| 10 | `- [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker)（启动两次，独立运行，交叉验证）` | `- [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker)（单实例两阶段：显式规则 → 隐含约定/反模式，#225）` |
| 11 | `**为什么 CLAUDE.md checker 跑两次（#122：差异化而非复跑）**：两个 checker 使用**不同 framing**（Checker-1 显式规则、Checker-2 隐含约定/反模式），让召回增益来自视角互补而非采样噪声。两者的 \`reason\` 都为 \`"CLAUDE.md"\`、schema 不变，下游无需改动。这与跨 harness 的并行审查（pi vs cc）是两个不同层次的冗余——前者在同一 skill 内部，后者跨 harness。` | `**为什么 CLAUDE.md checker 只派发一次（#225：两阶段合并）**：#122 曾以两个不同 framing 的 checker 做视角互补（显式规则 / 隐含约定）；#225 将其合并为单 checker——prompt 内分两阶段，先逐条核对明文规则、再切换视角检查隐含约定与反模式，视角互补保留在同一份 prompt 内，Round-1 fanout 由 5 降为 4。\`reason\` 仍包含 \`"CLAUDE.md"\`、schema 不变，下游无需改动。合并是否无损由同一真实 PR 的新旧对比验证（issue #225 验收 U1）确认后定稿。这与跨 harness 的并行审查（pi vs cc）是两个不同层次的冗余——前者在同一 skill 内部，后者跨 harness。` |

- [ ] **Step 3: 修改 `SKILL.md`（3 处）**

| # | old | new |
|---|---|---|
| 1 | `\| Step 4 \| 5 个并行审查 Agent \| [subagent-prompts.md](references/subagent-prompts.md) \|` | `\| Step 4 \| 4 个并行审查 Agent \| [subagent-prompts.md](references/subagent-prompts.md) \|` |
| 2 | `\| claude-compliance-checker \| 检查 CLAUDE.md 合规（显式规则 + 隐含约定两种 framing） \| 2（差异化，#122） \|` | `\| claude-compliance-checker \| 检查 CLAUDE.md 合规（单 checker 两阶段：显式规则 → 隐含约定/反模式） \| 1（两阶段，#225） \|` |
| 3 | `2. **冗余检查**：两个 CLAUDE.md checker 用**不同 framing**（显式规则 + 隐含约定）互补运行（#122）` | `2. **两阶段规范检查**：单个 CLAUDE.md checker 在一份 prompt 内顺序执行两阶段——先核对明文规则，再切换视角检查隐含约定与反模式（#225 合并自 #122 的差异化 framing）` |

- [ ] **Step 4: 修改 `delta-review.md`（2 处）**

| # | old | new |
|---|---|---|
| 1 | `\| Step 3 \| summarizer + 5 个审查 subagent \| delta-reviewer 1 个 subagent \|` | `\| Step 3 \| summarizer + 4 个审查 subagent \| delta-reviewer 1 个 subagent \|` |
| 2 | `\| Step 4 \| 5 个并行审查 subagent \| delta-reviewer（旧 issue 对比）+ Δ2a 并行 bug/logic scanner（新 hunk，#123） \|` | `\| Step 4 \| 4 个并行审查 subagent \| delta-reviewer（旧 issue 对比）+ Δ2a 并行 bug/logic scanner（新 hunk，#123） \|` |

- [ ] **Step 5: 运行 Task 1 的新测试类，确认全部通过（绿）**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_contracts.py::TestCheckerMergeDocs -q`
Expected: 7 个测试全部 PASS

- [ ] **Step 6: 运行整个 pi contract 文件，确认既有断言无回归**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_contracts.py -q`
Expected: 全部 PASS（含 `TestModelDispatchDocs` / `TestModelTieringDocs` 的 #224 断言）

- [ ] **Step 7: Commit**

```bash
cd "$WT"
git add tests/unit/test_cr_batch_contracts.py \
  pi/github-code-review-batch/references/subagent-prompts.md \
  pi/github-code-review-batch/references/flow.md \
  pi/github-code-review-batch/SKILL.md \
  pi/github-code-review-batch/references/delta-review.md
git commit -m "refactor(cr-batch): merge dual CLAUDE checkers into single two-phase checker (pi skill) (#225)"
```

---

### Task 3: cc 侧 contract 测试（红）

**Files:**
- Test: `tests/unit/test_cr_batch_plugin_contracts.py`（顶部 import 区加 `re`；文件末尾追加新 class）

**Interfaces:**
- Consumes: 现有 `PLUGIN_ROOT`、`_REPO_ROOT`、`pytest`；新增 `import re`
- Produces: class `TestCcCheckerMergeDocs`；helper `_cc_dispatch_section` / `_checker_section`

- [ ] **Step 1: 在 `tests/unit/test_cr_batch_plugin_contracts.py` 的 import 区加 `import re`**

当前 import 块为 `import json` / `import subprocess` / `import sys`，按字母序在 `import json` 之后插入：

```python
import re
```

- [ ] **Step 2: 在文件末尾追加以下 class**

```python
class TestCcCheckerMergeDocs:
    """Issue #225: the cc plugin copy mirrors the pi two-phase merge.

    The plugin keeps its Agent-tool dispatch shape (no pi workflowScript or
    model tiering) but must carry the same single two-phase checker prompt.
    """

    LEGACY_TOKENS = (
        "启动两次",
        "claude-checker-1",
        "claude-checker-2",
        "CLAUDE.md checker ×2",
    )

    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        docs = {
            "skill": (PLUGIN_ROOT / "SKILL.md").read_text(encoding="utf-8"),
            "flow": (PLUGIN_ROOT / "references" / "flow.md").read_text(encoding="utf-8"),
            "delta": (PLUGIN_ROOT / "references" / "delta-review.md").read_text(
                encoding="utf-8"
            ),
            "prompts": (PLUGIN_ROOT / "references" / "subagent-prompts.md").read_text(
                encoding="utf-8"
            ),
        }
        for md_path in sorted(PLUGIN_ROOT.rglob("*.md")):
            docs.setdefault(
                str(md_path.relative_to(PLUGIN_ROOT)),
                md_path.read_text(encoding="utf-8"),
            )
        return docs

    @staticmethod
    def _section(text: str, start: str, end: str) -> str:
        return text.split(start, 1)[1].split(end, 1)[0]

    def _cc_dispatch_section(self, flow_text: str) -> str:
        return self._section(flow_text, "派发结构：", "task 的 prompt 模板见")

    @staticmethod
    def _checker_section(prompts_text: str) -> str:
        return prompts_text.split("## claude-compliance-checker", 1)[1].split(
            "## agents-compliance-checker", 1
        )[0]

    # --- A3: four agents in the cc Agent-tool dispatch list ---

    def test_cc_step4_dispatch_has_four_agents(self, texts):
        section = self._cc_dispatch_section(texts["flow"])
        keys = re.findall(
            r"`(claude-checker|agents-checker|bug-scanner|logic-analyzer)`", section
        )
        assert keys == [
            "claude-checker",
            "agents-checker",
            "bug-scanner",
            "logic-analyzer",
        ], f"cc Step 4 dispatch list must name exactly these 4 agents: {keys}"
        for token in ("runs.all", "FAST_OVERRIDE", "PI_CR_FAST_MODEL"):
            assert (
                token not in section
            ), f"pi-only dispatch token {token!r} leaked into cc flow.md"

    def test_cc_round1_agent_count_docs_are_consistent(self, texts):
        assert "4 个并行审查 Agent" in texts["skill"]
        assert "4 个并行审查 Agent" in texts["flow"]
        assert "4 个并行审查 sub-agent" in texts["delta"]

    # --- A4: cc checker prompt carries the same two-phase contract ---

    def test_cc_checker_prompt_matches_two_phase_contract(self, texts):
        section = self._checker_section(texts["prompts"])
        for token in ("阶段 1", "阶段 2", "切换视角", "一个扁平 JSON 数组"):
            assert token in section, f"cc checker prompt missing {token!r}"

    # --- A6: no legacy dual-checker execution text in the plugin copy ---

    def test_cc_no_legacy_dual_checker_execution_text(self, texts):
        for name, text in texts.items():
            for token in self.LEGACY_TOKENS:
                assert (
                    token not in text
                ), f"legacy dual-checker token {token!r} remains in cc {name}"

    # --- Sync guard: pi and cc checker sections stay byte-identical ---

    def test_pi_and_cc_checker_prompt_sections_are_identical(self):
        pi_prompts = (
            _REPO_ROOT
            / "pi"
            / "github-code-review-batch"
            / "references"
            / "subagent-prompts.md"
        ).read_text(encoding="utf-8")
        cc_prompts = (PLUGIN_ROOT / "references" / "subagent-prompts.md").read_text(
            encoding="utf-8"
        )
        assert self._checker_section(pi_prompts) == self._checker_section(cc_prompts), (
            "pi and cc checker sections must be byte-identical "
            "(dispatch headers live outside the section)"
        )
```

- [ ] **Step 3: 运行新测试类，确认失败（红）**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_plugin_contracts.py::TestCcCheckerMergeDocs -q`
Expected: 5 个测试中前 4 个 FAIL（cc 文档仍是双 checker 形态）；`test_pi_and_cc_checker_prompt_sections_are_identical` 此时 PASS（两侧当前本就一致，Task 4 后仍一致）

- [ ] **Step 4: 确认既有 plugin contract 测试不受影响**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_plugin_contracts.py -q -k "not TestCcCheckerMergeDocs"`
Expected: 全部 PASS

**本 task 不 commit**（红测试与 Task 4 的文档改动一起提交）。

---

### Task 4: cc 侧文档改写（转绿 + 提交）

**Files:**
- Modify: `plugins/pr-automation/skills/github-code-review-batch/references/subagent-prompts.md`（checker 小节与 pi 字节一致）
- Modify: `plugins/pr-automation/skills/github-code-review-batch/references/flow.md`（9 处）
- Modify: `plugins/pr-automation/skills/github-code-review-batch/SKILL.md`（3 处）
- Modify: `plugins/pr-automation/skills/github-code-review-batch/references/delta-review.md`（2 处）

**Interfaces:**
- Consumes: Task 2 的 pi checker section 最终文本；Task 3 的 `TestCcCheckerMergeDocs`
- Produces: 与 pi 字节一致的 cc checker section（sync guard 测试锁定）

- [ ] **Step 1: 用 pi 版最终文本替换 cc 的 checker 小节**

将 cc `subagent-prompts.md` 中 `## claude-compliance-checker {#claude-compliance-checker}` 到 `## agents-compliance-checker` 之前的内容替换为与 pi 版**完全相同**的小节文本（即 Task 2 Step 1 的结果，连空行都一致）。推荐做法：

```bash
cd "$WT"
python3 - <<'EOF'
from pathlib import Path

pi = Path("pi/github-code-review-batch/references/subagent-prompts.md")
cc = Path("plugins/pr-automation/skills/github-code-review-batch/references/subagent-prompts.md")

START = "## claude-compliance-checker"
END = "## agents-compliance-checker"

pi_text = pi.read_text(encoding="utf-8")
cc_text = cc.read_text(encoding="utf-8")

pi_section = pi_text.split(START, 1)[1].split(END, 1)[0]
head, _, tail = cc_text.partition(START)
_, _, cc_tail = tail.partition(END)
cc.write_text(head + START + pi_section + END + cc_tail, encoding="utf-8")
EOF
```

验证字节一致：

```bash
cd "$WT"
diff <(sed -n '/^## claude-compliance-checker/,/^## agents-compliance-checker/p' pi/github-code-review-batch/references/subagent-prompts.md) \
     <(sed -n '/^## claude-compliance-checker/,/^## agents-compliance-checker/p' plugins/pr-automation/skills/github-code-review-batch/references/subagent-prompts.md) \
  && echo "sections identical"
```

Expected: 无 diff 输出，打印 `sections identical`

- [ ] **Step 2: 修改 cc `flow.md`（9 处精确替换）**

| # | old | new |
|---|---|---|
| 1 | `- CLAUDE.md checker ×2、AGENTS.md checker：接收**完整 diff**（规范检查需要完整上下文），预算 20K` | `- CLAUDE.md checker、AGENTS.md checker：接收**完整 diff**（规范检查需要完整上下文），预算 20K` |
| 2 | `## Step 4: 5 个并行审查 Agent {#step-4}` | `## Step 4: 4 个并行审查 Agent {#step-4}` |
| 3 | `启动 5 个并行 sub-agent（每个用 \`Agent\` 工具派发，独立上下文）` | `启动 4 个并行 sub-agent（每个用 \`Agent\` 工具派发，独立上下文）` |
| 4 | `- \`claude-checker-1\`（显式规则 framing）→ [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker) Checker-1 prompt`<br>`- \`claude-checker-2\`（隐含约定 framing）→ [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker) Checker-2 prompt` | `- \`claude-checker\`（两阶段 prompt：显式规则 → 隐含约定/反模式）→ [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker) prompt` |
| 5 | `以模板变量方式填入。5 个 sub-agent 职责：` | `以模板变量方式填入。4 个 sub-agent 职责：` |
| 6 | `- **CLAUDE.md checker ×2、AGENTS.md checker**：完整 diff` | `- **CLAUDE.md checker、AGENTS.md checker**：完整 diff` |
| 7 | `5 个 agent 的具体职责、输入输出契约、prompt 模板见` | `4 个 agent 的具体职责、输入输出契约、prompt 模板见` |
| 8 | `- [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker)（启动两次，独立运行，交叉验证）` | `- [claude-compliance-checker](subagent-prompts.md#claude-compliance-checker)（单实例两阶段：显式规则 → 隐含约定/反模式，#225）` |
| 9 | `**为什么 CLAUDE.md checker 跑两次（#122：差异化而非复跑）**：两个 checker 使用**不同 framing**（Checker-1 显式规则、Checker-2 隐含约定/反模式），让召回增益来自视角互补而非采样噪声。两者的 \`reason\` 都为 \`"CLAUDE.md"\`、schema 不变，下游无需改动。这与跨 harness 的并行审查（cc vs pi）是两个不同层次的冗余——前者在同一 skill 内部，后者跨 harness。` | `**为什么 CLAUDE.md checker 只派发一次（#225：两阶段合并）**：#122 曾以两个不同 framing 的 checker 做视角互补（显式规则 / 隐含约定）；#225 将其合并为单 checker——prompt 内分两阶段，先逐条核对明文规则、再切换视角检查隐含约定与反模式，视角互补保留在同一份 prompt 内，Round-1 fanout 由 5 降为 4。\`reason\` 仍包含 \`"CLAUDE.md"\`、schema 不变，下游无需改动。合并是否无损由同一真实 PR 的新旧对比验证（issue #225 验收 U1）确认后定稿。这与跨 harness 的并行审查（cc vs pi）是两个不同层次的冗余——前者在同一 skill 内部，后者跨 harness。` |

- [ ] **Step 3: 修改 cc `SKILL.md`（3 处，文本与 pi 版相同）**

| # | old | new |
|---|---|---|
| 1 | `\| Step 4 \| 5 个并行审查 Agent \| [subagent-prompts.md](references/subagent-prompts.md) \|` | `\| Step 4 \| 4 个并行审查 Agent \| [subagent-prompts.md](references/subagent-prompts.md) \|` |
| 2 | `\| claude-compliance-checker \| 检查 CLAUDE.md 合规（显式规则 + 隐含约定两种 framing） \| 2（差异化，#122） \|` | `\| claude-compliance-checker \| 检查 CLAUDE.md 合规（单 checker 两阶段：显式规则 → 隐含约定/反模式） \| 1（两阶段，#225） \|` |
| 3 | `2. **冗余检查**：两个 CLAUDE.md checker 用**不同 framing**（显式规则 + 隐含约定）互补运行（#122）` | `2. **两阶段规范检查**：单个 CLAUDE.md checker 在一份 prompt 内顺序执行两阶段——先核对明文规则，再切换视角检查隐含约定与反模式（#225 合并自 #122 的差异化 framing）` |

- [ ] **Step 4: 修改 cc `delta-review.md`（2 处）**

| # | old | new |
|---|---|---|
| 1 | `\| Step 3 \| summarizer + 5 个审查 sub-agent \| delta-reviewer 1 个 sub-agent \|` | `\| Step 3 \| summarizer + 4 个审查 sub-agent \| delta-reviewer 1 个 sub-agent \|` |
| 2 | `\| Step 4 \| 5 个并行审查 sub-agent \| delta-reviewer（旧 issue 对比）+ Δ2a 并行 bug/logic scanner（新 hunk，#123） \|` | `\| Step 4 \| 4 个并行审查 sub-agent \| delta-reviewer（旧 issue 对比）+ Δ2a 并行 bug/logic scanner（新 hunk，#123） \|` |

- [ ] **Step 5: 运行 cc 新测试类，确认全部通过（绿）**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_plugin_contracts.py::TestCcCheckerMergeDocs -q`
Expected: 5 个测试全部 PASS

- [ ] **Step 6: Commit**

```bash
cd "$WT"
git add tests/unit/test_cr_batch_plugin_contracts.py \
  plugins/pr-automation/skills/github-code-review-batch/references/subagent-prompts.md \
  plugins/pr-automation/skills/github-code-review-batch/references/flow.md \
  plugins/pr-automation/skills/github-code-review-batch/SKILL.md \
  plugins/pr-automation/skills/github-code-review-batch/references/delta-review.md
git commit -m "refactor(cr-batch): sync two-phase checker merge to cc plugin skill (#225)"
```

---

### Task 5: 全量验证门（A1 / A8）

**Files:** 无新改动；如有格式/lint 修复，随本 task 提交。

- [ ] **Step 1: 两个 contract 测试文件全量运行（A1）**

Run: `cd "$WT" && uv run pytest tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py -q`
Expected: 全部 PASS（既有契约 + 新增 12 项 checker-merge 断言）

- [ ] **Step 2: 全部 unit 测试**

Run: `cd "$WT" && uv run pytest tests/unit/ -q`
Expected: 全部 PASS

- [ ] **Step 3: ruff（A8）**

Run: `cd "$WT" && uv run ruff check tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py`
Expected: 无输出、退出码 0

- [ ] **Step 4: black（A8）**

Run: `cd "$WT" && uv run black --check tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py --line-length 100`
Expected: `2 files would be left unchanged`；如需格式化则运行 `uv run black`（去掉 `--check`）后重跑 Step 1-4，并把格式化改动按文件 commit：

```bash
cd "$WT"
git add tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py
git commit -m "style(cr-batch): format checker-merge contract tests (#225)"
```

- [ ] **Step 5: 遗留 token 全局自查（A6 双保险）**

Run: `cd "$WT" && rg -n "启动两次|claude-checker-1|claude-checker-2|checker ×2" pi/github-code-review-batch/ plugins/pr-automation/skills/github-code-review-batch/ || echo "no legacy tokens"`
Expected: `no legacy tokens`（spec/plan 文档不在 skill 目录内，不会误命中）

---

### Task 6: U1 真实 PR 召回对比（用户实测，定稿红线）

**Files:** 无仓库改动。产物写入 `~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-225/research/validation/pr-205-7b23046/`（不进仓库）。

**Interfaces:**
- Consumes: Task 2 定稿的新 prompt（worktree `subagent-prompts.md` checker 小节）；基线 commit `2e3a8a3` 的旧双 prompt
- Produces: `comparison.md` + 三份原始输出；用户确认后 issue #225 才算可合并

完整协议见 spec 第 9 节；以下为执行步骤摘要（命令可直接复制）：

- [ ] **Step 1: 冻结输入包**

```bash
VALIDATION_DIR="$HOME/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-225/research/validation/pr-205-7b23046"
mkdir -p "$VALIDATION_DIR"

gh pr view 205 --repo zhuxixi/zima-blue-cli \
  --json number,title,body,reviews \
  > "$VALIDATION_DIR/pr-and-reviews.json"

cd "$WT"
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

- [ ] **Step 2: 覆盖预检（哨兵必须在输入内）**

```bash
python3 -c "
import json, pathlib, sys
d = pathlib.Path('$VALIDATION_DIR')
m = json.loads((d/'diff-meta.json').read_text())
diff = (d/'diff-20k.patch').read_text()
assert m['diff_truncated'] is False, m
assert m['covered_files'] == m['total_files'] == 2, m
assert 'DEFAULT_CONFIG = \"~/.zima/configs/auto-merge.yaml\"' in diff
assert 'DEFAULT_LOG = \"~/.zima/logs/auto-merge.log\"' in diff
print('coverage precheck OK')
"
```

Expected: `coverage precheck OK`；任何断言失败 → U1 标记 `blocked`，记录原因后停止，不换样本。

- [ ] **Step 3: 生成并冻结 PR 摘要**

由 parent 基于 `pr-and-reviews.json` 的 title/body 与 `diff.patch` 写一段不超过 300 字的中文摘要，保存为 `$VALIDATION_DIR/summary.md`。三次 checker 调用复用同一文件。

- [ ] **Step 4: 提取新旧 prompt**

```bash
cd "$WT"
git show 2e3a8a3:pi/github-code-review-batch/references/subagent-prompts.md > /tmp/issue-225-old-prompts.md
# 旧 Checker-1 显式规则 prompt = /tmp/issue-225-old-prompts.md 中 "Checker-1（显式规则违反）" 代码块
# 旧 Checker-2 隐含约定 prompt = 同文件 "Checker-2（隐含约定 / 反模式）" 代码块
# 新两阶段 prompt = worktree pi/.../subagent-prompts.md 的「推荐 prompt」代码块
```

- [ ] **Step 5: 模型档位 preflight（一次）**

按 spec §9.2：读取 `PI_CR_FAST_MODEL`，做格式 → registry → modelScope 校验。fast 档通过 → 三个 child 都显式用同一个 canonical `provider/id` override；未启用或任一步失败 → 三个 child 都省略 `model` 属性。把结论记入比较记录。**不允许一个 child 有 override、另一个没有。**

- [ ] **Step 6: 同一个 `runs.all` 并行派发三个 fresh reviewer**

用 subagent 工具 `workflowScript` + `runs.all`，三项均为 `agent: "reviewer"`、`context: "fresh"`，模型处理按 Step 5 结果三向一致；task 分别填 `{summary}` `{diff}` `{claude_md_content}` 代入后的三份 prompt（`diff` 用 `diff-20k.patch` 内容、`claude_md_content` 用 `CLAUDE.md` 内容）：

```js
await runs.all([
  { key: "old-explicit", agent: "reviewer", context: "fresh", /* ...MODEL_OVERRIDE, */ task: "<旧 Checker-1 prompt 代入后>" },
  { key: "old-implicit", agent: "reviewer", context: "fresh", /* ...MODEL_OVERRIDE, */ task: "<旧 Checker-2 prompt 代入后>" },
  { key: "new-two-phase", agent: "reviewer", context: "fresh", /* ...MODEL_OVERRIDE, */ task: "<新两阶段 prompt 代入后>" },
])
```

**只读纪律**：child 只执行 checker prompt，禁止发 PR 评论、改标签、push、跑 fix agent、执行 Step 7-10。任一 child 因基础设施失败无结果 → 整轮 blocked，不单独重跑。

- [ ] **Step 7: 保存原始输出并做 schema 检查**

把三个 child 的 JSON 输出分别保存为 `old-explicit.json` / `old-implicit.json` / `new-two-phase.json`，然后：

```bash
python3 - <<'EOF' "$VALIDATION_DIR"
import json, sys
from pathlib import Path

REQUIRED = {"description": str, "reason": str, "file": str, "lines": str, "suggestion": str, "severity": str}
SEVERITIES = {"critical", "high", "medium", "low"}

def check(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list), f"{path.name}: root must be a JSON array"
    for i, item in enumerate(data):
        assert isinstance(item, dict), f"{path.name}[{i}]: not an object"
        for key, typ in REQUIRED.items():
            assert key in item and isinstance(item[key], typ) and item[key], f"{path.name}[{i}]: bad {key}"
        assert "CLAUDE.md" in item["reason"], f"{path.name}[{i}]: reason lacks CLAUDE.md"
        assert item["severity"] in SEVERITIES, f"{path.name}[{i}]: bad severity"
        if "blocking" in item:
            assert isinstance(item["blocking"], bool), f"{path.name}[{i}]: blocking not boolean"
    return data

base = Path(sys.argv[1])
for name in ("old-explicit.json", "old-implicit.json", "new-two-phase.json"):
    findings = check(base / name)
    print(f"{name}: {len(findings)} findings, schema OK")
EOF
```

Expected: 三行 `schema OK`；任一失败 → U1 失败，不进入召回比较，按 spec §9.6 处理（修 prompt 后整轮重跑）。

- [ ] **Step 8: 人工匹配与裁决，写 `comparison.md`**

按 spec §9.5 的匹配规则（file 相同 + lines 重叠/相邻 + 同一问题主张 + 覆盖同一风险/依据/修复方向）对旧方案去重后的每个 finding 标记 `retained` / `duplicate` / `false-positive` / `lost-valid`；新方案额外 finding 标记 `valid` / `false-positive`；哨兵单独标记 `sentinel-retained` / `sentinel-missed`。`comparison.md` 必须记录：模型身份、三份 finding 数、去重与有效性、新旧匹配表、哨兵结果、新增 finding 有效性、最终结论。

- [ ] **Step 9: 通过判定（spec §9.6）**

全部满足才算通过：三次运行同输入同模型且 schema 通过；新方案 `sentinel-retained`（召回 `ZIMA_HOME` 规则违规）；旧方案本轮每个有效 finding 均 `retained`（`lost-valid=0`，不分 severity 放宽）；新方案无规范类 false positive；`comparison.md` 完整。

- [ ] **Step 10: 呈交用户确认**

向用户展示 `comparison.md` 结论并明确询问「是否确认无明显召回损失」。**用户确认前，U1 状态为 pending，不得宣称 issue 完成、不得推进合并。** 若失败：按 spec §9.6 修 prompt（两份副本共同正文）后从 Step 1 整轮重跑，每轮产物存独立子目录。

---

## Self-Review 记录

- **Spec 覆盖**：A1→Task 5；A2/A5/A7→Task 1-2；A3→Task 3-4；A4/A6→Task 1-4；A8→Task 5；U1→Task 6。spec §5 prompt 在 Task 2 Step 1 全量内嵌；spec §6 文件清单与 Task 2/4 一一对应；无遗漏。
- **占位符扫描**：无 TBD/TODO；所有测试代码与文档替换文本均为完整可用内容。
- **类型一致性**：`TestCheckerMergeDocs._checker_section` 与 `TestCcCheckerMergeDocs._checker_section` 提取范围一致（`## claude-compliance-checker` → `## agents-compliance-checker`）；sync guard 复用同一 helper；cc regex key 集合与 pi lane key 集合一致。
- **已知注意点**：`test_pi_and_cc_checker_prompt_sections_are_identical` 在 Task 3 红利期即应 PASS（两侧当前一致），其真正价值在 Task 4 后防漂移；Task 6 是用户实测项，A1-A8 全绿不能替代 U1。
