# Issue #259 留档目录迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 github-issue-driven 流程的调研/spec 留档目录从 `~/.claude/github-issue-driven/` 迁到 `~/.github-issue-driven/`，并用幂等迁移脚本 + 旧路径符号链接保证历史引用、CC 侧流程与跨仓库消费方无感。

**Architecture:** 三层解析（`$GITHUB_ISSUE_DRIVEN_HOME` → `~/.github-issue-driven/` → 迁移前旧路径）；路径解析是纯函数、IO 是薄层、CLI 是壳（三层可分别单测）；文档口径由契约测试钉住；存量数据由一次性脚本迁移并留符号链接。

**Tech Stack:** Python 3.10+（stdlib only：`argparse` / `pathlib` / `os` / `shutil`）、pytest（仓内既有 `uv run pytest`）、ripgrep（静态验收）。

**Spec:** `docs/superpowers/specs/2026-10-16-issue-driven-home-relocation-design.md`（本 worktree 首个 commit `14c9380`；评审留痕 `~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-259/`）

## Global Constraints

- 新默认路径 `~/.github-issue-driven/`，**目录名 `github-issue-driven` 保持不变**（pi-auto-rename 的 `RE_DRIVEN_PATH` 只认该后缀）。
- 环境变量 `GITHUB_ISSUE_DRIVEN_HOME` 优先于默认路径。
- 旧路径字面量（`~/.claude/github-issue-driven`）**只允许**出现在 `scripts/migrate_issue_driven_home.py`（唯一权威定义）与 `tests/**`（夹具）。
- `pi/**/*.md` 与 `README.md` / `CLAUDE.md` **不得**出现 `~/.claude`。
- **不改** `tests/unit/test_spec_cross_review_contracts.py` 的任何断言（#254 的契约）。
- 覆盖率门槛：`--cov-fail-under=60`。
- commit 格式 `type(scope): …`；`git add <file>` 逐文件，**禁用 `git add -A`**。
- 所有编辑路径以 worktree 绝对路径开头：`WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-259-issue-driven-home-relocation`；git 命令用 `git -C $WT`。
- worktree 内首次 `uv run pytest` 会自建 `.venv`（gitignored），属正常；如需复用主 checkout 的环境可加 `UV_PROJECT_ENVIRONMENT=/home/elling/git-repo/github/zima-blue-cli/.venv`。

## File Structure

| 文件 | 职责 | 动作 |
|------|------|------|
| `scripts/migrate_issue_driven_home.py` | 路径解析（纯函数）+ 状态探测 + 迁移执行 + CLI 壳 | 新增 |
| `tests/unit/test_migrate_issue_driven_home.py` | `resolve_home` / `resolve_action` / `describe_action` 的纯函数测试 | 新增 |
| `tests/integration/test_migrate_issue_driven_home.py` | tmp HOME 下真实跑脚本：四态 + 幂等 + `--dry-run` + env 覆盖 + `--help` | 新增 |
| `tests/unit/test_issue_driven_home_contracts.py` | 文档口径契约（5 条断言） | 新增 |
| `pi/github-issue-driven/SKILL.md` | 7 处路径 + 「留档目录解析」定稿文本 | 修改 |
| `pi/issue-research/SKILL.md` | 2 处路径 | 修改 |
| `pi/spec-cross-review/SKILL.md` | 2 处路径（含目录树示意） | 修改 |
| `pi/README.md` | 「注意」区一行约定 | 修改 |

---

### Task 1: 迁移脚本纯函数层（`resolve_home` / `resolve_action` / `describe_action`）

**Files:**
- Create: `scripts/migrate_issue_driven_home.py`
- Test: `tests/unit/test_migrate_issue_driven_home.py`
- 验收 ID：**A2**

**Interfaces:**
- Consumes: 无（首个任务）
- Produces（后续任务与测试依赖的精确签名）：
  ```python
  ENV_VAR = "GITHUB_ISSUE_DRIVEN_HOME"
  DEFAULT_DIRNAME = ".github-issue-driven"
  LEGACY_HOME: Path            # ~/.claude/github-issue-driven（唯一权威定义）
  State = Literal["absent", "dir", "symlink_to_new", "symlink_other"]
  Action = Literal["migrate", "noop_migrated", "noop_fresh", "conflict"]
  def resolve_home(env_value: str | None, home: Path) -> Path
  def resolve_action(legacy: State, new: State) -> Action
  def describe_action(action: Action, legacy: Path, new: Path) -> str
  ```

- [ ] **Step 1: 写失败的测试**

