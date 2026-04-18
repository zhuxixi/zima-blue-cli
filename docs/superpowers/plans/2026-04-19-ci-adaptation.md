# CI Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace minimal ci.yml with tiered integration-test.yml + publish.yml, adapted from jfox.

**Architecture:** Delete existing ci.yml, create integration-test.yml (4 jobs: lint → test-fast → quality-gate + coverage) and publish.yml (OIDC PyPI publish). Add `slow` pytest marker. Switch from pip to uv.

**Tech Stack:** GitHub Actions, uv, pytest, ruff, black, PyPI OIDC

**Spec:** `docs/superpowers/specs/2026-04-19-ci-adaptation-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Delete | `.github/workflows/ci.yml` | Old minimal CI |
| Create | `.github/workflows/integration-test.yml` | Tiered test pipeline |
| Create | `.github/workflows/publish.yml` | PyPI auto-publish |
| Modify | `pyproject.toml` | Add pytest markers |
| Modify | `tests/conftest.py` | Add slow marker registration |

---

### Task 1: Add pytest markers to pyproject.toml and conftest.py

**Files:**
- Modify: `pyproject.toml:59-61`
- Modify: `tests/conftest.py:87-89`

- [ ] **Step 1: Add markers to pyproject.toml**

Add `markers` key after `addopts` in `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
markers = [
    "integration: mark test as integration test",
    "slow: mark test as slow (deselect with '-m \"not slow\"')",
]
```

- [ ] **Step 2: Add slow marker to conftest.py**

Replace the existing `pytest_configure` function:

```python
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "slow: mark test as slow (deselect with '-m \"not slow\"')")
```

- [ ] **Step 3: Verify locally**

Run: `pytest tests/ -m "not slow" -q`
Expected: All tests pass (no tests are marked slow yet).

Run: `pytest tests/ -m "not integration" -q`
Expected: Unit tests pass (integration tests skipped).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "chore: add slow and integration pytest markers for CI tiering"
```

---

### Task 2: Create integration-test.yml

**Files:**
- Create: `.github/workflows/integration-test.yml`

- [ ] **Step 1: Write integration-test.yml**

Create `.github/workflows/integration-test.yml` with this complete content:

```yaml
name: Integration Tests

on:
  push:
    branches: [main, master]
    paths:
      - 'zima/**'
      - 'tests/**'
      - 'pyproject.toml'
      - '.github/workflows/integration-test.yml'
  pull_request:
    branches: [main, master]
    paths:
      - 'zima/**'
      - 'tests/**'
      - 'pyproject.toml'
      - '.github/workflows/integration-test.yml'
  workflow_dispatch:
    inputs:
      test_type:
        description: 'Test type to run'
        required: true
        default: 'fast'
        type: choice
        options:
          - fast
          - full

env:
  PYTHONIOENCODING: utf-8
  PYTHONUTF8: 1

jobs:
  # ============ Lint ============
  lint:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Set up uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
          enable-cache: true

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Run ruff check
        run: uv run ruff check zima/ tests/

      - name: Run black check
        run: uv run black --check zima/ tests/ --line-length 100

  # ============ Fast Tests (PR + push) ============
  test-fast:
    runs-on: ${{ matrix.os }}
    needs: lint
    if: github.event_name != 'workflow_dispatch' || github.event.inputs.test_type == 'fast'
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ['3.13']

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Set up uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
          enable-cache: true

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Run tests (Ubuntu)
        if: runner.os == 'Linux'
        run: uv run pytest tests/ -m "not slow" --cov=zima --cov-report=xml --cov-fail-under=60 --tb=short -v
        timeout-minutes: 10

      - name: Run tests (Windows)
        if: runner.os == 'Windows'
        run: uv run pytest tests/ -m "not slow" --tb=short -v
        timeout-minutes: 20

      - name: Upload coverage data
        if: runner.os == 'Linux'
        uses: actions/upload-artifact@v4
        with:
          name: coverage-data
          path: coverage.xml
          retention-days: 1

  # ============ Full Tests (manual only) ============
  test-full:
    runs-on: ${{ matrix.os }}
    needs: lint
    if: github.event.inputs.test_type == 'full'
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ['3.13']

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Set up uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
          enable-cache: true

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Run full test suite
        run: uv run pytest tests/ -v --tb=short
        timeout-minutes: 20

  # ============ Quality Gate ============
  quality-gate:
    runs-on: ubuntu-latest
    needs: [lint, test-fast]
    if: always()
    steps:
      - name: Check all jobs passed
        run: |
          echo "lint: ${{ needs.lint.result }}"
          echo "test-fast: ${{ needs.test-fast.result }}"
          if [[ "${{ needs.lint.result }}" == "success" && "${{ needs.test-fast.result }}" == "success" ]]; then
            echo "Quality gate passed!"
            exit 0
          else
            echo "Quality gate FAILED!"
            exit 1
          fi

  # ============ Coverage Report ============
  coverage:
    runs-on: ubuntu-latest
    needs: [test-fast]
    if: always() && needs.test-fast.result == 'success' && github.event_name == 'pull_request'
    permissions:
      pull-requests: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Download coverage data
        uses: actions/download-artifact@v4
        with:
          name: coverage-data

      - name: Post coverage comment on PR
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python -c "
          import xml.etree.ElementTree as ET
          import subprocess

          tree = ET.parse('coverage.xml')
          root = tree.getroot()
          rate = float(root.attrib['line-rate'])
          lines_covered = int(root.attrib['lines-covered'])
          lines_valid = int(root.attrib['lines-valid'])

          rows = []
          for cls in root.iter('class'):
              name = cls.attrib['filename']
              r = float(cls.attrib['line-rate'])
              rows.append((name, r))
          rows.sort(key=lambda x: x[1])

          comment = '## Test Coverage\n\n'
          comment += '**Overall: {:.1f}%** ({}/{} lines)\n\n'.format(rate * 100, lines_covered, lines_valid)
          comment += '| Module | Coverage | Status |\n|--------|----------|--------|\n'
          for name, r in rows:
              icon = ':green_circle:' if r >= 0.8 else ':yellow_circle:' if r >= 0.5 else ':red_circle:'
              comment += '| {} | {:.1f}% | {} |\n'.format(name, r * 100, icon)

          pr = '${{ github.event.pull_request.number }}'
          subprocess.run(['gh', 'pr', 'comment', pr, '--body', comment])
          "
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/integration-test.yml
git commit -m "ci: add tiered integration-test workflow (replaces ci.yml)"
```

---

### Task 3: Create publish.yml

**Files:**
- Create: `.github/workflows/publish.yml`

- [ ] **Step 1: Write publish.yml**

Create `.github/workflows/publish.yml` with this complete content:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  pypi-publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Build package
        run: uv build

      - name: Publish to PyPI
        run: uv publish
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "ci: add PyPI publish workflow with OIDC"
```

---

### Task 4: Delete old ci.yml and verify

**Files:**
- Delete: `.github/workflows/ci.yml`

- [ ] **Step 1: Delete old ci.yml**

```bash
git rm .github/workflows/ci.yml
```

- [ ] **Step 2: Verify local tests still pass**

Run: `pytest tests/ -m "not slow" -q`
Expected: All tests pass.

Run: `ruff check zima/ tests/`
Expected: No errors.

Run: `black --check zima/ tests/ --line-length 100`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git commit -m "ci: remove old ci.yml (replaced by integration-test.yml)"
```

---

### Task 5: Push and verify CI runs

- [ ] **Step 1: Push to remote**

```bash
git push origin main
```

- [ ] **Step 2: Verify workflow runs**

Run: `gh run list --workflow=integration-test.yml --limit 1`
Expected: Shows a new run triggered by the push.

Run: `gh run watch` (or check GitHub Actions UI)
Expected: lint + test-fast + quality-gate all pass.

- [ ] **Step 3: Verify old workflow is gone**

Confirm `.github/workflows/` only contains `integration-test.yml` and `publish.yml`. The old "CI" workflow should no longer appear in GitHub Actions.
