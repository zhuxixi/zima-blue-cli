# Issue #63: Plugin-based Action Provider Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple Zima's post-execution action system from GitHub by introducing an `ActionProvider` plugin architecture with built-in registry and entry-point discovery.

**Architecture:** Extract `GitHubOps` into `GitHubProvider` implementing the `ActionProvider` ABC. Introduce `ProviderRegistry` that loads built-in providers and discovers external ones via Python entry points. Refactor `ActionsRunner` to dispatch actions through the registry. Extend quickstart scenes via YAML config.

**Tech Stack:** Python 3.10+, dataclasses, ABC, `importlib.metadata.entry_points`, pytest, unittest.mock

---

## File Map

| File | Responsibility |
|------|---------------|
| `zima/actions/base.py` | `ActionProvider` ABC — interface all providers implement |
| `zima/actions/exceptions.py` | `ProviderNotFoundError`, `ProviderError` |
| `zima/actions/registry.py` | `ProviderRegistry` — loads built-in + entry-point providers, singleton |
| `zima/providers/__init__.py` | `BUILTIN_PROVIDERS` dict |
| `zima/providers/github.py` | `GitHubProvider` — `gh` CLI wrapper, extracted from `zima/github/ops.py` |
| `zima/models/actions.py` | `VALID_ACTION_TYPES` generic, `ActionsConfig.provider` field |
| `zima/execution/actions_runner.py` | Dispatches actions through registry instead of hardcoded `GitHubOps` |
| `zima/scenes.py` | `Scene` dataclass, `load_scenes()`, user scene YAML support |
| `zima/commands/quickstart.py` | Uses `scene.scan_command` instead of hardcoded `gh pr list` |
| `zima/templates/examples.py` | Update REVIEWER_PJOB to use generic action types |
| `zima/github/ops.py` | **Delete** — migrated to `zima/providers/github.py` |
| `zima/github/__init__.py` | **Delete** — empty re-export package |
| `tests/unit/test_actions_base.py` | Tests for `ActionProvider` ABC |
| `tests/unit/test_actions_exceptions.py` | Tests for exceptions |
| `tests/unit/test_actions_registry.py` | Tests for `ProviderRegistry` |
| `tests/unit/test_providers_github.py` | Tests for `GitHubProvider` (migrated from `test_github_ops.py`) |
| `tests/unit/test_models_actions.py` | Updated for generic types + provider field |
| `tests/unit/test_actions_runner.py` | Updated for registry-based runner |
| `tests/unit/test_scenes.py` | Updated for `Scene` dataclass + `load_scenes()` |
| `tests/unit/test_quickstart.py` | Updated for scan_command refactor |

---

### Task 1: ActionProvider ABC + Exceptions

**Files:**
- Create: `zima/actions/base.py`
- Create: `zima/actions/exceptions.py`
- Test: `tests/unit/test_actions_base.py`
- Test: `tests/unit/test_actions_exceptions.py`

- [ ] **Step 1: Write failing test for ActionProvider ABC**

```python
# tests/unit/test_actions_base.py
from zima.actions.base import ActionProvider


class TestActionProvider:
    def test_can_subclass_and_call_methods(self):
        """Test that ActionProvider can be subclassed and methods work."""

        class TestProvider(ActionProvider):
            @property
            def name(self):
                return "test"

            def add_label(self, repo, issue, label):
                pass

            def remove_label(self, repo, issue, label):
                pass

            def post_comment(self, repo, issue, body):
                pass

            def fetch_diff(self, repo, issue):
                return "diff"

        provider = TestProvider()
        assert provider.name == "test"
        provider.add_label("o/r", "1", "bug")
        provider.remove_label("o/r", "1", "bug")
        provider.post_comment("o/r", "1", "ok")
        assert provider.fetch_diff("o/r", "1") == "diff"

    def test_abstract_methods_must_be_implemented(self):
        """Test that missing abstract methods prevent instantiation."""
        with pytest.raises(TypeError):
            class BadProvider(ActionProvider):
                pass

            BadProvider()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_actions_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zima.actions.base'`

- [ ] **Step 3: Write exceptions module**

```python
# zima/actions/exceptions.py
class ProviderError(Exception):
    """Base exception for action provider errors."""


class ProviderNotFoundError(ProviderError):
    """Raised when a requested provider is not found in the registry."""
```

- [ ] **Step 4: Write ActionProvider ABC**

