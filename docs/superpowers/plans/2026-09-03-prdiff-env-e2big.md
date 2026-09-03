# Issue #201 Implementation Plan — pr_diff 字节截断 + requireReview postExec 门控

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 issue #201 的两个缺陷：(A) scan_pr 发现的大 diff 按字节截断到 100,000 字节以下，杜绝 E2BIG；(B) `PostExecAction` 新增 opt-in `requireReview` 字段，无有效 review 信号时跳过该 postExec 动作，杜绝 needs-fix 误标。

**Architecture:** 缺陷 A 在 `zima/execution/executor.py` 单点修复：新纯函数 `truncate_utf8_bytes` + 常量 `_DISCOVERED_TEXT_MAX_BYTES`，替换现有字符截断循环。缺陷 B 三层：`zima/models/actions.py` 加字段（默认 False，向后兼容）、`zima/execution/failure_guard.py` 的 `_has_valid_review_signal` 提升为公共函数复用、`zima/execution/actions_runner.py` 的 `run()` 加 `has_review_signal` 关键字参数并在循环内门控（判定对 substitution 前的原始 action 做，`_substitute_env` 透传字段）。

**Tech Stack:** Python 3.10+ dataclasses、pytest、ruff、black（100 chars）。

**Spec:** `docs/superpowers/specs/2026-09-03-prdiff-env-e2big-design.md`（验收矩阵 A1–A7 + U1，决策记录 §6）

**Worktree:** 所有编辑与 git 操作在 `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-201-prdiff-env-e2big`（下称 `$WT`），禁碰主 checkout；git 命令一律 `git -C $WT ...`。

## Global Constraints

- 字节 cap 常量值 `_DISCOVERED_TEXT_MAX_BYTES = 100_000`（spec §2.1，不得改动数值）。
- 截断警告文案必须保留 `"{key} exceeds"` 前缀（现有测试断言）。
- `require_review` 默认 `False`；`ActionsRunner.run` 的 `has_review_signal` 默认 `True`——旧调用方零行为变化（spec §2.2）。
- 不改变 `Status:` 行、`<zima-review>` XML、ReviewParser 的任何契约（spec §5 非目标）。
- 门控判定使用 `zima.execution.failure_guard.has_valid_review_signal`（promote 自 `_has_valid_review_signal`），不得新造判定逻辑。
- `_substitute_env` 重建 PostExecAction 必须透传 `require_review`（spec §2.2 关键实现约束）。
- `PostExecAction.to_dict` 在 `require_review=False` 时不序列化该键（`omit_empty` 保留 False，需覆写丢弃）。
- commit message 格式 `type(scope): description`，含 `(#201)`。
- 每 task 结束 `git add <具体文件>`（禁 `git add -A`）+ commit。

## File Structure

| 文件 | 责任 | 涉及 Task |
|---|---|---|
| `zima/execution/executor.py` | 字节 cap 常量、`truncate_utf8_bytes`、截断循环、postExec 门控接线 | 1, 2, 6 |
| `zima/execution/failure_guard.py` | `has_valid_review_signal` 提升公共 | 3 |
| `zima/models/actions.py` | `PostExecAction.require_review` 字段 + to_dict 覆写 | 4 |
| `zima/execution/actions_runner.py` | `run()` 门控参数、`_substitute_env` 透传 | 5 |
| `zima/templates/examples.py` | REVIEWER_PJOB 两个 postExec 动作加 `requireReview: true` | 8 |
| `tests/unit/test_executor_preexec.py` | 截断纯函数 + executor 截断测试 | 1, 2 |
| `tests/unit/test_failure_guard.py` | 公共信号函数直接测试 | 3 |
| `tests/unit/test_models_actions.py` | 字段 roundtrip/序列化测试 | 4 |
| `tests/unit/test_actions_runner.py` | 门控矩阵 + 透传测试 | 5 |
| `tests/integration/test_executor_actions.py` | executor 门控集成 + 大 CJK env Popen 测试 | 6, 7 |
| `tests/unit/test_examples.py` | 模板字段断言 | 8 |

---

### Task 1: `truncate_utf8_bytes` 纯函数 + 字节 cap 常量

**验收 ID:** A1, A2

