"""Unit tests for daemon command helpers."""

import sys
from unittest.mock import MagicMock, patch

from zima.commands.daemon import _is_process_alive


class TestIsProcessAliveWindows:
    """Test _is_process_alive on Windows."""

    @patch("sys.platform", "win32")
    def test_alive_process(self):
        """Returns True when OpenProcess returns a valid handle."""
        with patch.dict("sys.modules", {"ctypes": MagicMock()}):
            mock_ctypes = sys.modules["ctypes"]
            mock_handle = MagicMock()
            mock_ctypes.windll.kernel32.OpenProcess.return_value = mock_handle

            assert _is_process_alive(1234) is True
            mock_ctypes.windll.kernel32.OpenProcess.assert_called_once_with(0x1000, False, 1234)
            mock_ctypes.windll.kernel32.CloseHandle.assert_called_once_with(mock_handle)

    @patch("sys.platform", "win32")
    def test_dead_process(self):
        """Returns False when OpenProcess returns None/0."""
        with patch.dict("sys.modules", {"ctypes": MagicMock()}):
            mock_ctypes = sys.modules["ctypes"]
            mock_ctypes.windll.kernel32.OpenProcess.return_value = None

            assert _is_process_alive(1234) is False
            mock_ctypes.windll.kernel32.CloseHandle.assert_not_called()

    @patch("sys.platform", "win32")
    def test_zero_handle(self):
        """Returns False when OpenProcess returns 0."""
        with patch.dict("sys.modules", {"ctypes": MagicMock()}):
            mock_ctypes = sys.modules["ctypes"]
            mock_ctypes.windll.kernel32.OpenProcess.return_value = 0

            assert _is_process_alive(1234) is False


class TestIsProcessAliveUnix:
    """Test _is_process_alive on Unix."""

    @patch("sys.platform", "linux")
    def test_alive_process(self):
        """Returns True when os.kill doesn't raise."""
        with patch.dict("sys.modules", {"os": MagicMock()}):
            mock_os = sys.modules["os"]

            assert _is_process_alive(1234) is True
            mock_os.kill.assert_called_once_with(1234, 0)

    @patch("sys.platform", "linux")
    def test_dead_process(self):
        """Returns False when os.kill raises ProcessLookupError."""
        with patch.dict("sys.modules", {"os": MagicMock()}):
            mock_os = sys.modules["os"]
            mock_os.kill.side_effect = ProcessLookupError()

            assert _is_process_alive(1234) is False
            mock_os.kill.assert_called_once_with(1234, 0)

    @patch("sys.platform", "linux")
    def test_permission_denied_returns_alive(self):
        """Returns True when os.kill raises PermissionError (process exists)."""
        with patch.dict("sys.modules", {"os": MagicMock()}):
            mock_os = sys.modules["os"]
            mock_os.kill.side_effect = PermissionError()

            assert _is_process_alive(1234) is True
