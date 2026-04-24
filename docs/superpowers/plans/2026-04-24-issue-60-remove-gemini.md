# Remove Gemini Agent Type — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all references to the "gemini" agent type from production code and tests.

**Architecture:** Pure deletion — remove gemini entries from VALID_* sets, delete `_build_gemini_command()`, delete gemini-specific test methods. No refactoring, no new code.

**Tech Stack:** Python 3.10+, pytest

---

### Task 1: Remove gemini from core model (agent.py)

**Files:**
- Modify: `zima/models/agent.py`

- [ ] **Step 1: Remove gemini parameter template**

In `AGENT_PARAMETER_TEMPLATES` (lines 34-41), delete the entire `"gemini"` entry:

```python
# DELETE these lines:
    "gemini": {
        "approvalMode": "default",
        "checkpointing": False,
        "workDir": "./workspace",
        "addDirs": [],
        "outputFormat": "text",
    },
```

- [ ] **Step 2: Update VALID_AGENT_TYPES**

Line 43, change:
```python
VALID_AGENT_TYPES = {"kimi", "claude", "gemini"}
```
to:
```python
VALID_AGENT_TYPES = {"kimi", "claude"}
```

- [ ] **Step 3: Update docstrings**

Line 51, change:
```python
    Supports multiple agent types: kimi, claude, gemini
```
to:
```python
    Supports multiple agent types: kimi, claude
```

Line 54, change:
```python
        type: Agent type (kimi/claude/gemini)
```
to:
```python
        type: Agent type (kimi/claude)
```

Line 94, change:
```python
            agent_type: Agent type (kimi/claude/gemini)
```
to:
```python
            agent_type: Agent type (kimi/claude)
```

- [ ] **Step 4: Remove gemini from get_cli_command_template()**

In `get_cli_command_template()` (lines 180-185), remove the gemini template entry:

```python
        templates = {
            "kimi": ["kimi", "--print", "--yolo"],
            "claude": ["claude", "-p"],
            "gemini": ["gemini", "--yolo"],  # DELETE this line
        }
```

becomes:

```python
        templates = {
            "kimi": ["kimi", "--print", "--yolo"],
            "claude": ["claude", "-p"],
        }
```

- [ ] **Step 5: Remove gemini branch from build_command()**

In `build_command()` (lines 216-227), remove the gemini branches:

Delete lines 216-217:
```python
        elif self.type == "gemini":
            cmd = self._build_gemini_command(cmd, params)
```

Delete lines 226-227:
```python
            elif self.type == "gemini":
                cmd.extend(["-p", str(prompt_file)])
```

Delete lines 231-232:
```python
            if self.type == "gemini":
                cmd.extend(["--worktree", str(work_dir)])
```

After removal, the prompt_file block should look like:
```python
        if prompt_file:
            if self.type == "kimi":
                cmd.extend(["--prompt", str(prompt_file)])
            # Claude: prompt_file is passed via stdin pipe by the executor, not added to cmd
```

And the work_dir block should look like:
```python
        if work_dir:
            cmd.extend(["--work-dir", str(work_dir)])
```

- [ ] **Step 6: Delete _build_gemini_command() method**

Delete the entire method (lines 315-333):
```python
    def _build_gemini_command(self, cmd: list[str], params: dict) -> list[str]:
        """Build Gemini-specific command arguments."""
        if params.get("model"):
            cmd.extend(["-m", str(params["model"])])

        if params.get("approvalMode") and params["approvalMode"] != "default":
            cmd.extend(["--approval-mode", str(params["approvalMode"])])

        if params.get("checkpointing"):
            cmd.append("--checkpointing")

        # Handle addDirs (for Gemini: --include-directories)
        for add_dir in params.get("addDirs", []):
            cmd.extend(["--include-directories", str(add_dir)])

        if params.get("outputFormat"):
            cmd.extend(["--output-format", str(params["outputFormat"])])

        return cmd
```

- [ ] **Step 7: Commit**

```bash
git add zima/models/agent.py
git commit -m "chore(agent): remove gemini agent type from AgentConfig model"
```

---

### Task 2: Remove gemini from env and pmg models

**Files:**
- Modify: `zima/models/env.py`
- Modify: `zima/models/pmg.py`

- [ ] **Step 1: Update VALID_ENV_FOR_TYPES in env.py**

Line 18, change:
```python
VALID_ENV_FOR_TYPES = {"kimi", "claude", "gemini"}
```
to:
```python
VALID_ENV_FOR_TYPES = {"kimi", "claude"}
```

Line 201, change:
```python
        for_type: Target agent type (kimi/claude/gemini)
```
to:
```python
        for_type: Target agent type (kimi/claude)
```