```python
"""Unit tests for scripts.migrate_issue_driven_home pure functions (A2)."""
from pathlib import Path
import pytest
from scripts.migrate_issue_driven_home import (
    DEFAULT_DIRNAME, resolve_home, resolve_action, describe_action, Action, State,
)

HOME = Path("/home/tester")

class TestResolveHome:
    @pytest.mark.parametrize("env,expected", [
        ("/tmp/custom", Path("/tmp/custom")),          # env 有值 → 用它
        ("", HOME / DEFAULT_DIRNAME),                  # 空串 → 默认
        (None, HOME / DEFAULT_DIRNAME),                # None → 默认
    ])
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_migrate_issue_driven_home.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_issue_driven_home'`

- [ ] **Step 3: 实现纯函数层**

```python
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
import sys
from pathlib import Path
from typing import Literal

ENV_VAR = "GITHUB_ISSUE_DRIVEN_HOME"
DEFAULT_DIRNAME = ".github-issue-driven"
# 旧路径的唯一权威定义（文档中一律称「迁移前的旧路径」）
LEGACY_HOME = Path.home() / ".claude" / "github-issue-driven"

State = Literal["absent", "dir", "symlink_to_new", "symlink_other"]
Action = Literal["migrate", "noop_migrated", "noop_fresh", "conflict"]

_TABLE: dict[tuple[str, str], Action] = { ... }  # 与测试 EXPECTED 同构的 16 格


def resolve_home(env_value: str | None, home: Path) -> Path:
    """env 非空 → 该路径；否则 home/DEFAULT_DIRNAME（纯函数）。"""
    if env_value:
        return Path(env_value).expanduser()
    return home / DEFAULT_DIRNAME


def resolve_action(legacy: State, new: State) -> Action:
    """4×4 全组合决策（纯函数）；未列出组合一律 conflict。"""
    return _TABLE.get((legacy, new), "conflict")


def describe_action(action: Action, legacy: Path, new: Path) -> str:
    """首行契约 `<action>: <legacy> -> <new>`；migrate 附 unlink 警告与计数。"""
    ...
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_migrate_issue_driven_home.py -v`
Expected: PASS（≥ 4+16+1+4+1 个用例）

- [ ] **Step 5: 提交**

```bash
git -C $WT add scripts/migrate_issue_driven_home.py tests/unit/test_migrate_issue_driven_home.py
git -C $WT commit -m "feat(scripts): 留档目录迁移脚本纯函数层 + 决策表测试（#259 A2）"
```

---

### Task 2: 迁移脚本 IO 与 CLI 层

**Files:**
- Modify: `scripts/migrate_issue_driven_home.py`
- Test: `tests/integration/test_migrate_issue_driven_home.py`
- 验收 ID：**A3**

**Interfaces:**
- Consumes: Task 1 的 `resolve_home` / `resolve_action` / `describe_action` / `LEGACY_HOME` / `ENV_VAR`
- Produces:
  ```python
  def classify(path: Path, new: Path) -> State        # IO 只读
  def inspect_paths(legacy: Path, new: Path) -> tuple[State, State]
  def apply_action(action: Action, legacy: Path, new: Path) -> int
  def main(argv: list[str] | None = None) -> int      # 0 = 成功/无操作；2 = conflict
  ```

- [ ] **Step 1: 写失败的集成测试**

覆盖七类用例（tmp HOME 下真实执行，`subprocess` 或 `main(argv)` 均可，须断言文件系统效果）：
1. `migrate`：旧目录有文件 → 迁移后新目录含同名文件、旧路径是 `symlink` 且指向新目录、退出码 0、stdout 首行为 `migrate: …`。
2. 幂等：同一 tmp HOME 再跑一次 → `noop_migrated`、退出码 0、文件与链接不变。
3. `noop_fresh`：两侧皆无 → 退出码 0，且**不创建**新目录。
4. `conflict`（两侧皆有真实目录）→ 退出码 **非 0（2）**，旧目录文件名与新目录均未变化，且**未创建符号链接**。
5. `--dry-run`：迁移前后对 tmp HOME 做文件树快照（`os.walk` 排序），断言完全一致、无 `mv` 无 `symlink`。
6. env 覆盖：`GITHUB_ISSUE_DRIVEN_HOME=<tmp>/custom` → 迁移目标是 `<tmp>/custom`，且默认路径 `~/.github-issue-driven`（tmp 下）**不被创建**。
7. `--help`：stdout 含 `unlink` 与 `rm -rf` 警告句。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/integration/test_migrate_issue_driven_home.py -v`
Expected: FAIL（`classify` / `main` 未定义）

- [ ] **Step 3: 实现 IO 与 CLI**

`classify` 判定顺序：不存在 → `absent`；是符号链接 → 指向 `new` 则 `symlink_to_new`，否则 `symlink_other`；是目录 → `dir`。
`apply_action`：`migrate` 用 `Path.rename`（同一文件系统）后 `os.symlink`；`conflict` 打印诊断并 `return 2`；`noop_*` 打印一行并 `return 0`。`main` 解析 `--dry-run` / `--help`，env 取 `os.environ.get(ENV_VAR)`，home 取 `Path.home()`；`--dry-run` 只打印 `describe_action` 不做写操作。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/integration/test_migrate_issue_driven_home.py -v`
Expected: PASS（7 类用例）