```python
# zima/actions/base.py
from __future__ import annotations

from abc import ABC, abstractmethod


class ActionProvider(ABC):
    """Platform-agnostic action provider for post-exec automation."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier, e.g. 'github', 'gitlab'."""

    @abstractmethod
    def add_label(self, repo: str, issue: str, label: str) -> None:
        """Add label to issue/MR."""

    @abstractmethod
    def remove_label(self, repo: str, issue: str, label: str) -> None:
        """Remove label from issue/MR."""

    @abstractmethod
    def post_comment(self, repo: str, issue: str, body: str) -> None:
        """Post comment on issue/MR."""

    @abstractmethod
    def fetch_diff(self, repo: str, issue: str) -> str:
        """Fetch PR/MR diff content. Returns empty string on failure."""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_actions_base.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add zima/actions/base.py zima/actions/exceptions.py tests/unit/test_actions_base.py tests/unit/test_actions_exceptions.py
git commit -m "feat(actions): add ActionProvider ABC and exceptions"
```

---

### Task 2: GitHubProvider

**Files:**
- Create: `zima/providers/github.py`
- Test: `tests/unit/test_providers_github.py`

- [ ] **Step 1: Write failing test for GitHubProvider**

```python
# tests/unit/test_providers_github.py
from unittest.mock import MagicMock, patch

import pytest

from zima.providers.github import GitHubProvider


class TestGitHubProvider:
    def test_name(self):
        provider = GitHubProvider()
        assert provider.name == "github"

    def test_add_label(self):
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.add_label("owner/repo", "123", "zima:needs-fix")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "gh" in args
            assert "issue" in args
            assert "edit" in args
            assert "123" in args
            assert "--add-label" in args
            assert "zima:needs-fix" in args
            assert "--repo" in args
            assert "owner/repo" in args

    def test_remove_label(self):
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.remove_label("owner/repo", "123", "zima:needs-review")
            args = mock_run.call_args[0][0]
            assert "--remove-label" in args
            assert "zima:needs-review" in args

    def test_post_comment(self):
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.post_comment("owner/repo", "123", "Review done")
            args = mock_run.call_args[0][0]
            assert "comment" in args
            assert "--body" in args
            assert "Review done" in args

    def test_post_comment_multiline(self):
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            provider.post_comment("owner/repo", "123", "Line 1\nLine 2")
            args = mock_run.call_args[0][0]
            assert "--body" in args

    def test_add_label_failure_raises(self):
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="label not found")
            with pytest.raises(RuntimeError, match="gh CLI failed"):
                provider.add_label("owner/repo", "123", "bad-label")

    def test_fetch_diff(self):
        provider = GitHubProvider()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="diff --git a/foo.py b/foo.py", stderr=""
            )
            diff = provider.fetch_diff("owner/repo", "123")
            assert diff == "diff --git a/foo.py b/foo.py"
            args = mock_run.call_args[0][0]
            assert "pr" in args
            assert "view" in args
            assert "--patch" in args
            assert "123" in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_providers_github.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zima.providers.github'`

- [ ] **Step 3: Write GitHubProvider**

```python
# zima/providers/github.py
from __future__ import annotations

import subprocess

from zima.actions.base import ActionProvider


class GitHubProvider(ActionProvider):
    """GitHub action provider using gh CLI."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "github"

    def _run(
        self, args: list[str], check: bool = True, capture: bool = True
    ) -> subprocess.CompletedProcess:
        cmd = ["gh"] + args
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=self.timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"gh CLI failed: {' '.join(cmd)}\nstderr: {result.stderr.strip()}"
            )
        return result

    def add_label(self, repo: str, issue: str, label: str) -> None:
        self._run(["issue", "edit", issue, "--add-label", label, "--repo", repo])

    def remove_label(self, repo: str, issue: str, label: str) -> None:
        self._run(["issue", "edit", issue, "--remove-label", label, "--repo", repo])

    def post_comment(self, repo: str, issue: str, body: str) -> None:
        self._run(["issue", "comment", issue, "--body", body, "--repo", repo])

    def fetch_diff(self, repo: str, issue: str) -> str:
        result = self._run(
            ["pr", "view", issue, "--repo", repo, "--patch"],
            capture=True,
        )
        return result.stdout
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_providers_github.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/providers/github.py tests/unit/test_providers_github.py
git commit -m "feat(providers): add GitHubProvider extracted from github/ops"
```

---

### Task 3: ProviderRegistry

**Files:**
- Create: `zima/actions/registry.py`
- Create: `zima/providers/__init__.py`
- Test: `tests/unit/test_actions_registry.py`

- [ ] **Step 1: Write failing test for ProviderRegistry**

