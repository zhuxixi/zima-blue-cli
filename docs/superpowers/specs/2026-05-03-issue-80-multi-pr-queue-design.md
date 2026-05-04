# Issue #80: Multi-PR Queue for scan_pr

> **Status:** Approved
> **Date:** 2026-05-03
> **Issue:** [feat: multi-PR queue for scan_pr — pick next instead of always-first](https://github.com/zhuxixi/zima-blue-cli/issues/80)

## Problem

`scan_pr` in `actions_runner.py:149` hardcodes `pr = prs[0]`, always picking the first PR from `gh pr list`. When multiple PRs carry the target label (e.g. `zima:needs-review`):

1. **Only the first PR gets reviewed** — all others are silently ignored
2. **Starvation risk** — if the first PR's agent fails and its label isn't removed, subsequent PRs are never picked
3. **One PJob per cycle** — daemon scheduling runs one PJob instance per trigger, so N PRs need N cycles minimum, but the same failed PR may be picked repeatedly

## Design Decision

Use **time-based skip logic** backed by existing `ExecutionHistory` data. No new files or entities.

**Why not a separate skip-log file:** The execution history already stores per-PJob records with status and timestamps. Adding a `scan_pr_result` field to the existing `ExecutionRecord` reuses this infrastructure instead of introducing a new data path.

**Why time-based instead of cycle-based:** Cycle counting only works in daemon mode. Time-based skip (90 minutes) works for both daemon-triggered and manual (`zima pjob run`) invocations.

## Changes

### 1. Extend `ExecutionRecord` with `scan_pr_result`

**File:** `zima/execution/history.py`

Add an optional field to `ExecutionRecord`:

```python
scan_pr_result: Optional[dict] = None  # {"repo": "owner/repo", "pr_number": "42"}
```

- Included in `to_dict()` and `from_dict()` for serialization
- Backward-compatible: existing records without this field deserialize as `None`
- Added to `_STATE_FILE_FIELDS` list for runtime state persistence

### 2. Add `get_recent_scan_pr_failures()` to `ExecutionHistory`

**File:** `zima/execution/history.py`

```python
def get_recent_scan_pr_failures(self, pjob_code: str, within_minutes: int = 90) -> list[dict]:
```

Returns execution records where:
- `status` is one of `("failed", "timeout", "cancelled", "dead")`
- `scan_pr_result` is not `None`
- `started_at` is within the last `within_minutes` minutes

### 3. PR Selection Logic in `ActionsRunner`

**File:** `zima/execution/actions_runner.py`

**Constructor change:** Add optional parameters:

```python
def __init__(self, registry=None, history=None, pjob_code=None):
    self._registry = registry or get_default_registry()
    self._history = history      # Optional[ExecutionHistory]
    self._pjob_code = pjob_code  # Optional[str]
```

**Selection algorithm** (replaces `pr = prs[0]`):

1. If `self._history` and `self._pjob_code` are set, call `get_recent_scan_pr_failures(pjob_code, 90)`
2. Build a skip-set: `{(r["scan_pr_result"]["repo"], r["scan_pr_result"]["pr_number"]) for r in failures}`
3. Iterate through the PR list, return the first PR whose `(repo, pr_number)` is NOT in the skip-set
4. If no history is available, fall back to `prs[0]` (current behavior)
5. If all PRs are in the skip-set, raise `SkipAction("All PRs recently attempted, skipping")`

### 4. Executor Wiring

**File:** `zima/execution/executor.py`

Two changes in the `execute()` method:

**Before `run_pre()`:** Pass history and pjob_code to the ActionsRunner at executor construction time. `PJobExecutor.__init__` already creates `self._actions_runner`; add `self._history` and `pjob_code` as constructor arguments to `ActionsRunner`.

**After `run_pre()` succeeds:** Extract scan_pr_result and attach to the execution record:

```python
scan_pr_result = None
if "pr_number" in dynamic_vars:
    scan_pr_result = {"repo": dynamic_vars.get("repo", ""), "pr_number": dynamic_vars["pr_number"]}
# Store on result for history persistence
result.scan_pr_result = scan_pr_result
```

The executor's history-writing path already calls `ExecutionRecord.from_result(result)`, so `ExecutionRecord.from_result` needs to copy `scan_pr_result` from the result object.

## Files Changed

| File | Change |
|------|--------|
| `zima/execution/history.py` | Add `scan_pr_result` field to `ExecutionRecord`, add `get_recent_scan_pr_failures()` method |
| `zima/execution/actions_runner.py` | Add history/pjob_code params to `__init__`, replace `prs[0]` with skip-aware selection |
| `zima/execution/executor.py` | Wire history and pjob_code into ActionsRunner, persist scan_pr_result to record |

## Testing

| Test File | Tests |
|-----------|-------|
| `tests/unit/test_history.py` | `scan_pr_result` serialization, `get_recent_scan_pr_failures` filtering by status/time |
| `tests/unit/test_actions_runner.py` | Skip logic: recently-failed PR skipped, no-history fallback to `prs[0]`, all-skipped raises `SkipAction`, mixed eligible/skipped selects correct PR |

No integration test changes needed. The existing `test_preexec_vars_flow_to_template_and_postexec` covers the happy path.

## Scope Exclusions

- **Priority sorting** (e.g. `zima:urgent` label first) — not needed per user decision
- **Batch spawning** (multiple PJob instances per cycle) — out of scope, one PR per cycle is fine
- **Skip-log file** — reusing execution history instead