- [ ] **Step 5: 提交**

```bash
git -C $WT add scripts/migrate_issue_driven_home.py tests/integration/test_migrate_issue_driven_home.py
git -C $WT commit -m "feat(scripts): 迁移脚本 IO/CLI 层——四态、幂等、dry-run、env 覆盖（#259 A3）"
```

---

### Task 3: 文档口径契约测试（先红）

**Files:**
- Test: `tests/unit/test_issue_driven_home_contracts.py`
- 验收 ID：**A1**（红态）

**Interfaces:**
- Consumes: 无
- Produces: 5 条断言（后续 Task 4 使其转绿）
  ```python
  def test_no_claude_home_reference()          # pi/**/*.md 不含 ~/.claude
  def test_new_home_documented()               # 3 个 SKILL.md 含 ~/.github-issue-driven
  def test_env_override_documented()           # github-issue-driven/SKILL.md 含 GITHUB_ISSUE_DRIVEN_HOME
  def test_readme_documents_home()             # pi/README.md 含 ~/.github-issue-driven
  def test_legacy_path_defined_once()          # pi/**/*.md 零出现旧路径 + 脚本内 ≥1 次
  ```

- [ ] **Step 1: 写测试**

扫描面用 `Path.rglob("*.md")`（**不用 rg**——`.ignore` / glob 行为差异会引入假绿，spec §5 D5 有实测记录）；每类断言给文件级失败信息（`assert cond, name`）。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_home_contracts.py -v`
Expected: FAIL（`pi/**/*.md` 现存 11 处 `~/.claude`；新路径尚未出现）

- [ ] **Step 3: 提交红态测试**

```bash
git -C $WT add tests/unit/test_issue_driven_home_contracts.py
git -C $WT commit -m "test(contracts): 留档目录口径契约——pi 文档不得引用 ~/.claude（#259 A1，红）"
```

---

### Task 4: skill 文档迁移（转绿）

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（L19/20/28/46/60/66/70 + 「关键纪律」区）
- Modify: `pi/issue-research/SKILL.md`（L25/33）
- Modify: `pi/spec-cross-review/SKILL.md`（L29/123）
- Modify: `pi/README.md`（「注意」区）
- 验收 ID：**A1、A4**

**Interfaces:**
- Consumes: Task 3 的契约测试
- Produces: 文档口径（`~/.github-issue-driven/` + 定稿解析规则文本）

- [ ] **Step 1: 逐文件替换路径（含裸 `~/.claude` 写法）**

`pi/github-issue-driven/SKILL.md` 在「关键纪律」区插入 spec §5 D2 的定稿文本：

```text
留档目录解析（研究 / spec / 复核留痕统一规则）：
1. `$GITHUB_ISSUE_DRIVEN_HOME` 非空 → 用它；
2. 否则用 `~/.github-issue-driven/`；
3. 若默认目录不存在、而本机仍留有迁移前的旧路径，先做一次性迁移——在本技能包仓库
   （zima-blue-cli）的主 checkout 内执行 `python scripts/migrate_issue_driven_home.py`；
   同一 issue 的产物禁止写到两处。
```

`pi/issue-research/SKILL.md:33` 改为「一定放留档目录（见 github-issue-driven 的解析规则）」；`pi/spec-cross-review/SKILL.md` 的两处（含 L123 目录树示意）与 `pi/README.md` 一行约定同批改。

- [ ] **Step 2: 跑契约测试确认转绿**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_home_contracts.py -v`
Expected: PASS（5 条）

- [ ] **Step 3: 静态口径校验（两条都必须零命中）**

```bash
rg -n --glob '*.md' "~/\.claude" $WT/pi/            # 预期：零命中
rg -n --glob '*.md' "claude/github-issue-driven" $WT/pi/ $WT/README.md $WT/CLAUDE.md   # 预期：零命中
```

- [ ] **Step 4: 冲突检查：既有契约与禁用字面量**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -v`
Expected: PASS（#254 契约不受影响：新文本不含 `~/.pi/`、不含 banned 模型字面量）

- [ ] **Step 5: 提交**

```bash
git -C $WT add pi/github-issue-driven/SKILL.md pi/issue-research/SKILL.md pi/spec-cross-review/SKILL.md pi/README.md
git -C $WT commit -m "docs(skill): 留档目录迁到 ~/.github-issue-driven（#259 A1/A4）"
```

---

### Task 5: 全量回归与验收对账

**Files:** 无新增（只跑命令、记录结果）
- 验收 ID：**A5**（并复核 A1–A4 的命令口径）

- [ ] **Step 1: 全量套件 + 覆盖率**

Run: `cd $WT && uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
Expected: 全绿、覆盖率 ≥ 60%（新增的三个测试文件计入）