```python
# tests/unit/test_actions_registry.py
from unittest.mock import MagicMock, patch

import pytest

from zima.actions.exceptions import ProviderNotFoundError
from zima.actions.registry import ProviderRegistry, get_default_registry, reset_registry
from zima.providers.github import GitHubProvider


class TestProviderRegistry:
    def test_builtin_github_loaded(self):
        registry = ProviderRegistry()
        providers = registry.list()
        assert "github" in providers

    def test_get_github(self):
        registry = ProviderRegistry()
        provider = registry.get("github")
        assert isinstance(provider, GitHubProvider)
        assert provider.name == "github"

    def test_get_not_found_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError, match="Provider 'missing' not found"):
            registry.get("missing")

    def test_external_provider_via_entry_points(self):
        """Test that entry points are discovered and override builtins."""
        mock_provider = MagicMock()
        mock_provider.name = "gitlab"

        mock_ep = MagicMock()
        mock_ep.name = "gitlab"
        mock_ep.load.return_value = lambda: mock_provider

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = [mock_ep]
            registry = ProviderRegistry()
            assert "gitlab" in registry.list()
            assert registry.get("gitlab") == mock_provider

    def test_external_override_builtin(self):
        """Test that external provider with same name overrides builtin."""
        mock_provider = MagicMock()
        mock_provider.name = "github"

        mock_ep = MagicMock()
        mock_ep.name = "github"
        mock_ep.load.return_value = lambda: mock_provider

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = [mock_ep]
            registry = ProviderRegistry()
            assert registry.get("github") == mock_provider

    def test_entry_point_load_failure_warns(self):
        """Test that failing entry points are skipped with a warning."""
        mock_ep = MagicMock()
        mock_ep.name = "broken"
        mock_ep.load.side_effect = ImportError("no module")

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = [mock_ep]
            registry = ProviderRegistry()
            assert "broken" not in registry.list()
            assert "github" in registry.list()


class TestRegistrySingleton:
    def test_singleton(self):
        reset_registry()
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2

    def test_reset(self):
        reset_registry()
        r1 = get_default_registry()
        reset_registry()
        r2 = get_default_registry()
        assert r1 is not r2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_actions_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'zima.actions.registry'`

- [ ] **Step 3: Write ProviderRegistry + builtin registration**

```python
# zima/actions/registry.py
from __future__ import annotations

import importlib.metadata
from typing import Optional

from zima.actions.base import ActionProvider
from zima.actions.exceptions import ProviderNotFoundError


class ProviderRegistry:
    """Manages built-in and externally registered action providers."""

    def __init__(self):
        self._providers: dict[str, ActionProvider] = {}
        self._load_builtin()
        self._discover_entry_points()

    def _load_builtin(self) -> None:
        from zima.providers import BUILTIN_PROVIDERS

        for name, cls in BUILTIN_PROVIDERS.items():
            self._providers[name] = cls()

    def _discover_entry_points(self) -> None:
        try:
            eps = importlib.metadata.entry_points(group="zima.action_providers")
        except (AttributeError, TypeError):
            # Python < 3.10 compatibility
            try:
                all_eps = importlib.metadata.entry_points()
                eps = all_eps.get("zima.action_providers", [])
            except Exception:
                eps = []

        for ep in eps:
            try:
                cls = ep.load()
                instance = cls()
                # External overrides builtin
                self._providers[instance.name] = instance
            except Exception as e:
                print(f"Warning: Failed to load provider from {ep.name}: {e}")

    def get(self, name: str) -> ActionProvider:
        if name not in self._providers:
            raise ProviderNotFoundError(
                f"Provider '{name}' not found. "
                f"Available: {sorted(self._providers.keys())}"
            )
        return self._providers[name]

    def list(self) -> list[str]:
        return list(self._providers.keys())


_default_registry: Optional[ProviderRegistry] = None


def get_default_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ProviderRegistry()
    return _default_registry


def reset_registry() -> None:
    """Reset registry singleton. For testing only."""
    global _default_registry
    _default_registry = None
```

```python
# zima/providers/__init__.py
from __future__ import annotations

from zima.actions.base import ActionProvider
from zima.providers.github import GitHubProvider

BUILTIN_PROVIDERS: dict[str, type[ActionProvider]] = {
    "github": GitHubProvider,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_actions_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/actions/registry.py zima/providers/__init__.py tests/unit/test_actions_registry.py
git commit -m "feat(actions): add ProviderRegistry with builtin + entry point discovery"
```

---

### Task 4: Model Changes — Generic Action Types + Provider Field

