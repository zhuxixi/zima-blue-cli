from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["ActionProvider"]


class ActionProvider(ABC):
    """Platform-agnostic action provider for post-exec automation."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier, e.g. 'github', 'gitlab'."""

    @abstractmethod
    def add_label(self, repo: str, issue: str, label: str) -> None:
        """Add label to issue/MR."""

    @abstractmethod
    def remove_label(self, repo: str, issue: str, label: str) -> None:
        """Remove label from issue/MR."""

    @abstractmethod
    def post_comment(self, repo: str, issue: str, body: str) -> None:
        """Post comment on issue/MR."""

    @abstractmethod
    def fetch_diff(self, repo: str, issue: str) -> str:
        """Fetch PR/MR diff content. Returns empty string on failure."""

    @abstractmethod
    def scan_prs(self, repo: str, label: str) -> list[dict]:
        """Scan PRs by label.

        Args:
            repo: Repository in "owner/repo" format.
            label: Label to filter by.

        Returns:
            List of PR dictionaries with at least 'number', 'title', 'url'.
        """
        raise NotImplementedError