- [ ] **Step 2: Update VALID_PMG_FOR_TYPES in pmg.py**

Line 19, change:
```python
VALID_PMG_FOR_TYPES = {"kimi", "claude", "gemini"}
```
to:
```python
VALID_PMG_FOR_TYPES = {"kimi", "claude"}
```

- [ ] **Step 3: Commit**

```bash
git add zima/models/env.py zima/models/pmg.py
git commit -m "chore(models): remove gemini from VALID_*_FOR_TYPES sets"
```

---

### Task 3: Remove gemini from CLI commands

**Files:**
- Modify: `zima/commands/agent.py`
- Modify: `zima/commands/env.py`

- [ ] **Step 1: Update agent.py help text**

Line 29, change:
```python
    agent_type: str = typer.Option("kimi", "--type", "-t", help="Agent type: kimi/claude/gemini"),
```
to:
```python
    agent_type: str = typer.Option("kimi", "--type", "-t", help="Agent type: kimi/claude"),
```

Lines 431-435, change:
```python
    descriptions = {
        "kimi": "Kimi CLI - 月之暗面大模型",
        "claude": "Claude CLI - Anthropic AI",
        "gemini": "Gemini CLI - Google AI",
    }
```
to:
```python
    descriptions = {
        "kimi": "Kimi CLI - 月之暗面大模型",
        "claude": "Claude CLI - Anthropic AI",
    }
```

- [ ] **Step 2: Update env.py help text**

Line 29, change:
```python
        None, "--for-type", "-t", help="Target agent type: kimi/claude/gemini"
```
to:
```python
        None, "--for-type", "-t", help="Target agent type: kimi/claude"
```

- [ ] **Step 3: Commit**

```bash
git add zima/commands/agent.py zima/commands/env.py
git commit -m "chore(commands): remove gemini from CLI help text"
```

---

### Task 4: Remove gemini from utils.py

**Files:**
- Modify: `zima/utils.py`

- [ ] **Step 1: Update VALID_AGENT_TYPES**

Line 259, change:
```python
VALID_AGENT_TYPES = {"kimi", "claude", "gemini"}
```
to:
```python
VALID_AGENT_TYPES = {"kimi", "claude"}
```

- [ ] **Step 2: Commit**

```bash
git add zima/utils.py
git commit -m "chore(utils): remove gemini from VALID_AGENT_TYPES"
```

---

### Task 5: Remove gemini from unit tests

**Files:**
- Modify: `tests/unit/test_models_agent.py`
- Modify: `tests/unit/test_models_env.py`
- Modify: `tests/unit/test_utils.py`

- [ ] **Step 1: Update test_models_agent.py**

Delete the method `test_create_gemini_agent` (lines 33-39):
```python
    def test_create_gemini_agent(self):
        """Test creating Gemini agent."""
        config = AgentConfig.create(code="gemini-agent", name="Gemini Agent", agent_type="gemini")

        assert config.type == "gemini"
        assert "model" not in config.parameters
        assert config.parameters["approvalMode"] == "default"
```

Delete the method `test_validate_valid_gemini` (lines 107-111):
```python
    def test_validate_valid_gemini(self):
        """Test valid Gemini config."""
        config = AgentConfig.create("test", "Test", "gemini")
        errors = config.validate()
        assert errors == []
```

Update `test_from_yaml_file` (lines 196-219) — change gemini YAML to claude:

Change the yaml_content from:
```python
        yaml_content = """
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: yaml-agent
  name: YAML Agent
  description: From YAML
spec:
  type: gemini
  parameters:
    model: gemini-pro
  defaults:
    workflow: wf1
"""
```
to:
```python
        yaml_content = """
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: yaml-agent
  name: YAML Agent
  description: From YAML
spec:
  type: claude
  parameters:
    model: claude-sonnet
  defaults:
    workflow: wf1
"""
```

And the assertions from:
```python
        assert config.type == "gemini"
        assert config.parameters["model"] == "gemini-pro"
```
to:
```python
        assert config.type == "claude"
        assert config.parameters["model"] == "claude-sonnet"
```

Delete the method `test_get_cli_template_gemini` (lines 247-253):
```python
    def test_get_cli_template_gemini(self):
        """Test getting Gemini command template."""
        config = AgentConfig.create("test", "Test", "gemini")
        template = config.get_cli_command_template()

        assert "gemini" in template
        assert "--yolo" in template
```