**Files:**
- Modify: `$WT/zima/execution/executor.py:42-44`（常量区）
- Test: `$WT/tests/unit/test_executor_preexec.py`

**Interfaces:**
- Produces: `zima.execution.executor.truncate_utf8_bytes(text: str, limit: int) -> str`（Task 2 消费）；`zima.execution.executor._DISCOVERED_TEXT_MAX_BYTES: int`（Task 2、7 消费）

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_executor_preexec.py` 顶部 import 区不变，新增测试类方法（挂在现有截断测试所在 class 内）：

```python
    def test_truncate_utf8_bytes_ascii_boundary(self):
        from zima.execution.executor import truncate_utf8_bytes

        assert truncate_utf8_bytes("x" * 200, 100) == "x" * 100
        assert truncate_utf8_bytes("short", 100) == "short"

    def test_truncate_utf8_bytes_cjk_no_split(self):
        from zima.execution.executor import truncate_utf8_bytes

        text = "汉" * 100  # 300 bytes UTF-8
        out = truncate_utf8_bytes(text, 100)
        # 100 bytes cuts mid-codepoint (99 = 33 chars); tail must be dropped,
        # never a decode error or replacement char
        assert len(out.encode("utf-8")) == 99
        assert out == "汉" * 33

    def test_truncate_utf8_bytes_empty_and_zero(self):
        from zima.execution.executor import truncate_utf8_bytes

        assert truncate_utf8_bytes("", 100) == ""
        assert truncate_utf8_bytes("abc", 0) == ""

    def test_cap_fits_max_arg_strlen(self):
        """Byte cap + "pr_diff=" prefix + NUL must stay under 131072 (#201)."""
        from zima.execution.executor import _DISCOVERED_TEXT_MAX_BYTES

        assert _DISCOVERED_TEXT_MAX_BYTES + len("pr_diff=") + 1 <= 131072
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd $WT && uv run pytest tests/unit/test_executor_preexec.py -k "truncate_utf8 or cap_fits" -q
```
Expected: FAIL（`ImportError: cannot import name 'truncate_utf8_bytes'`）

- [ ] **Step 3: 最小实现**

`zima/execution/executor.py` 现有常量块（42-44 行附近）替换为：

```python
# Free-text scan values (pr_title/pr_url/pr_diff) entering the agent env /
# templates are capped in BYTES to stay under the kernel's per-string
# MAX_ARG_STRLEN (131072 bytes incl. the "KEY=" prefix and trailing NUL).
# A char-based cap cannot bound byte length for CJK text (1 char = 3 bytes
# UTF-8), so #158's 1 MiB char cap never actually prevented E2BIG (#201).
_DISCOVERED_TEXT_MAX_BYTES = 100_000


def truncate_utf8_bytes(text: str, limit: int) -> str:
    """Truncate text to at most ``limit`` UTF-8 bytes without splitting a
    codepoint; the partial tail is dropped via errors="ignore" (#201).

    The kernel counts envp strings in bytes, so env-injected free text must
    be capped in bytes, not characters.
    """
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit}")
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
```

注意：**保留旧名 `_DISCOVERED_TEXT_MAX` 的删除在 Task 2 一并做**（避免中间态两处引用断裂）；本 task 只新增。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd $WT && uv run pytest tests/unit/test_executor_preexec.py -k "truncate_utf8 or cap_fits" -q
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git -C $WT add zima/execution/executor.py tests/unit/test_executor_preexec.py
git -C $WT commit -m "feat(executor): byte-safe truncate_utf8_bytes + byte cap constant (#201)"
```

---

### Task 2: executor 截断循环改字节语义 + 更新现有截断测试

**验收 ID:** A3

**Files:**
- Modify: `$WT/zima/execution/executor.py:465-477`（截断循环）
- Test: `$WT/tests/unit/test_executor_preexec.py`（更新 `test_overlong_pr_diff_truncated_loudly`，新增 CJK 测试）

**Interfaces:**
- Consumes: `truncate_utf8_bytes`、`_DISCOVERED_TEXT_MAX_BYTES`（Task 1）
- Produces: 无新接口（行为变更）

- [ ] **Step 1: 先改现有测试为新预期（失败态）**

`tests/unit/test_executor_preexec.py:1496-1506` 的 `test_overlong_pr_diff_truncated_loudly` 替换为：