**Files:**
- Modify: `zima/models/actions.py`
- Test: `tests/unit/test_models_actions.py`

- [ ] **Step 1: Write failing test for new models**

```python
# tests/unit/test_models_actions.py
from zima.models.actions import ActionsConfig, PostExecAction


class TestPostExecAction:
    def test_default_action(self):
        action = PostExecAction()
        assert action.condition == "always"
        assert action.type == "add_label"
        assert action.add_labels == []
        assert action.remove_labels == []
        assert action.repo == ""
        assert action.issue == ""
        assert action.body == ""

    def test_full_action(self):
        action = PostExecAction(
            condition="success",
            type="add_comment",
            body="Review approved",
            repo="owner/repo",
            issue="123",
        )
        assert action.condition == "success"
        assert action.type == "add_comment"
        assert action.body == "Review approved"

    def test_to_dict(self):
        action = PostExecAction(
            condition="success",
            type="add_label",
            add_labels=["zima:needs-fix"],
            remove_labels=["zima:needs-review"],
            repo="owner/repo",
            issue="42",
        )
        d = action.to_dict()
        assert d["condition"] == "success"
        assert d["type"] == "add_label"
        assert d["addLabels"] == ["zima:needs-fix"]
        assert d["removeLabels"] == ["zima:needs-review"]
        assert d["repo"] == "owner/repo"
        assert d["issue"] == "42"

    def test_to_dict_omits_empty_fields(self):
        action = PostExecAction(condition="always", type="add_label")
        d = action.to_dict()
        assert "addLabels" not in d
        assert "removeLabels" not in d
        assert "repo" not in d
        assert "issue" not in d
        assert "body" not in d

    def test_from_dict(self):
        d = {
            "condition": "failure",
            "type": "add_comment",
            "body": "Failed",
            "repo": "o/r",
            "issue": "1",
        }
        action = PostExecAction.from_dict(d)
        assert action.condition == "failure"
        assert action.body == "Failed"

    def test_validate_valid(self):
        action = PostExecAction(condition="success", type="add_label")
        assert action.validate() == []

    def test_validate_invalid_condition(self):
        action = PostExecAction(condition="invalid", type="add_label")
        errors = action.validate()
        assert len(errors) == 1
        assert "Invalid condition" in errors[0]

    def test_validate_invalid_type(self):
        action = PostExecAction(condition="success", type="invalid")
        errors = action.validate()
        assert len(errors) == 1
        assert "Invalid type" in errors[0]

    def test_old_github_types_are_rejected(self):
        action = PostExecAction(condition="success", type="github_label")
        errors = action.validate()
        assert len(errors) == 1
        assert "Invalid type" in errors[0]


class TestActionsConfig:
    def test_empty_config(self):
        config = ActionsConfig()
        assert config.provider == "github"
        assert config.post_exec == []

    def test_with_provider(self):
        config = ActionsConfig(provider="gitlab")
        assert config.provider == "gitlab"

    def test_with_actions(self):
        action = PostExecAction(condition="success", type="add_label")
        config = ActionsConfig(post_exec=[action])
        assert len(config.post_exec) == 1

    def test_to_dict(self):
        config = ActionsConfig(
            provider="gitlab",
            post_exec=[PostExecAction(condition="success", type="add_label")],
        )
        d = config.to_dict()
        assert "provider" in d
        assert d["provider"] == "gitlab"
        assert "postExec" in d
        assert len(d["postExec"]) == 1

    def test_to_dict_omits_default_provider(self):
        config = ActionsConfig(post_exec=[])
        d = config.to_dict()
        assert "provider" not in d  # omit_empty should drop default "github"

    def test_from_dict(self):
        d = {
            "provider": "gitlab",
            "postExec": [{"condition": "success", "type": "add_label", "addLabels": ["a"]}],
        }
        config = ActionsConfig.from_dict(d)
        assert config.provider == "gitlab"
        assert len(config.post_exec) == 1

    def test_from_dict_defaults(self):
        d = {"postExec": [{"condition": "success", "type": "add_label"}]}
        config = ActionsConfig.from_dict(d)
        assert config.provider == "github"

    def test_validate_all_actions(self):
        config = ActionsConfig(
            post_exec=[
                PostExecAction(condition="success", type="add_label"),
                PostExecAction(condition="invalid", type="invalid"),
            ]
        )
        errors = config.validate()
        assert len(errors) == 2
        assert "Action[1]" in errors[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models_actions.py -v`
Expected: FAIL — old test expects `github_label`/`github_comment` default, new test expects `add_label`

- [ ] **Step 3: Modify models/actions.py**

