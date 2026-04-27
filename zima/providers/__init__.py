from __future__ import annotations

from zima.actions.base import ActionProvider
from zima.providers.github import GitHubProvider

BUILTIN_PROVIDERS: dict[str, type[ActionProvider]] = {
    "github": GitHubProvider,
}
