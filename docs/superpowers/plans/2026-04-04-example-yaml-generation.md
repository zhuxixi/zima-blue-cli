# --example Configuration Example Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--example` flag to all 6 entity create commands that outputs a complete YAML example to stdout and exits, without creating any files.

**Architecture:** Centralized example templates in `zima/templates/examples.py`, indexed by entity kind. Each create command adds an `--example` bool option that, when set, prints the example and exits before any validation. Required params (`name`, `code`, etc.) change from Typer `...` to `None` with manual validation, so `--example` can work without them.

**Tech Stack:** Python 3.10+, Typer, Rich, PyYAML, pytest

---

## File Structure

| Action | File | Purpose |
|--------|------|---------|
| Create | `zima/templates/__init__.py` | Package init (empty) |
| Create | `zima/templates/examples.py` | 6 example YAML strings + EXAMPLES dict |
| Create | `tests/unit/test_examples.py` | Unit tests: YAML parse + from_dict round-trip |
| Modify | `zima/commands/agent.py:22-36` | Add `--example`, relax required params |
| Modify | `zima/commands/workflow.py:24-39` | Add `--example`, relax required params |
| Modify | `zima/commands/variable.py:21-37` | Add `--example`, relax required params |
| Modify | `zima/commands/env.py:21-35` | Add `--example`, relax required params |
| Modify | `zima/commands/pmg.py:20-34` | Add `--example`, relax required params |
| Modify | `zima/commands/pjob.py:25-47` | Add `--example`, relax required params |

---

### Task 1: Create example YAML templates with round-trip tests

**Files:**
- Create: `zima/templates/__init__.py`
- Create: `zima/templates/examples.py`
- Create: `tests/unit/test_examples.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_examples.py`:

```python
"""Tests for example YAML templates."""

from __future__ import annotations

import yaml
import pytest

from zima.models.agent import AgentConfig
from zima.models.env import EnvConfig
from zima.models.pjob import PJobConfig
from zima.models.pmg import PMGConfig
from zima.models.variable import VariableConfig
from zima.models.workflow import WorkflowConfig
from zima.templates.examples import EXAMPLES, VALID_KINDS


class TestExampleYaml:
    """Verify each example YAML is valid and round-trips through from_dict."""

    @pytest.mark.parametrize("kind", list(EXAMPLES.keys()))
    def test_is_valid_yaml(self, kind):
        """Each example should be parseable YAML with correct structure."""
        data = yaml.safe_load(EXAMPLES[kind])
        assert isinstance(data, dict)
        assert data["apiVersion"] == "zima.io/v1"
        assert data["kind"] in VALID_KINDS

    @pytest.mark.parametrize("kind", list(EXAMPLES.keys()))
    def test_has_required_fields(self, kind):
        """Each example must have apiVersion, kind, metadata, spec."""
        data = yaml.safe_load(EXAMPLES[kind])
        assert "metadata" in data
        assert "spec" in data
        assert "code" in data["metadata"]
        assert "name" in data["metadata"]

    def test_agent_example_roundtrip(self):
        data = yaml.safe_load(EXAMPLES["agent"])
        config = AgentConfig.from_dict(data)
        assert config.metadata.code == "my-agent"
        assert config.type == "kimi"

    def test_workflow_example_roundtrip(self):
        data = yaml.safe_load(EXAMPLES["workflow"])
        config = WorkflowConfig.from_dict(data)
        assert config.metadata.code == "my-workflow"
        assert config.format == "jinja2"

    def test_variable_example_roundtrip(self):
        data = yaml.safe_load(EXAMPLES["variable"])
        config = VariableConfig.from_dict(data)
        assert config.metadata.code == "my-variables"
        assert "role" in config.values

    def test_env_example_roundtrip(self):
        data = yaml.safe_load(EXAMPLES["env"])
        config = EnvConfig.from_dict(data)
        assert config.metadata.code == "my-env"

    def test_pmg_example_roundtrip(self):
        data = yaml.safe_load(EXAMPLES["pmg"])
        config = PMGConfig.from_dict(data)
        assert config.metadata.code == "my-pmg"

    def test_pjob_example_roundtrip(self):
        data = yaml.safe_load(EXAMPLES["pjob"])
        config = PJobConfig.from_dict(data)
        assert config.metadata.code == "my-job"
        assert config.spec.agent == "my-agent"

    def test_all_kinds_present(self):
        """EXAMPLES must cover all 6 entity kinds."""
        expected = {"agent", "workflow", "variable", "env", "pmg", "pjob"}
        assert set(EXAMPLES.keys()) == expected

    def test_valid_kinds_constant(self):
        """VALID_KINDS must list all entity kind names."""
        assert "Agent" in VALID_KINDS
        assert "PJob" in VALID_KINDS
        assert len(VALID_KINDS) == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_examples.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zima.templates.examples'`

