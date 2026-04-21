# CLI `--version` Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--version` / `-v` flag to the `zima` CLI that prints the package version from `pyproject.toml`.

**Architecture:** Replace hardcoded `__version__` with `importlib.metadata` lookup. Wire an eager Typer Option into the existing `@app.callback()` to provide `--version` across all subcommands.

**Tech Stack:** Python 3.10+, Typer, importlib.metadata (stdlib)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `zima/__init__.py` | Replace `__version__` with `get_version()` using `importlib.metadata` |
| Modify | `zima/cli.py` | Add `_version_callback` and eager `--version` / `-v` option to `main()` |
| Create | `tests/unit/test_version.py` | Unit test for `get_version()` |
| Modify | `tests/integration/test_cli_version.py` (new file) | Integration tests for `zima --version` and `zima -v` via CliRunner |

---

### Task 1: Add `get_version()` to `zima/__init__.py`

**Files:**
- Modify: `zima/__init__.py` (full rewrite — only 3 lines currently)

- [ ] **Step 1: Write the failing unit test**

Create `tests/unit/test_version.py`:

```python
"""Unit tests for version helper."""

from zima import get_version


class TestGetVersion:
    def test_returns_non_empty_string(self):
        result = get_version()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_valid_semver_format(self):
        result = get_version()
        # Either a semver like "0.1.1" or "unknown" for uninstalled package
        parts = result.split(".")
        if result != "unknown":
            assert len(parts) >= 2, f"Expected semver, got: {result}"

    def test_fallback_on_missing_package(self, monkeypatch):
        """Verify 'unknown' fallback when package metadata is not found."""
        import importlib.metadata

        def _raise(name):
            raise importlib.metadata.PackageNotFoundError(name)

        monkeypatch.setattr(importlib.metadata, "version", _raise)
        assert get_version() == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_version.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_version' from 'zima'`

- [ ] **Step 3: Write the implementation**

Replace `zima/__init__.py` entirely with:

```python
"""Zima Blue CLI - Personal Agent Orchestration Platform"""

from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    """Get package version from pyproject.toml metadata.

    Returns:
        Version string (e.g. "0.1.1"), or "unknown" if package is not installed.
    """
    try:
        return version("zima-blue-cli")
    except PackageNotFoundError:
        return "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_version.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/__init__.py tests/unit/test_version.py
git commit -m "feat: replace __version__ with importlib.metadata get_version()"
```

---

### Task 2: Wire `--version` flag into `zima/cli.py`

**Files:**
- Modify: `zima/cli.py:1-44`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_cli_version.py`:

```python
"""Integration tests for zima --version flag."""

from typer.testing import CliRunner

from zima.cli import app

runner = CliRunner()


class TestCLIVersion:
    def test_version_long_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "zima" in result.output

    def test_version_short_flag(self):
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "zima" in result.output

    def test_version_output_format(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        # Should be "zima X.Y.Z" or "zima unknown"
        output = result.output.strip()
        assert output.startswith("zima "), f"Unexpected output: {output}"

    def test_version_in_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--version" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_cli_version.py -v`
Expected: FAIL — `Error: No such option: --version`

- [ ] **Step 3: Write the implementation**

Replace `zima/cli.py` entirely with:

```python
"""ZimaBlue CLI - v2 Simplified"""

from __future__ import annotations

from zima.utils import setup_windows_utf8

setup_windows_utf8()

import typer

from zima import get_version
from zima.commands import agent as agent_cmd
from zima.commands import daemon as daemon_cmd
from zima.commands import env as env_cmd
from zima.commands import pjob as pjob_cmd
from zima.commands import pmg as pmg_cmd
from zima.commands import schedule as schedule_cmd
from zima.commands import variable as variable_cmd
from zima.commands import workflow as workflow_cmd

app = typer.Typer(
    name="zima",
    help="ZimaBlue CLI - Agent Runner",
    add_completion=False,
)


def _version_callback(value: bool):
    if value:
        typer.echo(f"zima {get_version()}")
        raise typer.Exit()


# Register subcommands
app.add_typer(agent_cmd.app, name="agent")
app.add_typer(workflow_cmd.app, name="workflow")
app.add_typer(variable_cmd.app, name="variable")
app.add_typer(env_cmd.app, name="env")
app.add_typer(pmg_cmd.app, name="pmg")
app.add_typer(pjob_cmd.app, name="pjob")
app.add_typer(schedule_cmd.app, name="schedule")
app.add_typer(daemon_cmd.app, name="daemon")


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """ZimaBlue CLI - Agent Runner"""


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_cli_version.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add zima/cli.py tests/integration/test_cli_version.py
git commit -m "feat: add --version/-v flag to zima CLI"
```

---

### Task 3: Verify full test suite and lint

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `pytest --cov=zima --cov-fail-under=60`
Expected: All tests pass, coverage >= 60%

- [ ] **Step 2: Run linter and formatter check**

Run: `ruff check zima/ tests/ && black zima/ tests/ --check --line-length 100`
Expected: No errors

- [ ] **Step 3: Manual smoke test**

Run: `zima --version`
Expected: `zima 0.1.1`

Run: `zima -v`
Expected: `zima 0.1.1`

Run: `zima --help`
Expected: `--version` option visible in help text

- [ ] **Step 4: Final commit if any formatting fixes needed**

```bash
git add -u
git commit -m "style: fix lint/format for version flag changes"
```
