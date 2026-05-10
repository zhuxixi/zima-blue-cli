# git-pull preExec Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `git_pull` preExec action type that runs `git pull` in the agent's workDir before execution.

**Architecture:** Extend the existing preExec action dispatch in `ActionsRunner.run_pre()` with a new `git_pull` case. The model constant `VALID_PRE_ACTION_TYPES` gains the new type. The executor passes `workdir` to `run_pre()`. Failure is non-blocking — logs warning and continues.

**Tech Stack:** Python 3.10+, subprocess, unittest.mock for testing

---

### Task 1: Add `git_pull` to valid preExec types

**Files:**
- Modify: `zima/models/actions.py:12`
- Test: `tests/unit/test_models_actions.py`

- [ ] **Step 1: Write the failing test**

Add to `TestPreExecAction` class in `tests/unit/test_models_actions.py` (after line 240):

```python
    def test_git_pull_valid_type(self):
        """Test git_pull is accepted as a valid preExec action type."""
        action = PreExecAction(type="git_pull")
        assert action.validate() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_actions.py::TestPreExecAction::test_git_pull_valid_type -v`
Expected: FAIL — `validate()` rejects `"git_pull"` because it's not in `VALID_PRE_ACTION_TYPES`

- [ ] **Step 3: Write minimal implementation**

In `zima/models/actions.py` line 12, change:

```python
VALID_PRE_ACTION_TYPES = {"scan_pr", "git_pull"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_actions.py::TestPreExecAction::test_git_pull_valid_type -v`
Expected: PASS

- [ ] **Step 5: Run full model tests to confirm no regressions**

Run: `uv run pytest tests/unit/test_models_actions.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add zima/models/actions.py tests/unit/test_models_actions.py
git commit -m "feat(actions): add git_pull to valid preExec action types"
```

---

### Task 2: Implement `git_pull` in ActionsRunner

**Files:**
- Modify: `zima/execution/actions_runner.py:1-4` (imports), `:171-217` (run_pre method)
- Test: `tests/unit/test_actions_runner.py`

- [ ] **Step 1: Write the failing test for git_pull success**

Add import at top of `tests/unit/test_actions_runner.py`:

```python
from zima.models.actions import PreExecAction
```

Note: `PreExecAction` is already imported inside individual test methods. Move it to the top-level imports alongside existing `PostExecAction`.

Add to `TestActionsRunnerPreExec` class (after line 425):

```python
    def test_git_pull_success(self, capsys):
        """Test git_pull runs git pull in workdir and returns empty dict."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="git_pull")]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = runner.run_pre(actions, {}, workdir="/path/to/repo")
        mock_run.assert_called_once_with(
            ["git", "pull"],
            cwd="/path/to/repo",
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result == {}

    def test_git_pull_failure_continues(self, capsys):
        """Test git_pull with non-zero returncode logs warning and continues."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="git_pull")]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="merge conflict")
                result = runner.run_pre(actions, {}, workdir="/path/to/repo")
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "merge conflict" in captured.out
        assert result == {}

    def test_git_pull_timeout(self, capsys):
        """Test git_pull timeout logs warning and continues."""
        import subprocess

        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="git_pull")]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd="git pull", timeout=60)
                result = runner.run_pre(actions, {}, workdir="/path/to/repo")
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "timed out" in captured.out
        assert result == {}

    def test_git_pull_no_workdir(self, capsys):
        """Test git_pull skipped with warning when no workdir configured."""
        runner = ActionsRunner()
        actions = ActionsConfig(
            pre_exec=[PreExecAction(type="git_pull")]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with patch("zima.execution.actions_runner.subprocess.run") as mock_run:
                result = runner.run_pre(actions, {})
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert "no workdir" in captured.out
        mock_run.assert_not_called()
        assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_actions_runner.py::TestActionsRunnerPreExec::test_git_pull_success tests/unit/test_actions_runner.py::TestActionsRunnerPreExec::test_git_pull_failure_continues tests/unit/test_actions_runner.py::TestActionsRunnerPreExec::test_git_pull_timeout tests/unit/test_actions_runner.py::TestActionsRunnerPreExec::test_git_pull_no_workdir -v`
Expected: FAIL — `run_pre()` doesn't accept `workdir` parameter, and no `git_pull` handling exists

- [ ] **Step 3: Update run_pre signature and add git_pull case**

In `zima/execution/actions_runner.py`, add `subprocess` import at the top (after line 3):

```python
import subprocess
```

Change `run_pre` signature at line 171:

```python
    def run_pre(self, actions: ActionsConfig, env: dict[str, str], workdir: Optional[str] = None) -> dict[str, str]:
```

Update the docstring at line 172-183, add `workdir` param:

```python
        """Execute all preExec actions, return discovered variables.

        Args:
            actions: Actions configuration from PJob.
            env: Environment dict for {{VAR}} substitution in action fields.
            workdir: Working directory for git_pull action (agent's workDir).

        Returns:
            Dictionary of discovered variables (e.g., pr_number, pr_url, pr_diff).

        Raises:
            SkipAction: If a preExec action indicates no work to do.
        """
```

Replace the `else` block at line 214-215 with:

```python
            elif action.type == "git_pull":
                if not workdir:
                    print("Warning: git_pull skipped, no workdir configured")
                else:
                    try:
                        pull_result = subprocess.run(
                            ["git", "pull"],
                            cwd=workdir,
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                        if pull_result.returncode != 0:
                            print(
                                f"Warning: git pull failed in {workdir}: "
                                f"{pull_result.stderr.strip()}"
                            )
                    except subprocess.TimeoutExpired:
                        print(f"Warning: git pull timed out in {workdir}")
            else:
                print(f"Warning: Unknown preExec action type '{action.type}', skipping")
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/unit/test_actions_runner.py::TestActionsRunnerPreExec -v`
Expected: All tests PASS (8 existing + 4 new)

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `uv run pytest tests/unit/test_actions_runner.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add zima/execution/actions_runner.py tests/unit/test_actions_runner.py
git commit -m "feat(actions): implement git_pull preExec action in ActionsRunner"
```

---

### Task 3: Wire executor to pass workdir to run_pre

**Files:**
- Modify: `zima/execution/executor.py:217`

- [ ] **Step 1: Update the run_pre call site**

In `zima/execution/executor.py` at line 217, change:

```python
                    dynamic_vars = self._actions_runner.run_pre(pjob.spec.actions, pre_env)
```

to:

```python
                    dynamic_vars = self._actions_runner.run_pre(
                        pjob.spec.actions, pre_env, workdir=bundle.work_dir
                    )
```

- [ ] **Step 2: Run integration tests to verify no regressions**

Run: `uv run pytest tests/integration/test_executor_actions.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add zima/execution/executor.py
git commit -m "feat(executor): pass workdir to run_pre for git_pull action"
```
