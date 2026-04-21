# Design: CLI `--version` Flag

**Date:** 2026-04-21
**Issue:** #40 — [Bug] CLI missing --version option
**Status:** Approved

## Problem

- `zima --version` errors with "No such option: --version"
- `__version__` in `zima/__init__.py` (0.1.0) is out of sync with `pyproject.toml` (0.1.1)

## Solution

### Version Source

**Single source of truth:** `pyproject.toml` via `importlib.metadata`.

Remove the hardcoded `__version__` from `__init__.py`. Replace with a `get_version()` helper that reads from package metadata at runtime. This eliminates manual sync drift permanently.

### Approach

**Typer eager Option in `@app.callback()`.** This is the idiomatic Typer pattern:

- `--version` and `-v` flags
- `is_eager=True` so it runs before any subcommand validation
- Shows in `--help` output automatically
- Note: `--version` is available at top-level only; Typer sub-apps registered via `add_typer` do not inherit callback options

## Changes

### `zima/__init__.py`

Remove `__version__ = "0.1.0"`. Add:

```python
from importlib.metadata import version, PackageNotFoundError

def get_version() -> str:
    try:
        return version("zima-blue-cli")
    except PackageNotFoundError:
        return "unknown"
```

### `zima/cli.py`

Add version callback and eager option:

```python
from zima import get_version

def _version_callback(value: bool):
    if value:
        typer.echo(f"zima {get_version()}")
        raise typer.Exit()

@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """ZimaBlue CLI - Agent Runner"""
```

## Behavior

| Command | Output | Exit Code |
|---------|--------|-----------|
| `zima --version` | `zima 0.1.1` | 0 |
| `zima -v` | `zima 0.1.1` | 0 |
| `zima --help` | Shows `--version` in options | 0 |
| `zima agent --version` | Not supported (Typer sub-app limitation) | — |
| Uninstalled/dev mode | `zima unknown` | 0 |

## Testing

- **Unit:** `get_version()` returns a non-empty string
- **Integration:** `CliRunner.invoke(app, ["--version"])` exits 0, output matches `zima X.Y.Z`
- **Integration:** `CliRunner.invoke(app, ["-v"])` same behavior as `--version`
