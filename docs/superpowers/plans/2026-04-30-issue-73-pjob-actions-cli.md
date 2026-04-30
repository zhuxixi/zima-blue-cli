# PJob Actions CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `zima pjob actions <code>` subcommand group for managing postExec actions and provider via CLI.

**Architecture:** Add a Typer sub-app (`actions_app`) inside `zima/commands/pjob.py` with 4 commands (list, add, remove, provider), registered on the main `pjob` app. Also enhance `pjob show` to display actions. Integration tests exercise the full CLI via `CliRunner`.

**Tech Stack:** Python 3.10+, Typer, Rich, pytest

---

### Task 1: Register `actions` subcommand group on pjob app

**Files:**
- Modify: `zima/commands/pjob.py:21` (after main `app` declaration)

- [ ] **Step 1: Add `actions_app` Typer sub-app and register it**

Add after line 21 (`app = typer.Typer(...)`):

```python
actions_app = typer.Typer(name="actions", help="Manage PJob postExec actions and provider")
app.add_typer(actions_app, name="actions")
```

- [ ] **Step 2: Verify registration works**

Run: `uv run zima pjob actions --help`
Expected: Shows help text with available subcommands (empty list is fine — commands come next)

- [ ] **Step 3: Commit**

```bash
git add zima/commands/pjob.py
git commit -m "feat(pjob): register actions subcommand group on pjob app (#73)"
```

---

### Task 2: Implement `actions provider` command

**Files:**
- Modify: `zima/commands/pjob.py` (add `provider` command in `actions_app`)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_pjob_actions_commands.py`:

```python
"""Integration tests for PJob actions subcommands."""

import pytest
from typer.testing import CliRunner

from zima.cli import app
from zima.config.manager import ConfigManager
from zima.models.agent import AgentConfig
from zima.models.workflow import WorkflowConfig

runner = CliRunner()


