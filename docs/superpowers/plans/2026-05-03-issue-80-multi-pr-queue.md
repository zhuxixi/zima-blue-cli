# Multi-PR Queue for scan_pr Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `prs[0]` in scan_pr with skip-aware PR selection that avoids recently-failed PRs for 90 minutes.

**Architecture:** Extend `ExecutionRecord` with a `scan_pr_result` field to persist which PR was processed per execution. Add a `get_recent_scan_pr_failures()` query method to `ExecutionHistory`. Update `ActionsRunner.run_pre()` to skip PRs that failed within the last 90 minutes, falling back to `prs[0]` when no history is available. Wire the executor to pass history context to the runner and persist `scan_pr_result` to execution records.

**Tech Stack:** Python 3.10+, dataclasses, pytest with `unittest.mock`

---

### Task 1: Add `scan_pr_result` field to `ExecutionRecord`

**Files:**
- Modify: `zima/execution/history.py:71-161` (ExecutionRecord class)
- Test: `tests/unit/test_execution_history.py`

- [ ] **Step 1: Write the failing test for `scan_pr_result` serialization**

Add to `tests/unit/test_execution_history.py`, inside `TestExecutionHistoryWriteAndRead` class:

```python
def test_scan_pr_result_round_trip(self):
    """scan_pr_result is persisted and loaded correctly."""
    from zima.execution.history import ExecutionRecord

    record = ExecutionRecord(
        execution_id="a1",
        pjob_code="test-pjob",
        status="failed",
        returncode=1,
        scan_pr_result={"repo": "owner/repo", "pr_number": "42"},
        started_at="2026-05-03T10:00:00+08:00",
    )
    data = record.to_dict()
    assert data["scan_pr_result"] == {"repo": "owner/repo", "pr_number": "42"}

    restored = ExecutionRecord.from_dict(data)
    assert restored.scan_pr_result == {"repo": "owner/repo", "pr_number": "42"}

def test_scan_pr_result_defaults_to_none(self):
    """Existing records without scan_pr_result deserialize as None."""
    from zima.execution.history import ExecutionRecord

    record = ExecutionRecord.from_dict({
        "execution_id": "a1",
        "pjob_code": "test-pjob",
        "status": "success",
        "returncode": 0,
    })
    assert record.scan_pr_result is None

def test_scan_pr_result_excluded_when_none(self):
    """to_dict omits scan_pr_result when it is None."""
    from zima.execution.history import ExecutionRecord

    record = ExecutionRecord(
        execution_id="a1",
        pjob_code="test-pjob",
        status="success",
        returncode=0,
    )
    data = record.to_dict()
    assert "scan_pr_result" not in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_execution_history.py::TestExecutionHistoryWriteAndRead::test_scan_pr_result_round_trip -v`
Expected: FAIL — `ExecutionRecord.__init__` got an unexpected keyword argument `scan_pr_result`

- [ ] **Step 3: Implement `scan_pr_result` field**

In `zima/execution/history.py`, add the field to `ExecutionRecord` after `pid`:

```python
pid: Optional[int] = None
scan_pr_result: Optional[dict] = None
```

Add to `to_dict()` method, after the `"pid"` entry:

```python
"pid": self.pid,
"scan_pr_result": self.scan_pr_result,
```

Replace with conditional output — omit when `None`:

```python
"pid": self.pid,
**({"scan_pr_result": self.scan_pr_result} if self.scan_pr_result is not None else {}),
```

Add to `from_dict()` method, after `pid=data.get("pid"),`:

```python
pid=data.get("pid"),
scan_pr_result=data.get("scan_pr_result"),
```

Add to `from_result()` method, after `pid=result.pid,`:

```python
pid=result.pid,
scan_pr_result=getattr(result, "scan_pr_result", None),
```

Add `"scan_pr_result"` to the `_STATE_FILE_FIELDS` list:

```python
_STATE_FILE_FIELDS = [
    "execution_id",
    "pjob_code",
    "status",
    "pid",
    "command",
    "started_at",
    "finished_at",
    "duration_seconds",
    "returncode",
    "stdout_preview",
    "stderr_preview",
    "error_detail",
    "log_path",
    "agent",
    "workflow",
    "scan_pr_result",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_execution_history.py::TestExecutionHistoryWriteAndRead::test_scan_pr_result_round_trip tests/unit/test_execution_history.py::TestExecutionHistoryWriteAndRead::test_scan_pr_result_defaults_to_none tests/unit/test_execution_history.py::TestExecutionHistoryWriteAndRead::test_scan_pr_result_excluded_when_none -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/execution/history.py tests/unit/test_execution_history.py
git commit -m "feat(history): add scan_pr_result field to ExecutionRecord"
```