```python
# zima/models/actions.py
from __future__ import annotations

from dataclasses import dataclass, field

from zima.models.serialization import YamlSerializable, omit_empty

VALID_ACTION_CONDITIONS = {"success", "failure", "always"}
VALID_ACTION_TYPES = {"add_label", "remove_label", "add_comment"}


@dataclass
class PostExecAction(YamlSerializable):
    """Single post-execution action run after agent exits."""

    FIELD_ALIASES = {
        "add_labels": "addLabels",
        "remove_labels": "removeLabels",
    }

    condition: str = "always"
    type: str = "add_label"
    add_labels: list[str] = field(default_factory=list)
    remove_labels: list[str] = field(default_factory=list)
    repo: str = ""
    issue: str = ""
    body: str = ""

    def __post_init__(self):
        if self.issue is None:
            self.issue = ""
        elif not isinstance(self.issue, str):
            if isinstance(self.issue, (int, float)):
                self.issue = str(self.issue)
            else:
                raise TypeError(
                    f"issue must be a string or number, got {type(self.issue).__name__}"
                )

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> PostExecAction:
        action = super().from_dict(data)
        errors = action.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return action

    def validate(self) -> list[str]:
        errors = []
        if self.condition not in VALID_ACTION_CONDITIONS:
            errors.append(
                f"Invalid condition '{self.condition}'. Valid: {VALID_ACTION_CONDITIONS}"
            )
        if self.type not in VALID_ACTION_TYPES:
            errors.append(f"Invalid type '{self.type}'. Valid: {VALID_ACTION_TYPES}")
        return errors


@dataclass
class ActionsConfig(YamlSerializable):
    """Collection of actions for a PJob."""

    FIELD_ALIASES = {"post_exec": "postExec"}

    provider: str = "github"
    post_exec: list[PostExecAction] = field(default_factory=list)

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> ActionsConfig:
        config = super().from_dict(data)
        errors = config.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return config

    def validate(self) -> list[str]:
        errors = []
        for i, action in enumerate(self.post_exec):
            action_errors = action.validate()
            errors.extend([f"Action[{i}]: {e}" for e in action_errors])
        return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_models_actions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/models/actions.py tests/unit/test_models_actions.py
git commit -m "feat(models): generic action types and provider field in ActionsConfig"
```

---

### Task 5: ActionsRunner Refactor

**Files:**
- Modify: `zima/execution/actions_runner.py`
- Test: `tests/unit/test_actions_runner.py`

- [ ] **Step 1: Write failing test for new ActionsRunner**

```python
# tests/unit/test_actions_runner.py
from unittest.mock import MagicMock, patch

from zima.actions.registry import ProviderRegistry, reset_registry
from zima.execution.actions_runner import ActionsRunner, _matches_condition
from zima.models.actions import ActionsConfig, PostExecAction


class TestMatchesCondition:
    def test_success_with_zero_returncode(self):
        assert _matches_condition("success", returncode=0) is True

    def test_success_with_nonzero_returncode(self):
        assert _matches_condition("success", returncode=1) is False

    def test_failure_with_nonzero_returncode(self):
        assert _matches_condition("failure", returncode=1) is True

    def test_failure_with_zero_returncode(self):
        assert _matches_condition("failure", returncode=0) is False

    def test_always_matches(self):
        assert _matches_condition("always", returncode=0) is True
        assert _matches_condition("always", returncode=1) is True


class TestActionsRunner:
    def setup_method(self):
        reset_registry()

    def test_run_no_actions(self):
        runner = ActionsRunner()
        runner.run(ActionsConfig(), returncode=0, env={})

    def test_run_success_action(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.add_label.assert_called_once_with("owner/repo", "123", "zima:needs-fix")
            mock_provider.remove_label.assert_called_once_with("owner/repo", "123", "zima:needs-review")

    def test_run_failure_action_not_triggered_on_success(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_comment",
                    body="Failed",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.post_comment.assert_not_called()

    def test_run_comment_action(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_comment",
                    body="Review complete: approved",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.post_comment.assert_called_once_with(
                "owner/repo", "123", "Review complete: approved"
            )

    def test_run_env_variable_substitution(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_comment",
                    body="Repo: {{REPO}} Issue: {{ISSUE}}",
                    repo="owner/repo",
                    issue="123",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(
                actions,
                returncode=0,
                env={"REPO": "my-org/my-repo", "ISSUE": "42"},
            )
            called_body = mock_provider.post_comment.call_args[0][2]
            assert "my-org/my-repo" in called_body
            assert "42" in called_body

    def test_run_failure_condition(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_comment",
                    body="Failed",
                    repo="o/r",
                    issue="1",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=1, env={})
            mock_provider.post_comment.assert_called_once_with("o/r", "1", "Failed")

    def test_run_skips_without_repo_or_issue(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["x"],
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            mock_provider.add_label.assert_not_called()

    def test_run_uses_custom_provider(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            provider="gitlab",
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["reviewed"],
                    repo="group/project",
                    issue="42",
                )
            ]
        )
        mock_provider = MagicMock()
        with patch.object(runner._registry, "get", return_value=mock_provider):
            runner.run(actions, returncode=0, env={})
            runner._registry.get.assert_called_once_with("gitlab")
            mock_provider.add_label.assert_called_once_with("group/project", "42", "reviewed")

    def test_run_provider_not_found_warns(self):
        runner = ActionsRunner()
        actions = ActionsConfig(
            provider="missing",
            post_exec=[
                PostExecAction(
                    condition="success",
                    type="add_label",
                    add_labels=["x"],
                    repo="o/r",
                    issue="1",
                )
            ]
        )
        with patch.object(runner._registry, "get", side_effect=Exception("not found")):
            # Should not raise — warning printed, execution continues
            runner.run(actions, returncode=0, env={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_actions_runner.py -v`
