# Quickstart Code-Review Scene Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix quickstart wizard so `zima quickstart` with code-review scene generates a fully functional PJob with preExec scan_pr, complete variables, and unified labels.

**Architecture:** Minimal fix to 2 source files (`scenes.py`, `quickstart.py`) plus test updates. Scene definition gets preExec + complete variables + unified labels. Quickstart gets git remote repo auto-detection.

**Tech Stack:** Python 3.10+, dataclasses, unittest.mock for testing.

---

### Task 1: Fix scenes.py code-review scene definition

**Files:**
- Modify: `zima/scenes.py:11` (add import)
- Modify: `zima/scenes.py:38-82` (fix code-review scene)
- Test: `tests/unit/test_scenes.py`

- [ ] **Step 1: Update the import line in scenes.py**

At `zima/scenes.py:11`, change:
```python
from zima.models.actions import ActionsConfig, PostExecAction
```
to:
```python
from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction
```

- [ ] **Step 2: Replace the code-review scene definition in scenes.py**

Replace the `"code-review": Scene(...)` block at `zima/scenes.py:39-75` with:

```python
    "code-review": Scene(
        name="Code Review",
        description="Review PRs/MRs with AI agent",
        workflow_template="review pr {{ pr_url }}",
        variables={"pr_url": "", "repo": "", "pr_number": ""},
        provider="github",
        default_actions=ActionsConfig(
            pre_exec=[
                PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review"),
            ],
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    remove_labels=["zima:needs-review"],
                    repo="{{repo}}",
                    issue="{{pr_number}}",
                ),
                PostExecAction(
                    condition="failure",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="{{repo}}",
                    issue="{{pr_number}}",
                ),
            ],
        ),
    ),
```

Note: `scan_command` is removed entirely. The `custom` scene remains unchanged.

- [ ] **Step 3: Run existing tests to see which ones break**

Run: `uv run pytest tests/unit/test_scenes.py -v`
Expected: `test_code_review_scene_structure` fails (variables/scan_command assertions), `test_code_review_scene_has_default_actions` may pass or fail depending on assertions.

- [ ] **Step 4: Update test_scenes.py**

In `tests/unit/test_scenes.py`, make these changes:

1. In `test_code_review_scene_structure` (line 63-81), replace the assertion block:
```python
    def test_code_review_scene_structure(self):
        """Test code-review scene has correct fields."""
        scene = BUILTIN_SCENES["code-review"]
        assert scene.name == "Code Review"
        assert scene.description == "Review PRs/MRs with AI agent"
        assert scene.workflow_template == "review pr {{ pr_url }}"
        assert scene.variables == {"pr_url": "", "repo": "", "pr_number": ""}
        assert scene.provider == "github"
        assert scene.scan_command is None
```

2. In `test_code_review_scene_has_default_actions` (line 93-114), add pre_exec assertions:
```python
    def test_code_review_scene_has_default_actions(self):
        """Test code-review scene has preExec and postExec actions."""
        scene = BUILTIN_SCENES["code-review"]
        assert scene.default_actions is not None
        assert isinstance(scene.default_actions, ActionsConfig)

        # preExec: scan_pr
        assert len(scene.default_actions.pre_exec) == 1
        pre_action = scene.default_actions.pre_exec[0]
        assert pre_action.type == "scan_pr"
        assert pre_action.repo == "{{repo}}"
        assert pre_action.label == "zima:needs-review"

        # postExec: success and failure label transitions
        assert len(scene.default_actions.post_exec) == 2

        success_action = scene.default_actions.post_exec[0]
        assert success_action.condition == "success"
        assert success_action.type == "add_label"
        assert success_action.remove_labels == ["zima:needs-review"]
        assert success_action.add_labels == []
        assert success_action.repo == "{{repo}}"
        assert success_action.issue == "{{pr_number}}"

        failure_action = scene.default_actions.post_exec[1]
        assert failure_action.condition == "failure"
        assert failure_action.type == "add_label"
        assert failure_action.add_labels == ["zima:needs-fix"]
        assert failure_action.remove_labels == ["zima:needs-review"]
        assert failure_action.repo == "{{repo}}"
        assert failure_action.issue == "{{pr_number}}"
```

