# cr-batch 模型分档（Issue #224）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `pi/github-code-review-batch` skill 中落地 `PI_CR_FAST_MODEL` / `PI_CR_STRONG_MODEL` 环境变量驱动的模型分档：全流程派发点按职责档位条件注入 `model`，父 agent preflight（格式 → registry → modelScope）失败时省略属性并用固定 `Note:` 披露 fallback。

**Architecture:** 纯文档 + 契约测试改动（无运行时代码）。flow.md Step 4 的「可选自选模型」段重写为「每轮一次 preflight」标准流程；派发示例改为 `FAST_OVERRIDE` / `STRONG_OVERRIDE` 条件 spread；Step 5、Step 10、delta-review.md、subagent-prompts.md、edge-cases.md 同步；`tests/unit/test_cr_batch_contracts.py` 新增 `TestModelTieringDocs` 并迁移一条与条件注入冲突的 #216 旧断言。

**Tech Stack:** Python 3.10+（pytest 契约测试，纯文本断言）、Markdown skill 文档。

**Spec:** `docs/superpowers/specs/2026-09-07-cr-model-tiering-design.md`（worktree 内，用户已批准 2026-09-07）

## Global Constraints

- 所有改动只在 worktree `$WT`（`/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-224-cr-model-tiering`）内进行；git 操作用 `git -C $WT`；禁止碰 main checkout。
- 不引入任何具体模型 ID（#216 契约：`deepseek-v4`、`zai-coding-cn` 等字符串不得出现在 skill 目录任何 `.md`；已有测试 `test_docs_no_hardcoded_deepseek_models` 全程必须保持绿）。
- 环境变量名精确拼写：`PI_CR_FAST_MODEL` / `PI_CR_STRONG_MODEL`，无其他变体。
- fallback 语义：省略整个 `model` 属性（禁止 `model: ""` / `model: null`）；note 固定格式 `model profile fallback: <tier>=resolution-chain (<reason>)`，多档以 `; ` 合并；未配置（disabled）永不披露。
- 术语纪律：全文说「沿用正常 subagent model resolution chain」，不说「继承父模型」「继承当前模型」；不宣称省略 `model` 能修复既有 strict modelScope 越界。
- 现有 `TestModelDispatchDocs` 断言除明确迁移的一条外全部保持绿：`subagent({action:"models"})`、`provider/id`、「不代表模型通过了 modelScope」、`enforce: true`/`strict: true`、`整体替换`、`:max`+`剥离`、`enabledModels` 辨析、「省略 `model`」、「完整的 `provider/id`」+`bare model ID`、「缺省继承当前模型」不在 prompts、resolution chain 在 prompts。
- 派发示例按当前 main 双 checker 形态写；契约测试不锁 checker 数量与 key 名（#225 串行约定）。
- 测试命令：`uv run pytest tests/unit/test_cr_batch_contracts.py -q`；全套：`uv run pytest -q`；lint：`uv run ruff check tests/`；format：`uv run black --check tests/ --line-length 100`。
- Commit message 用 conventional commits（英文）。

---

