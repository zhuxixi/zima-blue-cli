"""Unit tests for utility functions."""

import os
from pathlib import Path

import pytest

from zima import utils


class TestValidateCode:
    """Test code format validation."""

    @pytest.mark.parametrize(
        "code,expected",
        [
            # Valid codes
            ("test-agent", True),
            ("myagent123", True),
            ("a-b-c", True),
            ("agent-v1-0", True),
            ("a", True),
            ("agent", True),
            ("my-123-agent", True),
            # Invalid codes - uppercase
            ("Test-Agent", False),
            ("TEST", False),
            ("MyAgent", False),
            # Invalid codes - special chars
            ("test_agent", False),  # underscore
            ("test.agent", False),  # dot
            ("test@agent", False),  # @
            ("test/agent", False),  # slash
            # Invalid codes - start/end
            ("123-agent", False),  # number start
            ("-test", False),  # hyphen start
            ("test-", False),  # hyphen end
            ("-test-", False),  # hyphen both
            # Invalid codes - other
            ("", False),  # empty
            ("a" * 65, False),  # too long (>64)
            ("test agent", False),  # space
        ],
    )
    def test_validate_code(self, code, expected):
        """Test various code formats."""
        result = utils.validate_code(code)
        assert result == expected, f"Code '{code}' should be {'valid' if expected else 'invalid'}"

    def test_validate_code_with_error_valid(self):
        """Test validate_code_with_error for valid code."""
        is_valid, error = utils.validate_code_with_error("valid-code")
        assert is_valid is True
        assert error == ""

    def test_validate_code_with_error_empty(self):
        """Test validate_code_with_error for empty code."""
        is_valid, error = utils.validate_code_with_error("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_code_with_error_too_long(self):
        """Test validate_code_with_error for long code."""
        is_valid, error = utils.validate_code_with_error("a" * 100)
        assert is_valid is False
        assert "too long" in error.lower()


class TestPathUtils:
    """Test path utility functions."""

    def test_get_zima_home_default(self, monkeypatch):
        """Test default ZIMA_HOME."""
        monkeypatch.delenv("ZIMA_HOME", raising=False)
        home = utils.get_zima_home()
        assert home == Path.home() / ".zima"

    def test_get_zima_home_from_env(self, monkeypatch, tmp_path):
        """Test ZIMA_HOME from environment variable."""
        test_path = str(tmp_path / "zima-test")
        monkeypatch.setenv("ZIMA_HOME", test_path)
        home = utils.get_zima_home()
        assert home == Path(test_path)

    def test_get_config_dir(self, monkeypatch, tmp_path):
        """Test config directory path."""
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        config_dir = utils.get_config_dir()
        assert config_dir == tmp_path / "configs"

    def test_ensure_dir_creates_directory(self, tmp_path):
        """Test ensure_dir creates directory."""
        test_dir = tmp_path / "new" / "nested" / "dir"
        result = utils.ensure_dir(test_dir)
        assert test_dir.exists()
        assert test_dir.is_dir()
        assert result == test_dir

    def test_ensure_dir_returns_existing(self, tmp_path):
        """Test ensure_dir returns existing directory."""
        existing = tmp_path / "existing"
        existing.mkdir()
        result = utils.ensure_dir(existing)
        assert result == existing


class TestAgentTypeValidation:
    """Test agent type validation."""

    @pytest.mark.parametrize(
        "agent_type,expected",
        [
            ("kimi", True),
            ("claude", True),
            ("gemini", True),
            ("invalid", False),
            ("KIMI", False),  # case sensitive
            ("", False),
        ],
    )
    def test_validate_agent_type(self, agent_type, expected):
        """Test agent type validation."""
        result = utils.validate_agent_type(agent_type)
        assert result == expected

    def test_get_valid_agent_types(self):
        """Test getting valid agent types."""
        types = utils.get_valid_agent_types()
        assert types == {"kimi", "claude", "gemini"}
        # Ensure it's a copy
        types.add("new")
        assert "new" not in utils.get_valid_agent_types()


class TestTimestamp:
    """Test timestamp utilities."""

    def test_generate_timestamp_format(self):
        """Test timestamp format."""
        ts = utils.generate_timestamp()
        # Should be ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
        assert len(ts) == 20
        assert ts.endswith("Z")
        assert "T" in ts

    def test_format_timestamp_valid(self):
        """Test formatting valid timestamp."""
        formatted = utils.format_timestamp("2026-03-26T14:30:00Z")
        assert "2026-03-26" in formatted
        assert "14:30" in formatted

    def test_format_timestamp_invalid(self):
        """Test formatting invalid timestamp."""
        result = utils.format_timestamp("invalid")
        assert result == "invalid"

    def test_format_timestamp_empty(self):
        """Test formatting empty timestamp."""
        result = utils.format_timestamp("")
        assert result == ""


class TestSafeDelete:
    """Test safe delete utility."""

    def test_safe_delete_file(self, tmp_path):
        """Test deleting file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = utils.safe_delete(test_file)
        assert result is True
        assert not test_file.exists()

    def test_safe_delete_directory(self, tmp_path):
        """Test deleting directory."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("test")

        result = utils.safe_delete(test_dir)
        assert result is True
        assert not test_dir.exists()

    def test_safe_delete_nonexistent(self, tmp_path):
        """Test deleting non-existent path."""
        result = utils.safe_delete(tmp_path / "nonexistent")
        assert result is True  # Returns True for non-existent


class TestSafePrint:
    """Test safe print utility."""

    def test_safe_print_ascii(self, capsys):
        """Test printing ASCII text."""
        utils.safe_print("Hello World")
        captured = capsys.readouterr()
        assert "Hello World" in captured.out

    def test_safe_print_unicode(self, capsys):
        """Test printing unicode text."""
        # This should not raise even if encoding issues exist
        utils.safe_print("Hello 世界 🚀")
        captured = capsys.readouterr()
        # Output may vary based on encoding, but should not crash
        assert "Hello" in captured.out or captured.out == ""


class TestIcon:
    """Test icon utility."""

    def test_icon_known(self):
        """Test getting known icon."""
        # On non-Windows, should return actual icon
        result = utils.icon("rocket")
        if os.name != "nt":
            assert result == "🚀"

    def test_icon_windows(self, monkeypatch):
        """Test icon returns empty on Windows."""
        monkeypatch.setattr(os, "name", "nt")
        result = utils.icon("rocket")
        assert result == ""

    def test_icon_unknown(self):
        """Test getting unknown icon."""
        result = utils.icon("unknown_icon")
        assert result == ""