```python
    def test_overlong_pr_diff_truncated_loudly(self, isolated_zima_home, capsys):
        """A >100KB-byte discovered pr_diff is capped before entering env/render
        (#201 — byte-based; #158's char cap could not prevent E2BIG for CJK)."""
        from zima.execution.executor import _DISCOVERED_TEXT_MAX_BYTES

        result, _ = self._run_with_discovered(
            isolated_zima_home,
            {"pr_number": "42", "pr_diff": "x" * (_DISCOVERED_TEXT_MAX_BYTES + 5)},
        )
        assert result.status == ExecutionStatus.SUCCESS
        out = capsys.readouterr().out
        assert "pr_diff exceeds" in out
        assert "bytes" in out

    def test_overlong_cjk_pr_diff_truncated_by_bytes(self, isolated_zima_home):
        """CJK diff: byte cap binds even when char count is far below it (#201).
        100_000 CJK chars = 300KB bytes — must still land under the byte cap."""
        from zima.execution.executor import _DISCOVERED_TEXT_MAX_BYTES

        cjk_diff = "汉" * _DISCOVERED_TEXT_MAX_BYTES
        result, _ = self._run_with_discovered(
            isolated_zima_home, {"pr_number": "42", "pr_diff": cjk_diff}
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert len(result.env["pr_diff"].encode("utf-8")) <= _DISCOVERED_TEXT_MAX_BYTES
```

（`result.env` 的既有用法见同文件 line 231 附近 `result.env.get("pr_diff")`。）

- [ ] **Step 2: 跑测试确认失败**

```bash
cd $WT && uv run pytest tests/unit/test_executor_preexec.py -k "overlong" -q
```
Expected: FAIL（旧循环按字符截断，CJK 测试的 env 值仍有 300KB；旧警告无 "bytes" 字样）

- [ ] **Step 3: 实现 — 替换截断循环**

`zima/execution/executor.py` 现有循环（465-477 行附近）替换为：

```python
                    # Remaining scan-discovered values (pr_title / pr_url /
                    # pr_diff) are provider/author-controlled free text: cap
                    # them BYTES-wise before they enter the agent subprocess
                    # env (E2BIG / MAX_ARG_STRLEN is a per-string byte limit)
                    # and Jinja2 rendering. A cap hit means a pathological
                    # payload, so the value is truncated loudly (#201).
                    for _dk in [k for k in dynamic_vars if k.startswith("pr_")]:
                        _dv = str(dynamic_vars[_dk])
                        if len(_dv.encode("utf-8")) > _DISCOVERED_TEXT_MAX_BYTES:
                            print(
                                f"Warning: discovered {_dk} exceeds "
                                f"{_DISCOVERED_TEXT_MAX_BYTES} bytes "
                                f"(len={len(_dv)} chars); truncating (#201)"
                            )
                            dynamic_vars[_dk] = truncate_utf8_bytes(
                                _dv, _DISCOVERED_TEXT_MAX_BYTES
                            )
```

同时删除旧常量 `_DISCOVERED_TEXT_MAX = 1_048_576`（Task 1 已加新常量；全仓 grep 确认无其他引用后删除）。

- [ ] **Step 4: 跑测试确认通过 + 无残留引用**

```bash
cd $WT && uv run pytest tests/unit/test_executor_preexec.py -k "overlong or truncate_utf8 or cap_fits" -q
grep -rn "_DISCOVERED_TEXT_MAX\b" zima/ tests/ | grep -v "_DISCOVERED_TEXT_MAX_BYTES" || echo "no stale refs"
```
Expected: 测试全过；`no stale refs`

- [ ] **Step 5: Commit**

```bash
git -C $WT add zima/execution/executor.py tests/unit/test_executor_preexec.py
git -C $WT commit -m "fix(executor): cap discovered pr_* values by bytes, not chars (#201)"
```

---

### Task 3: `has_valid_review_signal` 提升为公共函数

**验收 ID:** A6（支撑）

**Files:**
- Modify: `$WT/zima/execution/failure_guard.py:176-183`
- Test: `$WT/tests/unit/test_failure_guard.py`