3. Add a new test method after `test_code_review_scene_has_default_actions`:
```python
    def test_code_review_scene_pre_exec_scan_pr(self):
        """Test code-review preExec scan_pr has correct repo and label."""
        scene = BUILTIN_SCENES["code-review"]
        pre = scene.default_actions.pre_exec[0]
        assert pre.type == "scan_pr"
        assert pre.repo == "{{repo}}"
        assert pre.label == "zima:needs-review"
        assert pre.condition == "always"
```

4. Update `test_user_scene_with_default_actions` (line 212-242) — no changes needed, it tests user scenes YAML loading which is unaffected.

- [ ] **Step 5: Run tests to verify all pass**

Run: `uv run pytest tests/unit/test_scenes.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add zima/scenes.py tests/unit/test_scenes.py
git commit -m "fix(scenes): add preExec scan_pr, complete variables, unify labels in code-review scene"
```

---

### Task 2: Add repo auto-detection to quickstart.py

**Files:**
- Modify: `zima/commands/quickstart.py:30-42` (add helper function)
- Modify: `zima/commands/quickstart.py:110-117` (add parameter to `_create_all_configs`)
- Modify: `zima/commands/quickstart.py:152-158` (merge detected repo into variables)
- Modify: `zima/commands/quickstart.py:284-365` (remove scan display, add repo detection call)
- Test: `tests/unit/test_quickstart.py`

- [ ] **Step 1: Add `_detect_repo_slug` helper function**

Add after `_detect_git_repo` (after line 42):

```python
def _detect_repo_slug() -> str:
    """Detect owner/repo slug from git remote URL. Returns '' if not detected."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        url = result.stdout.strip()
    except Exception:
        return ""

    # HTTPS: https://github.com/owner/repo.git
    # SSH:   git@github.com:owner/repo.git
    # Plain: owner/repo
    if url.startswith("git@"):
        # git@host:owner/repo.git
        path = url.split(":", 1)[-1]
    elif "://" in url:
        # https://host/owner/repo.git
        path = url.split("://", 1)[-1].split("/", 1)[-1]
    else:
        path = url

    path = path.removesuffix(".git")
    parts = path.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return ""
```

- [ ] **Step 2: Add `detected_repo` parameter to `_create_all_configs`**

Change the function signature at line 110-117:
```python
def _create_all_configs(
    base_name: str,
    scene_key: str,
    agent_type: str,
    work_dir: str,
    env_code: Optional[str],
    manager: ConfigManager,
    detected_repo: str = "",
) -> dict[str, str]:
```

- [ ] **Step 3: Merge detected repo into variable values**

Replace line 152-158 (the Variable creation block):
```python
    # 3. Create Variable
    values = scene.variables.copy()
    if detected_repo:
        values["repo"] = detected_repo
    var = VariableConfig.create(
        code=var_code,
        name=f"{base_name.title()} Variables",
        for_workflow=wf_code,
        values=values,
    )
    manager.save_config("variable", var_code, var.to_dict())
```

- [ ] **Step 4: Remove scan_command display section and add repo detection in quickstart()**

In the `quickstart()` function (starting at line 284), make these changes:

1. Remove the entire Step 5 block (lines 311-320):
```python
    # Step 5: Show PR scan (display only)
    scene = scenes[scene_key]
    if scene.scan_command:
        ...
```

2. After the `_resolve_work_dir` call (around line 309), add repo detection:
```python
    # Step 4: Resolve workDir
    resolved_work_dir = _resolve_work_dir(preselected=work_dir)

    # Step 5: Detect repo from git remote
    detected_repo = _detect_repo_slug()
```

3. Update the scene variable reference. After repo detection, load scene for later use:
```python
    scene = scenes[scene_key]
```

4. Update the `_create_all_configs` call (around line 346) to pass `detected_repo`:
```python
    codes = _create_all_configs(
        base_name=base_name,
        scene_key=scene_key,
        agent_type=agent_type,
        work_dir=resolved_work_dir,
        env_code=env_code,
        manager=manager,
        detected_repo=detected_repo,
    )
```

- [ ] **Step 5: Run quickstart tests to see which break**

