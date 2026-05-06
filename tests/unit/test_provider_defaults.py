"""Tests for zima/providers/defaults.py — default provider resolver."""


class TestGetDefaultProviderName:
    def test_returns_github_by_default(self, monkeypatch):
        """Without env var, default is github."""
        monkeypatch.delenv("ZIMA_GIT_REPO_PROVIDER", raising=False)
        from zima.providers.defaults import get_default_provider_name

        assert get_default_provider_name() == "github"

    def test_returns_env_var_when_set(self, monkeypatch):
        """With env var set, returns its value."""
        monkeypatch.setenv("ZIMA_GIT_REPO_PROVIDER", "gitlab")
        from zima.providers.defaults import get_default_provider_name

        assert get_default_provider_name() == "gitlab"

    def test_returns_empty_string_if_env_var_empty(self, monkeypatch):
        """Empty env var is treated as a valid provider name."""
        monkeypatch.setenv("ZIMA_GIT_REPO_PROVIDER", "")
        from zima.providers.defaults import get_default_provider_name

        assert get_default_provider_name() == ""


class TestIsDefaultProvider:
    def test_github_is_default_when_no_env(self, monkeypatch):
        """Without env var, 'github' is the default."""
        monkeypatch.delenv("ZIMA_GIT_REPO_PROVIDER", raising=False)
        from zima.providers.defaults import is_default_provider

        assert is_default_provider("github") is True
        assert is_default_provider("gitlab") is False

    def test_custom_default_matches_env(self, monkeypatch):
        """With env var, the env value is the default."""
        monkeypatch.setenv("ZIMA_GIT_REPO_PROVIDER", "gitlab")
        from zima.providers.defaults import is_default_provider

        assert is_default_provider("gitlab") is True
        assert is_default_provider("github") is False
