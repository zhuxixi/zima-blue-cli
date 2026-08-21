"""Tests for background_runner signal handling."""

import signal
from unittest.mock import MagicMock

from zima.execution.background_runner import _create_sigterm_handler


class TestSigtermHandler:
    def test_handler_cancels_executor(self):
        """SIGTERM handler should call executor.cancel() to terminate agent subprocess."""
        mock_executor = MagicMock()
        handler = _create_sigterm_handler(mock_executor)

        handler(signal.SIGTERM, None)

        mock_executor.cancel.assert_called_once()


class TestDedupOffForwarding:
    def _fake_result(self):
        from types import SimpleNamespace

        return SimpleNamespace(
            stdout="",
            stderr="",
            status=SimpleNamespace(value="success"),
            returncode=0,
            duration_seconds=0.0,
            scan_pr_result=None,
            error_detail="",
        )

    def test_run_pjob_in_background_forwards_dedup_off(self, isolated_zima_home):
        from unittest.mock import patch

        from zima.execution.background_runner import run_pjob_in_background

        with patch("zima.execution.executor.PJobExecutor") as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = self._fake_result()
            MockExecutor.return_value = mock_executor
            run_pjob_in_background(
                pjob_code="test-pjob",
                execution_id="abc00001",
                overrides_json="{}",
                dedup_off=True,
            )
            kwargs = mock_executor.execute.call_args.kwargs
            assert kwargs["dedup_off"] is True

    def test_run_pjob_in_background_forwards_execution_id(self, isolated_zima_home):
        from unittest.mock import MagicMock, patch

        from zima.execution.background_runner import run_pjob_in_background

        with patch("zima.execution.executor.PJobExecutor") as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = self._fake_result()
            MockExecutor.return_value = mock_executor
            run_pjob_in_background(
                pjob_code="test-pjob",
                execution_id="cli00001",
                overrides_json="{}",
            )
            kwargs = mock_executor.execute.call_args.kwargs
            assert kwargs["execution_id"] == "cli00001"

    def test_main_parses_dedup_off_flag(self, isolated_zima_home):
        from unittest.mock import patch

        import zima.execution.background_runner as br

        with patch.object(br, "run_pjob_in_background", return_value=0) as mock_run:
            with patch.object(
                br.sys,
                "argv",
                ["background_runner", "test-pjob", "--execution-id", "x", "--dedup-off"],
            ):
                assert br.main() == 0
            kwargs = mock_run.call_args.kwargs
            assert kwargs["dedup_off"] is True

    def test_run_pjob_in_background_backfills_pid(self, isolated_zima_home):
        """The runner must record its own pid so a crash ages the running
        record out (pid-less running records are never auto-marked dead;
        #181 CR round-1 finding)."""
        import os
        from unittest.mock import patch

        from zima.execution.background_runner import run_pjob_in_background
        from zima.execution.history import ExecutionHistory

        history = ExecutionHistory()
        history.write_runtime_state(
            "test-pjob",
            "cli00001",
            {
                "execution_id": "cli00001",
                "pjob_code": "test-pjob",
                "status": "running",
                "pid": None,
                "started_at": "2026-08-22T10:00:00+00:00",
            },
        )
        with patch("zima.execution.executor.PJobExecutor") as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = self._fake_result()
            MockExecutor.return_value = mock_executor
            run_pjob_in_background(
                pjob_code="test-pjob",
                execution_id="cli00001",
                overrides_json="{}",
            )
        state = history.get_runtime_state("test-pjob", "cli00001")
        assert state is not None
        assert state["pid"] == os.getpid()