Run: `uv run pytest tests/unit/test_quickstart.py -v`
Expected: `test_create_all_configs_code_review` and `test_create_all_configs_code_review_has_actions` may fail or pass depending on how they call the function. The integration tests that mock `_scan_with_command` will fail since that function is still imported but no longer called.

- [ ] **Step 6: Update integration test_quickstart.py**

In `tests/integration/test_quickstart.py`, the `test_quickstart_code_review_non_interactive` test (line 11-40) patches `_scan_with_command`. Since we removed the scan display step, we can remove that patch. Also add a patch for `_detect_repo_slug`:

Replace the test:
```python
    def test_quickstart_code_review_non_interactive(self):
        """Test quickstart with pre-selected options (minimal interaction)."""
        from typer.testing import CliRunner

        from zima.cli import app

        runner = CliRunner()

        with patch("zima.commands.quickstart._detect_git_repo", return_value="/tmp/workspace"):
            with patch(
                "zima.commands.quickstart._detect_repo_slug",
                return_value="owner/repo",
            ):
                with patch("zima.commands.quickstart.typer.prompt", return_value="1"):
                    with patch("zima.commands.quickstart.typer.confirm", return_value=True):
                        result = runner.invoke(
                            app,
                            [
                                "quickstart",
                                "--scene",
                                "code-review",
                                "--name",
                                "testqs",
                                "--work-dir",
                                "/tmp/workspace",
                            ],
                        )

        assert result.exit_code == 0, result.output
        assert "Created" in result.output or "created" in result.output
        assert "testqs-job" in result.output
        assert "zima pjob run" in result.output
        assert "--dry-run" in result.output
```

- [ ] **Step 7: Add unit tests for `_detect_repo_slug`**

Add a new test class in `tests/unit/test_quickstart.py`, after the `TestDetectGitRepo` class (after line 33):

```python
class TestDetectRepoSlug(TestIsolator):
    """Test git remote repo slug detection."""

    def test_detect_repo_slug_https(self):
        """Test detection from HTTPS URL."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/zhuxixi/zima-blue-cli.git\n", stderr=""
            )
            result = _detect_repo_slug()
            assert result == "zhuxixi/zima-blue-cli"

    def test_detect_repo_slug_ssh(self):
        """Test detection from SSH URL."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="git@github.com:zhuxixi/zima-blue-cli.git\n", stderr=""
            )
            result = _detect_repo_slug()
            assert result == "zhuxixi/zima-blue-cli"

    def test_detect_repo_slug_no_git(self):
        """Test returns empty string when git command fails."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("no git")
            result = _detect_repo_slug()
            assert result == ""

    def test_detect_repo_slug_https_no_git_suffix(self):
        """Test detection from HTTPS URL without .git suffix."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/owner/repo\n", stderr=""
            )
            result = _detect_repo_slug()
            assert result == "owner/repo"
```

- [ ] **Step 8: Update `test_create_all_configs_code_review` to verify repo variable**

In `tests/unit/test_quickstart.py`, update the `test_create_all_configs_code_review` test (line 113-158). Add repo verification after line 151:

```python
    def test_create_all_configs_code_review(self):
        """Test creating full config set for code-review scene."""
        from zima.commands.quickstart import _create_all_configs
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        codes = _create_all_configs(
            base_name="test",
            scene_key="code-review",
            agent_type="kimi",
            work_dir="/tmp/workspace",
            env_code="test-env",
            manager=manager,
            detected_repo="zhuxixi/zima-blue-cli",
        )

        assert "agent" in codes
        assert "workflow" in codes
        assert "variable" in codes
        assert "pjob" in codes
        assert codes["env"] == "test-env"

        # Verify configs were saved
        assert manager.config_exists("agent", codes["agent"])
        assert manager.config_exists("workflow", codes["workflow"])
        assert manager.config_exists("variable", codes["variable"])
        assert manager.config_exists("pjob", codes["pjob"])

        # Verify agent has workDir
        agent_data = manager.load_config("agent", codes["agent"])
        assert agent_data["spec"]["parameters"]["workDir"] == "/tmp/workspace"

        # Verify workflow has variables
        wf_data = manager.load_config("workflow", codes["workflow"])
        var_names = {v["name"] for v in wf_data["spec"]["variables"]}
        assert "pr_url" in var_names
        assert "repo" in var_names
        assert "pr_number" in var_names

        # Verify variable has forWorkflow and repo populated
        var_data = manager.load_config("variable", codes["variable"])
        assert var_data["spec"]["forWorkflow"] == codes["workflow"]
        assert var_data["spec"]["values"]["repo"] == "zhuxixi/zima-blue-cli"

        # Verify pjob refs are correct
        job_data = manager.load_config("pjob", codes["pjob"])
        assert job_data["spec"]["agent"] == codes["agent"]
        assert job_data["spec"]["workflow"] == codes["workflow"]
        assert job_data["spec"]["variable"] == codes["variable"]
        assert job_data["spec"]["env"] == "test-env"
```

