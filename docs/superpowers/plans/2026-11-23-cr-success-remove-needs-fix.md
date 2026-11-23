# Issue #267 — success 分支摘除 `zima:needs-fix` 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 code-review scene 在 review 通过时顺手摘掉历史残留的 `zima:needs-fix`，使收敛态 PR 不再残留「需要修复」标签。

**Architecture:** 只改配置常量与其测试，不改执行器逻辑。`ActionsRunner` 已支持多标签摘除，`PostExecAction.remove_labels` 是字符串列表，因此改动是往列表里加一个元素。

**Tech Stack:** Python 3.10+ / pytest / dataclasses / Typer。

**Spec:** `docs/superpowers/specs/2026-11-23-cr-success-remove-needs-fix-design.md`（本 worktree 内）

## Global Constraints

- 工作目录固定为本 worktree：`/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-267-cr-success-remove-needs-fix`，禁止改主 checkout。
- 格式：`black --line-length 100`，lint：`ruff check`。
- 提交格式：`type(scope): description`。
- `git add <file>` 逐文件 stage，禁止 `git add -A`。
- 不改 `zima/models/actions.py`、`zima/execution/actions_runner.py`、`zima/providers/github.py`。

---

### Task 1: 端到端回归测试（先红）

**Files:**
- Test: `tests/integration/test_executor_actions.py`（在文件末尾新增一个测试类）

**Interfaces:**
- Consumes: `zima.scenes.BUILTIN_SCENES["code-review"].default_actions`、`PJobExecutor.execute(code)`、`PJobExecutor._actions_runner._registry`
- Produces: 测试类 `TestCodeReviewSceneLabelTransitions`，Task 2 用它验证修好之后转绿

- [ ] **Step 1: 写测试**

在 `tests/integration/test_executor_actions.py` 末尾追加（文件顶部若缺少 `import copy` 就补上；`sys`、`MagicMock`、`PJobConfig`、`ActionsConfig` 已在文件中导入）：

```python
class TestCodeReviewSceneLabelTransitions(TestIsolator):
    """issue #267: the built-in code-review scene must clear zima:needs-fix on
    an approved round, so a converged PR never keeps the red label."""

    def _run_scene_pjob(self, isolated_zima_home, config_manager, script):
        """Execute a PJob whose actions come from the builtin code-review scene."""
        import copy

        from zima.config.manager import ConfigManager
        from zima.models.variable import VariableConfig
        from zima.models.workflow import WorkflowConfig
        from zima.scenes import BUILTIN_SCENES

        agent_data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "scene-agent", "name": "Scene Agent"},
            "spec": {"type": "kimi", "parameters": {"mockCommand": [sys.executable, "-c", script]}},
        }
        config_manager.save_config("agent", "scene-agent", agent_data)

        wf = WorkflowConfig.create(
            code="scene-wf",
            name="Scene Workflow",
            template="Review {{repo}}#{{pr_number}}",
        )
        config_manager.save_config("workflow", "scene-wf", wf.to_dict())

        var = VariableConfig.create(
            code="scene-var",
            name="Scene Variables",
            values={"repo": "owner/repo", "pr_number": "42"},
        )
        config_manager.save_config("variable", "scene-var", var.to_dict())

        pjob = PJobConfig.create(
            code="scene-pjob",
            name="Scene PJob",
            agent="scene-agent",
            workflow="scene-wf",
            variable="scene-var",
        )
        pjob.spec.actions = copy.deepcopy(BUILTIN_SCENES["code-review"].default_actions)
        ConfigManager().save_config("pjob", "scene-pjob", pjob.to_dict())

        executor = PJobExecutor()
        mock_ops = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_ops
        executor._actions_runner._registry = mock_registry
        return executor.execute("scene-pjob"), mock_ops

    def test_approved_round_removes_both_labels(self, isolated_zima_home, config_manager):
        approved = (
            "Review done.\n<zima-review>\n  <verdict>approved</verdict>\n"
            "  <summary>LGTM</summary>\n</zima-review>"
        )
        result, mock_ops = self._run_scene_pjob(
            isolated_zima_home, config_manager, f"print({approved!r})"
        )
        removed = [call.args[2] for call in mock_ops.remove_label.call_args_list]
        assert removed == ["zima:needs-review", "zima:needs-fix"]
        mock_ops.add_label.assert_not_called()

    def test_needs_fix_round_only_removes_trigger_label(self, isolated_zima_home, config_manager):
        needs_fix = (
            "Review done.\n<zima-review>\n  <verdict>needs_fix</verdict>\n"
            "  <summary>Found issues</summary>\n</zima-review>"
        )
        _, mock_ops = self._run_scene_pjob(
            isolated_zima_home, config_manager, f"print({needs_fix!r})"
        )
        mock_ops.add_label.assert_called_once_with("owner/repo", "42", "zima:needs-fix")
        removed = [call.args[2] for call in mock_ops.remove_label.call_args_list]
        assert removed == ["zima:needs-review"]
```

- [ ] **Step 2: 跑测试确认红**

Run: `uv run pytest tests/integration/test_executor_actions.py::TestCodeReviewSceneLabelTransitions -v`