**Interfaces:**
- Produces: `zima.execution.failure_guard.has_valid_review_signal(stdout: str) -> bool`（Task 6 消费）

- [ ] **Step 1: 写失败测试**

`tests/unit/test_failure_guard.py` 新增：

```python
def test_has_valid_review_signal_public():
    """Public review-signal predicate reused by the postExec gate (#201)."""
    from zima.execution.failure_guard import has_valid_review_signal

    assert has_valid_review_signal("some output\nStatus: NEEDS_FIX\n") is True
    assert has_valid_review_signal("Status: PASS") is True
    assert has_valid_review_signal("Status: NO_NEW_COMMITS\n") is True
    assert (
        has_valid_review_signal("<zima-review><verdict>approved</verdict></zima-review>")
        is True
    )
    assert has_valid_review_signal("") is False
    assert has_valid_review_signal("Status: NEEDS_F") is False  # truncated line
    assert has_valid_review_signal("<zima-review><verdict></verdict>") is False  # unclosed
    assert has_valid_review_signal(None) is False
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd $WT && uv run pytest tests/unit/test_failure_guard.py::test_has_valid_review_signal_public -q
```
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现 — rename**

`zima/execution/failure_guard.py`：`_has_valid_review_signal` 改名为 `has_valid_review_signal`（docstring 保留并追加一行 "Also used by the executor's postExec requireReview gate (#201)."），同文件 line 204 的内部调用点同步改名。`_has_review_verdict` 保持私有不动。

- [ ] **Step 4: 跑测试确认通过 + 全模块回归**

```bash
cd $WT && uv run pytest tests/unit/test_failure_guard.py -q
```
Expected: 全过（含既有 classify/cooldown 测试）

- [ ] **Step 5: Commit**

```bash
git -C $WT add zima/execution/failure_guard.py tests/unit/test_failure_guard.py
git -C $WT commit -m "refactor(cr): promote has_valid_review_signal to public (#201)"
```

---

### Task 4: `PostExecAction.require_review` 模型字段

**验收 ID:** A5

**Files:**
- Modify: `$WT/zima/models/actions.py`
- Test: `$WT/tests/unit/test_models_actions.py`

**Interfaces:**
- Produces: `PostExecAction.require_review: bool = False`；YAML 别名 `requireReview`；`to_dict()` 在 False 时不含该键（Task 5、8 消费）

- [ ] **Step 1: 写失败测试**

`tests/unit/test_models_actions.py` 新增：

```python
class TestPostExecActionRequireReview:
    def test_default_false(self):
        action = PostExecAction.from_dict(
            {"condition": "failure", "type": "add_label", "repo": "a/b", "issue": "1"}
        )
        assert action.require_review is False

    def test_yaml_alias_roundtrip(self):
        action = PostExecAction.from_dict(
            {
                "condition": "failure",
                "type": "add_label",
                "repo": "a/b",
                "issue": "1",
                "requireReview": True,
            }
        )
        assert action.require_review is True
        assert action.to_dict()["requireReview"] is True

    def test_false_omitted_in_to_dict(self):
        """omit_empty preserves False (serialization.py:338), so to_dict must
        explicitly drop the flag to keep saved YAMLs noise-free (#201)."""
        action = PostExecAction(
            condition="failure", type="add_label", repo="a/b", issue="1"
        )
        assert "requireReview" not in action.to_dict()

    def test_legacy_yaml_without_field_loads(self):
        """Pre-#201 PJob YAMLs (no requireReview key) load unchanged."""
        action = PostExecAction.from_dict(
            {
                "condition": "success",
                "type": "add_label",
                "removeLabels": ["zima:needs-review"],
                "repo": "{{repo}}",
                "issue": "{{pr_number}}",
            }
        )
        assert action.require_review is False
        assert action.remove_labels == ["zima:needs-review"]
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd $WT && uv run pytest tests/unit/test_models_actions.py -k "RequireReview" -q
```
Expected: FAIL（`TypeError: unexpected keyword argument` / attribute missing）

- [ ] **Step 3: 实现**

`zima/models/actions.py` 的 `PostExecAction`：