- [ ] **Step 3: Create templates module**

Create `zima/templates/__init__.py` (empty file).

Create `zima/templates/examples.py`:

```python
"""Example YAML templates for each entity type.

Used by the ``--example`` flag on each ``create`` command to output
a ready-to-use configuration that users can pipe to a file and edit.
"""

from __future__ import annotations

AGENT_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: my-agent
  name: My Agent
  description: "An example agent"
spec:
  type: kimi
  parameters:
    model: moonshot-v1-8k
  defaults:
    workflow: my-workflow
    env: my-env
"""

WORKFLOW_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: my-workflow
  name: My Workflow
  description: "An example workflow"
spec:
  format: jinja2
  template: |
    You are {{ role }}.
    Please help me with {{ task }}.
  variables:
    - name: role
      type: string
      required: true
      description: "Agent role"
    - name: task
      type: string
      required: true
      description: "Task description"
  tags: [example]
  version: "1.0.0"
"""

VARIABLE_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Variable
metadata:
  code: my-variables
  name: My Variables
  description: "Example variables"
spec:
  forWorkflow: my-workflow
  values:
    role: "senior developer"
    task: "code review"
"""

ENV_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Env
metadata:
  code: my-env
  name: My Environment
  description: "Example env config"
spec:
  forType: kimi
  variables:
    DEBUG: "false"
  secrets:
    - name: API_KEY
      source: env
      key: MY_API_KEY
  overrideExisting: false
"""

PMG_EXAMPLE = """\
apiVersion: zima.io/v1
kind: PMG
metadata:
  code: my-pmg
  name: My Parameter Group
  description: "Example PMG"
spec:
  forTypes: [kimi, claude]
  parameters:
    - name: verbose
      type: flag
      enabled: true
    - name: model
      type: long
      value: "moonshot-v1-8k"
"""

PJOB_EXAMPLE = """\
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: my-job
  name: My Job
  description: "Example PJob"
  labels: [example]
spec:
  agent: my-agent
  workflow: my-workflow
  variable: my-variables
  env: my-env
  pmg: my-pmg
  execution:
    workDir: .
    timeout: 600
    keepTemp: false
  output:
    saveTo: ./output.md
    format: raw
    append: false
"""

EXAMPLES = {
    "agent": AGENT_EXAMPLE,
    "workflow": WORKFLOW_EXAMPLE,
    "variable": VARIABLE_EXAMPLE,
    "env": ENV_EXAMPLE,
    "pmg": PMG_EXAMPLE,
    "pjob": PJOB_EXAMPLE,
}

VALID_KINDS = {"Agent", "Workflow", "Variable", "Env", "PMG", "PJob"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_examples.py -v`
Expected: PASS (all tests green)

If any `from_dict` round-trip fails, adjust the corresponding YAML string to match the model's expected fields.

- [ ] **Step 5: Commit**

```bash
git add zima/templates/__init__.py zima/templates/examples.py tests/unit/test_examples.py
git commit -m "feat: add example YAML templates for all 6 entity types"
```

---

### Task 2: Add `--example` to agent create command (establish pattern)

**Files:**
- Modify: `zima/commands/agent.py:22-36`

This establishes the pattern for all 6 commands. The key change: required params (`name`, `code`) change from `typer.Option(...)` to `typer.Option(None)` so `--example` can work without them. Manual validation is added after the `--example` early exit.

- [ ] **Step 1: Write CLI test**

Create `tests/integration/test_example_flag.py`:

```python
"""CLI integration tests for --example flag on create commands."""

from __future__ import annotations

from typer.testing import CliRunner

from zima.commands.agent import app as agent_app
from zima.commands.workflow import app as workflow_app
from zima.commands.variable import app as variable_app
from zima.commands.env import app as env_app
from zima.commands.pmg import app as pmg_app
from zima.commands.pjob import app as pjob_app

runner = CliRunner()


class TestAgentExample:
    def test_create_example_exits_zero(self):
        result = runner.invoke(agent_app, ["create", "--example"])
        assert result.exit_code == 0

    def test_create_example_outputs_yaml(self):
        result = runner.invoke(agent_app, ["create", "--example"])
        assert "apiVersion: zima.io/v1" in result.output
        assert "kind: Agent" in result.output
        assert "my-agent" in result.output

    def test_create_example_ignores_other_params(self):
        """When --example is set, other params are ignored."""
        result = runner.invoke(
            agent_app, ["create", "--example", "--name", "test", "--code", "test"]
        )
        assert result.exit_code == 0
        # Output should be the example, not a created config
        assert "my-agent" in result.output

    def test_create_without_example_still_requires_params(self):
        """Without --example, required params must be provided."""
        result = runner.invoke(agent_app, ["create"])
        assert result.exit_code == 1


class TestWorkflowExample:
    def test_create_example(self):
        result = runner.invoke(workflow_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: Workflow" in result.output


class TestVariableExample:
    def test_create_example(self):
        result = runner.invoke(variable_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: Variable" in result.output


class TestEnvExample:
    def test_create_example(self):
        result = runner.invoke(env_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: Env" in result.output


class TestPmgExample:
    def test_create_example(self):
        result = runner.invoke(pmg_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: PMG" in result.output


class TestPjobExample:
    def test_create_example(self):
        result = runner.invoke(pjob_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: PJob" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_example_flag.py -v`
Expected: FAIL — `No such option: --example`

- [ ] **Step 3: Modify agent.py**

In `zima/commands/agent.py`, modify the `create` function:

1. Add `example` parameter as the first param
2. Change `name` and `code` from required (`...`) to optional (`None`)
3. Add `--example` early exit at function top
4. Add manual validation for `name` and `code` after the `--example` check

Replace the `create` function signature (lines 22-36) and add early checks:

```python
@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name"
    ),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    agent_type: str = typer.Option("kimi", "--type", "-t", help="Agent type: kimi/claude/gemini"),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing agent"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name"),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", "-w", help="Working directory"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if agent already exists"
    ),
):
    """Create a new agent"""
    if example:
        from zima.templates.examples import EXAMPLES
        print(EXAMPLES["agent"])
        raise typer.Exit(0)

    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)
    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # ... rest of existing function unchanged ...
```

- [ ] **Step 4: Run agent tests to verify they pass**

Run: `pytest tests/integration/test_example_flag.py::TestAgentExample -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/agent.py tests/integration/test_example_flag.py
git commit -m "feat: add --example flag to agent create command"
```

---

### Task 3: Add `--example` to remaining 5 commands

**Files:**
- Modify: `zima/commands/workflow.py:24-39`
- Modify: `zima/commands/variable.py:21-37`
- Modify: `zima/commands/env.py:21-35`
- Modify: `zima/commands/pmg.py:20-34`
- Modify: `zima/commands/pjob.py:25-47`

Each modification follows the exact same pattern as Task 2:
1. Add `example: bool = typer.Option(False, "--example", help="Print example YAML and exit")` as first param
2. Change required params from `...` to `None`
3. Add `if example:` early exit at function top
4. Add manual validation for formerly-required params

- [ ] **Step 1: Modify workflow.py**

In `zima/commands/workflow.py`, replace the `create` signature (lines 24-39) with:

```python
@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name"
    ),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    template: Optional[str] = typer.Option(
        None, "--template", "-t", help="Template content (or @file to load from file)"
    ),
    format: str = typer.Option(
        "jinja2", "--format", "-f", help="Template format: jinja2/mustache/plain"
    ),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing workflow"),
    force: bool = typer.Option(False, "--force", help="Force overwrite if workflow already exists"),
):
    """Create a new workflow"""
    if example:
        from zima.templates.examples import EXAMPLES
        print(EXAMPLES["workflow"])
        raise typer.Exit(0)

    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)
    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # ... rest of existing function unchanged ...
```

- [ ] **Step 2: Modify variable.py**

In `zima/commands/variable.py`, replace the `create` signature (lines 21-37) with:

```python
@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name"
    ),
    for_workflow: Optional[str] = typer.Option(
        None, "--for-workflow", "-w", help="Target workflow code"
    ),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(
        None, "--from", help="Copy from existing variable config"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if variable config already exists"
    ),
):
    """Create a new variable configuration"""
    if example:
        from zima.templates.examples import EXAMPLES
        print(EXAMPLES["variable"])
        raise typer.Exit(0)

    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)
    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # ... rest of existing function unchanged ...
```

