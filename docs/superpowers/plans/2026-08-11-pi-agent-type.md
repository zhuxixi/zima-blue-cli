# pi-coding-agent Agent Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pi` as a new zima agent type that invokes `pi -p` (pi-coding-agent print mode) for code review, reusing claude's stdin-pipe execution path.

**Architecture:** Only the Agent type-recognition + command-building layer changes. `_build_pi_command` maps camelCase parameters to pi CLI flags. `needs_stdin_pipe=True` for pi reuses executor's existing `Popen(stdin=prompt_file, cwd=work_dir)` path — executor, ReviewParser, ConfigBundle zero changes. pi uses `--mode` (not claude's `--output-format`), `--thinking max` (CR is deep reasoning), `--tools` read-only whitelist, `--no-session`.

**Tech Stack:** Python 3.10+ dataclasses, Typer CLI, pytest, black 100, ruff.

## Global Constraints

- **Worktree:** All work in `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-143-pi-agent-type` (branch `issue-143-pi-agent-type`). Never touch main.
- **Python 3.10+**, dataclasses (not pydantic models).
- **camelCase** parameter serialization (PR #58 convention) — pi params use `noSession`/`outputFormat`/`noContextFiles`/`excludeTools`/`appendSystemPrompt`, NOT snake_case.
- **pi uses `--mode`** for output format (text/json/rpc), NOT claude's `--output-format`.
- **pi has no `--add-dir`** — addDirs unsupported for pi (CR runs in single repo).
- **No `--work-dir`/`--cwd`** passed to pi (relies on executor's `Popen(cwd=)`; learn from PR #71).
- **Commit format:** conventional commits (`feat(agent): ...` / `test: ...` / `docs: ...`).
- **Stage files explicitly** (`git add <file>`), never `git add -A`.
- **Tests use `mockCommand`** to avoid depending on real pi install.
- **Run tests:** `uv run pytest tests/unit/test_models_agent.py -v` (project uses `uv`).

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `zima/models/agent.py` | pi type registration, param template, `_build_pi_command`, `needs_stdin_pipe` | Modify |
| `zima/utils.py:259` | Duplicate `VALID_AGENT_TYPES` set (used by CLI) | Modify |
| `zima/models/env.py:22` | `VALID_ENV_FOR_TYPES` set | Modify |
| `zima/models/pmg.py:19` | `VALID_PMG_FOR_TYPES` set | Modify |
| `zima/commands/agent.py` | `--type` help, `types` subcommand descriptions | Modify |
| `zima/templates/examples.py` | Agent example YAML, `forTypes` list | Modify |
| `AGENTS.md` / `CLAUDE.md` | Agent type docs | Modify |
| `tests/unit/test_models_agent.py` | pi create/build_command/needs_stdin_pipe tests | Modify |
| `tests/unit/test_utils.py` | `VALID_AGENT_TYPES` assertion | Modify |
| `tests/unit/test_models_env.py` | `VALID_ENV_FOR_TYPES` pi test | Modify |
| `tests/unit/test_models_pmg.py` | `VALID_PMG_FOR_TYPES` pi test | Modify |
| `tests/integration/test_agent_commands.py` | `--type pi` CLI test | Modify |

---

### Task 1: agent.py — pi type core support

**Files:**
- Modify: `zima/models/agent.py` (VALID_AGENT_TYPES line ~24, AGENT_PARAMETER_TEMPLATES line ~13, get_cli_command_template line ~150, build_command line ~175, needs_stdin_pipe line ~230)
- Test: `tests/unit/test_models_agent.py`

**Interfaces:**
- Produces: `AgentConfig(type="pi")` valid; `_build_pi_command(cmd, params) -> list[str]`; `needs_stdin_pipe` True for pi; `get_cli_command_template()` returns `["pi","-p"]` for pi.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_models_agent.py` inside `TestAgentConfig` class, near existing `test_create_claude_agent`):

```python
    def test_create_pi_agent(self):
        """Test creating a pi agent."""
        config = AgentConfig.create(code="pi-agent", name="Pi Agent", agent_type="pi")
        assert config.type == "pi"
        assert config.metadata.code == "pi-agent"

    def test_pi_default_parameters(self):
        """Test pi agent gets default parameters merged (thinking max, noSession, text, tools)."""
        config = AgentConfig.create("test", "Test", "pi")
        assert config.parameters["thinking"] == "max"
        assert config.parameters["noSession"] is True
        assert config.parameters["outputFormat"] == "text"
        assert config.parameters["tools"] == ["read", "bash", "grep", "find", "ls"]
        assert config.parameters["noContextFiles"] is False

    def test_pi_needs_stdin_pipe(self):
        """Test pi agent receives prompt via stdin (like claude)."""
        config = AgentConfig.create("test", "Test", "pi")
        assert config.needs_stdin_pipe is True

    def test_build_pi_command(self):
        """Test pi command construction with all flags."""
        config = AgentConfig.create(
            "test", "Test", "pi",
            parameters={
                "provider": "ollama",
                "model": "deepseek-v4-flash:0731-cloud",
                "thinking": "max",
                "noSession": True,
                "outputFormat": "text",
                "tools": ["read", "bash", "grep", "find", "ls"],
            },
        )
        cmd = config.build_command()
        assert cmd[0] == "pi"
        assert "-p" in cmd
        assert "--provider" in cmd and "ollama" in cmd
        assert "--model" in cmd and "deepseek-v4-flash:0731-cloud" in cmd
        assert "--thinking" in cmd and "max" in cmd
        assert "--no-session" in cmd
        assert "--mode" in cmd and "text" in cmd
        assert "--tools" in cmd and "read,bash,grep,find,ls" in cmd

    def test_build_pi_command_no_work_dir(self):
        """Test pi command does NOT pass work-dir/cwd (relies on Popen cwd, per PR #71)."""
        config = AgentConfig.create("test", "Test", "pi", parameters={"workDir": "/tmp"})
        cmd = config.build_command()
        assert "--work-dir" not in cmd
        assert "--cwd" not in cmd

    def test_build_pi_command_no_model_by_default(self):
        """Test pi command omits --model when not set."""
        config = AgentConfig.create("test", "Test", "pi")
        cmd = config.build_command()
        assert "--model" not in cmd
```

Also update the existing `VALID_AGENT_TYPES` assertion test (around line 361):

```python
        assert VALID_AGENT_TYPES == {"kimi", "claude", "pi"}
        assert "openai" not in VALID_AGENT_TYPES
        assert "custom" not in VALID_AGENT_TYPES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_models_agent.py -v -k "pi or VALID_AGENT_TYPES"`
Expected: FAIL — `ValueError: Invalid agent type: pi` (create rejects pi), assertions fail.

- [ ] **Step 3: Implement — add pi to VALID_AGENT_TYPES and param template**

In `zima/models/agent.py`, change:
```python
VALID_AGENT_TYPES = {"kimi", "claude"}
```
to:
```python
VALID_AGENT_TYPES = {"kimi", "claude", "pi"}
```

Add to `AGENT_PARAMETER_TEMPLATES` (after the `"claude"` entry):
```python
    "pi": {
        "provider": "",
        "model": "",
        "thinking": "max",
        "noSession": True,
        "outputFormat": "text",
        "tools": ["read", "bash", "grep", "find", "ls"],
        "noContextFiles": False,
        "addDirs": [],
    },
```

- [ ] **Step 4: Implement — add pi to `get_cli_command_template`**

In the `templates` dict inside `get_cli_command_template`:
```python
        templates = {
            "kimi": ["kimi"],  # Kimi Code CLI
            "claude": ["claude", "-p"],
            "pi": ["pi", "-p"],  # pi-coding-agent print mode
        }
```

- [ ] **Step 5: Implement — add `_build_pi_command` method and `build_command` branch**

Add this method after `_build_claude_command`:
```python
    def _build_pi_command(self, cmd: list[str], params: dict) -> list[str]:
        """Build pi-coding-agent CLI-specific command arguments.

        pi flags (from `pi --help`):
          --provider            : Provider name (ollama, google, etc.)
          --model              : Model pattern or ID
          --thinking           : off/minimal/low/medium/high/xhigh/max
          --no-session         : Don't save session (ephemeral)
          --mode               : Output mode (text/json/rpc) — NOT --output-format
          --tools              : Comma-separated tool allowlist
          --exclude-tools      : Comma-separated tool denylist
          --no-context-files   : Disable AGENTS.md/CLAUDE.md discovery
          --system-prompt      : Replace system prompt
          --append-system-prompt : Append to system prompt

        Note: no --work-dir/--cwd (relies on executor's Popen(cwd=), per PR #71).
        pi has no --add-dir equivalent; addDirs unsupported for pi.
        """
        if params.get("provider"):
            cmd.extend(["--provider", str(params["provider"])])

        if params.get("model"):
            cmd.extend(["--model", str(params["model"])])

        if params.get("thinking"):
            cmd.extend(["--thinking", str(params["thinking"])])

        if params.get("noSession"):
            cmd.append("--no-session")

        if params.get("outputFormat"):
            cmd.extend(["--mode", str(params["outputFormat"])])

        if params.get("tools"):
            tools = params["tools"]
            if isinstance(tools, list) and tools:
                cmd.extend(["--tools", ",".join(str(t) for t in tools)])

        if params.get("excludeTools"):
            tools = params["excludeTools"]
            if isinstance(tools, list) and tools:
                cmd.extend(["--exclude-tools", ",".join(str(t) for t in tools)])

        if params.get("noContextFiles"):
            cmd.append("--no-context-files")

        if params.get("systemPrompt"):
            cmd.extend(["--system-prompt", str(params["systemPrompt"])])

        if params.get("appendSystemPrompt"):
            cmd.extend(["--append-system-prompt", str(params["appendSystemPrompt"])])

        return cmd
```

In `build_command`, add the pi branch alongside kimi/claude:
```python
        if self.type == "kimi":
            cmd = self._build_kimi_command(cmd, params)
        elif self.type == "claude":
            cmd = self._build_claude_command(cmd, params)
        elif self.type == "pi":
            cmd = self._build_pi_command(cmd, params)
```

In the prompt_file handling block, update the comment so pi is documented as stdin-piped like claude (pi falls through to the no-add path):
```python
        if prompt_file:
            if self.type == "kimi":
                cmd.extend(["--prompt", str(prompt_file)])
            # Claude and pi: prompt_file passed via stdin pipe by executor, not added to cmd
```

- [ ] **Step 6: Implement — `needs_stdin_pipe` includes pi**

Change:
```python
    @property
    def needs_stdin_pipe(self) -> bool:
        """Whether this agent type receives prompt via stdin pipe instead of CLI argument."""
        return self.type == "claude"
```
to:
```python
    @property
    def needs_stdin_pipe(self) -> bool:
        """Whether this agent type receives prompt via stdin pipe instead of CLI argument."""
        return self.type in ("claude", "pi")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models_agent.py -v -k "pi or VALID_AGENT_TYPES"`
Expected: PASS — all 7 pi tests + updated assertion green.

- [ ] **Step 8: Lint + format**

Run: `uv run ruff check zima/models/agent.py tests/unit/test_models_agent.py && uv run black --check zima/models/agent.py tests/unit/test_models_agent.py --line-length 100`
Expected: no errors. If black complains, run `uv run black zima/models/agent.py tests/unit/test_models_agent.py --line-length 100`.

- [ ] **Step 9: Commit**

```bash
git add zima/models/agent.py tests/unit/test_models_agent.py
git commit -m "feat(agent): add pi-coding-agent type with _build_pi_command

- VALID_AGENT_TYPES + AGENT_PARAMETER_TEMPLATES add pi
- _build_pi_command: --provider/--model/--thinking/--no-session/--mode/--tools
- needs_stdin_pipe True for pi (reuse claude stdin path)
- no --work-dir (relies on Popen cwd, per PR #71)
- thinking default max, tools read-only whitelist
- tests: create/default-params/needs_stdin_pipe/build_command/no-work-dir

Refs #143"
```

---

### Task 2: utils.py — sync duplicate VALID_AGENT_TYPES

**Files:**
- Modify: `zima/utils.py:259`
- Test: `tests/unit/test_utils.py:114-132`

**Interfaces:**
- Produces: `utils.get_valid_agent_types()` returns `{"kimi","claude","pi"}` (used by `commands/agent.py` CLI validation).

- [ ] **Step 1: Write the failing test** (update `tests/unit/test_utils.py` around line 114-115 and 128-129):

```python
            ("kimi", True),
            ("claude", True),
            ("pi", True),
```
and:
```python
    def test_get_valid_agent_types(self):
        types = utils.get_valid_agent_types()
        assert types == {"kimi", "claude", "pi"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_utils.py -v -k "valid_agent_types or is_valid_agent"`
Expected: FAIL — `{"kimi","claude"} != {"kimi","claude","pi"}`.

- [ ] **Step 3: Implement** — in `zima/utils.py` line 259, change:
```python
VALID_AGENT_TYPES = {"kimi", "claude"}
```
to:
```python
VALID_AGENT_TYPES = {"kimi", "claude", "pi"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_utils.py -v -k "valid_agent_types or is_valid_agent"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add zima/utils.py tests/unit/test_utils.py
git commit -m "feat(agent): add pi to utils VALID_AGENT_TYPES

Refs #143"
```

---

### Task 3: env.py — VALID_ENV_FOR_TYPES add pi

**Files:**
- Modify: `zima/models/env.py:22`
- Test: `tests/unit/test_models_env.py`

**Interfaces:**
- Produces: `EnvConfig.create(for_type="pi")` valid; `VALID_ENV_FOR_TYPES` contains pi.

- [ ] **Step 1: Write the failing test** (add near `test_models_env.py` line 158, after the claude for_type test):

```python
    def test_create_pi_for_type(self):
        """Test env config accepts pi as for_type."""
        env = EnvConfig.create(
            code="test-env-pi", name="Test Pi Env", for_type="pi"
        )
        assert env.for_type == "pi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_env.py -v -k "pi_for_type"`
Expected: FAIL — `ValueError: Invalid for_type: pi`.

- [ ] **Step 3: Implement** — in `zima/models/env.py` line 22, change:
```python
VALID_ENV_FOR_TYPES = {"kimi", "claude"}
```
to:
```python
VALID_ENV_FOR_TYPES = {"kimi", "claude", "pi"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_env.py -v -k "pi_for_type"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add zima/models/env.py tests/unit/test_models_env.py
git commit -m "feat(env): add pi to VALID_ENV_FOR_TYPES

Refs #143"
```

---

### Task 4: pmg.py — VALID_PMG_FOR_TYPES add pi

**Files:**
- Modify: `zima/models/pmg.py:19`
- Test: `tests/unit/test_models_pmg.py`

**Interfaces:**
- Produces: `PMGConfig.create(for_types=["pi"])` valid; `VALID_PMG_FOR_TYPES` contains pi.

- [ ] **Step 1: Write the failing test** (add near `tests/unit/test_models_pmg.py` line 222, after the `["kimi","claude"]` for_types test):

```python
    def test_create_pmg_with_pi_for_types(self):
        """Test pmg config accepts pi in for_types."""
        pmg = PMGConfig.create(
            code="test-pmg-pi", name="Test Pi PMG", for_types=["kimi", "claude", "pi"]
        )
        assert pmg.for_types == ["kimi", "claude", "pi"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_pmg.py -v -k "pi_for_types"`
Expected: FAIL — `ValueError: Invalid forType: pi`.

- [ ] **Step 3: Implement** — in `zima/models/pmg.py` line 19, change:
```python
VALID_PMG_FOR_TYPES = {"kimi", "claude"}
```
to:
```python
VALID_PMG_FOR_TYPES = {"kimi", "claude", "pi"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models_pmg.py -v -k "pi_for_types"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add zima/models/pmg.py tests/unit/test_models_pmg.py
git commit -m "feat(pmg): add pi to VALID_PMG_FOR_TYPES

Refs #143"
```

---

### Task 5: commands/agent.py — CLI help + types subcommand

**Files:**
- Modify: `zima/commands/agent.py:28` (create `--type` help), `zima/commands/agent.py:430-433` (descriptions dict), `zima/commands/agent.py:447` (example hint)

**Interfaces:**
- Produces: `zima agent create --type pi` accepted by CLI; `zima agent types` lists pi.

- [ ] **Step 1: Implement** — line 28, change help text:
```python
    agent_type: str = typer.Option("kimi", "--type", "-t", help="Agent type: kimi/claude/pi"),
```

- [ ] **Step 2: Implement** — line 430-433, add pi to descriptions dict:
```python
    descriptions = {
        "kimi": "Kimi CLI - 月之暗面大模型",
        "claude": "Claude CLI - Anthropic AI",
        "pi": "pi-coding-agent - pi print mode (ollama/deepseek etc.)",
    }
```

- [ ] **Step 3: Implement** — line 447, add pi example line after the kimi example:
```python
    console.print(
        "[dim]Example: [bold]zima agent create --type kimi --name 'My Agent' --code my-agent[/bold][/dim]"
    )
    console.print(
        "[dim]        [bold]zima agent create --type pi --name 'Pi CR Agent' --code pi-cr-agent[/bold][/dim]"
    )
```

- [ ] **Step 4: Verify CLI**

Run: `uv run zima agent types`
Expected: table lists 3 types (claude, kimi, pi) with pi description + parameters (provider, model, thinking, noSession, ...).

Run: `uv run zima agent create --type pi --name "Test Pi" --code test-pi-cli --work-dir /tmp 2>&1 | head -5; uv run zima agent delete test-pi-cli --force`
Expected: "Agent 'test-pi-cli' created successfully" + Type: pi, then deleted.

- [ ] **Step 5: Lint + format**

Run: `uv run ruff check zima/commands/agent.py && uv run black --check zima/commands/agent.py --line-length 100`

- [ ] **Step 6: Commit**

```bash
git add zima/commands/agent.py
git commit -m "feat(agent): list pi in CLI types and help

Refs #143"
```

---

### Task 6: templates/examples.py — pi example + forTypes

**Files:**
- Modify: `zima/templates/examples.py:13` (AGENT_EXAMPLE), `zima/templates/examples.py:87` (forTypes)

**Interfaces:**
- Produces: `zima agent examples` (or example generation) shows a pi agent example; PMG example forTypes includes pi.

- [ ] **Step 1: Implement** — add a `PI_AGENT_EXAMPLE` constant after the existing `AGENT_EXAMPLE` (line ~19):

```python
PI_AGENT_EXAMPLE = """\
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: my-pi-agent
  name: My Pi Agent
  description: "An example pi-coding-agent for code review"
spec:
  type: pi
  parameters:
    provider: ollama
    model: deepseek-v4-flash:0731-cloud
    thinking: max
    noSession: true
    outputFormat: text
    tools:
    - read
    - bash
    - grep
    - find
    - ls
  defaults:
    workflow: my-workflow
    env: my-env
"""
```

Wire it into wherever `AGENT_EXAMPLE` is referenced (search `examples.py` for `AGENT_EXAMPLE` usage — likely an `EXAMPLES` dict keyed by kind; add `pi` variant or a separate entry so `zima agent examples --type pi` can surface it).

- [ ] **Step 2: Implement** — line 87, add pi to forTypes:
```python
  forTypes: [kimi, claude, pi]
```

- [ ] **Step 3: Verify**

Run: `uv run python -c "from zima.templates.examples import PI_AGENT_EXAMPLE; print(PI_AGENT_EXAMPLE[:60])"`
Expected: prints the YAML head. Also run any existing examples test:
Run: `uv run pytest tests/ -k "example" -v 2>/dev/null | tail -5`

- [ ] **Step 4: Lint + format**

Run: `uv run ruff check zima/templates/examples.py && uv run black --check zima/templates/examples.py --line-length 100`

- [ ] **Step 5: Commit**

```bash
git add zima/templates/examples.py
git commit -m "feat(examples): add pi agent example and forTypes entry

Refs #143"
```

---

### Task 7: AGENTS.md + CLAUDE.md — docs type list

**Files:**
- Modify: `AGENTS.md:52`, `AGENTS.md:70`, `AGENTS.md:103`, `AGENTS.md:182-183`; `CLAUDE.md:52`, `CLAUDE.md:70`, `CLAUDE.md:99`, `CLAUDE.md:169`

**Interfaces:** None (docs only).

- [ ] **Step 1: Implement** — in both `AGENTS.md` and `CLAUDE.md`, update the Agent table row (line 52) from `(kimi/claude)` to `(kimi/claude/pi)`:

```
| Agent | `AgentConfig` | AI executor config (kimi/claude/pi), builds CLI commands |
```

- [ ] **Step 2: Implement** — update the runner line (AGENTS.md line 70 / CLAUDE.md line 70) to mention pi reuses executor stdin path (no dedicated runner):

```
- **`zima/core/kimi_runner.py`** / **`zima/core/claude_runner.py`** — Agent-specific subprocess runners for Kimi and Claude. (pi type reuses the executor's generic subprocess + stdin-pipe path, no dedicated runner.)
```

- [ ] **Step 3: Implement** — update execution flow line (AGENTS.md line 103 / CLAUDE.md line 99) `Executes subprocess (kimi/claude)` → `Executes subprocess (kimi/claude/pi)`.

- [ ] **Step 4: Implement** — update the "To add a new Agent type" extension section (AGENTS.md line 182-183 / CLAUDE.md line 169) — append a note that pi is now supported and uses `--mode` (not `--output-format`), `needs_stdin_pipe=True`, no `--work-dir`:

```
To add a new **Agent type** (e.g., a new AI CLI):
1. Add to `VALID_AGENT_TYPES` and parameter template in `zima/models/agent.py`
...
Note: `pi` type is supported (pi-coding-agent print mode). It uses `--mode` for output format (not `--output-format`), `needs_stdin_pipe=True` (stdin-piped like claude), and relies on `Popen(cwd=)` (no `--work-dir` flag).
```

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs: document pi agent type in AGENTS.md and CLAUDE.md

Refs #143"
```

---

### Task 8: integration test + full suite verification

**Files:**
- Modify: `tests/integration/test_agent_commands.py` (near line 173-178)

**Interfaces:**
- Produces: integration test covers `zima agent create --type pi` + `list --type pi`.

- [ ] **Step 1: Write the failing test** (add near line 175, after the claude create test):

```python
        result = runner.invoke(
            app, ["agent", "create", "--name", "Pi", "--code", "p1", "--type", "pi"]
        )
        assert result.exit_code == 0
        assert "Pi" in result.output
        assert "pi" in result.output
        # list filter
        result_list = runner.invoke(app, ["agent", "list", "--type", "pi"])
        assert result_list.exit_code == 0
```

- [ ] **Step 2: Run test to verify it passes** (pi already supported after Task 1-5, so this should pass immediately — it's a regression guard):

Run: `uv run pytest tests/integration/test_agent_commands.py -v -k "pi or create" 2>&1 | tail -15`
Expected: PASS. If FAIL, re-check Task 1/5.

- [ ] **Step 3: Run full unit + integration suite**

Run: `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60 2>&1 | tail -20`
Expected: all pass, coverage ≥ 60%.

- [ ] **Step 4: Lint + format whole project**

Run: `uv run ruff check zima/ tests/ && uv run black --check zima/ tests/ --line-length 100`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_agent_commands.py
git commit -m "test(agent): integration test for --type pi create and list

Refs #143"
```

- [ ] **Step 6: Final full-suite green check**

Run: `uv run pytest tests/ -m "not slow" 2>&1 | tail -5`
Expected: all pass.

---

## Self-Review

**1. Spec coverage:**
- pi type registration + param template + `_build_pi_command` + `needs_stdin_pipe` → Task 1 ✓
- `--provider`/`--model`/`--thinking`/`--no-session`/`--mode`/`--tools`/`--exclude-tools`/`--no-context-files`/`--system-prompt`/`--append-system-prompt` flags → Task 1 `_build_pi_command` ✓
- `--mode` not `--output-format` → Task 1 + Global Constraints ✓
- no `--work-dir`/`--cwd` → Task 1 `test_build_pi_command_no_work_dir` ✓
- thinking default max → Task 1 param template + `test_pi_default_parameters` ✓
- tools whitelist `read,bash,grep,find,ls` → Task 1 ✓
- utils.py sync → Task 2 ✓
- env.py `VALID_ENV_FOR_TYPES` → Task 3 ✓
- pmg.py `VALID_PMG_FOR_TYPES` → Task 4 ✓
- CLI help + types subcommand → Task 5 ✓
- examples.py pi example + forTypes → Task 6 ✓
- AGENTS.md + CLAUDE.md → Task 7 ✓
- integration test + full suite → Task 8 ✓
- executor/ReviewParser/ConfigBundle zero change → no task (by design) ✓

**2. Placeholder scan:** Task 6 Step 1 says "wire it into wherever AGENT_EXAMPLE is referenced — search examples.py" — this is a directed instruction, not a placeholder; implementer must check the actual `EXAMPLES` dict structure. All other steps have concrete code. No TBD/TODO.

**3. Type consistency:** `_build_pi_command(cmd, params) -> list[str]` signature matches across Task 1 steps and the `build_command` branch. Parameter names (`noSession`/`outputFormat`/`noContextFiles`/`excludeTools`/`appendSystemPrompt`) consistent in param template, `_build_pi_command`, and tests. `needs_stdin_pipe` returns `self.type in ("claude","pi")` — consistent.

All spec requirements covered. No placeholders. Types consistent.