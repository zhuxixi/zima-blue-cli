# Issue #84: preExec Render Order Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move preExec (`scan_pr`) before Jinja2 template rendering so dynamically discovered PR variables are available in workflow templates.

**Architecture:** Change `run_pre()` to return a `dict[str, str]` of discovered variables instead of mutating `env`. In `PJobExecutor.execute()`, reorder steps so `_resolve_env()` and `run_pre()` happen before `_render_workflow()`. Merge the returned dict into both `bundle.variable.values` (for Jinja2) and `env_vars` (for postExec substitution).

**Tech Stack:** Python 3.10+, pytest, unittest.mock

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `zima/execution/actions_runner.py` | Modify | `run_pre()` returns `dict[str, str]` instead of `None` |
| `zima/execution/executor.py` | Modify | Reorder execution steps, merge dynamic vars |
| `tests/unit/test_actions_runner.py` | Modify | Update `TestActionsRunnerPreExec` to assert return value |
| `tests/unit/test_executor_preexec.py` | Modify | Update mocks, add template-rendering-with-dynamic-vars test |

---

### Task 1: Change `run_pre()` to return `dict[str, str]`

**Files:**
- Modify: `zima/execution/actions_runner.py:122-153`
- Modify: `tests/unit/test_actions_runner.py:211-303`

- [ ] **Step 1: Write the failing test — assert return value**

In `tests/unit/test_actions_runner.py`, update the existing `test_run_pre_exec_scan_pr` test to also assert the return value. Change the test at line 212:

```python
def test_run_pre_exec_scan_pr(self):
    """Test running preExec scan_pr action returns discovered variables."""
    from zima.models.actions import PreExecAction

    runner = ActionsRunner()
    actions = ActionsConfig(
        pre_exec=[
            PreExecAction(
                type="scan_pr",
                repo="owner/repo",
                label="zima:needs-review",
            )
        ]
    )
    mock_provider = MagicMock()
    mock_provider.scan_prs.return_value = [
        {"number": "42", "title": "Fix", "url": "https://github.com/o/r/pull/42"}
    ]
    mock_provider.fetch_diff.return_value = "diff content"
    with patch.object(runner._registry, "get", return_value=mock_provider):
        env = {}
        result = runner.run_pre(actions, env)
        mock_provider.scan_prs.assert_called_once_with("owner/repo", "zima:needs-review")
        mock_provider.fetch_diff.assert_called_once_with("owner/repo", "42")
        # Assert return value
        assert result == {
            "repo": "owner/repo",
            "pr_number": "42",
            "pr_title": "Fix",
            "pr_url": "https://github.com/o/r/pull/42",
            "pr_diff": "diff content",
        }
        # env should NOT be mutated anymore
        assert "pr_number" not in env
```

Also update `test_run_pre_exec_env_substitution` (line 277) to assert return value and no env mutation:

```python
def test_run_pre_exec_env_substitution(self):
    """Test env variable substitution in run_pre before calling scan_prs."""
    from zima.models.actions import PreExecAction

    runner = ActionsRunner()
    actions = ActionsConfig(
        pre_exec=[
            PreExecAction(
                type="scan_pr",
                repo="{{repo}}",
                label="{{label}}",
            )
        ]
    )
    mock_provider = MagicMock()
    mock_provider.scan_prs.return_value = [
        {"number": "7", "title": "Test", "url": "https://github.com/o/r/pull/7"}
    ]
    mock_provider.fetch_diff.return_value = "diff data"
    with patch.object(runner._registry, "get", return_value=mock_provider):
        env = {"repo": "my-org/my-repo", "label": "needs-review"}
        result = runner.run_pre(actions, env)
        mock_provider.scan_prs.assert_called_once_with("my-org/my-repo", "needs-review")
        mock_provider.fetch_diff.assert_called_once_with("my-org/my-repo", "7")
        assert result["repo"] == "my-org/my-repo"
        assert result["pr_number"] == "7"
        assert result["pr_diff"] == "diff data"
```

And update `test_run_pre_provider_not_found` (line 256) — `run_pre` should return empty dict instead of None:

```python
def test_run_pre_provider_not_found(self, capsys):
    """Test run_pre warns and returns empty dict when provider is not found."""
    from zima.models.actions import PreExecAction

    runner = ActionsRunner()
    actions = ActionsConfig(
        provider="nonexistent",
        pre_exec=[PreExecAction(type="scan_pr", repo="owner/repo", label="x")],
    )
    with patch.object(
        runner._registry,
        "get",
        side_effect=ProviderNotFoundError("Provider 'nonexistent' not found"),
    ):
        env = {"existing": "value"}
        result = runner.run_pre(actions, env)
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "nonexistent" in captured.out
        assert result == {}
        assert env == {"existing": "value"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_actions_runner.py::TestActionsRunnerPreExec -v`
Expected: FAIL — `run_pre` returns `None`, tests assert return value is a dict

- [ ] **Step 3: Implement `run_pre()` return value**

In `zima/execution/actions_runner.py`, change `run_pre()` to return `dict[str, str]`:

```python
def run_pre(self, actions: ActionsConfig, env: dict[str, str]) -> dict[str, str]:
    """Execute all preExec actions, return discovered variables.

    Args:
        actions: Actions configuration from PJob.
        env: Environment dict for {{VAR}} substitution in action fields.

    Returns:
        Dictionary of discovered variables (e.g., pr_number, pr_url, pr_diff).

    Raises:
        SkipAction: If a preExec action indicates no work to do.
    """
    discovered: dict[str, str] = {}
    try:
        provider = self._registry.get(actions.provider)
    except ProviderNotFoundError as e:
        print(f"Warning: {e}")
        return discovered

    for action in actions.pre_exec:
        if action.type == "scan_pr":
            repo = self._substitute_env_str(action.repo, env)
            label = self._substitute_env_str(action.label, env)
            prs = provider.scan_prs(repo, label)
            if not prs:
                raise SkipAction(f"No PRs found with label '{label}' in {repo}")
            pr = prs[0]
            discovered["repo"] = repo
            discovered["pr_number"] = str(pr.get("number") or "")
            discovered["pr_title"] = pr.get("title") or ""
            discovered["pr_url"] = pr.get("url") or ""
            discovered["pr_diff"] = provider.fetch_diff(repo, discovered["pr_number"])
        else:
            print(f"Warning: Unknown preExec action type '{action.type}', skipping")

    return discovered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_actions_runner.py::TestActionsRunnerPreExec -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/execution/actions_runner.py tests/unit/test_actions_runner.py
git commit -m "refactor(actions): run_pre() returns dict instead of mutating env"
```

---

### Task 2: Reorder executor steps and merge dynamic vars

**Files:**
- Modify: `zima/execution/executor.py:156-228`
- Modify: `tests/unit/test_executor_preexec.py:1-170`

- [ ] **Step 1: Write the failing test — dynamic vars in template rendering**

Add a new test to `tests/unit/test_executor_preexec.py` in the `TestPreExecIntegration` class:

```python
def test_run_pre_exec_vars_available_in_template(self, isolated_zima_home):
    """Test that preExec discovered variables are available for Jinja2 rendering."""
    from zima.config.manager import ConfigManager
    from zima.models.variable import VariableConfig

    manager = ConfigManager()

    agent = AgentConfig.create(
        code="test-agent",
        name="Test Agent",
        agent_type="kimi",
        parameters={"mockCommand": "echo hello"},
    )
    manager.save_config("agent", "test-agent", agent.to_dict())

    workflow = WorkflowConfig.create(
        code="test-workflow",
        name="Test Workflow",
        template="Review PR #{{pr_number}}: {{pr_title}}\n{{pr_diff}}",
    )
    manager.save_config("workflow", "test-workflow", workflow.to_dict())

    var = VariableConfig.create(
        code="test-var",
        name="Test Vars",
        values={"pr_number": "", "pr_title": "", "pr_diff": ""},
    )
    manager.save_config("variable", "test-var", var.to_dict())

    pjob = PJobConfig.create(
        code="test-pjob",
        name="Test PJob",
        agent="test-agent",
        workflow="test-workflow",
        variable="test-var",
    )
    pjob.spec.actions = ActionsConfig(
        provider="github",
        pre_exec=[
            PreExecAction(type="scan_pr", repo="owner/repo", label="ready"),
        ],
    )
    manager.save_config("pjob", "test-pjob", pjob.to_dict())

    executor = PJobExecutor()

    dynamic_vars = {
        "repo": "owner/repo",
        "pr_number": "42",
        "pr_title": "Fix bug",
        "pr_url": "https://github.com/owner/repo/pull/42",
        "pr_diff": "+added line",
    }

    with patch.object(
        executor._actions_runner,
        "run_pre",
        return_value=dynamic_vars,
    ):
        with patch.object(executor, "_run_command") as mock_run_command:
            mock_run_command.return_value = (0, "done", "", 12345)
            result = executor.execute("test-pjob")

    # The rendered template should contain the dynamic PR data
    assert result.status == ExecutionStatus.SUCCESS
    assert result.env.get("pr_number") == "42"
    assert result.env.get("pr_title") == "Fix bug"
    assert result.env.get("pr_diff") == "+added line"
```

