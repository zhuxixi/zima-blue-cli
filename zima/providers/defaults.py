"""Default provider resolution via environment variable."""

from __future__ import annotations

import os

DEFAULT_PROVIDER_ENV = "ZIMA_GIT_REPO_PROVIDER"
_FALLBACK_PROVIDER = "github"


def get_default_provider_name() -> str:
    """Return the default action provider name.

    Reads ``ZIMA_GIT_REPO_PROVIDER`` env var, falling back to ``"github"``.
    """
    return os.environ.get(DEFAULT_PROVIDER_ENV, _FALLBACK_PROVIDER)


def is_default_provider(name: str) -> bool:
    """Return True if *name* matches the resolved default provider."""
    return name == get_default_provider_name()
