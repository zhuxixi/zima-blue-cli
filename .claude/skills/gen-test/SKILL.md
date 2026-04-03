---
name: gen-test
description: Generate pytest unit tests for a given source module or function
---

# Generate Tests

Generate pytest unit tests for a target Python module or function.

## Usage

- `/gen-test zima/models/agent.py` — generate tests for the agent model
- `/gen-test zima/config/manager.py::ConfigManager.save_config` — generate tests for a specific method

## Instructions

1. **Read the target source file** to understand its public API, classes, and functions.

2. **Determine the test file path** using the project convention:
   - Source: `zima/foo/bar.py` -> Test: `tests/unit/test_foo_bar.py` (flattened with underscores)
   - But check existing naming first: `zima/models/agent.py` -> `tests/unit/test_models_agent.py`
   - If the test file already exists, **append** new test classes/methods rather than overwriting.

3. **Generate tests** following these conventions:
   - Test classes inherit from `TestIsolator` (from `tests/base.py`) when filesystem/config isolation is needed
   - Use `monkeypatch` for `ZIMA_HOME` isolation (handled by `TestIsolator`)
   - Use fixtures from `tests/conftest.py` (`config_manager`, `cli_runner`, `unique_code`, `isolated_zima_home`)
   - Google-style docstrings on test classes
   - Cover: happy path, edge cases, error handling
   - Use `pytest.raises` for expected exceptions
   - Use `tmp_path` or `TestIsolator.get_test_path()` for temp files

4. **Example test structure**:

```python
"""Tests for <module description>."""

import pytest

from zima.<module> import <TargetClass>
from tests.base import TestIsolator


class Test<TargetClass>(TestIsolator):
    """Tests for <TargetClass>."""

    def test_<behavior>_success(self):
        """Test <behavior> with valid input."""
        # arrange
        ...
        # act
        result = ...
        # assert
        assert result == expected

    def test_<behavior>_invalid_input(self):
        """Test <behavior> raises on invalid input."""
        with pytest.raises(ValueError):
            ...
```

5. **After generating**, run the test to verify it passes:
   ```bash
   pytest <test_file> -v
   ```

6. **Report** the test file path, number of tests generated, and pass/fail status.