Also update the existing `test_run_pre_exec_mutates_env` (line 139) to use `return_value` instead of `side_effect` with env mutation:

```python
def test_run_pre_exec_vars_in_env(self, mock_pjob_with_pre_exec, isolated_zima_home):
    """Test that preExec returned variables are merged into env vars."""
    executor = PJobExecutor()

    with patch.object(
        executor._actions_runner,
        "run_pre",
        return_value={"pr_number": "42", "pr_title": "Test PR"},
    ):
        with patch.object(executor, "_run_command") as mock_run_command:
            mock_run_command.return_value = (0, "hello output", "", 12345)

            result = executor.execute("test-pjob")

    assert result.status == ExecutionStatus.SUCCESS
    assert result.env.get("pr_number") == "42"
    assert result.env.get("pr_title") == "Test PR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_executor_preexec.py -v`
Expected: FAIL — `run_pre` is still called after rendering, dynamic vars not merged

- [ ] **Step 3: Reorder executor steps and add merge logic**

In `zima/execution/executor.py`, change the `execute()` method. The key change is moving `_resolve_env()` and `run_pre()` before `_render_workflow()`. Replace lines 195-228 with:

```python
            # 4. Resolve environment variables (moved up for preExec)
            env_vars = self._resolve_env(bundle)
            result.env = env_vars

            # 5. Execute preExec actions (before rendering so dynamic vars are available)
            if pjob.spec.actions and pjob.spec.actions.pre_exec:
                try:
                    dynamic_vars = self._actions_runner.run_pre(pjob.spec.actions, env_vars)
                    # Merge discovered vars into env (for postExec substitution)
                    env_vars.update(dynamic_vars)
                    # Merge discovered vars into bundle (for Jinja2 rendering)
                    if dynamic_vars:
                        if bundle.variable:
                            bundle.variable.values.update(dynamic_vars)
                        else:
                            from zima.models.variable import VariableConfig

                            bundle.variable = VariableConfig(values=dynamic_vars)
                except SkipAction as e:
                    result.status = ExecutionStatus.SKIPPED
                    result.returncode = 0
                    result.stderr = str(e)
                    result.finished_at = generate_timestamp()
                    return result

            # 6. Render workflow template (after preExec so dynamic vars are available)
            prompt_file = self._render_workflow(bundle, temp_dir)
            result.prompt_file = prompt_file

            # 7. Build command
            command = bundle.build_command(prompt_file)
            result.command = command

            # 8. Dry run - capture prompt content and return
            if dry_run:
                result.status = ExecutionStatus.SUCCESS
                result.stdout = f"DRY RUN: Would execute:\n{' '.join(command)}"
                if prompt_file and prompt_file.exists():
                    result.prompt_content = prompt_file.read_text(encoding="utf-8")
                result.finished_at = generate_timestamp()
                return result

            # 9. Execute pre-hooks
            self._run_hooks(pjob.spec.hooks.get("preExec", []), env_vars, bundle.work_dir)
```