```python
    FIELD_ALIASES = {
        "add_labels": "addLabels",
        "remove_labels": "removeLabels",
        "require_review": "requireReview",
    }

    condition: str = "always"
    type: str = "add_label"
    add_labels: list[str] = field(default_factory=list)
    remove_labels: list[str] = field(default_factory=list)
    repo: str = ""
    issue: str = ""
    body: str = ""
    # Skip this action when the agent produced no valid review signal
    # (Status line / zima-review XML). Prevents "needs-fix" mislabeling on
    # startup failures like E2BIG where no review ever happened (#201).
    require_review: bool = False

    def to_dict(self) -> dict:
        d = omit_empty(super().to_dict())
        if not self.require_review:
            d.pop("requireReview", None)
        return d
```

同时更新 docstring 的 Attributes 段补一行 `require_review: Skip unless a valid review signal was produced (default False).`。

- [ ] **Step 4: 跑测试确认通过 + 模型全量回归**

```bash
cd $WT && uv run pytest tests/unit/test_models_actions.py -q
```
Expected: 全过

- [ ] **Step 5: Commit**

```bash
git -C $WT add zima/models/actions.py tests/unit/test_models_actions.py
git -C $WT commit -m "feat(actions): requireReview field on PostExecAction (#201)"
```

---

### Task 5: `ActionsRunner` 门控 + `_substitute_env` 透传

**验收 ID:** A6（unit 层）

**Files:**
- Modify: `$WT/zima/execution/actions_runner.py`（`run()` 96-128 行附近；`_substitute_env` 131-150 行附近）
- Test: `$WT/tests/unit/test_actions_runner.py`

**Interfaces:**
- Consumes: `PostExecAction.require_review`（Task 4）
- Produces: `ActionsRunner.run(actions, returncode, env, has_review_signal: bool = True) -> list[str]`（Task 6 消费）

- [ ] **Step 1: 写失败测试**

先看 `tests/unit/test_actions_runner.py` 现有 fake provider 写法并复用。新增：

```python
class TestRequireReviewGate:
    def _actions_cfg(self, require_review: bool) -> ActionsConfig:
        return ActionsConfig(
            provider="github",
            post_exec=[
                PostExecAction(
                    condition="failure",
                    type="add_label",
                    add_labels=["zima:needs-fix"],
                    remove_labels=["zima:needs-review"],
                    repo="a/b",
                    issue="1",
                    require_review=require_review,
                )
            ],
        )

    def test_gate_skips_without_signal(self, capsys):
        """requireReview + no review signal → provider never called (#201)."""
        runner, provider = <按文件现有模式构造 runner 与 mock/fake provider>
        errors = runner.run(
            self._actions_cfg(require_review=True), returncode=1, env={},
            has_review_signal=False,
        )
        assert errors == []
        assert not provider.add_label.called
        assert not provider.remove_label.called
        assert "requireReview" in capsys.readouterr().out

    def test_gate_fires_with_signal(self):
        runner, provider = <同现有模式>
        errors = runner.run(
            self._actions_cfg(require_review=True), returncode=1, env={},
            has_review_signal=True,
        )
        assert errors == []
        provider.add_label.assert_called_once_with("a/b", "1", "zima:needs-fix")

    def test_legacy_action_fires_without_signal(self):
        """No requireReview → legacy behavior unchanged even without signal."""
        runner, provider = <同现有模式>
        errors = runner.run(
            self._actions_cfg(require_review=False), returncode=1, env={},
            has_review_signal=False,
        )
        assert errors == []
        provider.add_label.assert_called_once_with("a/b", "1", "zima:needs-fix")

    def test_default_param_keeps_legacy_callers(self):
        """run() without has_review_signal kwarg behaves as True (old callers)."""
        runner, provider = <同现有模式>
        errors = runner.run(self._actions_cfg(require_review=True), returncode=1, env={})
        provider.add_label.assert_called_once()

    def test_substitute_env_preserves_require_review(self):
        """_substitute_env rebuilds the action with explicit kwargs — the flag
        must survive substitution or the gate silently never fires (#201)."""
        runner = ActionsRunner()
        action = PostExecAction(
            condition="failure", type="add_label", repo="{{repo}}", issue="{{pr_number}}",
            require_review=True,
        )
        processed = runner._substitute_env(action, {"repo": "a/b", "pr_number": "1"})
        assert processed.require_review is True
        assert processed.repo == "a/b"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd $WT && uv run pytest tests/unit/test_actions_runner.py -k "RequireReviewGate" -q
```
Expected: FAIL（`TypeError: run() got an unexpected keyword argument 'has_review_signal'`）

