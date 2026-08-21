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
    def test_run_pjob_in_background_forwards_dedup_off(self, isolated_zima_home):
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from zima.execution.background_runner import run_pjob_in_background

        fake_result = SimpleNamespace(
            stdout="",
            stderr="",
            status=SimpleNamespace(value="success"),
            returncode=0,
            duration_seconds=0.0,
            scan_pr_result=None,
            error_detail="",
        )
        # PJobExecutor is imported inside run_pjob_in_background, so patch
        # the source module attribute rather than the background_runner module.
        with patch("zima.execution.executor.PJobExecutor") as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute.return_value = fake_result
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
                br.sys,
                "argv",
                ["background_runner", "test-pjob", "--execution-id", "x", "--dedup-off"],
            ):
                assert br.main() == 0
            kwargs = mock_run.call_args.kwargs
            assert kwargs["dedup_off"] is True
