"""Tests for smee.io client."""

import json

from zima.webhook.smee import parse_smee_event


class TestParseSmeeEvent:
    """Tests for parsing smee SSE data lines."""

    def test_parse_data_event(self):
        """Parse a valid SSE data line."""
        payload = {"action": "labeled", "label": {"name": "zima:needs-review"}}
        line = "data: " + json.dumps(payload)
        event = parse_smee_event(line)
        assert event == payload

    def test_parse_empty_line(self):
        """Empty line returns None."""
        assert parse_smee_event("") is None

    def test_parse_non_data_line(self):
        """Non-data SSE line returns None."""
        assert parse_smee_event("id: 123") is None

    def test_parse_invalid_json(self):
        """Invalid JSON returns None."""
        assert parse_smee_event("data: not-json") is None
