# Issue-181 Execution-Layer Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block duplicate review streams — same PJob, same (repo, PR, head) already running or recently succeeded — at the execution layer, skipping the duplicate via the existing SKIPPED path.

**Architecture:** All three trigger streams (webhook / manual / daemon) funnel through `PJobExecutor.execute()`, and execution state lives in cross-process-visible JSON files under `~/.zima/history/pjobs/<code>/<execution_id>.json`. After preExec `scan_pr` resolves the authoritative `(repo, pr_number)`, the executor immediately persists `scan_pr_result` (now including `head_sha`) to its state file, then queries `ExecutionHistory.find_recent_duplicate()` for another stream covering the same key; on hit it raises `SkipAction`, which the existing preExec handler turns into `SKIPPED` (no review, no postExec, no label changes). `--dedup-off` is the manual escape hatch.

**Tech Stack:** Python 3.10+, dataclasses, typer CLI, pytest (fixtures: `isolated_zima_home`, `config_manager`), unittest.mock.

**Spec:** `docs/superpowers/specs/2026-08-22-issue-181-cr-duplicate-review-dedup-design.md` (authoritative; this plan implements it)

## Global Constraints

- Worktree: `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup` — ALL file edits and git operations happen here; never touch the main checkout.
- Python 3.10+; Google-style docstrings; black at 100 cols; ruff clean (`uv run ruff check zima/ tests/`).
- Commit format: `type(scope): description` — use `feat(dedup):`, `fix(dedup):`, `test(dedup):`.
- `git add <file>` per file, never `git add -A`.
- Tests use `isolated_zima_home` for ZIMA_HOME isolation; unit tests in `tests/unit/`, integration in `tests/integration/`.
- Coverage floor 60%: `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`.
- History state-file schema is backward compatible: old files without `head_sha` in `scan_pr_result` must keep working (treated as "head unknown").
- Skip semantics: dedup-skipped executions must NOT run postExec actions (label changes) — reuse `SkipAction` → `SKIPPED` path.

## File Structure

- `zima/execution/history.py` — ADD `ExecutionHistory.find_recent_duplicate()`. Pure query over state files; no executor dependency.
- `zima/execution/executor.py` — MODIFY `PJobExecutor.execute()`: (a) include `head_sha` in persisted `scan_pr_result`; (b) persist `scan_pr_result` immediately after preExec; (c) dedup guard raising `SkipAction`; (d) new `dedup_off: bool = False` parameter.
- `zima/execution/background_runner.py` — MODIFY `run_pjob_in_background()` + `main()` to accept/forward `--dedup-off`.
- `zima/commands/pjob.py` — MODIFY `run` command: add `--dedup-off` flag, forward to spawned background runner.
- `tests/unit/test_execution_history.py` — ADD `TestFindRecentDuplicate` (decision table).
- `tests/unit/test_executor_dedup.py` — NEW: executor-level dedup guard tests.
- `tests/unit/test_background_runner.py` — ADD flag-forwarding tests.

---

### Task 1: `ExecutionHistory.find_recent_duplicate()`

**Files:**
- Modify: `zima/execution/history.py` (add method to `ExecutionHistory`, after `get_recent_scan_pr_failures`)
- Test: `tests/unit/test_execution_history.py` (append `TestFindRecentDuplicate` class)

**Interfaces:**
- Produces: `ExecutionHistory.find_recent_duplicate(pjob_code: str, repo: str, pr_number: str, head_sha: str, exclude_execution_id: str, window_minutes: int = 30) -> Optional[dict]` — returns the first matching duplicate record dict (state-file contents), else `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_execution_history.py` (imports at top of file: add `from datetime import datetime, timedelta, timezone`):

