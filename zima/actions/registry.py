from __future__ import annotations

import importlib.metadata
from typing import Optional

from zima.actions.base import ActionProvider
from zima.actions.exceptions import ProviderNotFoundError


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, ActionProvider] = {}
        self._load_builtin()
        self._discover_entry_points()

    def _load_builtin(self) -> None:
        from zima.providers import BUILTIN_PROVIDERS

        for name, cls in BUILTIN_PROVIDERS.items():
            self._providers[name] = cls()

    def _discover_entry_points(self) -> None:
        try:
            eps = importlib.metadata.entry_points(group="zima.action_providers")
        except (AttributeError, TypeError):
            try:
                all_eps = importlib.metadata.entry_points()
                eps = all_eps.get("zima.action_providers", [])
            except Exception:
                eps = []

        for ep in eps:
            try:
                cls = ep.load()
                instance = cls()
                self._providers[instance.name] = instance  # external overrides builtin
            except Exception as e:
                print(f"Warning: Failed to load provider from {ep.name}: {e}")

    def get(self, name: str) -> ActionProvider:
        if name not in self._providers:
            raise ProviderNotFoundError(
                f"Provider '{name}' not found. " f"Available: {sorted(self._providers.keys())}"
            )
        return self._providers[name]

    def list(self) -> list[str]:
        return list(self._providers.keys())


_default_registry: Optional[ProviderRegistry] = None


def get_default_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ProviderRegistry()
    return _default_registry


def reset_registry() -> None:
    global _default_registry
    _default_registry = None
