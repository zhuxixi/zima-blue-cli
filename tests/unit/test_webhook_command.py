"""Tests for the webhook-server command entry helpers."""

import sys

from zima.commands.webhook import _enable_line_buffered_stdout


class TestEnableLineBufferedStdout:
    """stdout must be line-buffered so [webhook] logs reach journald in
    real time (block buffering hid them under systemd)."""

    def test_reconfigure_called(self, monkeypatch):
        class FakeStdout:
            def __init__(self):
                self.calls = []

            def reconfigure(self, **kwargs):
                self.calls.append(kwargs)

        fake = FakeStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        _enable_line_buffered_stdout()
        assert fake.calls == [{"line_buffering": True}]

    def test_tolerates_unconfigurable_stdout(self, monkeypatch):
        class BrokenStdout:
            def reconfigure(self, **kwargs):
                raise ValueError("I/O operation on closed file")

        monkeypatch.setattr(sys, "stdout", BrokenStdout())
        _enable_line_buffered_stdout()  # must not raise
