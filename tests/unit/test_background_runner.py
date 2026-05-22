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