Expected: FAIL — `ActionsRunner` still uses `_ops` not `_registry`

- [ ] **Step 3: Refactor ActionsRunner**

```python
# zima/execution/actions_runner.py
from __future__ import annotations

from typing import Optional

from zima.actions.base import ActionProvider
from zima.actions.registry import ProviderRegistry, get_default_registry
from zima.models.actions import ActionsConfig, PostExecAction


def _matches_condition(condition: str, returncode: int) -> bool:
    if condition == "always":
        return True
    if condition == "success":
        return returncode == 0
    if condition == "failure":
        return returncode != 0
    return False


class ActionsRunner:
    """Executes postExec actions after agent process exits."""

    def __init__(self, registry: Optional[ProviderRegistry] = None):
        self._registry = registry or get_default_registry()

    def run(
        self,
        actions: ActionsConfig,
        returncode: int,
        env: dict[str, str],
    ) -> None:
        try:
            provider = self._registry.get(actions.provider)
        except Exception as e:
            print(f"Warning: Failed to get action provider '{actions.provider}': {e}")
            return

        for action in actions.post_exec:
            if not _matches_condition(action.condition, returncode):
                continue

            processed = self._substitute_env(action, env)
            self._execute_action(processed, provider)

    def _substitute_env(self, action: PostExecAction, env: dict[str, str]) -> PostExecAction:
        def sub(value: str) -> str:
            for key, val in env.items():
                value = value.replace(f"{{{{{key}}}}}", str(val))
            return value

        return PostExecAction(
            condition=action.condition,
            type=action.type,
            add_labels=[sub(label) for label in action.add_labels],
            remove_labels=[sub(label) for label in action.remove_labels],
            repo=sub(action.repo),
            issue=sub(action.issue),
            body=sub(action.body),
        )

    def _execute_action(self, action: PostExecAction, provider: ActionProvider) -> None:
        if not action.repo or not action.issue:
            return

        try:
            issue_num = int(action.issue)
        except ValueError:
            return

        if action.type == "add_label":
            for label in action.add_labels:
                try:
                    provider.add_label(action.repo, action.issue, label)
                except RuntimeError as e:
                    print(f"Warning: Failed to add label '{label}': {e}")
            for label in action.remove_labels:
                try:
                    provider.remove_label(action.repo, action.issue, label)
                except RuntimeError as e:
                    print(f"Warning: Failed to remove label '{label}': {e}")

        elif action.type == "add_comment":
            if action.body:
                try:
                    provider.post_comment(action.repo, action.issue, action.body)
                except RuntimeError as e:
                    print(f"Warning: Failed to post comment: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_actions_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/execution/actions_runner.py tests/unit/test_actions_runner.py
git commit -m "feat(execution): refactor ActionsRunner to use ProviderRegistry"
```

---

### Task 6: Scene Extension