Expected: `test_approved_round_removes_both_labels` FAIL（实际 `removed == ["zima:needs-review"]`）；`test_needs_fix_round_only_removes_trigger_label` PASS。

- [ ] **Step 3: 提交测试**

```bash
git add tests/integration/test_executor_actions.py
git commit -m "test(cr): approved round must clear both CR labels (#267)"
```

---

### Task 2: 修 scene 配置并同步示例模板（转绿）

**Files:**
- Modify: `zima/scenes.py:48`
- Modify: `zima/templates/examples.py:226-229`（`REVIEWER_PJOB` 的 success 分支 `removeLabels`）
- Test: `tests/unit/test_scenes.py:124`
- Test: `tests/unit/test_examples.py:303`

**Interfaces:**
- Consumes: Task 1 的 `TestCodeReviewSceneLabelTransitions`
- Produces: `BUILTIN_SCENES["code-review"].default_actions.post_exec[0].remove_labels == ["zima:needs-review", "zima:needs-fix"]`

- [ ] **Step 1: 改测试断言（先红）**

`tests/unit/test_scenes.py:124` 改为：

```python
        assert success_action.remove_labels == ["zima:needs-review", "zima:needs-fix"]
```

`tests/unit/test_examples.py` 中找到（约 `:303`）既有断言：

```python
        assert "zima:needs-review" in config.spec.actions.post_exec[0].remove_labels
```

改为：

```python
        assert config.spec.actions.post_exec[0].remove_labels == [
            "zima:needs-review",
            "zima:needs-fix",
        ]
```

- [ ] **Step 2: 跑测试确认红**

Run: `uv run pytest tests/unit/test_scenes.py tests/unit/test_examples.py -q`

Expected: 两条断言 FAIL。

- [ ] **Step 3: 改配置**

`zima/scenes.py:48`：

```python
                    remove_labels=["zima:needs-review", "zima:needs-fix"],
```

`zima/templates/examples.py` 的 `REVIEWER_PJOB` success 分支：

```yaml
      - condition: success
        type: add_label
        requireReview: true
        removeLabels:
          - zima:needs-review
          - zima:needs-fix
        repo: "{{repo}}"
        issue: "{{pr_number}}"
```

failure 分支保持原样（仍只 `removeLabels: [zima:needs-review]`）。

- [ ] **Step 4: 跑全部相关测试确认绿**

Run: `uv run pytest tests/unit/test_scenes.py tests/unit/test_examples.py tests/integration/test_executor_actions.py -q`

Expected: 全 PASS（含 Task 1 两个用例）。

- [ ] **Step 5: 提交实现**

```bash
git add zima/scenes.py zima/templates/examples.py tests/unit/test_scenes.py tests/unit/test_examples.py
git commit -m "fix(cr): clear zima:needs-fix on the success branch (#267)"
```

---

### Task 3: 锁住 runner 的多标签行为

**Files:**
- Test: `tests/unit/test_actions_runner.py`（在 `TestActionsRunner` 内新增一个用例）

**Interfaces:**
- Consumes: `ActionsRunner.run`、`ActionsConfig`、`PostExecAction`
- Produces: 一个 characterization 用例（该行为已存在，用例立即为绿，用于防止回退）

- [ ] **Step 1: 写用例**

在 `tests/unit/test_actions_runner.py` 的 `TestActionsRunner` 类中新增：

```python
    def test_run_success_action_removes_every_listed_label(self):
        """Every label in remove_labels is removed, in order; nothing is added."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    remove_labels=["zima:needs-review", "zima:needs-fix"],
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            errors = runner.run(actions, returncode=0, env={})

        assert errors == []
        assert [call.args[2] for call in mock_provider.remove_label.call_args_list] == [
            "zima:needs-review",
            "zima:needs-fix",
        ]
        mock_provider.add_label.assert_not_called()
```

- [ ] **Step 2: 跑用例**

Run: `uv run pytest tests/unit/test_actions_runner.py -q`

Expected: PASS（现有行为已支持；若 FAIL 说明前提有误，停下来报告，不要改实现）。

- [ ] **Step 3: 全量验证**

Run: `uv run pytest tests/ -m "not slow" -q`

Expected: 全 PASS。

Run: `uv run ruff check zima/ tests/ && uv run black --check zima/ tests/ --line-length 100`

Expected: 两条命令退出码 0（若 black 报差异，先 `uv run black zima/ tests/ --line-length 100` 再重跑）。

- [ ] **Step 4: 提交**

```bash
git add tests/unit/test_actions_runner.py
git commit -m "test(cr): lock multi-label removal in ActionsRunner (#267)"
```

---

## 验收对照

| Spec ID | Plan Task |
|---|---|
| A1 | Task 2 Step 1–4 |
| A2 | Task 3 Step 1–2 |
| A3 | Task 1 Step 1–2、Task 2 Step 4 |
| A4 | Task 1 Step 1（失败分支用例）、Task 2 Step 4 |
| A5 | Task 2 Step 1–4 |
| A6 | Task 3 Step 3 |
| U1 | 合并后由用户在本机迁移 PJob 后实测（不在本 plan 范围） |
