"""Quickstart wizard command - creates all configs from scratch."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console

from zima.config.manager import ConfigManager

console = Console(legacy_windows=False, force_terminal=True)

AGENT_CHOICES: dict[str, str] = {
    "kimi": "kimi-code-cli (月之暗面)",
    "claude": "claude-code (Anthropic)",
}


def _detect_git_repo() -> Optional[str]:
    """Detect if current directory is a git repo. Returns path or None."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
        return str(Path.cwd())
    except Exception:
        return None


def _scan_github_prs(label: str = "need-review") -> list[dict]:
    """Scan GitHub for open PRs with given label. Returns display-only results."""
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--label",
                label,
                "--json",
                "number,title,url",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except Exception:
        return []


def _generate_unique_code(base: str, manager: ConfigManager, kind: str) -> str:
    """Generate a unique config code, appending -N if needed."""
    code = base
    suffix = 2
    while manager.config_exists(kind, code):
        code = f"{base}-{suffix}"
        suffix += 1
    return code