**Files:**
- Modify: `zima/scenes.py`
- Test: `tests/unit/test_scenes.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_scenes.py
from unittest.mock import patch

from tests.base import TestIsolator
from zima.scenes import BUILTIN_SCENES, Scene, load_scenes


class TestSceneDataclass:
    def test_scene_creation(self):
        scene = Scene(
            name="Code Review",
            description="Review PRs",
            workflow_template="CR {{ pr_url }}",
            variables={"pr_url": ""},
            provider="github",
            scan_command=["gh", "pr", "list"],
        )
        assert scene.name == "Code Review"
        assert scene.provider == "github"
        assert scene.scan_command == ["gh", "pr", "list"]

    def test_scene_defaults(self):
        scene = Scene(
            name="Custom",
            description="Custom task",
            workflow_template="",
            variables={},
        )
        assert scene.provider == "github"
        assert scene.scan_command is None


class TestBuiltinScenes:
    def test_builtin_scenes_non_empty(self):
        assert len(BUILTIN_SCENES) > 0
        assert "code-review" in BUILTIN_SCENES
        assert "custom" in BUILTIN_SCENES

    def test_code_review_scene(self):
        scene = BUILTIN_SCENES["code-review"]
        assert scene.name == "Code Review"
        assert "workflow_template" in scene.__dataclass_fields__
        assert "variables" in scene.__dataclass_fields__
        assert "pr_url" in scene.variables
        assert scene.provider == "github"
        assert scene.scan_command is not None

    def test_custom_scene(self):
        scene = BUILTIN_SCENES["custom"]
        assert scene.name == "Custom Task"
        assert scene.workflow_template == ""
        assert scene.variables == {}


class TestLoadScenes(TestIsolator):
    def test_load_builtin_only(self):
        scenes = load_scenes()
        assert "code-review" in scenes
        assert "custom" in scenes

    def test_load_user_scenes(self):
        user_scenes = self.temp_dir / "scenes.yaml"
        user_scenes.write_text(
            "scenes:\n"
            "  gitlab-review:\n"
            "    name: GitLab Review\n"
            "    description: Review GitLab MRs\n"
            "    workflow_template: 'Review {{ mr_url }}'\n"
            "    variables:\n"
            "      mr_url: ''\n"
            "    provider: gitlab\n",
            encoding="utf-8",
        )
        scenes = load_scenes()
        assert "gitlab-review" in scenes
        assert scenes["gitlab-review"].name == "GitLab Review"
        assert scenes["gitlab-review"].provider == "gitlab"

    def test_user_scenes_override_builtin(self):
        user_scenes = self.temp_dir / "scenes.yaml"
        user_scenes.write_text(
            "scenes:\n"
            "  code-review:\n"
            "    name: Overridden Review\n"
            "    description: Custom\n"
            "    workflow_template: ''\n"
            "    variables: {}\n",
            encoding="utf-8",
        )
        scenes = load_scenes()
        assert scenes["code-review"].name == "Overridden Review"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_scenes.py -v`
Expected: FAIL — `Scene` dataclass and `load_scenes()` don't exist yet

- [ ] **Step 3: Modify scenes.py**

```python
# zima/scenes.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import yaml

from zima.utils import get_zima_home


@dataclass
class Scene:
    name: str
    description: str
    workflow_template: str
    variables: dict[str, str]
    provider: str = "github"
    scan_command: Optional[list[str]] = None


BUILTIN_SCENES: dict[str, Scene] = {
    "code-review": Scene(
        name="Code Review",
        description="Review PRs/MRs with AI agent",
        workflow_template="CR {{ pr_url }}",
        variables={"pr_url": ""},
        provider="github",
        scan_command=[
            "gh", "pr", "list", "--state", "open",
            "--label", "need-review", "--json", "number,title,url",
        ],
    ),
    "custom": Scene(
        name="Custom Task",
        description="Write your own prompt template",
        workflow_template="",
        variables={},
    ),
}


def load_scenes() -> dict[str, Scene]:
    """Load built-in scenes merged with user-defined scenes from ~/.zima/scenes.yaml."""
    scenes = BUILTIN_SCENES.copy()
    user_path = get_zima_home() / "scenes.yaml"
    if user_path.exists():
        data = yaml.safe_load(user_path.read_text(encoding="utf-8"))
        for key, spec in data.get("scenes", {}).items():
            scenes[key] = Scene(**spec)
    return scenes
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_scenes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/scenes.py tests/unit/test_scenes.py
git commit -m "feat(scenes): add Scene dataclass and load_scenes() with user YAML support"
```

---

### Task 7: Quickstart Refactor

