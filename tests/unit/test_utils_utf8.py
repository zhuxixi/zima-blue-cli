"""Unit tests for utils bug fixes (#16)."""

import sys

from zima.utils import setup_windows_utf8


class TestSetupWindowsUtf8:
    """Test setup_windows_utf8() for issue #16."""

    def test_idempotent(self):
        """Calling twice should not raise."""
        setup_windows_utf8()
        setup_windows_utf8()  # Should not raise

    def test_noop_on_non_windows(self, monkeypatch):
        """On non-Windows, function should return without modifying anything."""
        monkeypatch.setattr(sys, "platform", "linux")
        # Should not raise even if stdout/stderr don't support reconfigure
        setup_windows_utf8()

    def test_handles_no_reconfigure(self, monkeypatch):
        """Should handle streams without reconfigure method gracefully."""
        # Save originals
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr

        class FakeStream:
            """A stream without reconfigure method."""

            pass

        try:
            if sys.platform == "win32":
                sys.stdout = FakeStream()
                sys.stderr = FakeStream()
                setup_windows_utf8()  # Should not raise
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
