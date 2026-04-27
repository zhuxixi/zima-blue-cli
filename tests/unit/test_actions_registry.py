from unittest.mock import MagicMock, patch

import pytest

from zima.actions.exceptions import ProviderNotFoundError
from zima.actions.registry import ProviderRegistry, get_default_registry, reset_registry
from zima.providers.github import GitHubProvider


class TestProviderRegistry:
    def test_builtin_github_loaded(self):
        registry = ProviderRegistry()
        providers = registry.list()
        assert "github" in providers

    def test_get_github(self):
        registry = ProviderRegistry()
        provider = registry.get("github")
        assert isinstance(provider, GitHubProvider)
        assert provider.name == "github"

    def test_get_not_found_raises(self):
        registry = ProviderRegistry()
        with pytest.raises(ProviderNotFoundError, match="Provider 'missing' not found"):
            registry.get("missing")

    def test_external_provider_via_entry_points(self):
        mock_provider = MagicMock()
        mock_provider.name = "gitlab"

        mock_ep = MagicMock()
        mock_ep.name = "gitlab"
        mock_ep.load.return_value = lambda: mock_provider

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = [mock_ep]
            registry = ProviderRegistry()
            assert "gitlab" in registry.list()
            assert registry.get("gitlab") == mock_provider

    def test_external_override_builtin(self):
        mock_provider = MagicMock()
        mock_provider.name = "github"

        mock_ep = MagicMock()
        mock_ep.name = "github"
        mock_ep.load.return_value = lambda: mock_provider

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = [mock_ep]
            registry = ProviderRegistry()
            assert registry.get("github") == mock_provider

    def test_entry_point_load_failure_warns(self):
        mock_ep = MagicMock()
        mock_ep.name = "broken"
        mock_ep.load.side_effect = ImportError("no module")

        with patch("importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = [mock_ep]
            registry = ProviderRegistry()
            assert "broken" not in registry.list()
            assert "github" in registry.list()


class TestRegistrySingleton:
    def test_singleton(self):
        reset_registry()
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2

    def test_reset(self):
        reset_registry()
        r1 = get_default_registry()
        reset_registry()
        r2 = get_default_registry()
        assert r1 is not r2