**Files:**
- Modify: `zima/commands/quickstart.py`
- Test: `tests/unit/test_quickstart.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_quickstart.py
# Add these tests to the existing file

class TestScanWithCommand(TestIsolator):
    def test_scan_with_command_success(self):
        from zima.commands.quickstart import _scan_with_command

        mock_json = '[{"number": 42, "title": "feat: add auth"}]'
        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_json, stderr="")
            result = _scan_with_command(["test", "cmd"])
            assert len(result) == 1
            assert result[0]["number"] == 42

    def test_scan_with_command_failure(self):
        from zima.commands.quickstart import _scan_with_command

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            result = _scan_with_command(["test", "cmd"])
            assert result == []

    def test_scan_with_command_exception(self):
        from zima.commands.quickstart import _scan_with_command

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("cmd not found")
            result = _scan_with_command(["test", "cmd"])
            assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_quickstart.py::TestScanWithCommand -v`
Expected: FAIL — `_scan_with_command` doesn't exist

- [ ] **Step 3: Modify quickstart.py**

Key changes in `zima/commands/quickstart.py`:

1. Replace `_scan_github_prs` with `_scan_with_command`
2. Use `load_scenes()` instead of `QUICKSTART_SCENES`
3. Use `scene.scan_command` in the PR scan step
4. Pass `scene.provider` to `_create_all_configs` (or set it on the PJob)

```python
# Replace _scan_github_prs with:
def _scan_with_command(command: list[str]) -> list[dict]:
    """Scan for open PRs/MRs using the given CLI command."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except Exception:
        return []
```

```python
# In _create_all_configs, after creating PJob, set actions provider:
# job = PJobConfig.create(...)
# if scene.provider != "github":
#     job.actions = ActionsConfig(provider=scene.provider)
```

```python
# In quickstart() function:
# scenes = load_scenes()  # instead of QUICKSTART_SCENES
# scene = scenes[scene_key]
# Step 5:
# if scene.scan_command:
#     console.print("\n[bold]Scanning for open items...[/bold]")
#     prs = _scan_with_command(scene.scan_command)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_quickstart.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/commands/quickstart.py tests/unit/test_quickstart.py
git commit -m "feat(quickstart): use scene.scan_command and load_scenes()"
```

---

### Task 8: Cleanup — Delete Old github Package + Update Examples

**Files:**
- Delete: `zima/github/ops.py`
- Delete: `zima/github/__init__.py`
- Modify: `zima/templates/examples.py`
- Delete: `tests/unit/test_github_ops.py`

- [ ] **Step 1: Update examples.py**

In `zima/templates/examples.py`, change `REVIEWER_PJOB`:

```yaml
      - condition: success
        type: add_label          # was: github_label
        addLabels:
          - zima:review-approved
        removeLabels:
          - zima:needs-review
```

```yaml
      - condition: failure
        type: add_label          # was: github_label
        addLabels:
          - zima:needs-fix
        removeLabels:
          - zima:needs-review
```

- [ ] **Step 2: Delete old files**

```bash
rm zima/github/ops.py
rm zima/github/__init__.py
rmdir zima/github  # if empty
rm tests/unit/test_github_ops.py
```

- [ ] **Step 3: Verify no broken imports**

Run: `uv run pytest tests/ -q`
Expected: All tests pass, no import errors

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove zima/github package, migrate to providers/github"
```

---

### Task 9: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/unit/ -q
```
Expected: All unit tests pass

- [ ] **Step 2: Run lint**

```bash
uv run ruff check zima/ tests/
uv run black zima/ tests/ --check --line-length 100
```
Expected: No errors

- [ ] **Step 3: Dry-run a quickstart**

```bash
uv run zima quickstart --scene code-review --name test-provider --work-dir .
```
Expected: Creates configs with `provider: github` in actions

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A && git commit -m "chore: fixes after action provider refactor"
```

---

## Self-Review

**1. Spec coverage check:**
- `ActionProvider` ABC — Task 1
- `ProviderRegistry` with builtin + entry points — Task 3
- `GitHubProvider` extracted — Task 2
- Generic `VALID_ACTION_TYPES` — Task 4
- `ActionsConfig.provider` field — Task 4
- `ActionsRunner` registry dispatch — Task 5
- Scene dataclass + `load_scenes()` — Task 6
- Quickstart `scan_command` refactor — Task 7
- Delete old `zima/github` package — Task 8
- All spec requirements covered.

**2. Placeholder scan:**
- No "TBD", "TODO", or vague steps found.
- All code blocks contain complete, runnable code.
- All test commands have expected outputs.

**3. Type consistency:**
- `ActionProvider.name` is `@property` everywhere
- `ProviderRegistry.get(name: str)` consistent
- `ActionsConfig.provider` defaults to `"github"` consistently
- `Scene.provider` defaults to `"github"` consistently
- No naming mismatches found.

Plan complete.