Delete the method `test_build_gemini_command` (lines 289-301):
```python
    def test_build_gemini_command(self):
        """Test building Gemini command."""
        config = AgentConfig.create("test", "Test", "gemini", parameters={"model": "gemini-pro"})

        cmd = config.build_command(
            prompt_file=Path("/tmp/prompt.md"), work_dir=Path("/tmp/workspace")
        )

        assert "gemini" in cmd
        assert "-p" in cmd  # Gemini uses -p for prompt file
        assert "--worktree" in cmd  # Gemini uses --worktree
        assert "-m" in cmd
        assert "gemini-pro" in cmd
```

Delete the method `test_build_gemini_command_no_model_by_default` (lines 345-350):
```python
    def test_build_gemini_command_no_model_by_default(self):
        """Test that -m is omitted for gemini when no model is set."""
        config = AgentConfig.create("test", "Test", "gemini")
        cmd = config.build_command()

        assert "-m" not in cmd
```

Update `test_valid_types` in `TestValidAgentTypes` (line 395), change:
```python
        assert VALID_AGENT_TYPES == {"kimi", "claude", "gemini"}
```
to:
```python
        assert VALID_AGENT_TYPES == {"kimi", "claude"}
```

- [ ] **Step 2: Update test_models_env.py**

In `test_to_dict` (around line 388-401), change `for_type="gemini"` to `for_type="claude"`:

Change:
```python
            env = EnvConfig.create(
                code="dict-test",
                name="Dict Test",
                for_type="gemini",
```
to:
```python
            env = EnvConfig.create(
                code="dict-test",
                name="Dict Test",
                for_type="claude",
```

Change:
```python
            assert data["spec"]["forType"] == "gemini"
```
to:
```python
            assert data["spec"]["forType"] == "claude"
```

- [ ] **Step 3: Update test_utils.py**

In `test_validate_agent_type` parametrize (lines 112-120), remove the gemini row:

Change:
```python
        [
            ("kimi", True),
            ("claude", True),
            ("gemini", True),
            ("invalid", False),
            ("KIMI", False),  # case sensitive
            ("", False),
        ],
```
to:
```python
        [
            ("kimi", True),
            ("claude", True),
            ("invalid", False),
            ("KIMI", False),  # case sensitive
            ("", False),
        ],
```

In `test_get_valid_agent_types` (line 130), change:
```python
        assert types == {"kimi", "claude", "gemini"}
```
to:
```python
        assert types == {"kimi", "claude"}
```

- [ ] **Step 4: Run unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass with no gemini references.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_models_agent.py tests/unit/test_models_env.py tests/unit/test_utils.py
git commit -m "test: remove gemini-related unit tests and update assertions"
```

---

### Task 6: Remove gemini from integration tests

**Files:**
- Modify: `tests/integration/test_agent_commands.py`
- Modify: `tests/integration/test_kimi_agent_integration.py`

- [ ] **Step 1: Update test_agent_commands.py**

Delete the method `test_create_gemini_agent` (lines 55-73):
```python
    def test_create_gemini_agent(self):
        """Test creating a Gemini agent."""
        result = runner.invoke(
            app,
            [
                "agent",
                "create",
                "--name",
                "Test Gemini Agent",
                "--code",
                "test-gemini",
                "--type",
                "gemini",
            ],
        )

        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "gemini" in result.output
```

- [ ] **Step 2: Update test_kimi_agent_integration.py**

In `test_agent_type_command_differences` (lines 132-153), remove all gemini-related code:

Delete lines creating and testing gemini_agent:
```python
        gemini_agent = AgentConfig.create(code="g", name="G", agent_type="gemini")
```

Delete:
```python
        gemini_cmd = gemini_agent.get_cli_command_template()
```

Delete:
```python
        assert gemini_cmd == ["gemini", "--yolo"]
```

Delete:
```python
        gemini_full = gemini_agent.build_command(work_dir=work_dir)
```

Delete:
```python
        assert "--worktree" in gemini_full  # Gemini uses different flag
```

In `test_agent_test_command` (lines 487-491), delete the gemini block:
```python
        # Test Gemini agent
        self.create_test_agent("g-agent", "gemini")
        result = runner.invoke(app, ["agent", "test", "g-agent"])
        assert result.exit_code == 0
        assert "gemini" in result.output
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_agent_commands.py tests/integration/test_kimi_agent_integration.py
git commit -m "test: remove gemini-related integration tests"
```

---

### Task 7: Verify no gemini references remain

- [ ] **Step 1: Search for remaining gemini references**

Run:
```bash
grep -ri "gemini" zima/ tests/ --include="*.py"
```
Expected: No output (zero matches).

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest --cov=zima --cov-fail-under=60`
Expected: All tests pass, coverage >= 60%.

- [ ] **Step 3: Run linter**

Run: `uv run ruff check zima/ tests/` and `uv run black --check zima/ tests/`
Expected: No errors.