- [ ] **Step 9: Update `test_create_all_configs_code_review_has_actions` to verify preExec**

In `tests/unit/test_quickstart.py`, update the test at line 160-183 to also check preExec:

```python
    def test_create_all_configs_code_review_has_actions(self):
        """Test code-review PJob gets preExec and postExec actions from scene defaults."""
        from zima.commands.quickstart import _create_all_configs
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        codes = _create_all_configs(
            base_name="test",
            scene_key="code-review",
            agent_type="kimi",
            work_dir="/tmp/workspace",
            env_code=None,
            manager=manager,
        )

        job_data = manager.load_config("pjob", codes["pjob"])
        actions = job_data["spec"].get("actions", {})

        # preExec: scan_pr
        pre_exec = actions.get("preExec", [])
        assert len(pre_exec) == 1
        assert pre_exec[0]["type"] == "scan_pr"
        assert pre_exec[0]["label"] == "zima:needs-review"
        assert pre_exec[0]["repo"] == "{{repo}}"

        # postExec: success and failure
        post_exec = actions.get("postExec", [])
        assert len(post_exec) == 2
        assert post_exec[0]["condition"] == "success"
        assert post_exec[0]["removeLabels"] == ["zima:needs-review"]
        assert post_exec[1]["condition"] == "failure"
        assert post_exec[1]["addLabels"] == ["zima:needs-fix"]
```

- [ ] **Step 10: Run all tests**

Run: `uv run pytest tests/unit/test_scenes.py tests/unit/test_quickstart.py tests/integration/test_quickstart.py -v`
Expected: All tests PASS.

- [ ] **Step 11: Run full test suite**

Run: `uv run pytest`
Expected: All tests PASS (947+ passed, same skip count as before).

- [ ] **Step 12: Commit**

```bash
git add zima/commands/quickstart.py tests/unit/test_quickstart.py tests/integration/test_quickstart.py
git commit -m "feat(quickstart): auto-detect repo from git remote for code-review scene"
```

---

### Task 3: Verify end-to-end with integration test

**Files:**
- Test: `tests/integration/test_quickstart.py`

- [ ] **Step 1: Run the full integration test suite**

Run: `uv run pytest tests/integration/test_quickstart.py -v`
Expected: All 4 integration tests pass including the updated code-review test.

- [ ] **Step 2: Verify generated config shape matches production**

Run a quick manual check to verify the generated PJob matches the production config shape on vocabo:

```bash
uv run python -c "
from zima.scenes import BUILTIN_SCENES
scene = BUILTIN_SCENES['code-review']
actions = scene.default_actions
print('preExec:', [{'type': a.type, 'repo': a.repo, 'label': a.label} for a in actions.pre_exec])
print('postExec:', [{'condition': a.condition, 'remove_labels': a.remove_labels} for a in actions.post_exec])
print('variables:', scene.variables)
print('scan_command:', scene.scan_command)
"
```

Expected output:
```
preExec: [{'type': 'scan_pr', 'repo': '{{repo}}', 'label': 'zima:needs-review'}]
postExec: [{'condition': 'success', 'remove_labels': ['zima:needs-review']}, {'condition': 'failure', 'remove_labels': ['zima:needs-review']}]
variables: {'pr_url': '', 'repo': '', 'pr_number': ''}
scan_command: None
```

This matches the production config shape on vocabo (with the addition of `pr_url` and `pr_number` in variables which scan_pr auto-populates at runtime).
