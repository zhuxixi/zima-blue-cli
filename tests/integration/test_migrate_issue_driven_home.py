"""Integration tests for migrate_issue_driven_home IO/CLI layer (A3).

每个用例都在 tmp_path 隔离 HOME 下真实执行 main()（或脚本子进程），
并断言文件系统最终状态，而非仅 stdout。绝不触碰真实 $HOME。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.migrate_issue_driven_home as mig
from scripts.migrate_issue_driven_home import ENV_VAR, classify, inspect_paths, main

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "migrate_issue_driven_home.py"

DEFAULT_NEW_NAME = ".github-issue-driven"


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔离 HOME：posix 的 $HOME + Windows 的 USERPROFILE/HOMEDRIVE/HOMEPATH
    （`Path.home()` 在 ntpath 下只认后三者，从不读 $HOME）+ 模块常量 LEGACY_HOME
    （import 时已固化）。不隔离 Windows 变量会让测试逃逸沙箱，把 tmp 里的旧目录
    搬进真实用户主目录（CR #261 issue-1）。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setattr(mig, "LEGACY_HOME", tmp_path / ".claude" / "github-issue-driven")
    return tmp_path


def make_legacy(filename: str = "issue-1.md", content: str = "data") -> Path:
    """在 LEGACY_HOME 下放一个带文件的旧目录。"""
    legacy = mig.LEGACY_HOME
    legacy.mkdir(parents=True)
    (legacy / filename).write_text(content, encoding="utf-8")
    return legacy


def tree_snapshot(root: Path) -> list[str]:
    """os.walk 排序快照：目录与文件条目（符号链接附目标），不跟随链接。"""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(dirnames):
            out.append(f"dir: {Path(dirpath) / name}")
        for name in sorted(filenames):
            entry = Path(dirpath) / name
            suffix = f" -> {os.readlink(entry)}" if entry.is_symlink() else ""
            out.append(f"file: {entry}{suffix}")
    return sorted(out)


class TestClassifyOnRealFS:
    """classify 的五态只读分类（含普通文件异常态映射）。"""

    def test_absent(self, tmp_home):
        assert classify(tmp_home / "nowhere", tmp_home / "new") == "absent"

    def test_dir(self, tmp_home):
        d = tmp_home / "real-dir"
        d.mkdir()
        assert classify(d, tmp_home / "new") == "dir"

    def test_symlink_to_new(self, tmp_home):
        new = tmp_home / "new"
        new.mkdir()
        link = tmp_home / "link"
        os.symlink(new, link)
        assert classify(link, new) == "symlink_to_new"

    def test_symlink_other(self, tmp_home):
        elsewhere = tmp_home / "elsewhere"
        elsewhere.mkdir()
        link = tmp_home / "link"
        os.symlink(elsewhere, link)
        assert classify(link, tmp_home / "new") == "symlink_other"

    def test_plain_file_maps_to_symlink_other(self, tmp_home):
        # 异常态：普通文件（既非目录也非符号链接）→ symlink_other（→ conflict）
        f = tmp_home / "plain-file"
        f.write_text("not a dir", encoding="utf-8")
        assert classify(f, tmp_home / "new") == "symlink_other"

    def test_inspect_paths_returns_both_states(self, tmp_home):
        make_legacy()
        new = tmp_home / DEFAULT_NEW_NAME
        new.mkdir()
        assert inspect_paths(mig.LEGACY_HOME, new) == ("dir", "dir")


class TestMainMigrate:
    """用例 1：migrate 真实迁移 + 用例 2：幂等。"""

    def test_migrate_moves_files_and_leaves_symlink(self, tmp_home, capsys):
        legacy = make_legacy()
        new = tmp_home / DEFAULT_NEW_NAME

        assert main([]) == 0

        assert (new / "issue-1.md").read_text(encoding="utf-8") == "data"
        assert legacy.is_symlink()
        assert legacy.resolve() == new.resolve()
        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line.startswith("migrate: ")

    def test_second_run_is_noop_migrated(self, tmp_home, capsys):
        make_legacy()
        assert main([]) == 0
        capsys.readouterr()
        new = tmp_home / DEFAULT_NEW_NAME
        link_target_before = os.readlink(mig.LEGACY_HOME)
        content_before = (new / "issue-1.md").read_text(encoding="utf-8")

        assert main([]) == 0

        out = capsys.readouterr().out
        assert out.splitlines()[0].startswith("noop_migrated: ")
        assert mig.LEGACY_HOME.is_symlink()
        assert os.readlink(mig.LEGACY_HOME) == link_target_before
        assert (new / "issue-1.md").read_text(encoding="utf-8") == content_before


class TestMainNoopFresh:
    """用例 3：fresh 安装——两侧皆无，不得创建任何东西。"""

    def test_noop_fresh_creates_nothing(self, tmp_home, capsys):
        assert main([]) == 0

        assert not (tmp_home / DEFAULT_NEW_NAME).exists()
        assert not mig.LEGACY_HOME.exists()
        assert not mig.LEGACY_HOME.parent.exists()  # ~/.claude 也不得创建
        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line.startswith("noop_fresh: ")


class TestMainConflict:
    """用例 4：conflict——退出码 2，零写操作。"""

    def test_both_dirs_conflict_leaves_sides_intact(self, tmp_home, capsys):
        legacy = make_legacy(filename="old.md", content="old")
        new = tmp_home / DEFAULT_NEW_NAME
        new.mkdir()
        (new / "new.md").write_text("new", encoding="utf-8")

        assert main([]) == 2

        assert legacy.is_dir()
        assert not legacy.is_symlink()
        assert sorted(p.name for p in legacy.iterdir()) == ["old.md"]
        assert (legacy / "old.md").read_text(encoding="utf-8") == "old"
        assert sorted(p.name for p in new.iterdir()) == ["new.md"]
        assert (new / "new.md").read_text(encoding="utf-8") == "new"
        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line.startswith("conflict: ")

    def test_plain_file_legacy_conflicts_without_changes(self, tmp_home, capsys):
        # 异常态：旧路径是普通文件 → symlink_other → conflict，原样保留
        legacy = mig.LEGACY_HOME
        legacy.parent.mkdir(parents=True)
        legacy.write_text("not a dir", encoding="utf-8")

        assert main([]) == 2

        assert legacy.is_file()
        assert not legacy.is_symlink()
        assert legacy.read_text(encoding="utf-8") == "not a dir"
        assert not (tmp_home / DEFAULT_NEW_NAME).exists()


class TestMainDryRun:
    """用例 5：--dry-run 只打印决策，文件系统零变化。"""

    def test_dry_run_migrate_touches_nothing(self, tmp_home, capsys):
        make_legacy()
        before = tree_snapshot(tmp_home)

        assert main(["--dry-run"]) == 0

        assert tree_snapshot(tmp_home) == before
        assert not mig.LEGACY_HOME.is_symlink()
        assert not (tmp_home / DEFAULT_NEW_NAME).exists()
        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line.startswith("migrate: ")

    def test_dry_run_conflict_exits_2_without_changes(self, tmp_home, capsys):
        make_legacy()
        new = tmp_home / DEFAULT_NEW_NAME
        new.mkdir()
        before = tree_snapshot(tmp_home)

        assert main(["--dry-run"]) == 2

        assert tree_snapshot(tmp_home) == before
        assert mig.LEGACY_HOME.is_dir()
        assert not mig.LEGACY_HOME.is_symlink()


class TestMainEnvOverride:
    """用例 6：GITHUB_ISSUE_DRIVEN_HOME 覆盖迁移目标。"""

    def test_env_redirects_target_and_skips_default(self, tmp_home, monkeypatch, capsys):
        make_legacy()
        custom = tmp_home / "custom"
        monkeypatch.setenv(ENV_VAR, str(custom))

        assert main([]) == 0

        assert (custom / "issue-1.md").read_text(encoding="utf-8") == "data"
        assert mig.LEGACY_HOME.is_symlink()
        assert mig.LEGACY_HOME.resolve() == custom.resolve()
        assert not (tmp_home / DEFAULT_NEW_NAME).exists()  # 默认路径不得被创建
        first_line = capsys.readouterr().out.splitlines()[0]
        assert first_line.startswith("migrate: ")


class TestMainRelativeEnvRejected:
    """review fix：env 覆盖为相对路径必须拒绝（rc=2、stderr 提示、零写操作）。"""

    def test_relative_env_exit_2_without_writes(self, tmp_home, monkeypatch, capsys):
        make_legacy()
        run_cwd = tmp_home / "run-cwd"
        run_cwd.mkdir()
        monkeypatch.chdir(run_cwd)  # 圈定相对路径的潜在落点，防止误写真实 cwd
        monkeypatch.setenv(ENV_VAR, "custom")
        home_before = tree_snapshot(tmp_home)

        assert main([]) == 2

        err = capsys.readouterr().err
        assert "must be an absolute path" in err
        assert "GITHUB_ISSUE_DRIVEN_HOME" in err
        assert tree_snapshot(tmp_home) == home_before  # tmp HOME 零新增目录/符号链接
        assert list(run_cwd.iterdir()) == []  # cwd 下也无 custom/ 目录


class TestHelpSubprocess:
    """用例 7：--help 子进程（真实脚本进程，--help 不做任何 IO）。"""

    def test_help_contains_unlink_and_rm_rf_warning(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0
        assert "unlink" in proc.stdout
        assert "rm -rf" in proc.stdout


class TestTmpHomeIsolation:
    """CR #261 issue-1：Windows 上 `Path.home()`（ntpath.expanduser）只认
    USERPROFILE / HOMEDRIVE+HOMEPATH，从不读 $HOME——不隔离就会逃逸沙箱。"""

    def test_home_env_vars_are_isolated(self, tmp_home):
        assert os.environ["HOME"] == str(tmp_home)
        assert os.environ["USERPROFILE"] == str(tmp_home)
        assert "HOMEDRIVE" not in os.environ
        assert "HOMEPATH" not in os.environ


class TestSymlinkFailure:
    """CR #261 issue-2：rename 成功但 os.symlink 失败（如 Windows 未开开发者模式的 EPERM）
    → 非 0 退出 + 补救指引，数据已在新位置，不静默假成功。"""

    def test_symlink_failure_returns_nonzero_with_guidance(self, tmp_home, monkeypatch, capsys):
        legacy = make_legacy()

        def boom(*args, **kwargs):
            raise OSError(1, "operation not permitted")

        monkeypatch.setattr(mig.os, "symlink", boom)
        rc = mig.main([])

        assert rc != 0
        err = capsys.readouterr().err
        assert "could not be created" in err
        assert "create it manually" in err
        new = tmp_home / DEFAULT_NEW_NAME
        assert (new / "issue-1.md").read_text(encoding="utf-8") == "data"  # 数据已迁到位
        assert not legacy.exists() and not legacy.is_symlink()  # 但链接未建成
