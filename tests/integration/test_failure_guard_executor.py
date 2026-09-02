"""Integration tests: failure guard wired into PJobExecutor (#202)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from tests.base import TestIsolator
from zima.execution.executor import PJobExecutor
from zima.execution.failure_guard import FailureGuardStore, normalize_target
from zima.models.actions import ActionsConfig, PostExecAction, PreExecAction
from zima.models.pjob import Overrides, PJobConfig
from zima.utils import get_zima_home

REPO = "owner/repo"
PR = "42"
HEAD = "abc123def456"
VERDICT_OK = "<zima-review>\n<verdict>approved</verdict>\n<summary>ok</summary>\n</zima-review>"


def _pin():
    return Overrides(variable_values={"repo": REPO, "pr_number": PR, "head_sha": HEAD})


def _mock_provider(executor):
    provider = MagicMock()
    provider.verify_pr_label.return_value = True
    provider.fetch_diff.return_value = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ +1\n"
    registry = MagicMock()
    registry.get.return_value = provider
    executor._actions_runner._registry = registry
    return provider


def _write_guard_state(head_sha, *, streak, cooldown_until):
    target = normalize_target("fg-pjob", REPO, PR, head_sha)
    store = FailureGuardStore(get_zima_home() / "state" / "failure-guard")
    path = store.path_for(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "target": target.to_dict(),
                "failure_streak": streak,
                "last_failure_at": "2026-08-31T00:00:00Z",
                "cooldown_until": cooldown_until,
                "last_failure_kind": "invalid_process",
                "last_execution_id": "seed",
            }
        ),
        encoding="utf-8",
    )
    return path


class _Base(TestIsolator):
    @pytest.fixture
    def configs(self, isolated_zima_home, config_manager):
        from zima.models.workflow import WorkflowConfig

        config_manager.save_config(
            "agent",
            "fg-agent",
            {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "fg-agent", "name": "FG Agent"},
                "spec": {"type": "pi", "parameters": {"mockCommand": ["echo", VERDICT_OK]}},
            },
        )
        wf = WorkflowConfig.create(
            code="fg-wf", name="FG Workflow", template="Review {{repo}}#{{pr_number}}", variables=[]
        )
        config_manager.save_config("workflow", "fg-wf", wf.to_dict())
        pjob = PJobConfig.create(code="fg-pjob", name="FG PJob", agent="fg-agent", workflow="fg-wf")
        pjob.spec.actions = ActionsConfig(
            pre_exec=[
                PreExecAction(
                    condition="always", type="scan_pr", repo=REPO, label="zima:needs-review"
                )
            ],
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    repo=REPO,
                    issue=PR,
                )
            ],
        )
        config_manager.save_config("pjob", "fg-pjob", pjob.to_dict())

    def _agent(self, config_manager, mock_command):
        data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "fg-agent", "name": "FG Agent"},
            "spec": {"type": "pi", "parameters": {"mockCommand": mock_command}},
        }
        config_manager.save_config("agent", "fg-agent", data)


class TestCooldownSkip(_Base):
    def test_cooldown_skips_before_agent_launch(self, configs, isolated_zima_home):
        future = (
            (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        executor = PJobExecutor()
        provider = _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        assert result.status.value == "skipped"
        assert "cooldown" in result.stderr
        assert "next allowed at" in result.stderr
        provider.add_label.assert_not_called()  # no postExec on SKIPPED
        # Genuine cooldown hit is labeled cooldown_skip (not guard_error).
        from zima.execution.history import ExecutionHistory

        rec = ExecutionHistory().list_executions("fg-pjob")[0]
        assert rec["failure_guard"]["status"] == "cooldown_skip"

    def test_corrupt_state_fails_closed(self, configs, isolated_zima_home):
        path = _write_guard_state(HEAD, streak=1, cooldown_until="")
        path.write_text("{ corrupted", encoding="utf-8")
        executor = PJobExecutor()
        _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        assert result.status.value == "skipped"
        assert "fail closed" in result.stderr
        # Corrupt state is labeled guard_error, not cooldown_skip.
        from zima.execution.history import ExecutionHistory

        rec = ExecutionHistory().list_executions("fg-pjob")[0]
        assert rec["failure_guard"]["status"] == "guard_error"

    def test_dedup_off_does_not_bypass_guard(self, configs, isolated_zima_home):
        future = (
            (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        executor = PJobExecutor()
        _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin(), dedup_off=True)
        assert result.status.value == "skipped"

    def test_failure_guard_off_bypasses_check_but_still_records(
        self, configs, config_manager, isolated_zima_home
    ):
        future = (
            (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        self._agent(config_manager, ["false"])  # keep failing
        executor = PJobExecutor()
        _mock_provider(executor)
        overrides = _pin()
        overrides.failure_guard_off = True
        result = executor.execute("fg-pjob", overrides=overrides)
        assert result.status.value == "failed"  # ran despite cooldown
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        data = json.loads(
            FailureGuardStore(get_zima_home() / "state" / "failure-guard")
            .path_for(target)
            .read_text(encoding="utf-8")
        )
        assert data["failure_streak"] == 3  # outcome still recorded


class TestRecording(_Base):
    def test_two_failures_then_cooldown_skip(self, configs, config_manager, isolated_zima_home):
        self._agent(config_manager, ["false"])
        # dedup_off isolates the failure guard from the orthogonal #181 dedup
        # guard: direct execute() calls leave prior records "running"
        # (terminal status is the caller's job), which would otherwise dedup-
        # skip runs 2/3 before the failure guard ever fires.
        for expected in ("failed", "failed"):
            executor = PJobExecutor()
            _mock_provider(executor)
            result = executor.execute("fg-pjob", overrides=_pin(), dedup_off=True)
            assert result.status.value == expected
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        path = FailureGuardStore(get_zima_home() / "state" / "failure-guard").path_for(target)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["failure_streak"] == 2
        assert data["cooldown_until"]
        # Third attempt: skipped before launch (guard cooldown — dedup_off is
        # on, so the failure guard is the only possible skipper), no postExec.
        executor = PJobExecutor()
        provider = _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin(), dedup_off=True)
        assert result.status.value == "skipped"
        assert "cooldown" in result.stderr
        assert provider.add_label.call_count == 0

    def test_record_error_writes_guard_error_state_note(
        self, configs, config_manager, isolated_zima_home
    ):
        # Spec §6.1-3: guard errors must leave a runtime-state trace. A
        # corrupt state file first surfacing at record time (only reachable
        # via the override, since check fails closed first) must annotate
        # this execution instead of waiting for the next run's check.
        path = _write_guard_state(HEAD, streak=1, cooldown_until="")
        path.write_text("{ corrupted", encoding="utf-8")
        self._agent(config_manager, ["false"])  # countable-failure outcome
        executor = PJobExecutor()
        _mock_provider(executor)
        overrides = _pin()
        overrides.failure_guard_off = True  # bypass the fail-closed check; record still runs
        result = executor.execute("fg-pjob", overrides=overrides)
        assert result.status.value == "failed"  # record error must not fail the run
        from zima.execution.history import ExecutionHistory

        rec = ExecutionHistory().list_executions("fg-pjob")[0]
        assert rec["failure_guard"]["status"] == "guard_error"
        assert rec["failure_guard"]["phase"] == "record"
        assert "unreadable" in rec["failure_guard"]["reason"]

    def test_valid_review_clears_streak(self, configs, isolated_zima_home):
        _write_guard_state(HEAD, streak=1, cooldown_until="")
        executor = PJobExecutor()
        _mock_provider(executor)
        result = executor.execute("fg-pjob", overrides=_pin())
        assert result.status.value == "success"
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        path = FailureGuardStore(get_zima_home() / "state" / "failure-guard").path_for(target)
        assert not path.exists()

    def test_new_head_has_independent_budget(self, configs, isolated_zima_home):
        future = (
            (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        )
        _write_guard_state(HEAD, streak=2, cooldown_until=future)
        executor = PJobExecutor()
        _mock_provider(executor)
        new_head = Overrides(
            variable_values={"repo": REPO, "pr_number": PR, "head_sha": "ffff00001111"}
        )
        result = executor.execute("fg-pjob", overrides=new_head)
        assert result.status.value == "success"  # new head is not blocked

    def test_needs_fix_verdict_is_valid_and_clears(
        self, configs, config_manager, isolated_zima_home
    ):
        needs_fix = (
            "<zima-review>\n<verdict>needs_fix</verdict>\n<summary>issues</summary>\n</zima-review>"
        )
        self._agent(config_manager, ["echo", needs_fix])
        _write_guard_state(HEAD, streak=1, cooldown_until="")
        executor = PJobExecutor()
        provider = _mock_provider(executor)
        executor.execute("fg-pjob", overrides=_pin())
        # postExec failure branch fires (verdict needs_fix → effective rc 1)
        provider.add_label.assert_called()
        target = normalize_target("fg-pjob", REPO, PR, HEAD)
        path = FailureGuardStore(get_zima_home() / "state" / "failure-guard").path_for(target)
        assert not path.exists()  # NEEDS_FIX cleared the streak


class TestCliFlag(_Base):
    def test_run_passes_failure_guard_off_into_overrides(
        self, configs, isolated_zima_home, monkeypatch, cli_runner
    ):
        from zima.cli import app

        captured = {}

        class FakeExecutor:
            def execute(self, pjob_code, overrides=None, dry_run=False, keep_temp=False):
                captured["overrides"] = overrides
                from zima.execution.executor import ExecutionResult, ExecutionStatus

                return ExecutionResult(
                    pjob_code=pjob_code, status=ExecutionStatus.SUCCESS, command=["echo", "x"]
                )

        monkeypatch.setattr("zima.commands.pjob.PJobExecutor", FakeExecutor)
        result = cli_runner.invoke(
            app, ["pjob", "run", "fg-pjob", "--failure-guard-off", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert captured["overrides"].failure_guard_off is True