### Task 1: TestModelTieringDocs 骨架 + preflight 契约测试 + flow.md Step 4 preflight 段重写（验收 A1）

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md`（Step 4 的「按 agent 职责差异化指定模型（#170，可选）」整段，约 237-246 行）
- Test: `tests/unit/test_cr_batch_contracts.py`（新增 class `TestModelTieringDocs`，放在 `TestModelDispatchDocs` 之后）

**Interfaces:**
- Consumes: 现有模块级 `SKILL_DIR`、`pytest`、`re`（文件已 import）。
- Produces: `TestModelTieringDocs.texts` class-scoped fixture（dict：`flow`/`delta`/`prompts`/`edge` 四键 + 全目录 md 兜底）；`TestModelTieringDocs._section(text, start, end)` staticmethod。后续 Task 2/3/4 的测试方法挂载在同一 class 上，复用这两个成员。

- [ ] **Step 1: 写失败测试（preflight 契约）**

在 `tests/unit/test_cr_batch_contracts.py` 的 `TestModelDispatchDocs` class 结束后（`TestStatusReport` 之前）插入：

```python
class TestModelTieringDocs:
    """Issue #224: env-driven model tiering preflight contracts.

    flow.md Step 4 must document the parent-side per-round preflight
    (env read -> format check -> registry confirmation -> effective
    modelScope check -> conditional inject/omit), per-tier independence,
    selector safety, and the conservative default (omit the whole model
    property whenever anything cannot be confirmed).
    """

    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        docs = {
            "flow": (SKILL_DIR / "references" / "flow.md").read_text(encoding="utf-8"),
            "delta": (SKILL_DIR / "references" / "delta-review.md").read_text(
                encoding="utf-8"
            ),
            "prompts": (SKILL_DIR / "references" / "subagent-prompts.md").read_text(
                encoding="utf-8"
            ),
            "edge": (SKILL_DIR / "references" / "edge-cases.md").read_text(
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
        """Slice the text between two literal markers (exclusive of both)."""
        return text.split(start, 1)[1].split(end, 1)[0]

    def _step4_model_section(self, flow_text: str) -> str:
        # Marker matches the rewritten section title added by this issue;
        # before the rewrite this split raises IndexError => test fails (red).
        return self._section(
            flow_text, "模型分档 preflight", "task 的 prompt 模板见"
        )

    # --- A1: preflight variables and order ---

    def test_env_tier_variables_documented(self, texts):
        section = self._step4_model_section(texts["flow"])
        assert "PI_CR_FAST_MODEL" in section
        assert "PI_CR_STRONG_MODEL" in section
        # per-tier independence is stated
        assert "独立" in section

    def test_preflight_order_documented(self, texts):
        section = self._step4_model_section(texts["flow"])
        fmt = section.find("格式校验")
        reg = section.find("registry")
        scope = section.find("modelScope")
        assert 0 <= fmt < reg < scope, (
            "preflight must be documented in order: format -> registry -> modelScope"
        )

    # --- A1: registry guard ---

    def test_registry_guard_documented(self, texts):
        section = self._step4_model_section(texts["flow"])
        assert 'subagent({action:"models"})' in section
        assert "外形不等于" in section and "可用性" in section
        assert "canonical" in section

    # --- A1: modelScope semantics incl. absent-scope case ---

    def test_no_modelscope_means_no_restriction(self, texts):
        section = self._step4_model_section(texts["flow"])
        assert "没有有效 modelScope" in section
        assert "无范围限制" in section
        assert "scope-unverified" in section

    # --- A1: conservative omission + resolution chain boundary ---

    def test_conservative_omission_documented(self, texts):
        section = self._step4_model_section(texts["flow"])
        assert "无法确认" in section
        assert "省略整个 `model` 属性" in section
        assert "resolution chain" in section
        # must NOT promise fallback equals parent session model
        assert "继承父模型" not in section
        assert "继承当前模型" not in section

    # --- A1: selector safety ---

    def test_selector_safety_documented(self, texts):
        section = self._step4_model_section(texts["flow"])
        assert "trim" in section
        assert "控制字符" in section
        assert "字面量" in section
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: FAIL（6 个测试因 `_step4_model_section` 找不到新内容而 fail；若 split marker 不存在会 IndexError，同样算 fail）

- [ ] **Step 3: 重写 flow.md Step 4 模型段**

将 flow.md 中从 `**按 agent 职责差异化指定模型（#170，可选）**：` 开始、到 `注意：\`enabledModels\`...` 段结尾（含该行）的整块替换为：

````markdown
**模型分档 preflight（#224，每轮一次，必做）**：subagent 工具的派发项支持 `model` 字段。本流程的模型分档由环境变量驱动（部署策略），父 Pi agent 只做解析与守门，不自选、不猜模型名；child reviewer 自身不参与选型。首轮在 Step 4 派发前、增量轮在进入 delta-review 前各执行一次 preflight，该轮内 Step 4 / Step 5 / Round-2 的所有派发项复用同一结果。

对 `PI_CR_FAST_MODEL` 与 `PI_CR_STRONG_MODEL` 各自独立执行（两档独立解析、独立 fallback，只配一档不影响另一档）：

1. **读取并 trim 环境变量**：空值或仅空白视为该档未启用（disabled），不记 fallback。
2. **格式校验**：值必须是完整 `provider/id` 形态；先 trim，包含换行、控制字符或未闭合引号的值视为格式非法（invalid）。可选保留 Pi 已知 thinking 后缀（off/minimal/low/medium/high/xhigh/max）。失败 → 该档省略 `model`，reason 记 `invalid`。
3. **registry 可用性确认**：`provider/id` 外形不等于 registry 可用性。父 agent 调用 `subagent({action:"models"})` 获取当前 registry——该列表用于确认候选值存在，不代表模型通过了 modelScope 政策。剥离已知 thinking 后缀后，候选 base selector 必须能在当前 registry 中确认；只使用 registry 确认过的 canonical 完整 `provider/id`，不按 bare id 猜测。查询失败、候选不存在或无法唯一确认 → 该档省略 `model`，reason 记 `registry-unavailable`。
4. **有效 modelScope 确认**：读取当前 Pi 进程实际生效的 settings，检查 `subagents.modelScope.allow`；本流程所有 child 都用 `agent: "reviewer"`，若存在 `subagents.modelScope.agents.reviewer.allow`，还必须同时通过该角色级 allowlist。项目级 `.pi/settings.json` 只有在当前非交互 Pi 进程信任并加载时才生效；生效时项目级 `subagents.modelScope` 整体替换用户级同名配置。**没有有效 modelScope 或限制未启用（如 `enforce: false`）时视为无范围限制**，registry 确认仍然必需；**modelScope 存在但无法可靠判断有效配置时按 scope-unverified 处理，不得当作无限制**。已启用限制且候选不匹配 → 该档省略 `model`，reason 记 `scope-rejected`。
5. **条件注入或省略**：通过全部确认的档，把 registry 确认过的 canonical selector 以安全 JS 字符串字面量写入派发项 `model`（禁止把未经确认的环境变量原文直接拼接进 workflowScript）；任何一步无法确认的档，**省略整个 `model` 属性**（不写空字符串、不写 null），由 Pi 沿用正常 subagent model resolution chain 解析——这不保证最终模型等于父 session 模型，也不修复既有 strict modelScope 越界（后者是既有部署配置问题，不由本流程处理）。

档位映射（详见下方派发示例与 [Step 5](#step-5) / [delta-review.md](delta-review.md)）：

| 职责 | profile |
|---|---|
| CLAUDE.md checker ×2、AGENTS.md checker、bug-scanner | fast（`PI_CR_FAST_MODEL`） |
| issue-validator ×N | fast（`PI_CR_FAST_MODEL`） |
| logic-analyzer、delta-reviewer | strong（`PI_CR_STRONG_MODEL`） |

`subagents.modelScope` 是模型范围政策，不负责选择便宜模型：`enforce: true` 时显式传入的越界模型在 child 启动前报错；`strict: true` 进一步拒绝从 agent frontmatter、`subagents.defaultModel`、父 session 或 fallback 链解析出的越界模型。`allow` 按 resolved `provider/id` 做 glob 匹配，已知 thinking 后缀（如 `:max`）匹配时被剥离，无需为后缀单独加条目。

注意：`enabledModels`（settings 顶层）是主会话模型循环候选范围，不是 subagent 的 modelScope allowlist；它可能间接影响继承父 session 模型的 child，但不能用来判断 child 是否获准派发。
````

保留紧跟其后的原有内容（「task 的 prompt 模板见…」起）不动。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: 6 passed

- [ ] **Step 5: 跑 #216 旧测试确认无回归**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs -q`
Expected: 全部 passed（替换段保留了 `subagent({action:"models"})`、`provider/id`、「不代表模型通过了 modelScope」、`enforce: true`/`strict: true`、`整体替换`、`:max`+`剥离`、`enabledModels`、「省略 `model`」等关键句）

- [ ] **Step 6: Commit**

```bash
cd $WT && git add pi/github-code-review-batch/references/flow.md tests/unit/test_cr_batch_contracts.py
git commit -m "docs(cr-batch): model tiering preflight section in flow.md Step 4 (#224)"
```

---

### Task 2: 派发示例条件 spread 化 + 旧断言迁移（验收 A1，#216 冲突解决）

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md`（Step 4 的 `runs.all` 示例代码块）
- Modify: `tests/unit/test_cr_batch_contracts.py`（`TestModelDispatchDocs::test_step4_example_has_no_model_field`）

**Interfaces:**
- Consumes: Task 1 的 `TestModelTieringDocs.texts` fixture 与 `_section` helper。
- Produces: 迁移后的 `test_step4_example_conditional_model_spread`（挂在 `TestModelDispatchDocs`，沿用其 `_step4_runs_all_example` helper）。

- [ ] **Step 1: 迁移旧断言并新增 spread 契约（先改测试到失败态）**

在 `TestModelDispatchDocs` 中，将：

```python
    def test_step4_example_has_no_model_field(self, texts):
        block = self._step4_runs_all_example(texts["flow"])
        assert "model:" not in block
```

替换为：

```python
    def test_step4_example_conditional_model_spread(self, texts):
        """#224: the example shows conditional injection via spread objects;
        fallback omits the whole property (no null / empty-string model)."""
        block = self._step4_runs_all_example(texts["flow"])
        assert "FAST_OVERRIDE" in block
        assert "STRONG_OVERRIDE" in block
        assert 'model: "' not in block  # no literal model id anywhere
        assert "model:" not in block  # property only appears via spread
        assert "model: null" not in block
        assert 'model: ""' not in block
```

同时在 `TestModelTieringDocs` 末尾追加（示例形态契约，fallback 注释说明省略语义）：

```python
    def test_dispatch_example_spread_documented(self, texts):
        step4 = self._section(texts["flow"], "## Step 4", "## Step 5")
        assert "FAST_OVERRIDE" in step4 and "STRONG_OVERRIDE" in step4
        # spread-object comment must explain fallback = property omitted
        assert "...FAST_OVERRIDE" in step4 or "...STRONG_OVERRIDE" in step4
        assert "or omit" in step4 or "省略" in step4
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs::test_step4_example_conditional_model_spread tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: 2 个新断言 FAIL（旧示例无 spread），其余 TestModelTieringDocs 保持 pass

- [ ] **Step 3: 更新 flow.md Step 4 派发示例**

将 Step 4 现有 `runs.all` 示例代码块整体替换为：

```js
// Parent resolves each profile once per round (see "模型分档 preflight").
// FAST_OVERRIDE / STRONG_OVERRIDE hold the registry-confirmed canonical
// provider/id selector for their tier when preflight enabled it; a fallback
// tier uses {} so the dispatch item omits that property entirely
// (Pi resolution chain applies).
await runs.all([
  { key: "claude-checker-1", agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "<claude-compliance-checker prompt，显式规则 framing>" },
  { key: "claude-checker-2", agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "<claude-compliance-checker prompt，隐含约定 framing>" },
  { key: "agents-checker",   agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "<agents-compliance-checker prompt>" },
  { key: "bug-scanner",      agent: "reviewer", context: "fresh", ...FAST_OVERRIDE, task: "<bug-scanner prompt>" },
  { key: "logic-analyzer",   agent: "reviewer", context: "fresh", ...STRONG_OVERRIDE, task: "<logic-analyzer prompt>" },
])
```

并在代码块后补一行说明：

```markdown
spread 对象在 preflight 通过时持有 registry 确认过的 canonical `provider/id`；fallback 时为空对象，对应派发项的 `model` 属性整个省略（禁止 `model: ""` / `model: null` 伪装省略），由 Pi 正常 resolution chain 解析。示例按当前双 checker 形态书写，#225（checker 合并）落地后按实际 agent 数量更新，档位归属不变。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
cd $WT && git add pi/github-code-review-batch/references/flow.md tests/unit/test_cr_batch_contracts.py
git commit -m "docs(cr-batch): conditional model spread in Step 4 dispatch example (#224)"
```

---

### Task 3: 全流程档位映射接线（Step 5 + delta-review.md）+ 映射契约测试（验收 A2）

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md`（Step 5 派发段，293 行附近）
- Modify: `pi/github-code-review-batch/references/delta-review.md`（Step Δ2 与 Δ2a，29-50 行附近）
- Test: `tests/unit/test_cr_batch_contracts.py`（`TestModelTieringDocs` 追加映射测试）

**Interfaces:**
- Consumes: Task 1 的 `texts` fixture、`_section` helper；Task 1 已写入的 preflight 段（被引用）。
- Produces: flow.md Step 5 与 delta-review.md 中的档位标注句（后续 Task 4 的 note 契约、Task 5 的 prompts 摘要引用「flow.md Step 4 为单一事实源」的表述）。

- [ ] **Step 1: 写失败测试（映射契约）**

在 `TestModelTieringDocs` 末尾追加：

```python
    # --- A2: tier mapping across all dispatch points ---

    def test_step5_validator_fast_tier(self, texts):
        step5 = self._section(texts["flow"], "## Step 5", "## Step 6")
        assert "issue-validator" in step5 or "验证" in step5
        assert "fast" in step5 and "PI_CR_FAST_MODEL" in step5

    def test_delta_review_tier_mapping(self, texts):
        # delta-reviewer -> strong
        delta2 = self._section(texts["delta"], "Step Δ2:", "Step Δ3:")
        assert "delta-reviewer" in delta2
        assert "strong" in delta2 and "PI_CR_STRONG_MODEL" in delta2
        # Δ2a: bug-scanner -> fast, logic-analyzer -> strong
        delta2a = self._section(texts["delta"], "Step Δ2a:", "Step Δ3:")
        assert "bug-scanner" in delta2a and "logic-analyzer" in delta2a
        assert "PI_CR_FAST_MODEL" in delta2a and "PI_CR_STRONG_MODEL" in delta2a
        # mapping lines keep agent and tier on the same line
        for line in delta2a.splitlines():
            if "PI_CR_FAST_MODEL" in line:
                assert "bug-scanner" in line
            if "PI_CR_STRONG_MODEL" in line:
                assert "logic-analyzer" in line

    def test_round_entry_single_preflight(self, texts):
        flow_section = self._step4_model_section(texts["flow"])
        delta_text = texts["delta"]
        assert "一次 preflight" in flow_section or "各执行一次 preflight" in flow_section
        assert "preflight" in delta_text and "复用" in delta_text

    def test_flow_mapping_table_pairs(self, texts):
        section = self._step4_model_section(texts["flow"])
        for line in section.splitlines():
            if "PI_CR_FAST_MODEL" in line:
                assert any(
                    name in line
                    for name in ("checker", "bug-scanner", "validator")
                ), f"fast mapping line missing agent: {line}"
            if "PI_CR_STRONG_MODEL" in line:
                assert any(
                    name in line for name in ("logic-analyzer", "delta-reviewer")
                ), f"strong mapping line missing agent: {line}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: 新增 4 个测试 FAIL（Step 5 / delta-review.md 尚无档位标注），Task 1/2 的测试保持 pass

- [ ] **Step 3: flow.md Step 5 加档位标注**

在 Step 5 首段「对 [Step 4](#step-4) 中发现的每一个 issue，启动一个并行 `subagent` 进行验证…」句后追加一句：

```markdown
issue-validator 使用 fast profile（`PI_CR_FAST_MODEL`）：派发项复用本轮 Step 4 的 preflight 结果（见 [Step 4 模型分档 preflight](#step-4)），不在每个 validator 前重复解析。
```

- [ ] **Step 4: delta-review.md 加 preflight 接线**

在 delta-review.md「## 执行步骤」标题后、Step Δ1 之前插入：

```markdown
### Step Δ0: 模型分档 preflight（#224）

增量轮入口执行一次 preflight（流程同 [flow.md Step 4 模型分档 preflight](flow.md#step-4)），本文件所有 Round-2 派发复用同一结果：

- **delta-reviewer** 使用 strong profile（`PI_CR_STRONG_MODEL`）
- **Δ2a bug-scanner** 使用 fast profile（`PI_CR_FAST_MODEL`）
- **Δ2a logic-analyzer** 使用 strong profile（`PI_CR_STRONG_MODEL`）

档位判定与 fallback 语义以 [flow.md Step 4](flow.md#step-4) 为单一事实源；不因增量轮重新读取或猜测另一套模型。
```

同时在 Step Δ2 段（delta-reviewer 输入列表的末行「相关规范文件内容」之后）追加一句：

```markdown

delta-reviewer 使用 strong profile（`PI_CR_STRONG_MODEL`），复用 [Step Δ0](#step-Δ0) 的 preflight 结果。
```

并在 Step Δ2a 段「把该 delta-diff…优雅降级。」段落后追加一句：

```markdown

Δ2a bug-scanner 使用 fast profile（`PI_CR_FAST_MODEL`）、Δ2a logic-analyzer 使用 strong profile（`PI_CR_STRONG_MODEL`），均复用 [Step Δ0](#step-Δ0) 的 preflight 结果。
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: 全部 passed

- [ ] **Step 6: Commit**

```bash
cd $WT && git add pi/github-code-review-batch/references/flow.md pi/github-code-review-batch/references/delta-review.md tests/unit/test_cr_batch_contracts.py
git commit -m "docs(cr-batch): wire fast/strong tiers into Step 5 and delta-review dispatch (#224)"
```

---

### Task 4: fallback 披露接线（Step 10 note + edge-cases.md）+ 披露契约测试（验收 A3）

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md`（Step 10，「部分覆盖提示（#120）」段之后）
- Modify: `pi/github-code-review-batch/references/edge-cases.md`（「边界情况处理」表新增行 + 表后小节）
- Test: `tests/unit/test_cr_batch_contracts.py`（`TestModelTieringDocs` 追加披露测试）

**Interfaces:**
- Consumes: `render_status_report.py` 的可选 `note` 字段（#223 已建，零代码改动）；Task 1 的 preflight reason 集合（`invalid` / `registry-unavailable` / `scope-rejected` / `scope-unverified`）。
- Produces: Step 10 的「模型 fallback note（#224）」段；edge-cases.md 的模型分档边界条目。

- [ ] **Step 1: 写失败测试（披露契约）**

在 `TestModelTieringDocs` 末尾追加：

```python
    # --- A3: fallback disclosure via note ---

    def _step10_section(self, flow_text: str) -> str:
        # Step 10 spans the title through the end of the report-format body
        # ("### 用途" starts the trailing usage subsection).
        return self._section(flow_text, "## Step 10", "### 用途")

    def test_step10_model_fallback_note_contract(self, texts):
        step10 = self._step10_section(texts["flow"])
        assert "model profile fallback:" in step10
        assert "resolution-chain" in step10
        assert "未启用" in step10 or "disabled" in step10
        # unset tiers never appear in the note
        assert "不出现" in step10 or "不记" in step10

    def test_edge_cases_document_model_tiering(self, texts):
        edge = texts["edge"]
        assert "PI_CR_FAST_MODEL" in edge and "PI_CR_STRONG_MODEL" in edge
        for reason in ("invalid", "registry-unavailable", "scope-rejected", "scope-unverified"):
            assert reason in edge, f"edge-cases.md missing reason {reason}"
        assert "resolution-chain" in edge
        # disabled (unset) must be silent
        assert "静默" in edge

    def test_note_format_is_fixed(self, texts):
        step10 = self._step10_section(texts["flow"])
        # exact fixed format with mergeable tiers
        assert "<tier>=resolution-chain (<reason>)" in step10
        assert "; " in step10
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: 新增 3 个测试 FAIL，其余保持 pass

- [ ] **Step 3: flow.md Step 10 加 note 接线段**

在 Step 10「部分覆盖提示（#120）」段落之后插入：

```markdown
**模型 fallback note（#224）**：仅当已配置（非空）的档位在 preflight 中失败时，向 `render_status_report.py` 传入 `note`，固定格式：

```text
model profile fallback: <tier>=resolution-chain (<reason>)
```

reason 取 preflight 结果：`invalid` / `registry-unavailable` / `scope-rejected` / `scope-unverified`。两档同时 fallback 时合并为一条（以 `; ` 分隔），例：

```text
model profile fallback: fast=resolution-chain (invalid); strong=resolution-chain (scope-rejected)
```

未启用的档（未配置或空白）不出现、不记 fallback，报告保持静默；正常 enabled 档同样静默。`resolution-chain` 只表示派发项省略了 per-run `model` 属性（由 Pi 正常 resolution chain 解析），不表示最终模型一定是父 session 模型。模型 fallback note 与上文 `Diff truncated` / `Coverage` 提示相互独立、可同时存在（note 与 coverage 是 renderer 的不同输入字段）。
```

- [ ] **Step 4: edge-cases.md 加边界条目**

在「边界情况处理」表末尾（`.claude/cr-supstitutions.json` 行后）追加一行：

```markdown
| 两个模型档环境变量都未设置 | 两档均 disabled，派发不带 per-run `model`，沿用正常 resolution chain；报告静默，无模型 fallback note（#224） |
```

并在「边界情况处理」表之后、「故障排除」之前插入小节：

```markdown
### 模型分档边界（#224）

- `PI_CR_FAST_MODEL` / `PI_CR_STRONG_MODEL` 只设置一个：只解析对应档；另一档未启用，沿用正常 resolution chain 且不记 fallback。
- 环境变量值为空白：按未设置处理（disabled），静默。
- 非空但格式非法（非 `provider/id` 形态、含换行/控制字符/未闭合引号）：该档 fallback，省略整个 `model` 属性，note 记 `<tier>=resolution-chain (invalid)`。
- 格式正确但当前 registry 查不到 / 查询失败 / 无法唯一确认：该档 fallback，note 记 `<tier>=resolution-chain (registry-unavailable)`。`provider/id` 外形不等于可用性。
- registry 确认但有效 modelScope 不允许：该档 fallback，note 记 `<tier>=resolution-chain (scope-rejected)`。
- modelScope 配置存在但无法可靠判断有效规则：该档 fallback，note 记 `<tier>=resolution-chain (scope-unverified)`，不得当作无 modelScope 处理。
- 没有有效 modelScope 或限制未启用：不构成 scope 拒绝（无范围限制），registry 确认仍必需。
- 两个变量配了相同 selector：合法，两档独立 enabled，等效单档。
- fallback 后的实际模型：由 Pi 正常 subagent model resolution chain（per-run → provider-scoped → agentOverrides → frontmatter → `subagents.defaultModel` → parent session model）决定，不保证等于父 session 模型；既有 strict modelScope 越界不由本流程修复。
- thinking 后缀：只接受 Pi 已知后缀；registry 与 allowlist 匹配时剥离后缀，派发保留确认过的完整 selector；本流程不新增 thinking policy。
- checker 合并（#225）后：checker 数量变化不改变其 fast 档归属。
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs -q`
Expected: 全部 passed

- [ ] **Step 6: Commit**

```bash
cd $WT && git add pi/github-code-review-batch/references/flow.md pi/github-code-review-batch/references/edge-cases.md tests/unit/test_cr_batch_contracts.py
git commit -m "docs(cr-batch): fixed-format model fallback note wiring in Step 10 + edge cases (#224)"
```

---

### Task 5: subagent-prompts.md 单一事实源摘要 + 全套回归（验收 A4/A5 收口）

**Files:**
- Modify: `pi/github-code-review-batch/references/subagent-prompts.md`（header 第 3 行「pi 派发方式」段末尾追加）
- Test: `tests/unit/test_cr_batch_contracts.py`（`TestModelTieringDocs` 追加 prompts 契约）

**Interfaces:**
- Consumes: Task 1-4 已写入 flow.md 的 preflight / 映射 / note 契约（作为单一事实源被引用）。
- Produces: prompts header 的档位摘要句；全套绿 = A4/A5 验收完成。

- [ ] **Step 1: 写失败测试（prompts 摘要契约）**

在 `TestModelTieringDocs` 末尾追加：

```python
    # --- A4: prompts header points to flow.md as single source ---

    def test_prompts_header_tiering_summary(self, texts):
        header = texts["prompts"].split("## summarizer", 1)[0]
        assert "PI_CR_FAST_MODEL" in header and "PI_CR_STRONG_MODEL" in header
        assert "单一事实源" in header
        assert "flow.md" in header
        # must not restate full mapping per agent (single source only)
        body = texts["prompts"].split("## summarizer", 1)[1]
        assert "PI_CR_FAST_MODEL" not in body
        assert "PI_CR_STRONG_MODEL" not in body
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelTieringDocs::test_prompts_header_tiering_summary -q`
Expected: FAIL

- [ ] **Step 3: subagent-prompts.md header 追加摘要**

在 header「pi 派发方式」段（以「细则见 [flow.md Step 4](flow.md#step-4)。」结尾）的句号后追加：

```markdown
模型分档（#224）由环境变量 `PI_CR_FAST_MODEL` / `PI_CR_STRONG_MODEL` 驱动：父 Pi 每轮执行一次 preflight（格式 → registry → modelScope），按职责档位条件注入或省略派发项的 `model`；档位映射、fallback reason 与 note 披露以 [flow.md Step 4](flow.md#step-4) 为单一事实源，本文件不逐 agent 重复维护。
```

- [ ] **Step 4: 跑全套回归（A4 + A5）**

Run（四条逐一执行，全部要求 0 fail / 0 error）：

```bash
cd $WT && uv run pytest tests/unit/test_cr_batch_contracts.py -q
cd $WT && uv run pytest -q
cd $WT && uv run ruff check tests/
cd $WT && uv run black --check tests/ --line-length 100
```

Expected: 全部通过（含 `TestModelDispatchDocs` 全组、`test_docs_no_hardcoded_deepseek_models` 全目录扫描、全套件）

- [ ] **Step 5: 尾部检查 + Commit**

```bash
cd $WT && git diff --check && git status --short
git add pi/github-code-review-batch/references/subagent-prompts.md tests/unit/test_cr_batch_contracts.py
git commit -m "docs(cr-batch): prompts header model-tiering summary + full regression green (#224)"
```

---

## 验收对账表（plan ↔ spec 双向追溯）

| Spec 验收 ID | 覆盖 Task | 自动化证据 |
|---|---|---|
| A1 preflight 顺序与 registry 守门 | Task 1（+Task 2 示例形态） | `TestModelTieringDocs` preflight 6 测 + spread 2 测 |
| A2 全流程档位映射 | Task 3 | 映射 4 测（Step 5 / delta / 轮次单次解析 / 映射表行配对） |
| A3 fallback 与 note 语义 | Task 4 | 披露 3 测（Step 10 契约 / edge 条目 / 固定格式） |
| A4 #216 文档无回归 | Task 1 Step 5 / Task 5 Step 4 | `TestModelDispatchDocs` 全组 + no-hardcoded 全目录 |
| A5 文档格式与全套回归 | Task 5 Step 4 | pytest 全套 + ruff + black |
| U1a/U1b/U2/U3 | 合并后用户实测（plan 不含；PR 描述与 issue 评论记录步骤） | — |
