# Issue #84: preExec Renders Before Template — Fix Design

**Date**: 2026-05-03
**Issue**: https://github.com/zhuxixi/zima-blue-cli/issues/84
**Status**: Draft

## Problem

In `PJobExecutor.execute()`, Jinja2 template rendering (step 4, line 196) runs before `ActionsRunner.run_pre()` (step 9, line 220). The `scan_pr` preExec action discovers PR variables (`pr_url`, `pr_number`, `pr_title`, `pr_diff`) and injects them into `env_vars`, but the template has already been rendered with static Variable config values (typically empty strings).

Result: workflow templates like `{{pr_url}}` and `{{pr_diff}}` render as empty, making the REVIEWER_PJOB example non-functional.

## Approach

**Option A: Move preExec before template rendering.**

Rationale:
- Single render pass — no wasted work
- Clean mental model: "resolve all variables → render template → execute"
- Dynamic and static variables share the same Jinja2 namespace
- Minimal code change (~30 lines in executor.py + ~15 lines in actions_runner.py)

## Design

### 1. `run_pre()` Returns Variables Instead of Mutating Env

**Before** (`actions_runner.py`):
```python
def run_pre(self, actions, env) -> None:
    # Mutates env dict in-place
    env["pr_number"] = str(...)
    env["pr_url"] = ...
```

**After**:
```python
def run_pre(self, actions, env) -> dict[str, str]:
    """Execute preExec actions, return discovered variables."""
    discovered = {}
    for action in actions.pre_exec:
        if action.type == "scan_pr":
            # ... existing scan logic ...
            discovered["repo"] = repo
            discovered["pr_number"] = str(pr.get("number") or "")
            discovered["pr_title"] = pr.get("title") or ""
            discovered["pr_url"] = pr.get("url") or ""
            discovered["pr_diff"] = provider.fetch_diff(repo, discovered["pr_number"])
    return discovered
```

`env` parameter is kept for `{{VAR}}` substitution within action fields (e.g., `action.repo` containing `{{repo}}`).

### 2. New Execution Order in `executor.py`

```
1.  Load PJob
2.  Resolve ConfigBundle
3.  Create temp dir
4.  Resolve env vars            ← moved up (was step 5)
5.  Run preExec actions         ← moved up (was step 9)
6.  Merge discovered vars into bundle
7.  Render workflow template    ← moved down (was step 4)
8.  Build command
9.  Dry run check               ← after preExec, so dry-run sees real vars
10. Execute pre-hooks
11. Run main command
... (postExec unchanged)
```

### 3. Variable Merge Logic

PreExec-discovered variables are merged into `bundle.variable.values` before rendering:

```python
dynamic_vars = self._actions_runner.run_pre(pjob.spec.actions, env_vars)
if dynamic_vars and bundle.variable:
    bundle.variable.values.update(dynamic_vars)
elif dynamic_vars:
    # No Variable config exists — create ad-hoc values
    from zima.models.variable import VariableConfig
    bundle.variable = VariableConfig(values=dynamic_vars)
```

**Priority order** (highest to lowest):
1. Runtime overrides (`--set-var`)
2. PreExec discovered variables (NEW)
3. Variable config static values

This is achieved naturally because runtime overrides are applied via `apply_overrides()` in `_resolve_bundle()` (before preExec runs).

### 4. SkipAction Handling

`SkipAction` now fires after temp dir creation but before rendering. Cleanup still happens in the `finally` block as before — no change needed.

### 5. dry_run Behavior

dry_run now runs after preExec, so `--dry-run` shows the actual resolved template with PR data filled in. This is an improvement — previously dry-run showed empty variables.

### 6. postExec Compatibility

PostExec actions use `_substitute_env()` for `{{VAR}}` replacement in action fields (labels, comments, etc.). Since `run_pre()` no longer mutates `env_vars`, the caller must merge the returned dict into both `bundle.variable.values` (for Jinja2) and `env_vars` (for postExec substitution):

```python
dynamic_vars = self._actions_runner.run_pre(pjob.spec.actions, env_vars)
env_vars.update(dynamic_vars)  # For postExec {{VAR}} substitution
if dynamic_vars and bundle.variable:
    bundle.variable.values.update(dynamic_vars)
elif dynamic_vars:
    from zima.models.variable import VariableConfig
    bundle.variable = VariableConfig(values=dynamic_vars)
```

## Files Changed

| File | Change |
|------|--------|
| `zima/execution/executor.py` | Reorder steps 4→5→9 to 4→5→6→7; merge dynamic vars |
| `zima/execution/actions_runner.py` | `run_pre()` returns `dict[str, str]` instead of `None` |
| `zima/templates/examples.py` | No change needed — templates already use `{{pr_url}}` etc. |
| `tests/` | Update any test mocking `run_pre()` to return dict |

## Testing

- Unit test: `run_pre()` returns expected dict from `scan_pr`
- Unit test: `PJobExecutor.execute()` merges preExec vars into template rendering
- Integration test: REVIEWER_PJOB end-to-end with mocked GitHub provider
- Regression: existing postExec `{{VAR}}` substitution still works
- Regression: PJobs without preExec actions unchanged in behavior

## Edge Cases

1. **PJob has no actions** — `run_pre()` not called, behavior unchanged
2. **PJob has preExec but no scan_pr** — `run_pre()` returns empty dict, no merge
3. **Variable config doesn't exist** — ad-hoc VariableConfig created from discovered vars
4. **scan_pr finds no PRs** — `SkipAction` raised, execution returns SKIPPED status
5. **Variable config has static values for same keys** — preExec overwrites them (intentional: dynamic beats static)