```python
class TestFindRecentDuplicate:
    @pytest.fixture(autouse=True)
    def setup(self, isolated_zima_home):
        self.history = ExecutionHistory()
        self.pjob_code = "test-pjob"
        self.now = datetime.now(timezone.utc)

    def _write(self, execution_id, status, repo="owner/repo", pr_number="42",
               head_sha="", started_minutes_ago=0):
        started = (self.now - timedelta(minutes=started_minutes_ago)).isoformat()
        spr = {"repo": repo, "pr_number": pr_number}
        if head_sha:
            spr["head_sha"] = head_sha
        self.history.write_runtime_state(
            self.pjob_code,
            execution_id,
            {
                "execution_id": execution_id,
                "pjob_code": self.pjob_code,
                "status": status,
                "pid": None,
                "started_at": started,
                "scan_pr_result": spr,
            },
        )

    def _query(self, head_sha="", **kwargs):
        return self.history.find_recent_duplicate(
            pjob_code=self.pjob_code,
            repo="owner/repo",
            pr_number="42",
            head_sha=head_sha,
            exclude_execution_id="me000001",
            **kwargs,
        )

    def test_running_same_head_blocks(self):
        self._write("dup00001", "running", head_sha="abc123", started_minutes_ago=1)
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_running_different_head_allows(self):
        self._write("dup00001", "running", head_sha="abc123", started_minutes_ago=1)
        assert self._query(head_sha="def456") is None

    def test_success_within_window_same_head_blocks(self):
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=10)
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_success_within_window_different_head_allows(self):
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=10)
        assert self._query(head_sha="def456") is None

    def test_success_beyond_window_allows(self):
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=45)
        assert self._query(head_sha="abc123") is None

    def test_failed_allows(self):
        self._write("dup00001", "failed", started_minutes_ago=1)
        assert self._query(head_sha="abc123") is None

    def test_skipped_allows(self):
        self._write("dup00001", "skipped", started_minutes_ago=1)
        assert self._query(head_sha="abc123") is None

    def test_excludes_own_execution(self):
        self._write("me000001", "running", head_sha="abc123", started_minutes_ago=1)
        assert self._query(head_sha="abc123") is None

    def test_missing_head_treated_conservatively(self):
        # Candidate without head_sha blocks a query with head_sha (conservative).
        self._write("dup00001", "running", head_sha="", started_minutes_ago=1)
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_query_without_head_treated_conservatively(self):
        # Query without head_sha is blocked by a candidate WITH head_sha.
        self._write("dup00001", "success", head_sha="abc123", started_minutes_ago=5)
        dup = self._query(head_sha="")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_unparseable_started_treated_in_window(self):
        self.history.write_runtime_state(
            self.pjob_code,
            "dup00001",
            {
                "execution_id": "dup00001",
                "pjob_code": self.pjob_code,
                "status": "success",
                "pid": None,
                "started_at": "not-a-timestamp",
                "scan_pr_result": {"repo": "owner/repo", "pr_number": "42"},
            },
        )
        dup = self._query(head_sha="abc123")
        assert dup is not None and dup["execution_id"] == "dup00001"

    def test_other_pjob_not_checked(self):
        self._write("dup00001", "running", head_sha="abc123", started_minutes_ago=1)
        other = ExecutionHistory()
        dup = other.find_recent_duplicate(
            pjob_code="other-pjob",
            repo="owner/repo",
            pr_number="42",
            head_sha="abc123",
            exclude_execution_id="me000001",
        )
        assert dup is None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_execution_history.py::TestFindRecentDuplicate -v`
Expected: FAIL — `AttributeError: 'ExecutionHistory' object has no attribute 'find_recent_duplicate'`

- [ ] **Step 3: Implement `find_recent_duplicate`**

Add to `zima/execution/history.py`, inside `class ExecutionHistory`, right after `get_recent_scan_pr_failures`:

```python
    def find_recent_duplicate(
        self,
        pjob_code: str,
        repo: str,
        pr_number: str,
        head_sha: str,
        exclude_execution_id: str,
        window_minutes: int = 30,
    ) -> Optional[dict]:
        """Return the first recent execution duplicating the given review target.

        A duplicate is an execution of the same PJob whose ``scan_pr_result``
        matches ``(repo, pr_number)`` and which is either still ``running`` or
        finished ``success`` within ``window_minutes`` of its start.  Two
        executions with *different* known ``head_sha`` values are not
        duplicates (a new commit legitimately starts a new review round).
        A missing ``head_sha`` on either side is treated conservatively as
        "same head".  Failed / timed-out / skipped / dead executions never
        block a re-run (they produced no valid review).

        Args:
            pjob_code: PJob code to query.
            repo: Target repo full name.
            pr_number: Target PR number (already normalized).
            head_sha: Target head SHA (may be empty).
            exclude_execution_id: Execution ID to skip (the current run).
            window_minutes: Recent-completion window for ``success`` records.

        Returns:
            The first matching record dict, or ``None``.
        """
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=window_minutes)

        def _parse_started(value: str) -> Optional[datetime]:
            if not value:
                return None
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                return None

        target_repo = str(repo or "").strip().lower()
        target_pr = str(pr_number or "").strip()
        target_head = str(head_sha or "").strip().lower()

        for record in self.list_executions(pjob_code):
            if record.get("execution_id") == exclude_execution_id:
                continue
            spr = record.get("scan_pr_result")
            if not isinstance(spr, dict):
                continue
            if str(spr.get("repo") or "").strip().lower() != target_repo:
                continue
            if str(spr.get("pr_number") or "").strip() != target_pr:
                continue

            status = record.get("status", "")
            if status not in ("running", "success"):
                continue

            other_head = str(spr.get("head_sha") or "").strip().lower()
            if target_head and other_head and target_head != other_head:
                # Both heads known and different: a new review round.
                continue

            if status == "running":
                return record
            # success: require started_at within the window. Unparseable
            # timestamps are treated conservatively as in-window (better a
            # blocked re-run than two parallel review streams).
            started = _parse_started(record.get("started_at") or "")
            if started is None or started >= cutoff:
                return record
        return None
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_execution_history.py -v`
Expected: PASS (all, including the pre-existing class)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup
git add zima/execution/history.py tests/unit/test_execution_history.py
git commit -m "feat(dedup): ExecutionHistory.find_recent_duplicate for same-(repo,pr,head) review dedup"
```

---

### Task 2: Persist `head_sha` in `scan_pr_result` and write it immediately

**Files:**
- Modify: `zima/execution/executor.py` (preExec block, `result.scan_pr_result = {...}` at ~line 493)
- Test: `tests/unit/test_executor_dedup.py` (NEW — first two tests)

**Interfaces:**
- Consumes: nothing new; uses existing `bundle.overrides.variable_values` (already read in the same function for `pr_number`) and `self._history.update_runtime_state`.
- Produces: state file now carries `scan_pr_result.head_sha` (lowercased hex or omitted when absent); state file receives `scan_pr_result` at preExec completion, not at process end.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_executor_dedup.py`:

```python
"""Unit tests for execution-layer duplicate-review dedup (#181)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from zima.execution.actions_runner import SkipAction
from zima.execution.executor import ExecutionStatus, PJobExecutor
from zima.execution.history import ExecutionHistory
from zima.models.actions import ActionsConfig, PreExecAction
from zima.models.agent import AgentConfig
from zima.models.pjob import Overrides, PJobConfig
from zima.models.workflow import WorkflowConfig


@pytest.fixture
def mock_pjob_with_scan(isolated_zima_home):
    """Create a PJob with a scan_pr preExec action and save its configs."""
    from zima.config.manager import ConfigManager

    manager = ConfigManager()
    agent = AgentConfig.create(
        code="test-agent",
        name="Test Agent",
        agent_type="kimi",
        parameters={"mockCommand": "echo hello"},
    )
    manager.save_config("agent", "test-agent", agent.to_dict())
    workflow = WorkflowConfig.create(
        code="test-workflow", name="Test Workflow", template="Hello"
    )
    manager.save_config("workflow", "test-workflow", workflow.to_dict())
    pjob = PJobConfig.create(
        code="test-pjob", name="Test PJob", agent="test-agent", workflow="test-workflow"
    )
    pjob.spec.actions = ActionsConfig(
        provider="github",
        pre_exec=[PreExecAction(type="scan_pr", repo="owner/repo", label="ready-for-review")],
    )
    manager.save_config("pjob", "test-pjob", pjob.to_dict())
    return pjob


class TestScanResultPersistence:
    def test_head_sha_persisted_from_runtime_override(self, mock_pjob_with_scan):
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ), patch.object(executor, "_run_command", return_value=(0, "", "", 12345)):
            result = executor.execute(
                "test-pjob",
                overrides=Overrides(variable_values={"head_sha": "ABCDEF1234567890"}),
            )
        assert result.status == ExecutionStatus.SUCCESS
        state = executor._history.get_runtime_state("test-pjob", result.execution_id)
        assert state is not None
        assert state["scan_pr_result"]["head_sha"] == "abcdef1234567890"

    def test_scan_result_persisted_before_agent_runs(self, mock_pjob_with_scan):
        """The scan target must be on disk BEFORE the agent command runs,
        so a concurrent stream can see it while this one is still running."""
        executor = PJobExecutor()
        observed = {}

        def _run_command(command, env, work_dir, timeout, stdin_file):
            # At this point scan_pr_result must already be persisted.
            states = executor._history.list_executions("test-pjob")
            observed["count"] = len(states)
            observed["scan_pr_result"] = states[0].get("scan_pr_result")
            return (0, "", "", 12345)

        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ), patch.object(executor, "_run_command", side_effect=_run_command):
            result = executor.execute("test-pjob")
        assert result.status == ExecutionStatus.SUCCESS
        assert observed["count"] == 1
        assert observed["scan_pr_result"] == {"repo": "owner/repo", "pr_number": "42"}

    def test_dry_run_does_not_write_state(self, mock_pjob_with_scan):
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ):
            result = executor.execute("test-pjob", dry_run=True)
        assert result.status == ExecutionStatus.SUCCESS
        states = executor._history.list_executions("test-pjob")
        assert all(s.get("execution_id") != result.execution_id for s in states)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_executor_dedup.py -v`
Expected: FAIL — test 1 asserts `head_sha` present but scan_pr_result lacks it; test 2 asserts persisted-before-agent but the state file is written only at process end (state read yields no scan_pr_result or a missing record).

- [ ] **Step 3: Implement**

In `zima/execution/executor.py`, replace the scan_pr_result assembly block:

```python
                    _persistable_pr = normalize_pr_number(dynamic_vars.get("pr_number") or "")
                    _persistable_repo = str(dynamic_vars.get("repo") or "").strip()
                    # head_sha only exists for webhook-triggered runs
                    # (--set-var=head_sha); normalize to lowercase hex.
                    _persistable_head = str(
                        bundle.overrides.variable_values.get("head_sha") or ""
                    ).strip().lower()
                    if _scan_valid and (_persistable_pr or _persistable_repo):
                        result.scan_pr_result = {
                            k: v
                            for k, v in {
                                "repo": _persistable_repo,
                                "pr_number": _persistable_pr,
                                "head_sha": _persistable_head,
                            }.items()
                            if v
                        }
                        # Persist immediately: concurrent streams (webhook /
                        # manual / daemon) must see this target while the
                        # agent is still running (#181). dry_run writes
                        # nothing (it renders only). Read-merge-write:
                        # update_runtime_state is a no-op when the state
                        # file does not exist (e.g. executor invoked
                        # directly without the CLI layer writing it first).
                        if not dry_run:
                            _state = self._history.get_runtime_state(
                                pjob_code, execution_id
                            )
                            if _state is None:
                                _state = {
                                    "execution_id": execution_id,
                                    "pjob_code": pjob_code,
                                    "started_at": result.started_at,
                                }
                            _state["scan_pr_result"] = result.scan_pr_result
                            self._history.write_runtime_state(
                                pjob_code, execution_id, _state
                            )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_executor_dedup.py tests/unit/test_executor_preexec.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup
git add zima/execution/executor.py tests/unit/test_executor_dedup.py
git commit -m "feat(dedup): persist head_sha in scan_pr_result and write state immediately after preExec"
```