- [ ] **Step 3: 实现**

`zima/execution/actions_runner.py` 的 `run()` 签名与循环：

```python
    def run(
        self,
        actions: ActionsConfig,
        returncode: int,
        env: dict[str, str],
        has_review_signal: bool = True,
    ) -> list[str]:
        """Execute all matching postExec actions.

        Args:
            actions: Actions configuration from PJob.
            returncode: Agent process exit code.
            env: Environment variables for {{VAR}} substitution.
            has_review_signal: Whether agent stdout carried a valid review
                signal (Status line / zima-review XML). Actions with
                require_review=True are skipped when this is False (#201).
                Defaults True so legacy callers are unaffected.

        Returns:
            List of error messages from failed actions.
        """
        try:
            provider = self._registry.get(actions.provider)
        except ProviderNotFoundError as e:
            print(f"Warning: {e}")
            return [str(e)]

        errors: list[str] = []
        for action in actions.post_exec:
            if not _matches_condition(action.condition, returncode):
                continue
            # Gate on the PRE-substitution action; _substitute_env rebuilds
            # the dataclass with explicit kwargs (#201).
            if action.require_review and not has_review_signal:
                print(
                    f"Warning: postExec action skipped — requireReview set but "
                    f"no valid review signal in agent stdout (type={action.type}, "
                    f"condition={action.condition})"
                )
                continue

            processed = self._substitute_env(action, env)
            errors.extend(self._execute_action(processed, provider))

        return errors
```

`_substitute_env` 的 return 改为：

```python
        return PostExecAction(
            condition=action.condition,
            type=action.type,
            add_labels=[sub(label) for label in action.add_labels],
            remove_labels=[sub(label) for label in action.remove_labels],
            repo=sub(action.repo),
            issue=sub(action.issue),
            body=sub(action.body),
            require_review=action.require_review,
        )
```

- [ ] **Step 4: 跑测试确认通过 + 全文件回归**

```bash
cd $WT && uv run pytest tests/unit/test_actions_runner.py -q
```
Expected: 全过（65+ 个既有测试零变化）

- [ ] **Step 5: Commit**

```bash
git -C $WT add zima/execution/actions_runner.py tests/unit/test_actions_runner.py
git -C $WT commit -m "feat(actions): gate postExec actions on review signal via requireReview (#201)"
```

---

### Task 6: executor 接线 `has_review`

**验收 ID:** A6（integration 层）

**Files:**
- Modify: `$WT/zima/execution/executor.py`（import 区 25 行附近；`_run_post_exec_actions` 1012-1055 行附近）
- Test: `$WT/tests/integration/test_executor_actions.py`

**Interfaces:**
- Consumes: `has_valid_review_signal`（Task 3）、`ActionsRunner.run(..., has_review_signal=...)`（Task 5）

- [ ] **Step 1: 写失败测试**

在 `tests/integration/test_executor_actions.py` 按文件现有模式（fake agent + mock provider registry）新增：

```python
class TestRequireReviewExecutorGate:
    def test_startup_failure_skips_require_review_action(self, isolated_zima_home, ...):
        """Agent exits 1 with empty stdout (E2BIG-like): the requireReview
        failure action must NOT fire — label stays untouched (#201)."""
        # 按本文件现有 fixture 组一个 PJob：agent mockCommand 为 exit 1 无输出；
        # postExec failure add_label requireReview: true；provider 用 mock
        ...
        assert result.status == ExecutionStatus.FAILED
        assert not provider.add_label.called

    def test_needs_fix_verdict_still_fires_require_review_action(self, ...):
        """Agent exits 1 but stdout carries 'Status: NEEDS_FIX': action fires."""
        # agent mockCommand 输出含 "Status: NEEDS_FIX" 且 exit 1
        ...
        provider.add_label.assert_called_once_with(<repo>, <pr>, "zima:needs-fix")

    def test_success_without_review_skips_remove_label(self, ...):
        """exit 0 但无 review 信号：requireReview 的 success 动作（摘
        needs-review）同样被跳过 —— 无审查不摘待审标签（spec §2.2 连带语义）。"""
        ...
        assert not provider.remove_label.called
```

