"""Tests for background_runner signal handling."""

import signal
from unittest.mock import MagicMock

from zima.execution.background_runner import _create_sigterm_handler


class TestSigtermHandler:
    def test_handler_cancels_executor(self):
        """SIGTERM handler should call executor.cancel() to terminate agent subprocess."""
        mock_executor = MagicMock()
        handler, is_cancelled = _create_sigterm_handler(mock_executor)

        handler(signal.SIGTERM, None)

        mock_executor.cancel.assert_called_once()

    def test_handler_sets_cancelled_flag(self):
        """SIGTERM handler should set a cancelled flag so caller knows."""
        mock_executor = MagicMock()
        handler, is_cancelled = _create_sigterm_handler(mock_executor)

        assert not is_cancelled()
        handler(signal.SIGTERM, None)
        assert is_cancelled()
