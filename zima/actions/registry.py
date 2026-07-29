from __future__ import annotations

import importlib.metadata
import threading
from typing import Optional

from zima.actions.base import ActionProvider
from zima.actions.exceptions import ProviderNotFoundError


class ProviderRegistry:
    """Manages action providers discovered via the ``zima.action_providers`` group.

    Built-in providers (e.g. ``github``) are declared as entry points in
    ``pyproject.toml`` and discovered the same way as external ones, so this
    module never imports the concrete ``zima.providers`` package. A later
    entry point overrides an earlier one registering the same provider name.
    """

    def __init__(self):
        self._providers: dict[str, ActionProvider] = {}
        self._discover_entry_points()

    def _discover_entry_points(self) -> None:
        """Discover and register providers via ``zima.action_providers`` entry points."""
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
        """Get a registered provider by name.

        Args:
            name: Provider identifier (e.g. ``"github"``).

        Returns:
            The matching ``ActionProvider`` instance.

        Raises:
            ProviderNotFoundError: If no provider with the given name is registered.
        """
        if name not in self._providers:
            raise ProviderNotFoundError(
                f"Provider '{name}' not found. " f"Available: {sorted(self._providers.keys())}"
            )
        return self._providers[name]

    def list(self) -> list[str]:
        """List names of all registered providers.

        Returns:
            Sorted list of provider identifiers.
        """
        return list(self._providers.keys())


_default_registry: Optional[ProviderRegistry] = None
_registry_lock = threading.RLock()


def get_default_registry() -> ProviderRegistry:
    """Return the singleton ``ProviderRegistry`` instance.

    Creates the registry on first call. Thread-safe via ``RLock``.
    """
    global _default_registry
    with _registry_lock:
        if _default_registry is None:
            _default_registry = ProviderRegistry()
        return _default_registry


def reset_registry() -> None:
    """Reset the singleton registry. For testing only."""
    global _default_registry
    _default_registry = None
