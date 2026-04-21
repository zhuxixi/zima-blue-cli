# Design: Move PJob Temp Dir to ZIMA_HOME

**Issue**: #47
**Date**: 2026-04-21
**Status**: Approved

## Problem

PJob execution temp directories are created under the system temp folder (`%TEMP%/zima-pjobs/` on Windows, `/tmp/zima-pjobs/` on Unix). This places temp files outside ZIMA_HOME, breaking the unified-directory mental model for users with custom ZIMA_HOME.

## Solution

Change `_create_temp_dir()` in `zima/execution/executor.py` to create temp directories under `ZIMA_HOME/temp/pjobs/` instead of `tempfile.gettempdir()`.

## Changes

### zima/execution/executor.py

1. Add `from zima.utils import get_zima_home` to imports
2. Remove `import tempfile` (unused elsewhere in file)
3. Replace `_create_temp_dir()` implementation:

```python
def _create_temp_dir(self, pjob_code: str, execution_id: str) -> Path:
    """Create temporary directory for execution under ZIMA_HOME."""
    temp_dir = get_zima_home() / "temp" / "pjobs" / f"{pjob_code}-{execution_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
```

### Data Layout

New directory added to ZIMA_HOME:

```
ZIMA_HOME/
├── configs/        # existing - YAML configs
├── daemon/         # existing - daemon runtime
├── history/        # existing - execution history
├── logs/           # existing - background logs
└── temp/
    └── pjobs/      # NEW - ephemeral execution artifacts
        └── <code>-<id>/
            └── prompt.md
```

### Documentation Updates

- Update `CLAUDE.md` Data Layout section to include `temp/pjobs/`

## Impact

- **Behavior**: Identical lifecycle (ephemeral by default, cleaned up after execution unless `keep_temp` or `save_to` is set)
- **Tests**: No changes needed. Tests use `isolated_zima_home` fixture which sets `ZIMA_HOME` to a temp dir — new location is automatically under test isolation
- **Backward compatibility**: No breaking change. Old temp dirs in system temp are not migrated (they're ephemeral by design)

## Out of Scope

- Cleanup command for orphaned temp dirs (tracked as #49)
- Migration of existing system temp dirs
