#!/usr/bin/env python3
"""一次性迁移：~/.claude/github-issue-driven → ~/.github-issue-driven（issue #259）。

用法：
    python scripts/migrate_issue_driven_home.py [--dry-run]

默认新路径 ~/.github-issue-driven（可用 GITHUB_ISSUE_DRIVEN_HOME 覆盖）；
迁移后旧路径留符号链接。删除旧路径请用 `unlink`，禁止 `rm -rf <dir>/`
（带斜杠会穿透符号链接删真实数据）。
"""

from __future__ import annotations

import argparse
import os
import shutil
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


def classify(path: Path, new: Path) -> State:
    """IO 只读：判定 path 相对 new 的四态之一。

    判定顺序（「不存在」指无目录项，悬空符号链接也算存在）：
      1. 无任何目录项 → ``absent``；
      2. 符号链接 → 目标 ``Path.resolve()`` 后等于 new（两侧都 resolve，
         防相对链接误判）→ ``symlink_to_new``，否则 ``symlink_other``
         （悬空链接也归此类）；
      3. 目录 → ``dir``；
      4. 存在但既非目录也非符号链接（普通文件等异常态）→ ``symlink_other``
         （语义 = 异常态，决策表一律 conflict）。
    """
    if not (path.exists() or path.is_symlink()):
        return "absent"
    if path.is_symlink():
        if path.resolve() == new.resolve():
            return "symlink_to_new"
        return "symlink_other"
    if path.is_dir():
        return "dir"
    return "symlink_other"


def inspect_paths(legacy: Path, new: Path) -> tuple[State, State]:
    """IO 只读：同时探测两侧状态，返回 ``(legacy_state, new_state)``。"""
    return classify(legacy, new), classify(new, new)


def apply_action(action: Action, legacy: Path, new: Path) -> int:
    """执行决策表动作，返回退出码：0 成功/无操作，2 conflict。

    - ``migrate``：先 ``mkdir(parents=True, exist_ok=True)`` 确保旧路径父目录
      存在，再 ``Path.rename``（同文件系统，捕获 ``OSError`` 退
      ``shutil.move``），最后 ``os.symlink(new, legacy)`` 回填符号链接；
    - ``conflict``：只打印两侧诊断（含各自状态），零写操作，返回 2；
    - ``noop_*``：只打印一行说明，零写操作，返回 0。
    """
    print(describe_action(action, legacy, new))
    if action == "migrate":
        legacy.parent.mkdir(parents=True, exist_ok=True)
        try:
            legacy.rename(new)
        except OSError:
            shutil.move(str(legacy), str(new))
        os.symlink(new, legacy)
        return 0
    if action == "conflict":
        legacy_state, new_state = inspect_paths(legacy, new)
        print(f"  legacy state: {legacy_state}")
        print(f"  new state: {new_state}")
        print("  no filesystem changes made; resolve manually, then re-run.")
        return 2
    return 0  # noop_fresh / noop_migrated


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：解析参数、探测状态、按决策表执行。

    Returns:
        0 成功或无操作；2 conflict（含 ``--dry-run`` 下的 conflict）。
    """
    parser = argparse.ArgumentParser(
        prog="migrate_issue_driven_home.py",
        description=(
            "迁移 ~/.claude/github-issue-driven → ~/.github-issue-driven（issue #259），"
            "迁移后旧路径留符号链接。"
        ),
        epilog=(
            "警告：删除旧路径请用 `unlink`，禁止 `rm -rf <dir>/`"
            "（带斜杠会穿透符号链接删真实数据）。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印决策，不做任何写操作")
    args = parser.parse_args(argv)

    new = resolve_home(os.environ.get(ENV_VAR), Path.home())
    legacy = LEGACY_HOME
    legacy_state, new_state = inspect_paths(legacy, new)
    action = resolve_action(legacy_state, new_state)
    if args.dry_run:
        print(describe_action(action, legacy, new))
        return 2 if action == "conflict" else 0
    return apply_action(action, legacy, new)


if __name__ == "__main__":
    raise SystemExit(main())
