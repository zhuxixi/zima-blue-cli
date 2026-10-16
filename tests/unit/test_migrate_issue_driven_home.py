"""Unit tests for scripts.migrate_issue_driven_home pure functions (A2)."""

from pathlib import Path

import pytest

from scripts.migrate_issue_driven_home import (
    DEFAULT_DIRNAME,
    Action,
    State,
    describe_action,
    resolve_action,
    resolve_home,
)

HOME = Path("/home/tester")


class TestResolveHome:
    @pytest.mark.parametrize(
        "env,expected",
        [
            ("/tmp/custom", Path("/tmp/custom")),  # env 有值 → 用它
            ("", HOME / DEFAULT_DIRNAME),  # 空串 → 默认
            (None, HOME / DEFAULT_DIRNAME),  # None → 默认
        ],
    )
    def test_three_states(self, env, expected):
        assert resolve_home(env, HOME) == expected


EXPECTED = {
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
    ("absent", "symlink_to_new"): "conflict",
    ("absent", "symlink_other"): "conflict",
    ("dir", "symlink_to_new"): "conflict",
    ("dir", "symlink_other"): "conflict",
    ("symlink_to_new", "symlink_to_new"): "conflict",
    ("symlink_to_new", "symlink_other"): "conflict",
}


class TestResolveAction:
    @pytest.mark.parametrize("legacy,new", sorted(EXPECTED))
    def test_all_16_combinations(self, legacy: State, new: State):
        assert resolve_action(legacy, new) == EXPECTED[(legacy, new)]

    def test_every_combination_defined(self):
        assert len(EXPECTED) == 16, "决策表必须覆盖 4×4 全部组合"


class TestDescribeAction:
    @pytest.mark.parametrize("action", ["migrate", "noop_migrated", "noop_fresh", "conflict"])
    def test_first_line_contract(self, action: Action):
        line = describe_action(action, Path("/old"), Path("/new")).splitlines()[0]
        assert line.startswith(f"{action}:")

    def test_migrate_warns_about_unlink(self):
        out = describe_action("migrate", Path("/old"), Path("/new"))
        assert "unlink" in out
        assert "rm -rf" in out