- [ ] **Step 2: 逐条重跑 A1–A4 的验收命令**，把实际输出与结论写进本 plan 的「验收对账」小节（含 hook 失败与修复轮次）。

- [ ] **Step 3: 提交**（仅当 Step 2 产生对账记录改动时）

```bash
git -C $WT add docs/superpowers/plans/2026-10-16-issue-driven-home-relocation.md
git -C $WT commit -m "docs(plan): 记录 #259 A1–A5 实跑结果"
```

---

### Task 6: 人工验收（U1/U2，父 session 收尾，不派 subagent）

**Files:** 无仓库改动
- 验收 ID：**U1、U2**

- [ ] **Step 1: U2（本机存量迁移，需用户事先确认）**

在 issue worktree 内执行（脚本此时未进 `main`）：

```bash
cd $WT && python scripts/migrate_issue_driven_home.py --dry-run     # 预期 migrate
cd $WT && python scripts/migrate_issue_driven_home.py               # 执行
cd $WT && python scripts/migrate_issue_driven_home.py               # 预期 noop_migrated
readlink ~/.claude/github-issue-driven                              # 预期指向 ~/.github-issue-driven
```

对账（集合口径，不做严格计数）：迁移前 `find ~/.claude/github-issue-driven -type f | sed 's|.*github-issue-driven/||' | sort > /tmp/before.txt`，迁移后同法取新目录清单，`comm -23 /tmp/before.txt /tmp/after.txt` 必须为空。

- [ ] **Step 2: U1（PR 合并后执行）**

主 checkout `git checkout main && git pull` → 发起新会话跑一个小 issue 的步 3 + 步 4 → 断言：新产物落在 `~/.github-issue-driven/`；旧路径符号链接读到同一文件；pi-auto-rename 仍识别 issue 号（会话标题带 issue 号）；CC 侧写入经符号链接落到新目录。

---

## 验收追溯表（spec ↔ plan 双向）

| spec ID | 验收内容 | plan 落点 |
|---------|----------|-----------|
| A1 | skill 文档口径迁移（含 README 正向断言） | Task 3（红）→ Task 4（绿） |
| A2 | `resolve_home` 三态 + 决策表 16 格 + 文案 | Task 1 |
| A3 | 脚本四态 + 幂等 + dry-run + env 覆盖 + `--help` | Task 2 |
| A4 | 仓内活跃文件无旧路径残留 | Task 4 Step 3 |
| A5 | 既有套件与覆盖率不回归 | Task 5 Step 1–2 |
| U1 | 真实会话 + CC 侧兼容 | Task 6 Step 2 |
| U2 | 本机存量迁移集合对账 | Task 6 Step 1 |

无「没有验收归属的实现 task」，也无「无 plan 落点的验收项」。

---

## 验收对账（Task 5 实跑记录，2026-10-16）

| ID | 命令 | 实际结果 | 结论 |
|----|------|----------|------|
| A1 | `uv run pytest tests/unit/test_issue_driven_home_contracts.py` | 5 passed in 0.02s | ✅ |
| A1 | `rg -n --glob '*.md' "~/\.claude" pi/` | 0 行 | ✅ |
| A2 | `uv run pytest tests/unit/test_migrate_issue_driven_home.py` | 25 passed in 0.03s | ✅ |
| A3 | `uv run pytest tests/integration/test_migrate_issue_driven_home.py` | 15 passed in 0.05s | ✅ |
| A4 | `rg -n --glob '*.md' "claude/github-issue-driven" pi/ README.md CLAUDE.md` | 0 行 | ✅ |
| A5 | 全量套件（`-m "not slow"` + `--cov-fail-under=60`） | 1817 passed, 1 skipped；coverage 75.68%（门槛 60%） | ✅ |
| A5 | `uv run pytest tests/unit/test_spec_cross_review_contracts.py` | 92 passed（#254 契约不变仍过） | ✅ |

- 分支：`issue-259-issue-driven-home-relocation`；spec 首 commit `14c9380`，plan `15aaf31`。
- 未执行、留待人工验收（Task 6）：U1（真实会话 + CC 侧兼容，须 PR 合并后从主 checkout 执行）、U2（本机存量迁移，执行前需用户确认）。
- 复核留痕：`~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-259/research/spec-review-round-{1,2,3}.md` 与 `spec-cross-review-state.md`（三轮交叉复核，收敛轮 0 真缺口）。
