# Issue-192 Flaky UUID Collision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `tests/unit/test_executor_preexec.py` 的 flaky 断言——prompt 路径 uuid 撞禁词（#192/#177），把 12 处 `text = " ".join(cmd)` 改为过滤 `.md` 路径。

**Architecture:** 纯测试改动。加模块级 helper `_cmd_text`，12 处调用点替换。不改 executor 代码。

**Tech Stack:** Python/pytest。验证用确定性 repro（patch uuid4）+ 全量单测。

## Global Constraints

- 所有编辑在 worktree `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-192-flaky-uuid-collision` 内进行（模型 B：绝对路径编辑，session cwd 不切换）
- 不改 executor 代码；不改其他测试文件（已 grep 确认无同模式）
- 代码注释英文，commit message 英文

---

### Task 1: 加 helper + 替换 12 处调用点

**Files:**
- Modify: `tests/unit/test_executor_preexec.py`

- [ ] **Step 1: 在文件顶部（imports 之后、第一个 class 之前）加 helper**

在 `from zima.execution.executor import ...` 等 imports 之后插入：

```python
def _cmd_text(cmd: list[str]) -> str:
    """Join command args for assertion text, excluding the prompt file path —
    its random uuid can collide with asserted-forbidden substrings (#192/#177)."""
    return " ".join(a for a in cmd if not a.endswith(".md"))
```

- [ ] **Step 2: 替换 12 处调用点**

将全部 12 处：

```python
            text = " ".join(cmd)
```

替换为：

```python
            text = _cmd_text(cmd)
```

（`grep -c 'text = " ".join(cmd)'` 应为 0；`grep -c 'text = _cmd_text(cmd)'` 应为 12）

- [ ] **Step 3: 确定性验证（碰撞 uuid 下必过）**

Run:

```bash
uv run python - << 'EOF'
import uuid, pytest
import zima.execution.executor as executor_mod
_COLLIDING = uuid.UUID("99999999-0000-0000-0000-000000000000")
original = executor_mod.uuid.uuid4
executor_mod.uuid.uuid4 = lambda: _COLLIDING
try:
    rc = pytest.main([
        "-q",
        "tests/unit/test_executor_preexec.py::TestStaleOverrideCleanupCliPath::test_stale_static_override_loses_to_scanned_pr",
        "tests/unit/test_executor_preexec.py::TestSingleSinkPrAliasGate::test_both_valid_pr_number_authoritative",
    ])
finally:
    executor_mod.uuid.uuid4 = original
print("RC:", rc)
EOF
```

Expected: `2 passed`，RC 0（修复前同脚本必挂，见 #192 评论）

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_executor_preexec.py
git commit -m "test: exclude prompt path from assertion text — uuid collision flake (#192 #177)"
```

---

### Task 2: 全量验证

- [ ] **Step 1: 跑全量单测**

Run: `uv run pytest tests/unit/ -q`
Expected: 全部 PASS

- [ ] **Step 2: 检查 diff**

Run: `git diff main...HEAD --stat`
Expected: 仅 test_executor_preexec.py 与 spec 文档
