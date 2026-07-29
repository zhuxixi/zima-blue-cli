"""Action provider adapters (e.g. the GitHub provider).

Concrete providers live in their own modules (``zima.providers.github``) and are
registered with :class:`~zima.actions.registry.ProviderRegistry` via the
``zima.action_providers`` entry-point group declared in ``pyproject.toml``.
"""

from __future__ import annotations