class TestPJobActionsProvider:
    """Tests for 'zima pjob actions <code> provider'."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def create_deps(self, pjob_code="test-pjob"):
        agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
        self.manager.save_config("agent", "test-agent", agent.to_dict())
        wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
        self.manager.save_config("workflow", "test-workflow", wf.to_dict())
        result = runner.invoke(
            app,
            [
                "pjob", "create",
                "--name", "Test PJob",
                "--code", pjob_code,
                "--agent", "test-agent",
                "--workflow", "test-workflow",
            ],
        )
        assert result.exit_code == 0

    def test_provider_default(self):
        """Provider shows default 'github' when none set."""
        self.create_deps()
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "provider"])
        assert result.exit_code == 0
        assert "github" in result.output

    def test_provider_set(self):
        """Provider can be set to a new value."""
        self.create_deps()
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "provider", "gitlab"])
        assert result.exit_code == 0
        assert "gitlab" in result.output

        # Verify persisted
        result2 = runner.invoke(app, ["pjob", "actions", "test-pjob", "provider"])
        assert "gitlab" in result2.output

    def test_provider_pjob_not_found(self):
        """Provider on non-existent PJob returns error."""
        result = runner.invoke(app, ["pjob", "actions", "missing-pjob", "provider"])
        assert result.exit_code != 0
        assert "not found" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsProvider -v`
Expected: FAIL — commands not yet implemented

- [ ] **Step 3: Implement `provider` command**

Add in `zima/commands/pjob.py` after the `actions_app` registration:

```python
@actions_app.command("provider")
def actions_provider(
    code: str = typer.Argument(..., help="PJob code"),
    name: Optional[str] = typer.Argument(None, help="Provider name (omit to view current)"),
):
    """Get or set the action provider for a PJob."""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("pjob", code)
    config = PJobConfig.from_dict(data)

    if name is None:
        console.print(f"Provider: {config.spec.actions.provider}")
    else:
        config.spec.actions.provider = name
        manager.save_config("pjob", code, config.to_dict())
        console.print(f"[green]✓[/green] Provider set to '{name}'")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsProvider -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/pjob.py tests/integration/test_pjob_actions_commands.py
git commit -m "feat(pjob): add 'actions provider' subcommand (#73)"
```

---

### Task 3: Implement `actions list` command

**Files:**
- Modify: `zima/commands/pjob.py` (add `list` command in `actions_app`)
- Modify: `tests/integration/test_pjob_actions_commands.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_pjob_actions_commands.py`:

```python
class TestPJobActionsList:
    """Tests for 'zima pjob actions <code> list'."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def create_deps_with_action(self, pjob_code="test-pjob"):
        from zima.models.actions import ActionsConfig, PostExecAction

        agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
        self.manager.save_config("agent", "test-agent", agent.to_dict())
        wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
        self.manager.save_config("workflow", "test-workflow", wf.to_dict())
        result = runner.invoke(
            app,
            [
                "pjob", "create",
                "--name", "Test PJob",
                "--code", pjob_code,
                "--agent", "test-agent",
                "--workflow", "test-workflow",
            ],
        )
        assert result.exit_code == 0

        # Manually add an action to test listing
        data = self.manager.load_config("pjob", pjob_code)
        config = ConfigManager.__new__(ConfigManager)  # skip — just load
        from zima.models.pjob import PJobConfig
        pjob = PJobConfig.from_dict(data)
        pjob.spec.actions.post_exec.append(
            PostExecAction(
                condition="success",
                type="add_label",
                add_labels=["reviewed"],
                remove_labels=["needs-review"],
                repo="owner/repo",
                issue="{{pr_number}}",
            )
        )
        self.manager.save_config("pjob", pjob_code, pjob.to_dict())

    def test_list_empty(self):
        """List shows message when no actions configured."""
        agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
        self.manager.save_config("agent", "test-agent", agent.to_dict())
        wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
        self.manager.save_config("workflow", "test-workflow", wf.to_dict())
        runner.invoke(
            app,
            ["pjob", "create", "--name", "T", "--code", "t1", "--agent", "test-agent", "--workflow", "test-workflow"],
        )
        result = runner.invoke(app, ["pjob", "actions", "t1", "list"])
        assert result.exit_code == 0
        assert "No postExec actions" in result.output

    def test_list_with_actions(self):
        """List shows configured actions in a table."""
        self.create_deps_with_action()
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert result.exit_code == 0
        assert "add_label" in result.output
        assert "reviewed" in result.output

    def test_list_pjob_not_found(self):
        """List on non-existent PJob returns error."""
        result = runner.invoke(app, ["pjob", "actions", "missing", "list"])
        assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsList -v`
Expected: FAIL — `list` command not yet implemented

- [ ] **Step 3: Implement `list` command**

Add in `zima/commands/pjob.py`:

```python
@actions_app.command("list")
def actions_list(
    code: str = typer.Argument(..., help="PJob code"),
):
    """List all postExec actions for a PJob."""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("pjob", code)
    config = PJobConfig.from_dict(data)
    actions = config.spec.actions.post_exec

    if not actions:
        console.print(f"[yellow]No postExec actions configured for '{code}'[/yellow]")
        return

    table = Table(title=f"PostExec Actions: {code}")
    table.add_column("Index", style="cyan", width=5)
    table.add_column("Condition", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Details")

    for i, action in enumerate(actions):
        if action.type == "add_label":
            parts = []
            if action.add_labels:
                parts.append("+" + ", +".join(action.add_labels))
            if action.remove_labels:
                parts.append("-" + ", -".join(action.remove_labels))
            detail = " ".join(parts) if parts else "(no labels)"
        elif action.type == "add_comment":
            detail = action.body[:60] if action.body else "(no body)"
        else:
            detail = ""

        if action.repo:
            detail += f" ({action.repo}"
            if action.issue:
                detail += f" #{action.issue}"
            detail += ")"

        table.add_row(str(i), action.condition, action.type, detail)

    console.print(table)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsList -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/pjob.py tests/integration/test_pjob_actions_commands.py
git commit -m "feat(pjob): add 'actions list' subcommand (#73)"
```

---

### Task 4: Implement `actions add` command

**Files:**
- Modify: `zima/commands/pjob.py` (add `add` command in `actions_app`)
- Modify: `tests/integration/test_pjob_actions_commands.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_pjob_actions_commands.py`:

```python
class TestPJobActionsAdd:
    """Tests for 'zima pjob actions <code> add'."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def create_deps(self, pjob_code="test-pjob"):
        agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
        self.manager.save_config("agent", "test-agent", agent.to_dict())
        wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
        self.manager.save_config("workflow", "test-workflow", wf.to_dict())
        result = runner.invoke(
            app,
            [
                "pjob", "create",
                "--name", "Test PJob",
                "--code", pjob_code,
                "--agent", "test-agent",
                "--workflow", "test-workflow",
            ],
        )
        assert result.exit_code == 0

    def test_add_label_action(self):
        """Add a postExec add_label action."""
        self.create_deps()
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "success",
                "--type", "add_label",
                "--add-label", "reviewed",
                "--remove-label", "needs-review",
                "--repo", "owner/repo",
                "--issue", "{{pr_number}}",
            ],
        )
        assert result.exit_code == 0
        assert "added" in result.output

        # Verify via list
        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "add_label" in list_result.output
        assert "reviewed" in list_result.output

    def test_add_comment_action(self):
        """Add a postExec add_comment action."""
        self.create_deps()
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "failure",
                "--type", "add_comment",
                "--body", "Review failed",
                "--repo", "owner/repo",
                "--issue", "{{pr_number}}",
            ],
        )
        assert result.exit_code == 0

    def test_add_invalid_condition(self):
        """Add with invalid condition returns error."""
        self.create_deps()
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "invalid",
                "--type", "add_label",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid condition" in result.output

    def test_add_invalid_type(self):
        """Add with invalid type returns error."""
        self.create_deps()
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "success",
                "--type", "invalid",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid type" in result.output

    def test_add_missing_condition(self):
        """Add without required --condition returns error."""
        self.create_deps()
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--type", "add_label",
            ],
        )
        assert result.exit_code != 0

    def test_add_missing_type(self):
        """Add without required --type returns error."""
        self.create_deps()
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "success",
            ],
        )
        assert result.exit_code != 0

    def test_add_label_warns_no_labels(self):
        """Add add_label with no labels shows warning but still adds."""
        self.create_deps()
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "success",
                "--type", "add_label",
            ],
        )
        assert result.exit_code == 0
        assert "Warning" in result.output or "warning" in result.output.lower()

    def test_add_pjob_not_found(self):
        """Add on non-existent PJob returns error."""
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "missing", "add",
                "--condition", "success",
                "--type", "add_label",
                "--add-label", "x",
            ],
        )
        assert result.exit_code != 0

    def test_add_multiple_actions(self):
        """Adding multiple actions accumulates in the list."""
        self.create_deps()
        runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "success", "--type", "add_label", "--add-label", "a",
            ],
        )
        result = runner.invoke(
            app,
            [
                "pjob", "actions", "test-pjob", "add",
                "--condition", "failure", "--type", "add_comment", "--body", "fail",
            ],
        )
        assert result.exit_code == 0

        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "add_label" in list_result.output
        assert "add_comment" in list_result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsAdd -v`
Expected: FAIL — `add` command not yet implemented

- [ ] **Step 3: Implement `add` command**

Add in `zima/commands/pjob.py` (needs `List` import which already exists):

```python
from zima.models.actions import VALID_ACTION_CONDITIONS, VALID_POST_ACTION_TYPES, PostExecAction

@actions_app.command("add")
def actions_add(
    code: str = typer.Argument(..., help="PJob code"),
    condition: str = typer.Option(..., "--condition", help="When to run: success, failure, always"),
    action_type: str = typer.Option(..., "--type", help="Action type: add_label, add_comment"),
    add_label: Optional[List[str]] = typer.Option(None, "--add-label", help="Labels to add (repeatable)"),
    remove_label: Optional[List[str]] = typer.Option(
        None, "--remove-label", help="Labels to remove (repeatable)"
    ),
    repo: str = typer.Option("", "--repo", help="Repository (owner/repo)"),
    issue: str = typer.Option("", "--issue", help="Issue/PR number (supports {{VAR}})"),
    body: str = typer.Option("", "--body", help="Comment body (for add_comment)"),
):
    """Add a postExec action to a PJob."""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    # Validate condition
    if condition not in VALID_ACTION_CONDITIONS:
        console.print(
            f"[red]✗[/red] Invalid condition '{condition}'. Valid: {', '.join(sorted(VALID_ACTION_CONDITIONS))}"
        )
        raise typer.Exit(1)

    # Validate type
    if action_type not in VALID_POST_ACTION_TYPES:
        console.print(
            f"[red]✗[/red] Invalid type '{action_type}'. Valid: {', '.join(sorted(VALID_POST_ACTION_TYPES))}"
        )
        raise typer.Exit(1)

    # Type-specific warnings
    if action_type == "add_label" and not add_label and not remove_label:
        console.print("[yellow]⚠[/yellow] No labels specified for add_label action")

    if action_type == "add_comment" and not body:
        console.print("[yellow]⚠[/yellow] No body specified for add_comment action")

    data = manager.load_config("pjob", code)
    config = PJobConfig.from_dict(data)

    action = PostExecAction(
        condition=condition,
        type=action_type,
        add_labels=list(add_label) if add_label else [],
        remove_labels=list(remove_label) if remove_label else [],
        repo=repo,
        issue=issue,
        body=body,
    )

    config.spec.actions.post_exec.append(action)
    manager.save_config("pjob", code, config.to_dict())

    console.print(f"[green]✓[/green] Action added to '{code}' (index {len(config.spec.actions.post_exec) - 1})")
```

Note: also add the import at the top of the file (near existing imports):

```python
from zima.models.actions import VALID_ACTION_CONDITIONS, VALID_POST_ACTION_TYPES, PostExecAction
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsAdd -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/pjob.py tests/integration/test_pjob_actions_commands.py
git commit -m "feat(pjob): add 'actions add' subcommand (#73)"
```

---

### Task 5: Implement `actions remove` command

**Files:**
- Modify: `zima/commands/pjob.py` (add `remove` command in `actions_app`)
- Modify: `tests/integration/test_pjob_actions_commands.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_pjob_actions_commands.py`:

```python
class TestPJobActionsRemove:
    """Tests for 'zima pjob actions <code> remove'."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def create_deps_with_actions(self, pjob_code="test-pjob"):
        agent = AgentConfig.create(code="test-agent", name="Test Agent", agent_type="kimi")
        self.manager.save_config("agent", "test-agent", agent.to_dict())
        wf = WorkflowConfig.create(code="test-workflow", name="Test WF", template="# Test")
        self.manager.save_config("workflow", "test-workflow", wf.to_dict())
        runner.invoke(
            app,
            ["pjob", "create", "--name", "T", "--code", pjob_code, "--agent", "test-agent", "--workflow", "test-workflow"],
        )
        runner.invoke(
            app,
            ["pjob", "actions", pjob_code, "add", "--condition", "success", "--type", "add_label", "--add-label", "a"],
        )
        runner.invoke(
            app,
            ["pjob", "actions", pjob_code, "add", "--condition", "failure", "--type", "add_comment", "--body", "fail"],
        )

    def test_remove_by_index(self):
        """Remove action by index."""
        self.create_deps_with_actions()
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "0"])
        assert result.exit_code == 0
        assert "removed" in result.output

        # Verify: list should have 1 action left (the comment one)
        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "add_comment" in list_result.output
        assert "add_label" not in list_result.output

    def test_remove_out_of_range(self):
        """Remove with out-of-range index returns error."""
        self.create_deps_with_actions()
        result = runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "99"])
        assert result.exit_code != 0
        assert "Invalid index" in result.output or "out of range" in result.output

    def test_remove_pjob_not_found(self):
        """Remove on non-existent PJob returns error."""
        result = runner.invoke(app, ["pjob", "actions", "missing", "remove", "--index", "0"])
        assert result.exit_code != 0

    def test_remove_last_action(self):
        """Removing the last action leaves empty list."""
        self.create_deps_with_actions()
        runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "0"])
        runner.invoke(app, ["pjob", "actions", "test-pjob", "remove", "--index", "0"])
        list_result = runner.invoke(app, ["pjob", "actions", "test-pjob", "list"])
        assert "No postExec actions" in list_result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsRemove -v`
Expected: FAIL — `remove` command not yet implemented

- [ ] **Step 3: Implement `remove` command**

Add in `zima/commands/pjob.py`:

```python
@actions_app.command("remove")
def actions_remove(
    code: str = typer.Argument(..., help="PJob code"),
    index: int = typer.Option(..., "--index", help="0-based index of action to remove"),
):
    """Remove a postExec action by index."""
    manager = ConfigManager()

    if not manager.config_exists("pjob", code):
        console.print(f"[red]✗[/red] PJob '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("pjob", code)
    config = PJobConfig.from_dict(data)
    actions = config.spec.actions.post_exec

    if index < 0 or index >= len(actions):
        console.print(
            f"[red]✗[/red] Invalid index {index}. PJob '{code}' has {len(actions)} action(s) (indices 0-{len(actions) - 1 if actions else 0})"
        )
        raise typer.Exit(1)

    removed = actions.pop(index)
    manager.save_config("pjob", code, config.to_dict())
    console.print(f"[green]✓[/green] Removed action at index {index} ({removed.type})")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_pjob_actions_commands.py::TestPJobActionsRemove -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/pjob.py tests/integration/test_pjob_actions_commands.py
git commit -m "feat(pjob): add 'actions remove' subcommand (#73)"
```

---

### Task 6: Enhance `pjob show` with actions branch

**Files:**
- Modify: `zima/commands/pjob.py:335-363` (the `show` command's tree rendering)
- Modify: `tests/integration/test_pjob_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_pjob_lifecycle.py` in `TestPJobLifecycle`:

```python
def test_show_with_actions(self):
    """Test show displays actions branch when configured."""
    self.create_test_agent()
    self.create_test_workflow()

    runner.invoke(
        app,
        ["pjob", "create", "--name", "T", "--code", "test-pjob", "--agent", "test-agent", "--workflow", "test-workflow"],
    )
    runner.invoke(
        app,
        ["pjob", "actions", "test-pjob", "add",
         "--condition", "success", "--type", "add_label", "--add-label", "reviewed",
         "--repo", "owner/repo", "--issue", "{{pr_number}}"],
    )

    result = runner.invoke(app, ["pjob", "show", "test-pjob"])
    assert result.exit_code == 0
    assert "Actions" in result.output
    assert "add_label" in result.output

def test_show_without_actions(self):
    """Test show omits actions branch when none configured."""
    self.create_test_agent()
    self.create_test_workflow()

    runner.invoke(
        app,
        ["pjob", "create", "--name", "T", "--code", "test-pjob", "--agent", "test-agent", "--workflow", "test-workflow"],
    )

    result = runner.invoke(app, ["pjob", "show", "test-pjob"])
    assert result.exit_code == 0
    assert "Actions" not in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_pjob_lifecycle.py::TestPJobLifecycle::test_show_with_actions -v`
Expected: FAIL — show doesn't render actions yet

- [ ] **Step 3: Implement actions tree in `show` command**

In the `show` command (around line 361, after the "Execution Options" branch and before `console.print(tree)`), add:

```python
    # Actions
    if config.spec.actions.post_exec or config.spec.actions.provider != "github":
        actions_branch = tree.add("[bold]Actions[/bold]")
        if config.spec.actions.provider != "github":
            actions_branch.add(f"Provider: {config.spec.actions.provider}")
        if config.spec.actions.post_exec:
            post_branch = actions_branch.add("[bold]PostExec[/bold]")
            for i, action in enumerate(config.spec.actions.post_exec):
                if action.type == "add_label":
                    parts = []
                    if action.add_labels:
                        parts.append("+" + ", +".join(action.add_labels))
                    if action.remove_labels:
                        parts.append("-" + ", -".join(action.remove_labels))
                    detail = " ".join(parts) if parts else "(no labels)"
                elif action.type == "add_comment":
                    detail = f'"{action.body[:50]}"' if action.body else "(no body)"
                else:
                    detail = action.type
                post_branch.add(f"[{i}] {action.condition} / {action.type}: {detail}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_pjob_lifecycle.py::TestPJobLifecycle::test_show_with_actions tests/integration/test_pjob_lifecycle.py::TestPJobLifecycle::test_show_without_actions -v`
Expected: Both tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/pjob.py tests/integration/test_pjob_lifecycle.py
git commit -m "feat(pjob): show actions branch in 'pjob show' output (#73)"
```

---

### Task 7: Run full test suite and format

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ tests/integration/ -v`
Expected: All tests PASS (no regressions)

- [ ] **Step 2: Format and lint**

Run: `uv run black zima/ tests/ --line-length 100 && uv run ruff check zima/ tests/`
Expected: No errors

- [ ] **Step 3: Final commit if formatting changed anything**

```bash
git add -A
git commit -m "chore: format and lint (#73)"
```