Note: the old step 8 (pre-hooks) becomes step 9. The old step 9 (preExec) is removed (replaced by step 5). The old step 10 (run command) stays at its original line position after this block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_executor_preexec.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `uv run pytest`
Expected: All tests PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add zima/execution/executor.py tests/unit/test_executor_preexec.py
git commit -m "fix(executor): run preExec before template rendering for dynamic vars"
```

---

### Task 3: Add integration test for full preExec → template → postExec flow

**Files:**
- Modify: `tests/integration/test_executor_actions.py`

- [ ] **Step 1: Write the integration test**

Add a new test class to `tests/integration/test_executor_actions.py`:

```python
class TestPreExecToPostExecFlow(TestIsolator):
    """Integration test: preExec discovers PR → template renders with vars → postExec uses vars."""

    @pytest.fixture
    def full_reviewer_setup(self, isolated_zima_home, config_manager):
        """Set up reviewer configs with preExec scan_pr + postExec label actions."""
        from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction
        from zima.models.variable import VariableConfig
        from zima.models.workflow import WorkflowConfig

        agent_data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "reviewer-agent", "name": "Reviewer Agent"},
            "spec": {
                "type": "kimi",
                "parameters": {
                    "mockCommand": [
                        "echo",
                        "Review done.\n<zima-review>\n  <verdict>approved</verdict>\n"
                        "  <summary>LGTM</summary>\n</zima-review>",
                    ]
                },
            },
        }
        config_manager.save_config("agent", "reviewer-agent", agent_data)

        wf = WorkflowConfig.create(
            code="reviewer-wf",
            name="Reviewer Workflow",
            template="Review PR #{{pr_number}} in {{repo}}\nDiff:\n{{pr_diff}}",
        )
        config_manager.save_config("workflow", "reviewer-wf", wf.to_dict())

        var = VariableConfig.create(
            code="reviewer-var",
            name="Reviewer Vars",
            values={"repo": "owner/repo", "pr_number": "", "pr_title": "", "pr_diff": ""},
        )
        config_manager.save_config("variable", "reviewer-var", var.to_dict())

        pjob = PJobConfig.create(
            code="reviewer-full",
            name="Full Reviewer",
            agent="reviewer-agent",
            workflow="reviewer-wf",
            variable="reviewer-var",
        )
        pjob.spec.actions = ActionsConfig(
            provider="github",
            pre_exec=[
                PreExecAction(
                    type="scan_pr",
                    repo="owner/repo",
                    label="zima:needs-review",
                )
            ],
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["zima:approved"],
                    remove_labels=["zima:needs-review"],
                    repo="{{repo}}",
                    issue="{{pr_number}}",
                )
            ],
        )
        config_manager.save_config("pjob", "reviewer-full", pjob.to_dict())

        return pjob

    def test_preexec_vars_flow_to_template_and_postexec(
        self, full_reviewer_setup, isolated_zima_home
    ):
        """preExec scan_pr → dynamic vars in template → postExec label with those vars."""
        from unittest.mock import MagicMock, patch

        executor = PJobExecutor()
        mock_ops = MagicMock()
        mock_ops.scan_prs.return_value = [
            {"number": "99", "title": "Bug fix", "url": "https://github.com/owner/repo/pull/99"}
        ]
        mock_ops.fetch_diff.return_value = "+fixed code"
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_ops
        executor._actions_runner._registry = mock_registry

        result = executor.execute("reviewer-full")

        assert result.status.value == "success"
        # Dynamic vars should be in env
        assert result.env.get("pr_number") == "99"
        assert result.env.get("pr_diff") == "+fixed code"
        # postExec should use the dynamic vars for label action
        mock_ops.add_label.assert_called_once_with("owner/repo", "99", "zima:approved")
        mock_ops.remove_label.assert_called_once_with("owner/repo", "99", "zima:needs-review")
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/integration/test_executor_actions.py::TestPreExecToPostExecFlow -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_executor_actions.py
git commit -m "test(integration): add preExec → template → postExec full flow test"
```

---

### Task 4: Lint, format, and final validation

**Files:** All changed files

- [ ] **Step 1: Run formatter**

Run: `uv run black zima/ tests/ --line-length 100`
Expected: No changes (or reformatted files)

- [ ] **Step 2: Run linter**

Run: `uv run ruff check zima/ tests/`
Expected: No errors

- [ ] **Step 3: Run full test suite with coverage**

Run: `uv run pytest --cov=zima --cov-fail-under=60`
Expected: All tests PASS, coverage >= 60%