---

### Task 2: Add `get_recent_scan_pr_failures()` to `ExecutionHistory`

**Files:**
- Modify: `zima/execution/history.py` (ExecutionHistory class)
- Test: `tests/unit/test_execution_history.py`

- [ ] **Step 1: Write the failing test**

Add a new test class to `tests/unit/test_execution_history.py`:

```python
class TestGetRecentScanPrFailures:
    @pytest.fixture(autouse=True)
    def setup(self, isolated_zima_home):
        self.history = ExecutionHistory()
        self.pjob_code = "reviewer-kimi"

    def _write_record(self, exec_id, status, scan_pr_result, started_at, minutes_ago=0):
        """Helper to write an execution record."""
        from datetime import datetime, timezone, timedelta

        if started_at is None:
            ts = datetime.now(timezone.utc).astimezone() - timedelta(minutes=minutes_ago)
            started_at = ts.isoformat()
        self.history.write_runtime_state(
            self.pjob_code,
            exec_id,
            {
                "execution_id": exec_id,
                "pjob_code": self.pjob_code,
                "status": status,
                "returncode": 1,
                "started_at": started_at,
                "scan_pr_result": scan_pr_result,
            },
        )

    def test_returns_recently_failed_prs(self):
        self._write_record("a1", "failed", {"repo": "o/r", "pr_number": "10"}, None, minutes_ago=5)
        self._write_record("a2", "failed", {"repo": "o/r", "pr_number": "20"}, None, minutes_ago=30)

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 2
        pr_numbers = {r["scan_pr_result"]["pr_number"] for r in results}
        assert pr_numbers == {"10", "20"}

    def test_excludes_prs_outside_time_window(self):
        self._write_record("a1", "failed", {"repo": "o/r", "pr_number": "10"}, None, minutes_ago=5)
        self._write_record("a2", "failed", {"repo": "o/r", "pr_number": "20"}, None, minutes_ago=120)

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 1
        assert results[0]["scan_pr_result"]["pr_number"] == "10"

    def test_excludes_success_and_running_status(self):
        self._write_record("a1", "success", {"repo": "o/r", "pr_number": "10"}, None, minutes_ago=5)
        self._write_record("a2", "running", {"repo": "o/r", "pr_number": "20"}, None, minutes_ago=5)

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 0

    def test_excludes_records_without_scan_pr_result(self):
        self._write_record("a1", "failed", None, None, minutes_ago=5)

        results = self.history.get_recent_scan_pr_failures(self.pjob_code, within_minutes=90)
        assert len(results) == 0

    def test_returns_empty_for_nonexistent_pjob(self):
        results = self.history.get_recent_scan_pr_failures("nonexistent", within_minutes=90)
        assert results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_execution_history.py::TestGetRecentScanPrFailures -v`
Expected: FAIL — `AttributeError: 'ExecutionHistory' object has no attribute 'get_recent_scan_pr_failures'`

- [ ] **Step 3: Implement `get_recent_scan_pr_failures()`**

Add to `ExecutionHistory` class in `zima/execution/history.py`, after the `get_stats()` method:

```python
def get_recent_scan_pr_failures(self, pjob_code: str, within_minutes: int = 90) -> list[dict]:
    """Return recent failed executions that have scan_pr_result.

    Used by scan_pr skip logic to avoid re-picking recently-failed PRs.

    Args:
        pjob_code: PJob code to query.
        within_minutes: Time window in minutes. Only failures within this
            window are returned.

    Returns:
        List of execution state dicts with status in
        ("failed", "timeout", "cancelled", "dead") and a non-None
        scan_pr_result, started within the given time window.
    """
    from datetime import datetime, timezone, timedelta

    failed_statuses = {"failed", "timeout", "cancelled", "dead"}
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)

    results: list[dict] = []
    for record in self.list_executions(pjob_code):
        if record.get("status") not in failed_statuses:
            continue
        spr = record.get("scan_pr_result")
        if spr is None:
            continue
        started = record.get("started_at", "")
        if not started:
            continue
        try:
            started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            if started_dt.tzinfo is None:
                started_dt = started_dt.replace(tzinfo=timezone.utc)
            if started_dt >= cutoff:
                results.append(record)
        except (ValueError, TypeError):
            continue

    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_execution_history.py::TestGetRecentScanPrFailures -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zima/execution/history.py tests/unit/test_execution_history.py
git commit -m "feat(history): add get_recent_scan_pr_failures query method"
```

---

