#!/usr/bin/env python3
"""auto-merge-guarded: auto approve + squash merge after CR convergence.

Whitelisted collaborators' PRs are merged automatically once CI required
checks are green and the Zima CR round has safely converged.  Scheduled by
cron every 45 minutes.  All secrets live outside this file (Pushover keys
in ~/.config/claude-notify.json, GitHub auth via the gh CLI login state).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoConfig:
    """Per-repo rules loaded from auto-merge.yaml."""

    allow_authors: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    expected_failing_checks: list[str] = field(default_factory=list)
    merge_method: str = "squash"
    delete_branch: bool = True
    sensitive_paths: list[str] = field(default_factory=list)
    cr_pjob_code: str = ""


@dataclass
class AppConfig:
    """Top-level config loaded from auto-merge.yaml."""

    enabled: bool = True
    pushover_config_file: str = "~/.config/claude-notify.json"
    repos: dict[str, RepoConfig] = field(default_factory=dict)


def load_config(path: Path) -> AppConfig:
    """Load auto-merge.yaml into an AppConfig.  Raises FileNotFoundError."""
    data = json.loads(json.dumps(_read_yaml(path)))
    cfg = AppConfig()
    cfg.enabled = bool(data.get("enabled", True))
    pushover = data.get("pushover") or {}
    cfg.pushover_config_file = pushover.get("config_file", cfg.pushover_config_file)
    for repo_name, repo_data in (data.get("repos") or {}).items():
        cfg.repos[repo_name] = RepoConfig(
            allow_authors=list(repo_data.get("allow_authors") or []),
            required_checks=list(repo_data.get("required_checks") or []),
            expected_failing_checks=list(repo_data.get("expected_failing_checks") or []),
            merge_method=repo_data.get("merge_method", "squash"),
            delete_branch=bool(repo_data.get("delete_branch", True)),
            sensitive_paths=list(repo_data.get("sensitive_paths") or []),
            cr_pjob_code=repo_data.get("cr_pjob_code", ""),
        )
    return cfg


def _read_yaml(path: Path) -> dict:
    """Minimal YAML subset parser: flat key/value maps and lists of scalars.

    The config schema only needs nested dicts and scalar lists, so a tiny
    indentation-based parser avoids a third-party dependency.  Raises
    FileNotFoundError when the file is missing.
    """
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if ":" in content:
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                child: dict = {}
                parent[key] = child
                stack.append((indent, child))
            elif value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                parent[key] = [
                    item.strip().strip("'\"") for item in inner.split(",") if item.strip()
                ]
            else:
                parent[key] = _scalar(value)
    return root


def _scalar(value: str):
    """Coerce a YAML scalar string to bool/int/float/str."""
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip("'\"")


class AuditLogger:
    """Append-only JSONL audit log."""

    def __init__(self, path: Path):
        self.path = path

    def log(self, entry: dict) -> None:
        """Append one JSON object as a single line."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
