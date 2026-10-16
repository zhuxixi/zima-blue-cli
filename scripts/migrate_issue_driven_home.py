#!/usr/bin/env python3
"""一次性迁移：~/.claude/github-issue-driven → ~/.github-issue-driven（issue #259）。

用法：
    python scripts/migrate_issue_driven_home.py [--dry-run]

默认新路径 ~/.github-issue-driven（可用 GITHUB_ISSUE_DRIVEN_HOME 覆盖）；
迁移后旧路径留符号链接。删除旧路径请用 `unlink`，禁止 `rm -rf <dir>/`
（带斜杠会穿透符号链接删真实数据）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

ENV_VAR = "GITHUB_ISSUE_DRIVEN_HOME"
DEFAULT_DIRNAME = ".github-issue-driven"
# 旧路径的唯一权威定义（文档中一律称「迁移前的旧路径」）
LEGACY_HOME = Path.home() / ".claude" / "github-issue-driven"

State = Literal["absent", "dir", "symlink_to_new", "symlink_other"]
Action = Literal["migrate", "noop_migrated", "noop_fresh", "conflict"]

# 决策表：显式写死 6 个语义格 + symlink_other 行展开的 4 格；
# 其余组合（×symlink_to_new / ×symlink_other 行）未列出，一律兜底 conflict。
_TABLE: dict[tuple[str, str], Action] = {
    ("absent", "absent"): "noop_fresh",
    ("absent", "dir"): "noop_migrated",
    ("dir", "absent"): "migrate",
    ("dir", "dir"): "conflict",
    ("symlink_to_new", "dir"): "noop_migrated",
    ("symlink_to_new", "absent"): "conflict",
    ("symlink_other", "absent"): "conflict",
    ("symlink_other", "dir"): "conflict",
    ("symlink_other", "symlink_to_new"): "conflict",
    ("symlink_other", "symlink_other"): "conflict",
}


def resolve_home(env_value: str | None, home: Path) -> Path:
    """env 非空 → 该路径；否则 home/DEFAULT_DIRNAME（纯函数）。"""
    if env_value:
        return Path(env_value).expanduser()
    return home / DEFAULT_DIRNAME


def resolve_action(legacy: State, new: State) -> Action:
    """4×4 全组合决策（纯函数）；未列出组合一律 conflict。"""
    return _TABLE.get((legacy, new), "conflict")


def describe_action(action: Action, legacy: Path, new: Path) -> str:
    """首行契约 `<action>: <legacy> -> <new>`；migrate 附 unlink 警告句。"""
    head = f"{action}: {legacy} -> {new}"
    if action == "migrate":
        return (
            f"{head}\n"
            f"  plan: mv {legacy} {new} && ln -s {new} {legacy}\n"
            "  warning: 删除旧路径请用 `unlink`，禁止 `rm -rf <dir>/`"
            "（带斜杠会穿透符号链接删真实数据）"
        )
    if action == "noop_migrated":
        return f"{head}\n  already migrated; nothing to do."
    if action == "noop_fresh":
        return f"{head}\n  fresh install; nothing to migrate."
    return f"{head}\n  conflict: both sides hold real data; resolve manually."