### Task 3: Add skip-aware PR selection to `ActionsRunner`

**Files:**
- Modify: `zima/execution/actions_runner.py:38-158` (ActionsRunner class)
- Test: `tests/unit/test_actions_runner.py`

- [ ] **Step 1: Write the failing tests**

Add a new test class to `tests/unit/test_actions_runner.py`:

```python
class TestActionsRunnerPreExecSkipLogic:
    def _make_actions(self, repo="owner/repo", label="zima:needs-review"):
        from zima.models.actions import PreExecAction

        return ActionsConfig(
            pre_exec=[PreExecAction(type="scan_pr", repo=repo, label=label)]
        )

    def test_no_history_falls_back_to_first_pr(self):
        """Without history, picks the first PR (prs[0] behavior)."""
        runner = ActionsRunner()
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
            {"number": "20", "title": "PR 20", "url": "url20"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "10"

    def test_skips_recently_failed_pr(self):
        """Skips a PR that failed within the time window."""
        mock_history = MagicMock()
        mock_history.get_recent_scan_pr_failures.return_value = [
            {"scan_pr_result": {"repo": "owner/repo", "pr_number": "10"}}
        ]
        runner = ActionsRunner(history=mock_history, pjob_code="reviewer")
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
            {"number": "20", "title": "PR 20", "url": "url20"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "20"
        mock_history.get_recent_scan_pr_failures.assert_called_once_with("reviewer", 90)

    def test_skips_all_raises_skip_action(self):
        """Raises SkipAction when all PRs were recently attempted."""
        mock_history = MagicMock()
        mock_history.get_recent_scan_pr_failures.return_value = [
            {"scan_pr_result": {"repo": "owner/repo", "pr_number": "10"}},
            {"scan_pr_result": {"repo": "owner/repo", "pr_number": "20"}},
        ]
        runner = ActionsRunner(history=mock_history, pjob_code="reviewer")
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
            {"number": "20", "title": "PR 20", "url": "url20"},
        ]
        with patch.object(runner._registry, "get", return_value=mock_provider):
            with pytest.raises(SkipAction) as exc_info:
                runner.run_pre(actions, {})
            assert "recently attempted" in str(exc_info.value).lower()

    def test_no_history_param_skips_query(self):
        """When history is None, no query is made and first PR is picked."""
        runner = ActionsRunner(history=None, pjob_code="reviewer")
        actions = self._make_actions()
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "10"

    def test_different_repo_not_skipped(self):
        """A failed PR on a different repo does not cause skipping."""
        mock_history = MagicMock()
        mock_history.get_recent_scan_pr_failures.return_value = [
            {"scan_pr_result": {"repo": "other/repo", "pr_number": "10"}},
        ]
        runner = ActionsRunner(history=mock_history, pjob_code="reviewer")
        actions = self._make_actions(repo="owner/repo")
        mock_provider = MagicMock()
        mock_provider.scan_prs.return_value = [
            {"number": "10", "title": "PR 10", "url": "url10"},
        ]
        mock_provider.fetch_diff.return_value = "diff"
        with patch.object(runner._registry, "get", return_value=mock_provider):
            result = runner.run_pre(actions, {})
        assert result["pr_number"] == "10"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_actions_runner.py::TestActionsRunnerPreExecSkipLogic -v`
Expected: FAIL — `ActionsRunner.__init__` got unexpected keyword arguments

- [ ] **Step 3: Implement skip-aware PR selection**

**3a. Update `ActionsRunner.__init__`** in `zima/execution/actions_runner.py`:

Replace:
```python
def __init__(self, registry: Optional[ProviderRegistry] = None):
    self._registry = registry or get_default_registry()
```

With:
```python
def __init__(
    self,
    registry: Optional[ProviderRegistry] = None,
    history=None,
    pjob_code: Optional[str] = None,
):
    self._registry = registry or get_default_registry()
    self._history = history
    self._pjob_code = pjob_code
```

**3b. Replace `prs[0]` with skip-aware selection** in the `run_pre()` method.

Replace the block from line 146 to line 154:

```python
prs = provider.scan_prs(repo, label)
if not prs:
    raise SkipAction(f"No PRs found with label '{label}' in {repo}")
pr = prs[0]
discovered["repo"] = repo
discovered["pr_number"] = str(pr.get("number") or "")
discovered["pr_title"] = pr.get("title") or ""
discovered["pr_url"] = pr.get("url") or ""
discovered["pr_diff"] = provider.fetch_diff(repo, discovered["pr_number"])
```

With:

```python
prs = provider.scan_prs(repo, label)
if not prs:
    raise SkipAction(f"No PRs found with label '{label}' in {repo}")
pr = self._select_pr(prs, repo)
discovered["repo"] = repo
discovered["pr_number"] = str(pr.get("number") or "")
discovered["pr_title"] = pr.get("title") or ""
discovered["pr_url"] = pr.get("url") or ""
discovered["pr_diff"] = provider.fetch_diff(repo, discovered["pr_number"])
```

**3c. Add the `_select_pr()` method** to `ActionsRunner`, after `_substitute_env_str()`:

```python
def _select_pr(self, prs: list[dict], repo: str) -> dict:
    """Select the next eligible PR, skipping recently-failed ones.

    Falls back to prs[0] when no history is configured.
    """
    if not self._history or not self._pjob_code:
        return prs[0]

    failures = self._history.get_recent_scan_pr_failures(self._pjob_code, 90)
    skip_set = set()
    for rec in failures:
        spr = rec.get("scan_pr_result")
        if spr:
            skip_set.add((spr.get("repo", ""), spr.get("pr_number", "")))

    for pr in prs:
        pr_num = str(pr.get("number") or "")
        if (repo, pr_num) not in skip_set:
            return pr

    raise SkipAction(f"All {len(prs)} PR(s) recently attempted, skipping")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_actions_runner.py::TestActionsRunnerPreExecSkipLogic -v`
Expected: PASS

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `uv run pytest tests/unit/test_actions_runner.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add zima/execution/actions_runner.py tests/unit/test_actions_runner.py
git commit -m "feat(actions): add skip-aware PR selection for scan_pr"
```

---

### Task 4: Wire executor to pass history context and persist `scan_pr_result`

**Files:**
- Modify: `zima/execution/executor.py:150-224` (PJobExecutor class)
- Modify: `zima/execution/background_runner.py:79-89` (state update)

- [ ] **Step 1: Update `PJobExecutor.__init__` to pass history and pjob_code**

In `zima/execution/executor.py`, replace the `__init__` method:

```python
def __init__(self):
    """Initialize executor."""
    self.config_manager = ConfigManager()
    self._current_process: Optional[subprocess.Popen] = None
    self._history = ExecutionHistory()
    self._actions_runner = ActionsRunner(
        history=self._history,
        pjob_code=None,
    )
```

Add the import at the top of the file:

```python
from zima.execution.history import ExecutionHistory
```

- [ ] **Step 2: Update `execute()` to set pjob_code and persist scan_pr_result**

In `zima/execution/executor.py`, inside the `execute()` method, add after line 175 (`result = ExecutionResult(...)`) and before the `try:` block — update the runner's pjob_code:

```python
self._actions_runner._pjob_code = pjob_code
```

Then, after line 218 (`bundle.inject_dynamic_vars(dynamic_vars)`), add `scan_pr_result` extraction:

```python
# Persist scan_pr_result for skip logic
if "pr_number" in dynamic_vars:
    result.scan_pr_result = {
        "repo": dynamic_vars.get("repo", ""),
        "pr_number": dynamic_vars["pr_number"],
    }
```

Add the `scan_pr_result` field to `ExecutionResult` in `zima/execution/executor.py` (after `action_errors`):

```python
action_errors: list[str] = field(default_factory=list)
scan_pr_result: Optional[dict] = None
```

- [ ] **Step 3: Update `background_runner.py` to persist `scan_pr_result`**

In `zima/execution/background_runner.py`, update the `history.update_runtime_state()` call (line 79) to include:

```python
history.update_runtime_state(
    pjob_code,
    execution_id,
    status=result.status.value,
    returncode=result.returncode,
    finished_at=finished_at,
    duration_seconds=result.duration_seconds,
    stdout_preview=stdout_preview,
    stderr_preview=stderr_preview,
    error_detail=result.error_detail[:2000] if result.error_detail else "",
    scan_pr_result=result.scan_pr_result,
)
```

- [ ] **Step 4: Run all unit tests to verify no regression**

Run: `uv run pytest tests/unit/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add zima/execution/executor.py zima/execution/background_runner.py
git commit -m "feat(executor): wire history and pjob_code into ActionsRunner, persist scan_pr_result"
```

---

### Task 5: Run full test suite and format

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest`
Expected: ALL PASS (including integration tests)

- [ ] **Step 2: Format and lint**

Run: `uv run black zima/ tests/ --line-length 100 && uv run ruff check zima/ tests/`
Expected: No errors

- [ ] **Step 3: Final commit if formatting changed anything**

```bash
git add -A
git commit -m "style: format code after multi-PR queue changes"
```

Only commit if there are changes.