---

### Task 3: Dedup guard in `execute()` + `dedup_off` parameter

**Files:**
- Modify: `zima/execution/executor.py` (`execute()` signature + guard right after the persistence added in Task 2, still INSIDE the preExec try block)
- Test: `tests/unit/test_executor_dedup.py` (append `TestDedupGuard` class)

**Interfaces:**
- Consumes: `ExecutionHistory.find_recent_duplicate` (Task 1), immediate persistence (Task 2).
- Produces: `PJobExecutor.execute(pjob_code, overrides=None, dry_run=False, keep_temp=False, dedup_off: bool = False)` — `dedup_off=True` bypasses the guard. Dedup skip returns `ExecutionResult(status=SKIPPED)` with reason in `stderr`, no postExec.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_executor_dedup.py`:

```python
class TestDedupGuard:
    def _seed_duplicate(self, status, head_sha="", started_minutes_ago=0):
        from datetime import datetime, timedelta, timezone

        history = ExecutionHistory()
        started = (datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)).isoformat()
        spr = {"repo": "owner/repo", "pr_number": "42"}
        if head_sha:
            spr["head_sha"] = head_sha
        history.write_runtime_state(
            "test-pjob",
            "dup00001",
            {
                "execution_id": "dup00001",
                "pjob_code": "test-pjob",
                "status": status,
                "pid": None,
                "started_at": started,
                "scan_pr_result": spr,
            },
        )

    def test_duplicate_running_stream_skips(self, mock_pjob_with_scan):
        self._seed_duplicate("running", started_minutes_ago=1)
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ), patch.object(executor, "_run_command") as mock_run:
            result = executor.execute("test-pjob")
        assert result.status == ExecutionStatus.SKIPPED
        assert "dedup" in result.stderr
        assert "dup00001" in result.stderr
        mock_run.assert_not_called()

    def test_recent_success_same_head_skips(self, mock_pjob_with_scan):
        self._seed_duplicate("success", head_sha="abc123", started_minutes_ago=5)
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ), patch.object(executor, "_run_command") as mock_run:
            result = executor.execute(
                "test-pjob",
                overrides=Overrides(variable_values={"head_sha": "abc123"}),
            )
        assert result.status == ExecutionStatus.SKIPPED
        mock_run.assert_not_called()

    def test_new_head_sha_allows(self, mock_pjob_with_scan):
        self._seed_duplicate("success", head_sha="abc123", started_minutes_ago=5)
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ), patch.object(executor, "_run_command", return_value=(0, "", "", 12345)) as mock_run:
            result = executor.execute(
                "test-pjob",
                overrides=Overrides(variable_values={"head_sha": "def456"}),
            )
        assert result.status == ExecutionStatus.SUCCESS
        mock_run.assert_called_once()

    def test_dedup_off_bypasses(self, mock_pjob_with_scan):
        self._seed_duplicate("running", started_minutes_ago=1)
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ), patch.object(executor, "_run_command", return_value=(0, "", "", 12345)) as mock_run:
            result = executor.execute("test-pjob", dedup_off=True)
        assert result.status == ExecutionStatus.SUCCESS
        mock_run.assert_called_once()

    def test_failed_duplicate_allows(self, mock_pjob_with_scan):
        self._seed_duplicate("failed", started_minutes_ago=1)
        executor = PJobExecutor()
        with patch.object(
            executor._actions_runner,
            "run_pre",
            return_value={"repo": "owner/repo", "pr_number": "42"},
        ), patch.object(executor, "_run_command", return_value=(0, "", "", 12345)) as mock_run:
            result = executor.execute("test-pjob")
        assert result.status == ExecutionStatus.SUCCESS
        mock_run.assert_called_once()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_executor_dedup.py -v`
Expected: FAIL — guard not implemented: no skip occurs (status SUCCESS), and `dedup_off` raises `TypeError: unexpected keyword argument`.

- [ ] **Step 3: Implement**

In `zima/execution/executor.py`:

(3a) Change signature:

```python
    def execute(
        self,
        pjob_code: str,
        overrides: Optional[Overrides] = None,
        dry_run: bool = False,
        keep_temp: bool = False,
        dedup_off: bool = False,
    ) -> ExecutionResult:
```

Add to the docstring under Args:

```python
            dedup_off: If True, skip the duplicate-execution dedup guard.
```

(3b) Insert the guard immediately AFTER the immediate-persistence block added in Task 2 (same preExec try block, still before its closing `except SkipAction`):

```python
                        # Same-(repo, pr, head) dedup guard (#181): skip when
                        # another stream is already reviewing this target
                        # (running) or reviewed it recently (success within
                        # the window). Runs inside the preExec try block so
                        # SkipAction yields SKIPPED (no postExec, no label
                        # changes).
                        if not dry_run and not dedup_off and result.scan_pr_result:
                            _dup = self._history.find_recent_duplicate(
                                pjob_code=pjob_code,
                                repo=result.scan_pr_result.get("repo", ""),
                                pr_number=result.scan_pr_result.get("pr_number", ""),
                                head_sha=result.scan_pr_result.get("head_sha", ""),
                                exclude_execution_id=execution_id,
                            )
                            if _dup:
                                _dup_spr = _dup.get("scan_pr_result") or {}
                                raise SkipAction(
                                    "dedup: duplicate review skipped — execution "
                                    f"'{_dup.get('execution_id')}' "
                                    f"(status={_dup.get('status')}) already covers "
                                    f"({_dup_spr.get('repo')}, PR "
                                    f"#{_dup_spr.get('pr_number')}); re-run with "
                                    "--dedup-off to force"
                                )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_executor_dedup.py tests/unit/test_executor_preexec.py tests/unit/test_executor_fixes.py -v`
Expected: PASS (guard tests + no regression in preExec/fixes suites)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup
git add zima/execution/executor.py tests/unit/test_executor_dedup.py
git commit -m "feat(dedup): skip duplicate same-(repo,pr,head) executions via SkipAction guard"
```

---

### Task 4: `--dedup-off` CLI flag + background runner forwarding

**Files:**
- Modify: `zima/commands/pjob.py` (`run` command: add option, append to spawn cmd)
- Modify: `zima/execution/background_runner.py` (`run_pjob_in_background` signature + `main()` argparse)
- Test: `tests/unit/test_background_runner.py` (append forwarding tests)

**Interfaces:**
- Consumes: `PJobExecutor.execute(..., dedup_off=...)` (Task 3).
- Produces: CLI `zima pjob run <code> --dedup-off`; background runner args `--dedup-off`; `run_pjob_in_background(pjob_code, execution_id, overrides_json=None, keep_temp=False, dedup_off=False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_background_runner.py`:

```python
class TestDedupOffForwarding:
    def test_run_pjob_in_background_forwards_dedup_off(self, isolated_zima_home):
        from unittest.mock import MagicMock, patch

        from zima.execution.background_runner import run_pjob_in_background

        with patch("zima.execution.background_runner.PJobExecutor") as MockExecutor:
            mock_executor = MagicMock()
            MockExecutor.return_value = mock_executor
            run_pjob_in_background(
                pjob_code="test-pjob",
                execution_id="abc00001",
                overrides_json="{}",
                dedup_off=True,
            )
            kwargs = mock_executor.execute.call_args.kwargs
            assert kwargs["dedup_off"] is True

    def test_main_parses_dedup_off_flag(self, isolated_zima_home):
        from unittest.mock import patch

        import zima.execution.background_runner as br

        with patch.object(br, "run_pjob_in_background", return_value=0) as mock_run:
            with patch.object(
                br.sys, "argv", ["background_runner", "test-pjob", "--execution-id", "x", "--dedup-off"]
            ):
                assert br.main() == 0
            kwargs = mock_run.call_args.kwargs
            assert kwargs["dedup_off"] is True
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_background_runner.py -v`
Expected: FAIL — `TypeError: run_pjob_in_background() got an unexpected keyword argument 'dedup_off'`

