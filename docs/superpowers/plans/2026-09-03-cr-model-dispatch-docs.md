# CR Skill Model Dispatch Docs Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove hardcoded model recommendations from the CR skill dispatch docs and replace them with parent-Pi model-confirmation guidance that respects `subagents.modelScope` (issue #207).

**Architecture:** Two docs (`flow.md`, `subagent-prompts.md`) are rewritten so the canonical `runs.all` example omits `model` and optional explicit tiering requires full `provider/id` validated against the effective modelScope. A new `TestModelDispatchDocs` contract-test class in `tests/unit/test_cr_batch_contracts.py` locks the documentation contract with pure text assertions (no IO, no Pi runtime), so regressions fail CI instead of silently misleading dispatch agents.

**Tech Stack:** Markdown skill docs (Chinese), pytest contract tests (English docstrings), Python stdlib `re` only.

**Spec:** `docs/superpowers/specs/2026-09-03-cr-model-dispatch-docs-design.md`

## Global Constraints

- Do not modify `SKILL.md` trigger phrases (`batch review pr`, `review pr batch`, `scheduled review pr`) — external contract with zima daemon.
- Skill docs are written in Chinese; test code/docstrings/comments in English.
- Tests use Python stdlib + pytest only — no third-party deps (portability contract of the skill scripts).
- Formatting: `black --line-length 100`, `ruff check` must pass on touched Python files.
- Commit format: conventional commits (`docs(...)` / `test(...)`).
- No hardcoded provider/model names may remain in dispatch guidance (`deepseek-v4*`, `zai-coding-cn/*`, etc.).
- All paths below are relative to the worktree root; the session operates via absolute path `WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-207-cr-model-dispatch-docs`.

---

### Task 1: flow.md model-dispatch fix + flow contract tests

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md` (Step 4 area: dispatch example lines ~204-214)
- Modify: `tests/unit/test_cr_batch_contracts.py` (add `TestModelDispatchDocs` class + `import re`)

**Interfaces:**
- Consumes: existing `SKILL_DIR` constant and class-scoped `texts` fixture pattern from `TestBlockingPolicyDocumentation` in the same test file.
- Produces: `TestModelDispatchDocs._step4_runs_all_example(flow_text) -> str` static helper; flow-focused tests that Task 2 leaves untouched. The class is extended (not replaced) in Task 2.

- [ ] **Step 1: Write the failing flow contract tests**

In `tests/unit/test_cr_batch_contracts.py`, add `re` to the stdlib imports (after `import json`):

```python
import re
```

Then append this class after `TestBlockingPolicyDocumentation`:

```python
class TestModelDispatchDocs:
    """Issue #207: dispatch guidance must not hardcode models or cite
    enabledModels as the subagent dispatch authority.

    The Step 4 runs.all example omits ``model``; explicit per-role tiering is
    documented as a parent-Pi responsibility requiring a full provider/id that
    passes both the registry and the effective subagents.modelScope.
    """

    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        return {
            "flow": (SKILL_DIR / "references" / "flow.md").read_text(encoding="utf-8"),
            "prompts": (SKILL_DIR / "references" / "subagent-prompts.md").read_text(
                encoding="utf-8"
            ),
        }

    @staticmethod
    def _step4_runs_all_example(flow_text: str) -> str:
        """Extract the first js code block inside flow.md Step 4 (the runs.all fanout)."""
        step4 = flow_text.split("## Step 4", 1)[1].split("## Step 5", 1)[0]
        blocks = re.findall(r"```js\n(.*?)```", step4, re.DOTALL)
        assert blocks and "runs.all" in blocks[0], (
            "Step 4 must contain a js code block with the runs.all fanout"
        )
        return blocks[0]

    # --- A1: canonical dispatch example carries no model selection ---

    def test_step4_example_has_no_model_field(self, texts):
        block = self._step4_runs_all_example(texts["flow"])
        assert "model:" not in block

    def test_docs_no_hardcoded_deepseek_models(self, texts):
        for name, text in texts.items():
            assert "deepseek-v4" not in text, f"hardcoded model remains in {name}"

    # --- A2: explicit-model confirmation flow is documented ---

    def test_flow_documents_parent_pi_confirmation_flow(self, texts):
        flow = texts["flow"]
        assert 'subagent({action:"models"})' in flow
        assert "provider/id" in flow
        # registry listing must be distinguished from modelScope policy
        assert "不代表模型通过了 modelScope" in flow

    def test_flow_documents_omit_model_when_unverified(self, texts):
        assert "省略 `model`" in texts["flow"]

    def test_flow_documents_full_provider_id_requirement(self, texts):
        flow = texts["flow"]
        assert "完整的 `provider/id`" in flow
        assert "bare model ID" in flow

    # --- A3: modelScope semantics ---

    def test_flow_documents_model_scope_layers(self, texts):
        flow = texts["flow"]
        assert "subagents.modelScope" in flow
        assert "agents.reviewer.allow" in flow
        assert "`enforce: true`" in flow
        assert "`strict: true`" in flow
        assert "整体替换" in flow  # project-level modelScope replaces user-level
        assert ":max" in flow and "剥离" in flow  # thinking suffix stripped

    # --- A4: enabledModels semantics ---

    def test_flow_distinguishes_enabled_models_from_model_scope(self, texts):
        flow = texts["flow"]
        assert "enabledModels" in flow
        assert "不是 subagent 的 modelScope allowlist" in flow
        # indirect parent-model inheritance influence acknowledged
        assert "继承父 session 模型" in flow
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs -v`
Expected: FAIL — `test_step4_example_has_no_model_field` (example still has `model:`), `test_docs_no_hardcoded_deepseek_models`, guidance assertions fail on missing phrases.

- [ ] **Step 3: Fix the flow.md dispatch example**

In `pi/github-code-review-batch/references/flow.md`, replace the two dispatch lines that carry `model:` (currently lines 209-210) so the block reads:

```js
await runs.all([
  { key: "claude-checker-1", agent: "reviewer", context: "fresh", task: "<claude-compliance-checker prompt，显式规则 framing>" },
  { key: "claude-checker-2", agent: "reviewer", context: "fresh", task: "<claude-compliance-checker prompt，隐含约定 framing>" },
  { key: "agents-checker",    agent: "reviewer", context: "fresh", task: "<agents-compliance-checker prompt>" },
  { key: "bug-scanner",       agent: "reviewer", context: "fresh", task: "<bug-scanner prompt>" },
  { key: "logic-analyzer",    agent: "reviewer", context: "fresh", task: "<logic-analyzer prompt>" },
])
```

- [ ] **Step 4: Replace the tiering paragraph**

Replace the single paragraph currently at line 214 (starting `**按 agent 职责差异化指定模型（#170，可选）**` and ending `模型名以 ~/.pi/agent/settings.json 的 enabledModels 为准。`) with:

```markdown
**按 agent 职责差异化指定模型（#170，可选）**：subagent 工具的派发项支持 `model` 字段，但上面的主派发示例默认不指定它。若确实需要按职责分档（机械扫描用便宜快模型、跨文件逻辑/安全推理用强模型），模型由执行本 skill 的父 Pi agent 选择，child reviewer 自身不参与选型：

1. 用 `subagent({action:"models"})` 查询当前 registry 中准确的 `provider/id`——该列表只用于确认 canonical ID，不代表模型通过了 modelScope 政策。
2. 读取当前实际生效的 settings，检查 `subagents.modelScope.allow`；本流程所有 child 都用 `agent: "reviewer"`，若存在 `subagents.modelScope.agents.reviewer.allow`，还必须同时通过该角色级 allowlist。
3. 项目级 `.pi/settings.json` 只有在当前非交互 Pi 进程信任并加载时才生效；生效时项目级 `subagents.modelScope` 整体替换用户级同名配置。
4. 显式传入时使用完整的 `provider/id`，不要使用可能跨 provider 歧义的 bare model ID（多 provider 注册同名 ID 时无法消歧，会在 modelScope 检查前解析失败）。无法确认有效 modelScope 时，省略 `model` 字段，不要按 registry 列表猜测。

`subagents.modelScope` 是模型范围政策，不负责选择便宜模型：`enforce: true` 时显式传入的越界模型在 child 启动前报错；`strict: true` 进一步拒绝从 agent frontmatter、`subagents.defaultModel`、父 session 或 fallback 链解析出的越界模型。`allow` 按 resolved `provider/id` 做 glob 匹配，已知 thinking 后缀（如 `:max`）匹配时被剥离，无需为后缀单独加条目。

注意：`enabledModels`（settings 顶层）是主会话模型循环候选范围，不是 subagent 的 modelScope allowlist；它可能间接影响继承父 session 模型的 child，但不能用来判断 child 是否获准派发。
```

- [ ] **Step 5: Run flow tests to verify they pass**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs -v`
Expected: PASS for all tests added in Step 1 (Task 2 adds the prompts-specific tests).

- [ ] **Step 6: Commit**

```bash
git add pi/github-code-review-batch/references/flow.md tests/unit/test_cr_batch_contracts.py
git commit -m "docs(cr-batch): drop hardcoded dispatch models, document modelScope-aware selection (#207)

