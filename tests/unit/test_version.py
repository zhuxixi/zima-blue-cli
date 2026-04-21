"""Unit tests for version helper."""

from zima import get_version


class TestGetVersion:
    def test_returns_non_empty_string(self):
        result = get_version()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_valid_semver_format(self):
        result = get_version()
        # Either a semver like "0.1.1" or "unknown" for uninstalled package
        parts = result.split(".")
        if result != "unknown":
            assert len(parts) >= 2, f"Expected semver, got: {result}"

    def test_fallback_on_missing_package(self, monkeypatch):
        """Verify 'unknown' fallback when package metadata is not found."""
        import importlib.metadata

        def _raise(name):
            raise importlib.metadata.PackageNotFoundError(name)

        monkeypatch.setattr(importlib.metadata, "version", _raise)
        assert get_version() == "unknown"