# CI Adaptation Design (Issue #24)

**Date:** 2026-04-19
**Status:** Approved
**Approach:** Full jfox-style adaptation (Approach A)

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Repo visibility | Make public after CI is done | Design CI to be efficient with Actions minutes first |
| Package manager | Switch to uv | Faster installs, proven in jfox |
| Python versions | 3.13 only | Simplest, matches current practice. `requires-python >= 3.10` stays in pyproject.toml |
| PyPI publish | Add now (OIDC) | Ready when needed, 15-line workflow |
| Coverage gate | 60% + PR comment | Informational only, no threshold change |
| CI approach | Full jfox 4-tier adaptation | Proven pattern, room for growth, saves minutes while private |

## File Changes

### Delete
- `.github/workflows/ci.yml`

### Create
- `.github/workflows/integration-test.yml`
- `.github/workflows/publish.yml`

### Modify
- `pyproject.toml` — add `slow` marker definition
- `tests/conftest.py` — add `slow` marker registration

## integration-test.yml

### Triggers

- `push` to `main`/`master`
- `pull_request` to `main`/`master`
- `workflow_dispatch` with `test_type` choice: `fast` | `full`
- Path filter: `zima/**`, `tests/**`, `pyproject.toml`, `.github/workflows/*`

### Environment Variables

```yaml
env:
  PYTHONIOENCODING: utf-8
  PYTHONUTF8: 1
```

### Jobs

#### lint

- **Runner:** ubuntu-latest
- **Trigger:** always
- **Steps:** checkout → setup-python 3.13 → setup-uv (cached) → `uv sync --extra dev` → `uv run ruff check zima/ tests/` → `uv run black --check zima/ tests/ --line-length 100`

#### test-fast

- **Runner:** `[ubuntu-latest, windows-latest]` matrix
- **Trigger:** always (after lint passes)
- **Condition:** `github.event_name != 'workflow_dispatch' || github.event.inputs.test_type == 'fast'`
- **Python:** 3.13
- **Steps:** checkout → setup-python → setup-uv (cached) → `uv sync --extra dev` → run pytest
- **Test command:**
  ```bash
  # ubuntu: with coverage
  uv run pytest tests/ -m "not slow" --cov=zima --cov-report=xml --cov-fail-under=60 --tb=short -v
  # windows: without coverage (just test)
  uv run pytest tests/ -m "not slow" --tb=short -v
  ```
- **Timeouts:** ubuntu 10min, windows 20min
- **Artifacts:** upload coverage.xml from ubuntu run

#### test-full (manual only)

- **Runner:** `[ubuntu-latest, windows-latest, macos-latest]` matrix
- **Trigger:** `workflow_dispatch` with `test_type == 'full'`
- **Python:** 3.13
- **Steps:** same as test-fast but no coverage threshold gate, all platforms
- **Timeout:** 20min all platforms

#### quality-gate

- **Runner:** ubuntu-latest
- **Depends on:** lint + test-fast
- **Condition:** `always()` (runs even if dependencies fail)
- **Steps:** assert lint.result == success AND test-fast.result == success

#### coverage

- **Runner:** ubuntu-latest
- **Depends on:** test-fast
- **Condition:** `always() && needs.test-fast.result == 'success' && github.event_name == 'pull_request'`
- **Permissions:** `pull-requests: write`
- **Steps:**
  1. Checkout
  2. Download coverage-data artifact
  3. Run Python script to parse coverage.xml and post PR comment
- **Comment format:**
  ```
  ## Test Coverage

  **Overall: XX.X%** (N/M lines)

  | Module | Coverage | Status |
  |--------|----------|--------|
  | zima/cli.py | 85.2% | 🟢 |
  | zima/config/manager.py | 71.0% | 🟡 |
  | zima/core/runner.py | 42.1% | 🔴 |
  ```
- **Thresholds:** >= 80% green, >= 50% yellow, < 50% red

## publish.yml

- **Trigger:** `release: [published]`
- **Environment:** `pypi`
- **Permissions:** `id-token: write` (OIDC)
- **Steps:** checkout → setup-uv → `uv build` → `uv publish`
- **One-time setup:** Configure PyPI Trusted Publisher for `zhuxixi/zima-blue-cli`, environment `pypi`, workflow `publish.yml`

## pyproject.toml Changes

Add to `[tool.pytest.ini_options]`:

```toml
markers = [
    "integration: mark test as integration test",
    "slow: mark test as slow (deselect with '-m \"not slow\"')",
]
```

## tests/conftest.py Changes

Add `slow` marker to `pytest_configure`:

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "slow: mark test as slow (deselect with '-m \"not slow\"')")
```

No existing tests are modified. The `slow` marker is for future use — CI's `-m "not slow"` passes all current tests.

## Task Breakdown

1. Delete `.github/workflows/ci.yml`
2. Create `.github/workflows/integration-test.yml`
3. Create `.github/workflows/publish.yml`
4. Update `pyproject.toml` with marker definitions
5. Update `tests/conftest.py` with slow marker registration
6. Verify locally: `pytest -m "not slow"` passes
7. Verify locally: `pytest -m "not integration"` passes
8. Push and verify CI runs correctly