The Step 4 runs.all example no longer passes model; explicit per-role
tiering is now parent-Pi guidance: resolve canonical provider/id via
subagent({action:\"models\"}), validate against the effective
subagents.modelScope (global allow + reviewer agent-scope allowlist),
prefer full provider/id over ambiguous bare ids, and omit model when
the effective scope cannot be confirmed. enabledModels is documented
as the main-session cycling scope, not a subagent allowlist."
```

---

### Task 2: subagent-prompts.md header fix + prompts contract tests

**Files:**
- Modify: `pi/github-code-review-batch/references/subagent-prompts.md` (header blockquote, line 3)
- Modify: `tests/unit/test_cr_batch_contracts.py` (extend `TestModelDispatchDocs`)

**Interfaces:**
- Consumes: `TestModelDispatchDocs` class and its `texts` fixture from Task 1.
- Produces: none (final docs state; Task 3 runs the full regression).

- [ ] **Step 1: Write the failing prompts contract tests**

Append to `TestModelDispatchDocs`:

```python
    # --- A5: prompts header has no stale guidance ---

    def test_prompts_header_no_stale_inheritance_claim(self, texts):
        prompts = texts["prompts"]
        assert "缺省继承当前模型" not in prompts
        assert "以 `enabledModels` 为准" not in prompts

    def test_prompts_header_documents_resolution_chain(self, texts):
        prompts = texts["prompts"]
        assert "subagents.defaultModel" in prompts
        assert "modelScope" in prompts
        # model selection belongs to the parent Pi, not the child reviewer
        assert "父 Pi" in prompts
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs -v`
Expected: the two new prompts tests FAIL (header still says `缺省继承当前模型`); Task 1 tests keep passing.

- [ ] **Step 3: Rewrite the prompts header blockquote**

In `pi/github-code-review-batch/references/subagent-prompts.md`, replace the first blockquote paragraph (line 3, ending `缺省继承当前模型）。`) with:

```markdown
> **pi 派发方式**：本文件的 prompt 模板在 pi 下由父 Pi agent 通过 `subagent` 工具派发——`agent: "reviewer"`（或项目自定义审查 agent）、`context: "fresh"`，task 字段填下方模板并代入输入变量。并行 fanout 用 subagent 工具的 `workflowScript` + `runs.all`（见 [flow.md Step 4](flow.md#step-4)）。派发项可按需指定 `model` 字段（#170 按职责分档），但默认不指定：缺省时由 pi-subagents 按 per-run override → provider-scoped override → `agentOverrides.<name>.model` → agent frontmatter → `subagents.defaultModel` → parent session model 的解析链决定。若显式指定，父 Pi 必须先确认完整 `provider/id` 同时满足当前 registry 与生效的 `subagents.modelScope`（含 reviewer 角色级 allowlist，如有）；细则见 [flow.md Step 4](flow.md#step-4)。
```

- [ ] **Step 4: Run class tests to verify all pass**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py::TestModelDispatchDocs -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add pi/github-code-review-batch/references/subagent-prompts.md tests/unit/test_cr_batch_contracts.py
git commit -m "docs(cr-batch): replace stale inheritance claim in prompts header (#207)

Document the full pi-subagents model resolution chain and the
modelScope validation duty of the parent Pi instead of the
incomplete 'inherits current model by default' wording."
```

---

### Task 3: Full regression + acceptance reconciliation

**Files:**
- No new modifications; verification only.

**Interfaces:**
- Consumes: Tasks 1-2 commits on branch `issue-207-cr-model-dispatch-docs`.
- Produces: acceptance ledger A1-A6 verified, U1/U2 recorded as pending user verification.

- [ ] **Step 1: Run the full contract suite (A6)**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py -v`
Expected: PASS — all existing contracts (trigger phrases, status report, metadata, portability) plus the new class stay green.

- [ ] **Step 2: Lint and format checks on touched Python file**

Run: `uv run black --check tests/unit/test_cr_batch_contracts.py --line-length 100 && uv run ruff check tests/unit/test_cr_batch_contracts.py`
Expected: both pass. If black reports reformatting needs, apply `uv run black tests/unit/test_cr_batch_contracts.py --line-length 100` and amend nothing — commit the formatting separately:

```bash
git add tests/unit/test_cr_batch_contracts.py
git commit -m "style: black formatting for contract tests"
```

- [ ] **Step 3: Whitespace and diff sanity**

Run: `git diff --check main` then `git diff main --stat`
Expected: no whitespace errors; changes limited to `flow.md`, `subagent-prompts.md`, `tests/unit/test_cr_batch_contracts.py` (plus optional style commit), and the spec/plan docs.

- [ ] **Step 4: Acceptance ledger reconciliation (A1-A6, U1/U2)**

Fill in with actual command results:

| ID | Status | Evidence |
|----|--------|----------|
| A1 | pass | `test_step4_example_has_no_model_field` + `test_docs_no_hardcoded_deepseek_models` |
| A2 | pass | `test_flow_documents_parent_pi_confirmation_flow` + `test_flow_documents_omit_model_when_unverified` + `test_flow_documents_full_provider_id_requirement` |
| A3 | pass | `test_flow_documents_model_scope_layers` |
| A4 | pass | `test_flow_distinguishes_enabled_models_from_model_scope` |
| A5 | pass | `test_prompts_header_no_stale_inheritance_claim` + `test_prompts_header_documents_resolution_chain` |
| A6 | pass | full suite + black + ruff + `git diff --check` |
| U1 | pending | post-merge: full Round-1 `batch review pr` under live modelScope |
| U2 | pending | post-merge: incremental round with delta-reviewer |

Record the ledger in the task output (and later the PR description); U1/U2 must stay `pending` until actually executed — do not mark them pass from static evidence.

- [ ] **Step 5: Final commit check**

Run: `git log --oneline main..HEAD`
Expected: spec commit, Task 1, Task 2, (optional style) commits present; working tree clean.