- [ ] **Step 3: Modify env.py**

In `zima/commands/env.py`, replace the `create` signature (lines 21-35) with:

```python
@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name"
    ),
    for_type: Optional[str] = typer.Option(
        None, "--for-type", "-t", help="Target agent type: kimi/claude/gemini"
    ),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing env config"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if env config already exists"
    ),
):
    """Create a new environment configuration"""
    if example:
        from zima.templates.examples import EXAMPLES
        print(EXAMPLES["env"])
        raise typer.Exit(0)

    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)
    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)
    if not for_type:
        console.print("[red]✗[/red] --for-type is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # ... rest of existing function unchanged ...
```

- [ ] **Step 4: Modify pmg.py**

In `zima/commands/pmg.py`, replace the `create` signature (lines 20-34) with:

```python
@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name"
    ),
    for_types: Optional[List[str]] = typer.Option(
        None, "--for-type", "-t", help="Target agent types (can specify multiple)"
    ),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    from_code: Optional[str] = typer.Option(None, "--from", help="Copy from existing PMG"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if PMG already exists"
    ),
):
    """Create a new parameters group"""
    if example:
        from zima.templates.examples import EXAMPLES
        print(EXAMPLES["pmg"])
        raise typer.Exit(0)

    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)
    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)
    if not for_types:
        console.print("[red]✗[/red] --for-type is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # ... rest of existing function unchanged ...
```

- [ ] **Step 5: Modify pjob.py**

In `zima/commands/pjob.py`, replace the `create` signature (lines 25-47) with:

```python
@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Display name"
    ),
    code: Optional[str] = typer.Option(
        None, "--code", "-c", help="Unique code (lowercase letters, numbers, hyphens)"
    ),
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent code"),
    workflow: Optional[str] = typer.Option(None, "--workflow", "-w", help="Workflow code"),
    variable: Optional[str] = typer.Option(None, "--variable", "-v", help="Variable code"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Env code"),
    pmg: Optional[str] = typer.Option(None, "--pmg", "-p", help="PMG code"),
    description: str = typer.Option("", "--description", "-d", help="Description"),
    label: Optional[List[str]] = typer.Option(
        None, "--label", "-l", help="Labels (can be used multiple times)"
    ),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", help="Working directory"),
    timeout: int = typer.Option(0, "--timeout", "-t", help="Timeout in seconds (0 = no timeout)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output save path"),
    from_code: Optional[str] = typer.Option(None, "--from-code", help="Copy from existing pjob"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force overwrite if PJob already exists"
    ),
):
    """Create a new PJob"""
    if example:
        from zima.templates.examples import EXAMPLES
        print(EXAMPLES["pjob"])
        raise typer.Exit(0)

    if not name:
        console.print("[red]✗[/red] --name is required")
        raise typer.Exit(1)
    if not code:
        console.print("[red]✗[/red] --code is required")
        raise typer.Exit(1)

    manager = ConfigManager()

    # ... rest of existing function unchanged ...
```

- [ ] **Step 6: Run all integration tests**

Run: `pytest tests/integration/test_example_flag.py -v`
Expected: All 7 test classes PASS (TestAgentExample, TestWorkflowExample, TestVariableExample, TestEnvExample, TestPmgExample, TestPjobExample)

- [ ] **Step 7: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests still pass. If any fail due to changed param defaults, check if those tests were calling `create` without required params — adjust those test calls to include the required params.

- [ ] **Step 8: Commit**

```bash
git add zima/commands/workflow.py zima/commands/variable.py zima/commands/env.py zima/commands/pmg.py zima/commands/pjob.py
git commit -m "feat: add --example flag to workflow, variable, env, pmg, pjob create commands"
```

---

### Task 4: Final validation and cleanup

- [ ] **Step 1: Run full test suite**

Run: `pytest --cov=zima --cov-fail-under=60`
Expected: All tests pass, coverage >= 60%

- [ ] **Step 2: Run linting and formatting**

Run: `ruff check zima/ tests/` and `black --check zima/ tests/ --line-length 100`
Expected: No errors. If formatting issues, run `black zima/ tests/ --line-length 100`.

- [ ] **Step 3: Manual smoke test**

Run: `zima agent create --example` and verify clean YAML output.
Run: `zima pjob create --example` and verify clean YAML output.

- [ ] **Step 4: Final commit (if any lint fixes)**

```bash
git add -A
git commit -m "chore: lint and format fixes for --example feature"
```
