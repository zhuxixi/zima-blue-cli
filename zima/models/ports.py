"""Ports (abstract interfaces) consumed by the domain layer.

These Protocols let ``zima.models`` depend on abstractions instead of on the
concrete adapters living in outer layers (``zima.config``, ``zima.execution``,
``zima.providers``), keeping the dependency direction pointing inward.
"""

from __future__ import annotations

from typing import Protocol


class ConfigStore(Protocol):
    """Read-only access to persisted configuration entities.

    The domain layer needs only to check existence and load configs by
    ``(kind, code)``. ``zima.config.manager.ConfigManager`` satisfies this
    structurally; tests may pass any conforming object (e.g. a ``Mock``).
    """

    def config_exists(self, kind: str, code: str) -> bool: ...

    def load_config(self, kind: str, code: str) -> dict: ...