- [ ] **Step 3: Implement**

(4a) `zima/execution/background_runner.py` — signature + call + argparse:

```python
def run_pjob_in_background(
    pjob_code: str,
    execution_id: str,
    overrides_json: str | None = None,
    keep_temp: bool = False,
    dedup_off: bool = False,
) -> int:
```

Docstring Args addition:

```python
        dedup_off: Whether to skip the duplicate-execution dedup guard.
```

In the body, replace the `executor.execute(...)` call:

```python
    result = executor.execute(
        pjob_code=pjob_code,
        overrides=overrides,
        dry_run=False,
        keep_temp=keep_temp,
        dedup_off=dedup_off,
    )
```

In `main()`:

```python
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary files")
    parser.add_argument(
        "--dedup-off",
        action="store_true",
        help="Skip duplicate-execution dedup check",
    )
```

and:

```python
    return run_pjob_in_background(
        pjob_code=args.pjob_code,
        execution_id=args.execution_id,
        overrides_json=args.overrides,
        keep_temp=args.keep_temp,
        dedup_off=args.dedup_off,
    )
```

(4b) `zima/commands/pjob.py` — add option to `run` (after `keep_temp`):

```python
    dedup_off: bool = typer.Option(
        False,
        "--dedup-off",
        help="Skip the duplicate-execution check (force run even if the same PR is already being or was recently reviewed)",
    ),
```

In the spawn cmd assembly (after the `if keep_temp:` block):

```python
    if dedup_off:
        cmd.append("--dedup-off")
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/unit/test_background_runner.py tests/unit/test_executor_dedup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup
git add zima/execution/background_runner.py zima/commands/pjob.py tests/unit/test_background_runner.py
git commit -m "feat(dedup): add --dedup-off flag to pjob run and background runner"
```

---

### Task 5: Full verification — lint, format, whole suite

**Files:** none (verification only; fix fallout if any)

- [ ] **Step 1: Run lint + format check**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run ruff check zima/ tests/ && uv run black --check zima/ tests/ --line-length 100`
Expected: PASS clean. If ruff/black flags the new code, fix and re-run.

- [ ] **Step 2: Run the full unit + integration suite**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup && uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
Expected: PASS. Pay attention to `tests/unit/test_executor_fixes.py` and `tests/integration/test_pjob_lifecycle.py` — any regression there is a real bug, not a test fix.

- [ ] **Step 3: Fix fallout (if any), then commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-181-cr-duplicate-review-dedup
git add <fixed files>
git commit -m "fix(dedup): resolve lint/test fallout from dedup guard"
```

---

## Self-Review

**Spec coverage:**
- §1 head_sha in scan_pr_result → Task 2 ✓
- §1b immediate persistence → Task 2 (test_scan_result_persisted_before_agent_runs) ✓
- §2 find_recent_duplicate decision table → Task 1 (all 13 rows: running/success/window/head-diff/missing-head/bad-timestamp/exclude-self/other-pjob) ✓
- §3 guard inside preExec try + SkipAction → Task 3 ✓
- §4 --dedup-off escape hatch → Task 4 ✓
- §5 race handling (last scan-finisher survives) → covered by Task 3 tests (running duplicate seen only after immediate persistence) ✓
- §6 same-pjob-only / bad-data tolerance → Task 1 tests (test_other_pjob_not_checked, test_unparseable_started_treated_in_window, missing-head conservative) ✓
- Phase-2 items (meta source/execution_id, postExec arbitration) — intentionally excluded per spec ✓

**Placeholder scan:** no TBD/TODO; every code step contains full code. ✓

**Type consistency:** `find_recent_duplicate(pjob_code, repo, pr_number, head_sha, exclude_execution_id, window_minutes=30) -> Optional[dict]` — Task 1 defines, Task 3 calls with keyword args matching. `execute(..., dedup_off: bool = False)` — Task 3 defines, Task 4 forwards. `run_pjob_in_background(..., dedup_off: bool = False)` — Task 4 defines and tests. ✓