（实现时按该文件既有 helper 填充 `...`；三条用例分别覆盖 failure 无信号跳过、failure 有信号放行、success 无信号跳过。）

- [ ] **Step 2: 跑测试确认失败**

```bash
cd $WT && uv run pytest tests/integration/test_executor_actions.py -k "RequireReviewExecutorGate" -q
```
Expected: FAIL（接线未做，provider 仍被调用 / 行为不符）

- [ ] **Step 3: 实现**

`zima/execution/executor.py` 25 行附近的 failure_guard import 追加 `has_valid_review_signal`。`_run_post_exec_actions` 中调用点改为：

```python
        try:
            action_errors = self._actions_runner.run(
                actions=pjob.spec.actions,
                returncode=effective_returncode,
                env=env_vars,
                has_review_signal=has_valid_review_signal(result.stdout or ""),
            )
```

- [ ] **Step 4: 跑测试确认通过 + executor 相关回归**

```bash
cd $WT && uv run pytest tests/integration/test_executor_actions.py tests/unit/test_executor_preexec.py -q
```
Expected: 全过

- [ ] **Step 5: Commit**

```bash
git -C $WT add zima/execution/executor.py tests/integration/test_executor_actions.py
git -C $WT commit -m "feat(executor): wire review-signal gate into postExec (#201)"
```

---

### Task 7: 集成测试 — 大 CJK env 值真实 Popen 不 E2BIG

**验收 ID:** A4

**Files:**
- Test: `$WT/tests/integration/test_executor_actions.py`

**Interfaces:**
- Consumes: `_DISCOVERED_TEXT_MAX_BYTES`（Task 1）、`PJobExecutor._run_command`

- [ ] **Step 1: 写测试（直接对 `_run_command` 薄层，不走完整 execute 链路）**

```python
def test_large_cjk_env_value_does_not_e2big(isolated_zima_home):
    """A 100KB-byte UTF-8 CJK env value must not trigger E2BIG at Popen (#201).

    Per-string budget: MAX_ARG_STRLEN=131072 bytes incl. "KEY=" and NUL;
    the #201 byte cap (100_000) keeps any single envp string under it.
    """
    import os
    import sys

    from zima.execution.executor import PJobExecutor, _DISCOVERED_TEXT_MAX_BYTES

    cjk_value = "汉" * (_DISCOVERED_TEXT_MAX_BYTES // 3)  # 99_999 bytes
    assert len(cjk_value.encode("utf-8")) <= _DISCOVERED_TEXT_MAX_BYTES

    executor = PJobExecutor()
    env = {**os.environ, "pr_diff": cjk_value}
    returncode, stdout, stderr, pid = executor._run_command(
        command=[sys.executable, "-c", "pass"],
        env=env,
        work_dir=str(isolated_zima_home),
        timeout=30,
    )
    assert returncode == 0
```

- [ ] **Step 2: 跑测试确认通过（此测试是防回归网，Task 2 之后即应通过；若在 Task 2 前先写则用于复现 E2BIG，可选）**

```bash
cd $WT && uv run pytest tests/integration/test_executor_actions.py::test_large_cjk_env_value_does_not_e2big -q
```
Expected: PASS（`_run_command` 本身不截断——截断在上游；本测试证明 cap 值在真实 Popen 下安全。另建议本地手动验证一次「未截断的 592KB 值会 E2BIG」作对照，不需写成测试）

- [ ] **Step 3: Commit**

```bash
git -C $WT add tests/integration/test_executor_actions.py
git -C $WT commit -m "test(executor): large CJK env value launches without E2BIG (#201)"
```

---

### Task 8: 内置 REVIEWER_PJOB 模板加 `requireReview: true`

**验收 ID:** A5（模板层）、A7（兼容）

**Files:**
- Modify: `$WT/zima/templates/examples.py:206-237`（REVIEWER_PJOB）
- Test: `$WT/tests/unit/test_examples.py:296-310` 附近

**Interfaces:**
- Consumes: `PostExecAction.require_review`（Task 4）

- [ ] **Step 1: 先改测试（失败态）**

`tests/unit/test_examples.py` 现有 post_exec 断言块后追加：

