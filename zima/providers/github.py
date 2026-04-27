"""GitHub action provider using gh CLI."""

from __future__ import annotations

import subprocess

from zima.actions.base import ActionProvider


class GitHubProvider(ActionProvider):
    """GitHub action provider using gh CLI."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "github"

    def _run(
        self, args: list[str], check: bool = True, capture: bool = True
    ) -> subprocess.CompletedProcess:
        cmd = ["gh"] + args
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=self.timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"gh CLI failed: {' '.join(cmd)}\nstderr: {result.stderr.strip()}")
        return result

    def add_label(self, repo: str, issue: str, label: str) -> None:
        """Add a label to a GitHub issue or PR.

        Args:
            repo: Repository in "owner/repo" format.
            issue: Issue or PR number.
            label: Label name to add.

        Raises:
            RuntimeError: If the gh CLI command fails.
        """
        self._run(["issue", "edit", issue, "--add-label", label, "--repo", repo])

    def remove_label(self, repo: str, issue: str, label: str) -> None:
        """Remove a label from a GitHub issue or PR.

        Args:
            repo: Repository in "owner/repo" format.
            issue: Issue or PR number.
            label: Label name to remove.

        Raises:
            RuntimeError: If the gh CLI command fails.
        """
        self._run(["issue", "edit", issue, "--remove-label", label, "--repo", repo])

    def post_comment(self, repo: str, issue: str, body: str) -> None:
        """Post a comment on a GitHub issue or PR.

        Args:
            repo: Repository in "owner/repo" format.
            issue: Issue or PR number.
            body: Comment body text.

        Raises:
            RuntimeError: If the gh CLI command fails.
        """
        self._run(["issue", "comment", issue, "--body", body, "--repo", repo])

    def fetch_diff(self, repo: str, issue: str) -> str:
        """Fetch the diff patch for a GitHub PR.

        Args:
            repo: Repository in "owner/repo" format.
            issue: PR number.

        Returns:
            The diff patch as a string, or empty string on failure.
        """
        result = self._run(
            ["pr", "view", issue, "--repo", repo, "--patch"],
            capture=True,
            check=False,
        )
        return result.stdout if result.returncode == 0 else ""
