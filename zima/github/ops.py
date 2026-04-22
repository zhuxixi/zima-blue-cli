from __future__ import annotations

import json
import subprocess


class GitHubOps:
    """Wrapper for GitHub CLI operations used by PJob actions."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _run(
        self, args: list[str], check: bool = True, capture: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a gh CLI command."""
        cmd = ["gh"] + args
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"GitHub CLI failed: {' '.join(cmd)}\n"
                f"stderr: {result.stderr.strip()}"
            )
        return result

    def add_label(self, repo: str, number: int, label: str) -> None:
        """Add a label to an issue or PR."""
        self._run(
            ["issue", "edit", str(number), "--add-label", label, "--repo", repo]
        )

    def remove_label(self, repo: str, number: int, label: str) -> None:
        """Remove a label from an issue or PR."""
        self._run(
            ["issue", "edit", str(number), "--remove-label", label, "--repo", repo]
        )

    def post_comment(self, repo: str, number: int, body: str) -> None:
        """Post a comment on an issue or PR."""
        self._run(
            ["issue", "comment", str(number), "--body", body, "--repo", repo]
        )

    def fetch_pr_diff(self, repo: str, number: int) -> str:
        """Fetch PR diff as text."""
        result = self._run(
            ["pr", "view", str(number), "--repo", repo, "--patch"],
            capture=True,
        )
        return result.stdout

    def fetch_issue_body(self, repo: str, number: int) -> str:
        """Fetch issue body as text."""
        result = self._run(
            ["issue", "view", str(number), "--repo", repo, "--json", "body"],
            capture=True,
        )
        data = json.loads(result.stdout)
        return data.get("body", "")