```python
        assert config.spec.actions.post_exec[0].require_review is True
        assert config.spec.actions.post_exec[1].require_review is True
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd $WT && uv run pytest tests/unit/test_examples.py -q
```
Expected: FAIL（模板尚无 requireReview）

- [ ] **Step 3: 改模板**

`zima/templates/examples.py` REVIEWER_PJOB 的两个 postExec 动作各加一行：

```yaml
    postExec:
      - condition: success
        type: add_label
        requireReview: true
        removeLabels:
          - zima:needs-review
        repo: "{{repo}}"
        issue: "{{pr_number}}"
      - condition: failure
        type: add_label
        requireReview: true
        addLabels:
          - zima:needs-fix
        removeLabels:
          - zima:needs-review
        repo: "{{repo}}"
        issue: "{{pr_number}}"
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd $WT && uv run pytest tests/unit/test_examples.py -q
```
Expected: 全过

- [ ] **Step 5: Commit**

```bash
git -C $WT add zima/templates/examples.py tests/unit/test_examples.py
git -C $WT commit -m "fix(examples): reviewer PJob postExec requires review signal (#201)"
```

---

### Task 9: 全量回归 + lint/format（A7）

**验收 ID:** A7

- [ ] **Step 1: 全量测试**

```bash
cd $WT && uv run pytest tests/unit/ tests/integration/ -q
```
Expected: 全过（关注 test_failure_guard / test_actions_runner / test_executor_* / test_examples 全绿）

- [ ] **Step 2: lint + format**

```bash
cd $WT && uv run ruff check zima/ tests/
cd $WT && uv run black zima/ tests/ --line-length 100
```
Expected: ruff 无错；black 若有重排则格式化后重跑 Step 1

- [ ] **Step 3:（如需格式化）Commit**

```bash
git -C $WT add <被 black 改动的具体文件>
git -C $WT commit -m "style: black formatting (#201)"
```

---

### Task 10: 实现后人工验证（U1，merge 后执行，不在本 plan 代码范围内）

**验收 ID:** U1

前置条件全部就绪后执行：

1. 合并 PR 并发布新版本（走 release skill）→ `uv tool upgrade zima-blue-cli`。
2. 本机 18 个 CR PJob YAML（`~/.zima/configs/pjobs/*-pi-cr-job.yaml` 与 `*-zc-*.yaml`）的两个 add_label 动作补 `requireReview: true`，逐个 diff 交用户过目。
3. 恢复 jfox #489 标签：`gh pr edit 489 --repo zhuxixi/jfox --remove-label zima:needs-fix --add-label zima:needs-review`。
4. 注意 FailureGuard 冷却：该 PR 当前冷却到 2026-09-03 09:06:33（北京时间）；过期后自动放行，或 `--failure-guard-off` 突破。
5. 观察 CR 执行：(a) 不再 13 秒 E2BIG 秒挂；(b) 若仍失败，标签保持 needs-review 不误标；(c) 报告含 `Diff truncated: yes` 且 Coverage 行显示丢弃的为尾部文件。

---

## Self-Review 记录

- **Spec 覆盖**：A1→Task 1，A2→Task 1，A3→Task 2，A4→Task 7，A5→Task 4+8，A6→Task 3+5+6，A7→Task 9，U1→Task 10。spec §2.1/§2.2/§3 的每个设计点均有对应 task；无非目标被误实现。
- **Placeholder 扫描**：Task 6 的三条集成测试含 `<按文件现有模式...>` 占位——这是刻意的：需读 `test_executor_actions.py` 现有 fixture 后填充，实现者必须先读该文件（已在 step 注明）。其余 task 均为完整代码。
- **类型一致性**：`truncate_utf8_bytes(text: str, limit: int) -> str`、`has_valid_review_signal(stdout: str) -> bool`、`PostExecAction.require_review: bool`、`ActionsRunner.run(actions, returncode, env, has_review_signal: bool = True)` 跨 task 一致；YAML 别名 `requireReview` 在模型/模板/测试三处一致。
- **可测性硬约束遵守**：纯函数（truncate/signal）独立成 task 1/3，副作用隔离在 runner/executor 接线 task 5/6，与 spec §3 拆分一致。
