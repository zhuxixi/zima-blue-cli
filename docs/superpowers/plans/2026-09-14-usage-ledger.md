# Execution Usage Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每次 PJob 执行在 history 里记录真实消耗的 tokens 与估算成本，覆盖父 agent 与全部子代理（issue #213）。

**Architecture:** pi 启动参数从 `--no-session` 改为 `--session-dir <temp>/pi-sessions`，把会话文件与子代理产物写进本次执行自己的临时目录；执行结束、删除临时目录之前，由一个新建的纯函数优先采集模块解析这些文件，聚合出 `usage` dict，随终态记录写进 history；CLI 详情视图展示一行汇总。采集全程 fail-open，绝不影响执行结果。

**Tech Stack:** Python 3.10+、dataclasses、pytest（unit + integration）、Typer/Rich（CLI 展示）、uv（依赖与运行）。

## Global Constraints

- Python 3.10+，dataclass 风格（不引入 pydantic）；**不新增任何第三方依赖**。
- 所有新增/修改代码通过 `uv run black zima/ tests/ --line-length 100` 与 `uv run ruff check zima/ tests/`。
- 覆盖率门槛 60%（`uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`）。
- 测试隔离：unit/integration 测试继承 `tests.base.TestIsolator` 或使用 `isolated_zima_home` fixture，**禁止**触碰真实 `~/.zima`。
- commit message 用英文 conventional commits（`feat`/`fix`/`test`/`refactor`/`docs`/`chore`）。
- 代码注释与 docstring 用英文；Google-style docstring。
- **fail-open 硬约束**：采集异常只产生 `{"collected": false, "reason": ...}`，不得影响 `result.status` / `returncode` / `error_detail` / `action_errors`，不得阻止 temp 目录清理，不得往 stdout/stderr 打印 warning。
- `cost_note` 固定字符串 `"estimated"`；失败形状**不含** `totals` 键。
- 采集只存数字，不存 prompt / stdout / 文件路径。
- 所有工作在本 worktree 内完成（`/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-213-usage-ledger`），**不碰 main**；`git add <file>` 按文件 stage，不用 `git add -A`。

---

## File Structure

| 文件 | 状态 | 职责 |
|------|------|------|
| `zima/execution/usage_collector.py` | 新增 | 用量采集的唯一实现：解析父会话、解析子代理产物、合并、fail-open 编排、展示格式化 |
| `tests/unit/test_usage_collector.py` | 新增 | 上述模块的单元测试（纯函数 + fail-open） |
| `zima/models/agent.py` | 修改 | pi 命令构造：`sessionDir` → `--session-dir`；删除 `noSession` 默认参数与分支 |
| `zima/models/config_bundle.py` | 修改 | `build_command` 增加 `runtime_args` 透传 |
| `zima/execution/executor.py` | 修改 | 构造命令时注入 `sessionDir`；`ExecutionResult.usage`；finally 内采集 |
| `zima/execution/history.py` | 修改 | `ExecutionRecord.usage`（含 to_dict/from_dict/from_result）；`_STATE_FILE_FIELDS` 登记 |
| `zima/execution/background_runner.py` | 修改 | 终态写入时转发 `usage` |
| `zima/commands/pjob.py` | 修改 | `pjob history --detail` 展示 usage 行 |
| `tests/unit/test_models_agent.py` | 修改 | pi 命令构造断言更新 |
| `tests/unit/test_execution_history.py` | 修改 | usage 读写与 legacy 兼容 |
| `tests/unit/test_background_runner.py` | 修改 | usage 转发断言 |
| `tests/integration/test_usage_ledger.py` | 新增 | 端到端：假 agent 写会话文件 → history 有 usage + temp 清理 |
| `zima/templates/examples.py` | 修改 | 示例 pi agent 去掉 `noSession` |
| `docs/architecture/data-and-runtime-reference.md` | 修改 | pi 参数字段表更新 |
| `CHANGELOG.md` | 修改 | 行为变更说明 |

---

### Task 1: `parse_parent_usage` — 解析父 agent 用量

**Files:**
- Create: `zima/execution/usage_collector.py`
- Test: `tests/unit/test_usage_collector.py`

**Interfaces:**
- Consumes: 无（本任务建立模块）
- Produces:
  - `parse_parent_usage(session_files: Sequence[Path]) -> dict`，返回 `{"totals": <totals>, "by_model": [<bucket>, ...]}`
  - `<totals>` = `{"input": int, "output": int, "cache_read": int, "cache_write": int, "total_tokens": int, "cost_usd": float}`
  - `<bucket>` = `<totals>` + `{"role": "parent", "agent": None, "provider": str, "model": str, "turns": None}`
  - 私有辅助：`_empty_totals() -> dict`、`_add_into(target: dict, entry: dict) -> None`、`_iter_session_messages(path: Path) -> Iterator[dict]`、`_parent_entry(message: dict) -> Optional[dict]`

- [ ] **Step 1: 写失败的测试**

```python
"""Unit tests for usage ledger collection (#213)."""

from __future__ import annotations

import json

from zima.execution.usage_collector import parse_parent_usage


def _write_session(tmp_path, name, entries):
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
        encoding="utf-8",
    )
    return path


def _assistant(provider, model, *, input_tokens, output, total, cost, cache_read=0):
    return {
        "type": "message",
        "id": "m1",
        "message": {
            "role": "assistant",
            "provider": provider,
            "model": model,
            "usage": {
                "input": input_tokens,
                "output": output,
                "cacheRead": cache_read,
                "cacheWrite": 0,
                "totalTokens": total,
                "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0,
                         "total": cost},
            },
        },
    }


class TestParseParentUsage:
    def test_sums_assistant_usage(self, tmp_path):
        path = _write_session(
            tmp_path,
            "a.jsonl",
            [
                {"type": "session", "version": 3, "id": "s1", "cwd": "/tmp"},
                {"type": "message", "message": {"role": "user", "content": "hi"}},
                _assistant("zai-coding-cn", "glm-5.3", input_tokens=1000, output=10,
                           total=1010, cost=0.01),
                _assistant("zai-coding-cn", "glm-5.3", input_tokens=2000, output=20,
                           total=2020, cost=0.02),
            ],
        )

        result = parse_parent_usage([path])

        assert result["totals"] == {
            "input": 3000,
            "output": 30,
            "cache_read": 0,
            "cache_write": 0,
            "total_tokens": 3030,
            "cost_usd": 0.03,
        }
        assert len(result["by_model"]) == 1
        bucket = result["by_model"][0]
        assert bucket["role"] == "parent"
        assert bucket["agent"] is None
        assert bucket["provider"] == "zai-coding-cn"
        assert bucket["model"] == "glm-5.3"
        assert bucket["turns"] is None
        assert bucket["input"] == 3000

    def test_skips_non_assistant_and_missing_usage(self, tmp_path):
        path = _write_session(
            tmp_path,
            "b.jsonl",
            [
                {"type": "message", "message": {"role": "user", "content": "hi"}},
                {"type": "message", "message": {"role": "toolResult", "toolName": "bash"}},
                {"type": "model_change", "provider": "x", "modelId": "y"},
                {"type": "message", "message": {"role": "assistant", "content": []}},
            ],
        )

        result = parse_parent_usage([path])

        assert result["totals"]["total_tokens"] == 0
        assert result["by_model"] == []

    def test_skips_malformed_lines_and_unreadable_files(self, tmp_path):
        path = tmp_path / "c.jsonl"
        path.write_text(
            '{"type": "message", "message": {"role": "assistant", "provider": "p",\n'
            "not json at all\n"
            + json.dumps(_assistant("p", "m", input_tokens=5, output=5, total=10, cost=0.001))
            + "\n",
            encoding="utf-8",
        )

        result = parse_parent_usage([path, tmp_path / "does-not-exist.jsonl"])

        assert result["totals"]["total_tokens"] == 10

    def test_groups_by_provider_and_model(self, tmp_path):
        path = _write_session(
            tmp_path,
            "d.jsonl",
            [
                _assistant("zai-coding-cn", "glm-5.3", input_tokens=10, output=1, total=11,
                           cost=0.001),
                _assistant("zai-coding-cn", "glm-5.3-flash", input_tokens=20, output=2, total=22,
                           cost=0.002),
                _assistant("zai-coding-cn", "glm-5.3", input_tokens=30, output=3, total=33,
                           cost=0.003),
            ],
        )

        result = parse_parent_usage([path])

        by_model = {(b["provider"], b["model"]): b for b in result["by_model"]}
        assert set(by_model) == {("zai-coding-cn", "glm-5.3"), ("zai-coding-cn", "glm-5.3-flash")}
        assert by_model[("zai-coding-cn", "glm-5.3")]["total_tokens"] == 44
        assert by_model[("zai-coding-cn", "glm-5.3-flash")]["total_tokens"] == 22
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_usage_collector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'zima.execution.usage_collector'`

- [ ] **Step 3: 写最小实现**

```python
"""Usage ledger collection for PJob executions (#213).

Reads pi session files and pi-subagents artifact metadata written under the
execution's own temp directory, aggregates them into a single ``usage`` dict
that is persisted with the execution history record.

Every function is fail-open: unreadable or malformed input degrades to an
empty result instead of raising. The orchestration entry point
(:func:`collect_usage`) never raises at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional, Sequence

ROLE_PARENT = "parent"
ROLE_CHILD = "child"

#: Keys shared by every totals bucket. Order matters only for readability.
_TOTAL_KEYS = ("input", "output", "cache_read", "cache_write", "total_tokens")


def _empty_totals() -> dict:
    """Return a zeroed totals bucket."""
    totals = {key: 0 for key in _TOTAL_KEYS}
    totals["cost_usd"] = 0.0
    return totals


def _add_into(target: dict, entry: dict) -> None:
    """Add an entry's numeric fields into a totals bucket (in place)."""
    for key in _TOTAL_KEYS:
        try:
            target[key] += int(entry.get(key) or 0)
        except (TypeError, ValueError):
            continue
    try:
        target["cost_usd"] += float(entry.get("cost_usd") or 0.0)
    except (TypeError, ValueError):
        pass


def _iter_session_messages(path: Path) -> Iterator[dict]:
    """Yield parsed JSON objects from a session JSONL file.

    Malformed lines and unreadable files are skipped silently so that one bad
    line cannot discard an otherwise valid ledger.
    """
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def _parent_entry(message: dict) -> Optional[dict]:
    """Extract a usage entry from a pi session ``assistant`` message.

    Returns ``None`` for any message that carries no provider-reported usage.
    """
    if message.get("role") != "assistant":
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    cost = usage.get("cost")
    return {
        "input": usage.get("input", 0),
        "output": usage.get("output", 0),
        "cache_read": usage.get("cacheRead", 0),
        "cache_write": usage.get("cacheWrite", 0),
        "total_tokens": usage.get("totalTokens", 0),
        "cost_usd": cost.get("total", 0.0) if isinstance(cost, dict) else 0.0,
        "provider": message.get("provider") or "unknown",
        "model": message.get("model") or "unknown",
    }


def parse_parent_usage(session_files: Sequence[Path]) -> dict:
    """Aggregate parent-agent usage from top-level pi session files.

    Args:
        session_files: Top-level session JSONL paths. Files under ``forks/``
            must NOT be passed here — they contain copies of parent messages
            and would double count.

    Returns:
        ``{"totals": <totals>, "by_model": [<bucket>, ...]}`` where each bucket
        is grouped by ``(provider, model)``.
    """
    totals = _empty_totals()
    buckets: dict[tuple[str, str], dict] = {}

    for path in session_files:
        for entry in _iter_session_messages(Path(path)):
            if entry.get("type") != "message":
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            parsed = _parent_entry(message)
            if parsed is None:
                continue

            _add_into(totals, parsed)
            key = (parsed["provider"], parsed["model"])
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "role": ROLE_PARENT,
                    "agent": None,
                    "provider": key[0],
                    "model": key[1],
                    "turns": None,
                    **_empty_totals(),
                }
                buckets[key] = bucket
            _add_into(bucket, parsed)

    return {"totals": totals, "by_model": list(buckets.values())}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_usage_collector.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add zima/execution/usage_collector.py tests/unit/test_usage_collector.py
git commit -m "feat(observability): parse parent-agent usage from pi session files (#213)"
```

---

### Task 2: `parse_child_usage` — 解析子代理用量

**Files:**
- Modify: `zima/execution/usage_collector.py`
- Test: `tests/unit/test_usage_collector.py`

**Interfaces:**
- Consumes: `_empty_totals`、`_add_into`（Task 1）
- Produces: `parse_child_usage(artifacts_dir: Optional[Path]) -> dict`，返回 `{"totals": <totals>, "by_model": [<child bucket>, ...], "children_count": int}`；child bucket = `<totals>` + `{"role": "child", "agent": str, "provider": str, "model": str, "turns": int | None}`

- [ ] **Step 1: 写失败的测试**

```python
def _write_child_meta(artifacts_dir, run_id, agent, model, *, input_tokens, output,
                      cache_read=0, cost=0.0, turns=1):
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = artifacts_dir / f"{run_id}_{agent}_meta.json"
    path.write_text(
        json.dumps(
            {
                "runId": run_id,
                "agent": agent,
                "model": model,
                "usage": {
                    "input": input_tokens,
                    "output": output,
                    "cacheRead": cache_read,
                    "cacheWrite": 0,
                    "cost": cost,
                    "turns": turns,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


class TestParseChildUsage:
    def test_reads_meta_files(self, tmp_path):
        artifacts = tmp_path / "subagent-artifacts"
        _write_child_meta(artifacts, "r1", "worker", "zai-coding-cn/glm-5.3-flash", 
                          input_tokens=1909, output=102, cache_read=2304, cost=0.0002, turns=1)

        result = parse_child_usage(artifacts)

        assert result["children_count"] == 1
        assert result["totals"] == {
            "input": 1909,
            "output": 102,
            "cache_read": 2304,
            "cache_write": 0,
            "total_tokens": 4315,
            "cost_usd": 0.0002,
        }
        bucket = result["by_model"][0]
        assert bucket["role"] == "child"
        assert bucket["agent"] == "worker"
        assert bucket["provider"] == "zai-coding-cn"
        assert bucket["model"] == "glm-5.3-flash"
        assert bucket["turns"] == 1

    def test_missing_dir_returns_empty(self, tmp_path):
        result = parse_child_usage(tmp_path / "nope")

        assert result == {"totals": _zero_totals(), "by_model": [], "children_count": 0}

    def test_skips_meta_without_usage(self, tmp_path):
        artifacts = tmp_path / "subagent-artifacts"
        artifacts.mkdir()
        (artifacts / "r9_worker_meta.json").write_text('{"agent": "worker"}', encoding="utf-8")
        (artifacts / "broken_meta.json").write_text("{ not json", encoding="utf-8")

        result = parse_child_usage(artifacts)

        assert result["children_count"] == 0
        assert result["by_model"] == []

    def test_aggregates_same_agent_and_model(self, tmp_path):
        artifacts = tmp_path / "subagent-artifacts"
        _write_child_meta(artifacts, "r1", "checker", "zai-coding-cn/glm-5.3-flash",
                          input_tokens=100, output=10, cost=0.001, turns=2)
        _write_child_meta(artifacts, "r2", "checker", "zai-coding-cn/glm-5.3-flash",
                          input_tokens=200, output=20, cost=0.002, turns=3)

        result = parse_child_usage(artifacts)

        assert result["children_count"] == 2
        assert result["totals"]["total_tokens"] == 330
        assert len(result["by_model"]) == 1
        assert result["by_model"][0]["input"] == 300
        assert result["by_model"][0]["turns"] == 5
```

> 测试文件顶部同时补充 import：`from zima.execution.usage_collector import _empty_totals, parse_child_usage`，并在测试里用 helper：
> ```python
> def _zero_totals():
>     return _empty_totals()
> ```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_usage_collector.py -k child -v`
Expected: FAIL — `ImportError: cannot import name 'parse_child_usage'`

- [ ] **Step 3: 写最小实现**

```python
def _split_child_model(raw: str) -> tuple[str, str]:
    """Split a pi-subagents model string into ``(provider, model)``.

    ``model`` keeps the reported value verbatim (including any ``:thinking``
    suffix) so the ledger can show which tier actually ran. Aggregation
    therefore happens per exact model string.
    """
    raw = raw or "unknown"
    if "/" in raw:
        provider, model = raw.split("/", 1)
        return provider, model
    return "unknown", raw


def _child_entry(meta: dict) -> Optional[dict]:
    """Extract a usage entry from a pi-subagents ``*_meta.json`` payload."""
    usage = meta.get("usage")
    if not isinstance(usage, dict):
        return None
    provider, model = _split_child_model(str(meta.get("model") or ""))
    try:
        input_tokens = int(usage.get("input") or 0)
        output = int(usage.get("output") or 0)
        cache_read = int(usage.get("cacheRead") or 0)
        cache_write = int(usage.get("cacheWrite") or 0)
        cost = float(usage.get("cost") or 0.0)
    except (TypeError, ValueError):
        return None
    turns = usage.get("turns")
    try:
        turns = int(turns) if turns is not None else None
    except (TypeError, ValueError):
        turns = None
    return {
        "input": input_tokens,
        "output": output,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "total_tokens": input_tokens + output + cache_read + cache_write,
        "cost_usd": cost,
        "agent": meta.get("agent") or "unknown",
        "provider": provider,
        "model": model,
        "turns": turns,
    }


def parse_child_usage(artifacts_dir: Optional[Path]) -> dict:
    """Aggregate subagent usage from pi-subagents artifact metadata.

    Args:
        artifacts_dir: ``<session_dir>/subagent-artifacts`` (may be missing).

    Returns:
        ``{"totals": <totals>, "by_model": [<bucket>, ...], "children_count": int}``
        where buckets are grouped by ``(agent, provider, model)``.
    """
    totals = _empty_totals()
    buckets: dict[tuple[str, str, str], dict] = {}
    children_count = 0

    if artifacts_dir is not None and Path(artifacts_dir).is_dir():
        for meta_file in sorted(Path(artifacts_dir).glob("*_meta.json")):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8", errors="replace"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            parsed = _child_entry(meta)
            if parsed is None:
                continue

            children_count += 1
            _add_into(totals, parsed)
            key = (parsed["agent"], parsed["provider"], parsed["model"])
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "role": ROLE_CHILD,
                    "agent": key[0],
                    "provider": key[1],
                    "model": key[2],
                    "turns": 0,
                    **_empty_totals(),
                }
                buckets[key] = bucket
            _add_into(bucket, parsed)
            if parsed["turns"] is not None:
                bucket["turns"] += parsed["turns"]
            else:
                bucket["turns"] = None if bucket["turns"] is None else bucket["turns"]

    return {"totals": totals, "by_model": list(buckets.values()), "children_count": children_count}
```

> 说明：`bucket["turns"]` 初始为 `0`；若某个子代理的 `turns` 缺失，则该 bucket 的 turns 记为 `None`（"未知"不能伪装成 0 之和）。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_usage_collector.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
git add zima/execution/usage_collector.py tests/unit/test_usage_collector.py
git commit -m "feat(observability): parse subagent usage from artifact metadata (#213)"
```

---

### Task 3: `merge_usage` — 合并父与子

**Files:**
- Modify: `zima/execution/usage_collector.py`
- Test: `tests/unit/test_usage_collector.py`

**Interfaces:**
- Consumes: `_empty_totals`、`_add_into`（Task 1）；`parse_parent_usage` / `parse_child_usage` 的返回形状（Task 1、2）
- Produces: `merge_usage(parent: dict, children: dict) -> dict`，返回最终 `usage` dict：`{"collected": True, "totals": ..., "by_role": {"parent": ..., "children": ...}, "by_model": [...], "children_count": int, "cost_note": "estimated"}`

- [ ] **Step 1: 写失败的测试**

```python
class TestMergeUsage:
    def test_combines_parent_and_children(self):
        parent = {"totals": {"input": 100, "output": 10, "cache_read": 0, "cache_write": 0,
                             "total_tokens": 110, "cost_usd": 0.01}, "by_model": [{"role": "parent"}]}
        children = {"totals": {"input": 900, "output": 90, "cache_read": 0, "cache_write": 0,
                               "total_tokens": 990, "cost_usd": 0.09},
                    "by_model": [{"role": "child"}], "children_count": 3}

        merged = merge_usage(parent, children)

        assert merged["collected"] is True
        assert merged["totals"] == {"input": 1000, "output": 100, "cache_read": 0,
                                    "cache_write": 0, "total_tokens": 1100, "cost_usd": 0.1}
        assert merged["by_role"]["parent"]["total_tokens"] == 110
        assert merged["by_role"]["children"]["total_tokens"] == 990
        assert merged["by_model"] == [{"role": "parent"}, {"role": "child"}]
        assert merged["children_count"] == 3
        assert merged["cost_note"] == "estimated"

    def test_no_children(self):
        parent = {"totals": {"input": 5, "output": 5, "cache_read": 0, "cache_write": 0,
                             "total_tokens": 10, "cost_usd": 0.0}, "by_model": []}
        children = {"totals": _empty_totals(), "by_model": [], "children_count": 0}

        merged = merge_usage(parent, children)

        assert merged["totals"]["total_tokens"] == 10
        assert merged["children_count"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_usage_collector.py -k merge -v`
Expected: FAIL — `ImportError: cannot import name 'merge_usage'`

- [ ] **Step 3: 写最小实现**

```python
#: Marks cost as a price-table estimate rather than a cash spend.
COST_NOTE_ESTIMATED = "estimated"


def merge_usage(parent: dict, children: dict) -> dict:
    """Merge parent and child usage into the persisted ``usage`` payload.

    Args:
        parent: Result of :func:`parse_parent_usage`.
        children: Result of :func:`parse_child_usage`.

    Returns:
        The complete ``usage`` dict stored on the execution record, with
        ``collected: True``.
    """
    totals = _empty_totals()
    _add_into(totals, parent.get("totals") or {})
    _add_into(totals, children.get("totals") or {})

    return {
        "collected": True,
        "totals": totals,
        "by_role": {
            "parent": parent.get("totals") or _empty_totals(),
            "children": children.get("totals") or _empty_totals(),
        },
        "by_model": list(parent.get("by_model") or []) + list(children.get("by_model") or []),
        "children_count": int(children.get("children_count") or 0),
        "cost_note": COST_NOTE_ESTIMATED,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_usage_collector.py -v`
Expected: PASS（10 passed）

- [ ] **Step 5: 提交**

```bash
git add zima/execution/usage_collector.py tests/unit/test_usage_collector.py
git commit -m "feat(observability): merge parent and child usage into one payload (#213)"
```

---

### Task 4: `collect_usage` — IO 编排与 fail-open

**Files:**
- Modify: `zima/execution/usage_collector.py`
- Test: `tests/unit/test_usage_collector.py`

**Interfaces:**
- Consumes: `parse_parent_usage`、`parse_child_usage`、`merge_usage`（Task 1-3）
- Produces: `collect_usage(session_dir: Optional[Path], agent_type: str = "pi") -> dict`，返回 `merge_usage` 的产物或 `{"collected": False, "reason": <code>}`，`reason ∈ {"no_session_dir", "empty", "parse_error", "unsupported_agent_type"}`

- [ ] **Step 1: 写失败的测试**

```python
class TestCollectUsage:
    def test_collects_parent_and_children_from_session_dir(self, tmp_path):
        session_dir = tmp_path / "pi-sessions"
        session_dir.mkdir()
        _write_session(
            session_dir,
            "s.jsonl",
            [_assistant("zai-coding-cn", "glm-5.3", input_tokens=100, output=10, total=110,
                        cost=0.01)],
        )
        _write_child_meta(session_dir / "subagent-artifacts", "r1", "checker",
                          "zai-coding-cn/glm-5.3-flash", input_tokens=900, output=90,
                          cost=0.09, turns=2)

        usage = collect_usage(session_dir)

        assert usage["collected"] is True
        assert usage["totals"]["total_tokens"] == 1100
        assert usage["by_role"]["parent"]["total_tokens"] == 110
        assert usage["by_role"]["children"]["total_tokens"] == 990
        assert usage["children_count"] == 1
        assert usage["cost_note"] == "estimated"

    def test_ignores_forks_and_transcripts(self, tmp_path):
        """forks/ copies and *_transcript.jsonl must not be counted twice."""
        session_dir = tmp_path / "pi-sessions"
        forks = session_dir / "forks"
        forks.mkdir(parents=True)
        parent_only = [_assistant("p", "m", input_tokens=100, output=10, total=110, cost=0.01)]
        _write_session(session_dir, "s.jsonl", parent_only)
        _write_session(forks, "fork.jsonl", parent_only)  # copy of the parent history
        artifacts = session_dir / "subagent-artifacts"
        artifacts.mkdir()
        (artifacts / "r1_worker_transcript.jsonl").write_text(
            json.dumps(parent_only[0]) + "\n", encoding="utf-8"
        )

        usage = collect_usage(session_dir)

        assert usage["totals"]["total_tokens"] == 110  # not 220

    def test_missing_dir_is_reported_not_raised(self, tmp_path):
        assert collect_usage(tmp_path / "absent") == {
            "collected": False,
            "reason": "no_session_dir",
        }

    def test_none_session_dir(self):
        assert collect_usage(None) == {"collected": False, "reason": "no_session_dir"}

    def test_empty_dir_reports_empty(self, tmp_path):
        session_dir = tmp_path / "pi-sessions"
        session_dir.mkdir()

        assert collect_usage(session_dir) == {"collected": False, "reason": "empty"}

    def test_unsupported_agent_type(self, tmp_path):
        session_dir = tmp_path / "pi-sessions"
        session_dir.mkdir()

        assert collect_usage(session_dir, agent_type="claude") == {
            "collected": False,
            "reason": "unsupported_agent_type",
        }

    def test_parse_error_is_swallowed(self, tmp_path, monkeypatch):
        session_dir = tmp_path / "pi-sessions"
        session_dir.mkdir()

        def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("zima.execution.usage_collector.parse_parent_usage", _boom)

        assert collect_usage(session_dir) == {"collected": False, "reason": "parse_error"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_usage_collector.py -k collect -v`
Expected: FAIL — `ImportError: cannot import name 'collect_usage'`

- [ ] **Step 3: 写最小实现**

```python
def collect_usage(session_dir: Optional[Path], agent_type: str = "pi") -> dict:
    """Collect the usage ledger for one execution. Never raises.

    Args:
        session_dir: ``<temp_dir>/pi-sessions`` — the directory handed to pi
            via ``--session-dir``.
        agent_type: Agent type of the executed PJob (only ``"pi"`` is supported).

    Returns:
        Either the merged ``usage`` payload (``collected: True``) or
        ``{"collected": False, "reason": <code>}``.
    """
    if agent_type != "pi":
        return {"collected": False, "reason": "unsupported_agent_type"}
    if session_dir is None:
        return {"collected": False, "reason": "no_session_dir"}

    try:
        root = Path(session_dir)
        if not root.is_dir():
            return {"collected": False, "reason": "no_session_dir"}

        session_files = sorted(p for p in root.glob("*.jsonl") if p.is_file())
        parent = parse_parent_usage(session_files)
        children = parse_child_usage(root / "subagent-artifacts")
        merged = merge_usage(parent, children)

        if merged["totals"]["total_tokens"] <= 0:
            return {"collected": False, "reason": "empty"}
        return merged
    except Exception:
        # Fail-open by design: observability must never break an execution.
        return {"collected": False, "reason": "parse_error"}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_usage_collector.py -v`
Expected: PASS（17 passed）

- [ ] **Step 5: 提交**

```bash
git add zima/execution/usage_collector.py tests/unit/test_usage_collector.py
git commit -m "feat(observability): fail-open usage collection entry point (#213)"
```

---

### Task 5: `format_usage_line` — 展示格式化

**Files:**
- Modify: `zima/execution/usage_collector.py`
- Test: `tests/unit/test_usage_collector.py`

**Interfaces:**
- Consumes: `usage` dict（Task 4 的形状）
- Produces: `format_usage_line(usage: Optional[dict]) -> str`；私有 `_human_count(value: float) -> str`

- [ ] **Step 1: 写失败的测试**

```python
class TestFormatUsageLine:
    def test_collected_line(self):
        usage = {
            "collected": True,
            "totals": {"input": 6_550_000, "output": 10_700, "cache_read": 0, "cache_write": 0,
                       "total_tokens": 6_560_700, "cost_usd": 0.4941},
            "by_role": {
                "parent": {"total_tokens": 17_163},
                "children": {"total_tokens": 6_543_537},
            },
            "by_model": [],
            "children_count": 12,
            "cost_note": "estimated",
        }

        line = format_usage_line(usage)

        assert line == ("Usage:  in 6.55M / out 10.70K  ·  est. $0.49  ·  "
                        "parent 0% / children 100%")

    def test_none_record_is_unknown(self):
        assert format_usage_line(None) == "Usage:  unknown (not_collected)"

    def test_failed_collection_shows_reason(self):
        line = format_usage_line({"collected": False, "reason": "no_session_dir"})

        assert line == "Usage:  unknown (no_session_dir)"

    def test_human_count_plain_number(self):
        assert _human_count(999) == "999"
        assert _human_count(1500) == "1.50K"
        assert _human_count(2_500_000) == "2.50M"

    def test_zero_total_does_not_divide_by_zero(self):
        usage = {
            "collected": True,
            "totals": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
                       "total_tokens": 0, "cost_usd": 0.0},
            "by_role": {"parent": {"total_tokens": 0}, "children": {"total_tokens": 0}},
            "by_model": [],
            "children_count": 0,
            "cost_note": "estimated",
        }

        assert "parent 0% / children 0%" in format_usage_line(usage)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_usage_collector.py -k format -v`
Expected: FAIL — `ImportError: cannot import name 'format_usage_line'`

- [ ] **Step 3: 写最小实现**

```python
def _human_count(value: float) -> str:
    """Format a token count with K/M suffixes (two decimals)."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    for suffix, divisor in (("M", 1_000_000.0), ("K", 1_000.0)):
        if abs(number) >= divisor:
            return f"{number / divisor:.2f}{suffix}"
    return f"{int(number)}"


def format_usage_line(usage: Optional[dict]) -> str:
    """Render one human-readable usage summary line.

    Handles three states: collected, failed collection (with reason), and
    missing/legacy records (``not_collected``).
    """
    if not isinstance(usage, dict):
        return "Usage:  unknown (not_collected)"
    if not usage.get("collected"):
        reason = usage.get("reason") or "not_collected"
        return f"Usage:  unknown ({reason})"

    totals = usage.get("totals") or {}
    by_role = usage.get("by_role") or {}
    total_tokens = int(totals.get("total_tokens") or 0)
    parent_tokens = int(((by_role.get("parent") or {}).get("total_tokens")) or 0)
    if total_tokens > 0:
        parent_pct = int(round(parent_tokens / total_tokens * 100))
        child_pct = 100 - parent_pct
    else:
        parent_pct = 0
        child_pct = 0
    cost = float(totals.get("cost_usd") or 0.0)

    return (
        f"Usage:  in {_human_count(totals.get('input'))} / out {_human_count(totals.get('output'))}"
        f"  ·  est. ${cost:.2f}"
        f"  ·  parent {parent_pct}% / children {child_pct}%"
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_usage_collector.py -v`
Expected: PASS（22 passed）

- [ ] **Step 5: 提交**

```bash
git add zima/execution/usage_collector.py tests/unit/test_usage_collector.py
git commit -m "feat(observability): render usage summary line (#213)"
```

---

### Task 6: pi 命令构造改为 `--session-dir`，退役 `noSession`

**Files:**
- Modify: `zima/models/agent.py`（`AGENT_PARAMETER_TEMPLATES["pi"]`、`_build_pi_command` 及其 docstring）
- Modify: `zima/templates/examples.py`（示例 agent 去掉 `noSession`）
- Test: `tests/unit/test_models_agent.py`

**Interfaces:**
- Consumes: 无
- Produces: pi 命令包含 `--session-dir <path>`（当参数 `sessionDir` 存在时）；`--no-session` 永不再出现；`AGENT_PARAMETER_TEMPLATES["pi"]` 不含 `noSession`

- [ ] **Step 1: 写失败的测试**

替换 `tests/unit/test_models_agent.py` 中 `test_pi_default_parameters` 与 `test_build_pi_command`，并新增两个测试：

```python
    def test_pi_default_parameters(self):
        """Test pi agent gets default parameters merged (thinking max, text, tools)."""
        config = AgentConfig.create("test", "Test", "pi")

        assert config.parameters["thinking"] == "max"
        assert "noSession" not in config.parameters
        assert config.parameters["outputFormat"] == "text"
        assert config.parameters["tools"] == ["read", "bash", "grep", "find", "ls"]
        assert config.parameters["noContextFiles"] is False

    def test_build_pi_command(self):
        """Test pi command construction with all flags."""
        config = AgentConfig.create(
            "test",
            "Test",
            "pi",
            parameters={
                "provider": "ollama",
                "model": "deepseek-v4-flash:0731-cloud",
                "thinking": "max",
                "outputFormat": "text",
                "tools": ["read", "bash", "grep", "find", "ls"],
            },
        )

        cmd = config.build_command()

        assert cmd[0] == "pi"
        assert "-p" in cmd
        assert "--provider" in cmd and "ollama" in cmd
        assert "--model" in cmd and "deepseek-v4-flash:0731-cloud" in cmd
        assert "--thinking" in cmd and "max" in cmd
        assert "--no-session" not in cmd
        assert "--session-dir" not in cmd  # only injected when provided at runtime
        assert "--mode" in cmd and "text" in cmd
        assert "--tools" in cmd and "read,bash,grep,find,ls" in cmd

    def test_build_pi_command_injects_session_dir(self):
        """sessionDir extra arg becomes --session-dir (#213)."""
        config = AgentConfig.create("test", "Test", "pi", parameters={})

        cmd = config.build_command(
            extra_args={"sessionDir": "/tmp/zima-exec/pi-sessions"}
        )

        assert "--session-dir" in cmd
        assert cmd[cmd.index("--session-dir") + 1] == "/tmp/zima-exec/pi-sessions"
        assert "--no-session" not in cmd

    def test_build_pi_command_ignores_residual_no_session(self):
        """Legacy `noSession: true` in user YAML must not resurrect --no-session."""
        config = AgentConfig.create("test", "Test", "pi", parameters={"noSession": True})

        cmd = config.build_command()

        assert "--no-session" not in cmd
```

> 同时删除文件里其他断言 `"--no-session" in cmd` 的用例（若存在），改断 `--no-session` 不出现。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_models_agent.py -k "pi" -v`
Expected: FAIL — `assert 'noSession' not in {…}` 与 `assert '--no-session' not in cmd` 失败

- [ ] **Step 3: 写最小实现**

`zima/models/agent.py` 的 `AGENT_PARAMETER_TEMPLATES["pi"]` 删除 `"noSession": True,` 一行；`_build_pi_command` 中把

```python
        if params.get("noSession"):
            cmd.append("--no-session")
```

替换为

```python
        if params.get("sessionDir"):
            cmd.extend(["--session-dir", str(params["sessionDir"])])
```

并把 docstring 中的

```
          --no-session           : Don't save session (ephemeral)
```

替换为

```
          --session-dir          : Write the session file into this directory
                                   (injected by the executor; #213)
```

`zima/templates/examples.py` 的示例 pi agent 删除 `    noSession: true` 一行。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_models_agent.py tests/unit/test_examples.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add zima/models/agent.py zima/templates/examples.py tests/unit/test_models_agent.py
git commit -m "refactor(agent): replace pi --no-session with --session-dir (#213)"
```

---

### Task 7: executor 注入 `sessionDir`

**Files:**
- Modify: `zima/models/config_bundle.py`（`build_command` 增加 `runtime_args`）
- Modify: `zima/execution/executor.py:629`（注入）
- Test: `tests/unit/test_config_bundle.py`、`tests/unit/test_executor_fixes.py`

**Interfaces:**
- Consumes: `AgentConfig.build_command(prompt_file, extra_args)`（Task 6）
- Produces: `ConfigBundle.build_command(prompt_file: Path, runtime_args: Optional[dict] = None) -> list[str]`；执行时命令含 `--session-dir <temp_dir>/pi-sessions`

- [ ] **Step 1: 写失败的测试**

`tests/unit/test_config_bundle.py` 新增：

```python
    def test_build_command_forwards_runtime_args(self, isolated_zima_home):
        from zima.models.agent import AgentConfig
        from zima.models.config_bundle import ConfigBundle

        agent = AgentConfig.create("a1", "A1", "pi", parameters={})
        bundle = ConfigBundle(agent=agent)

        cmd = bundle.build_command(
            prompt_file=Path("/tmp/prompt.md"),
            runtime_args={"sessionDir": "/tmp/exec/pi-sessions"},
        )

        assert "--session-dir" in cmd
        assert cmd[cmd.index("--session-dir") + 1] == "/tmp/exec/pi-sessions"
```

`tests/unit/test_executor_fixes.py` 新增（验证 executor 把 temp 目录下的 `pi-sessions` 传进去）：

```python
class TestExecutorSessionDirInjection:
    """pi agents must receive --session-dir pointing inside the temp dir (#213)."""

    def test_pi_command_carries_session_dir(self, isolated_zima_home, config_manager):
        from zima.models.pjob import PJobConfig
        from zima.models.workflow import WorkflowConfig

        config_manager.save_config(
            "agent",
            "sd-agent",
            {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "sd-agent", "name": "SD Agent"},
                "spec": {"type": "pi", "parameters": {"mockCommand": ["echo", "ok"]}},
            },
        )
        wf = WorkflowConfig.create(code="sd-wf", name="SD Workflow", template="do it",
                                   variables=[])
        config_manager.save_config("workflow", "sd-wf", wf.to_dict())
        pjob = PJobConfig.create(code="sd-pjob", name="SD PJob", agent="sd-agent",
                                workflow="sd-wf")
        config_manager.save_config("pjob", "sd-pjob", pjob.to_dict())

        executor = PJobExecutor()
        result = executor.execute("sd-pjob", dry_run=True)

        # dry_run echoes the command without executing the agent (the command is
        # built before the dry-run branch, executor.py:629-635)
        assert "--session-dir" in result.command
        session_dir = result.command[result.command.index("--session-dir") + 1]
        assert session_dir.endswith("sd-pjob-" + result.execution_id + "/pi-sessions")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_config_bundle.py tests/unit/test_executor_fixes.py -k "runtime_args or session_dir" -v`
Expected: FAIL — `TypeError: build_command() got an unexpected keyword argument 'runtime_args'`

- [ ] **Step 3: 写最小实现**

`zima/models/config_bundle.py`：

```python
    def build_command(
        self,
        prompt_file: Path,
        runtime_args: Optional[dict] = None,
    ) -> list[str]:
        """Build the complete agent command.

        Delegates type-specific command building to AgentConfig.build_command()
        which handles each agent's unique CLI flags and prompt passing mechanism.
        Then appends PMG parameters on top. (The working directory is applied by
        the executor via subprocess ``cwd=``, not encoded in the command string.)

        Args:
            prompt_file: Path to the rendered prompt file
            runtime_args: Runtime parameter overrides forwarded to the agent
                (e.g. ``{"sessionDir": "..."}`` for pi agents, #213). Unknown
                keys are ignored by agent types that do not consume them.

        Returns:
            Command as list of arguments (for subprocess)
        """
        cmd = self.agent.build_command(prompt_file=prompt_file, extra_args=runtime_args)
```

`zima/execution/executor.py:629`：

```python
            # 7. Build command (pi gets its session dir inside the temp dir so
            # that usage can be collected before the temp dir is removed; #213)
            command = bundle.build_command(
                prompt_file,
                runtime_args={"sessionDir": str(temp_dir / "pi-sessions")},
            )
            result.command = command
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_config_bundle.py tests/unit/test_executor_fixes.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add zima/models/config_bundle.py zima/execution/executor.py tests/unit/test_config_bundle.py tests/unit/test_executor_fixes.py
git commit -m "refactor(executor): inject pi session dir into the execution temp dir (#213)"
```

---

### Task 8: `ExecutionRecord.usage` 读写

**Files:**
- Modify: `zima/execution/history.py`（`ExecutionRecord`、`_STATE_FILE_FIELDS`）
- Test: `tests/unit/test_execution_history.py`

**Interfaces:**
- Consumes: `usage` dict 形状（Task 3）
- Produces: `ExecutionRecord.usage: Optional[dict] = None`；`to_dict()` 在非 None 时输出 `"usage"`；`from_dict()` 读回；`from_result()` 从 `result.usage` 取值；`_STATE_FILE_FIELDS` 包含 `"usage"`

- [ ] **Step 1: 写失败的测试**

`tests/unit/test_execution_history.py` 新增：

```python
class TestUsageLedgerField:
    @pytest.fixture(autouse=True)
    def setup(self, isolated_zima_home):
        self.history = ExecutionHistory()
        self.pjob_code = "usage-pjob"
        self.exec_id = "u1u2u3u4"
        self.usage = {
            "collected": True,
            "totals": {"input": 100, "output": 10, "cache_read": 0, "cache_write": 0,
                       "total_tokens": 110, "cost_usd": 0.01},
            "by_role": {"parent": {"total_tokens": 110}, "children": {"total_tokens": 0}},
            "by_model": [],
            "children_count": 0,
            "cost_note": "estimated",
        }

    def test_usage_survives_write_and_read(self):
        self.history.write_runtime_state(
            self.pjob_code,
            self.exec_id,
            {
                "execution_id": self.exec_id,
                "pjob_code": self.pjob_code,
                "status": "success",
                "started_at": "2026-09-14T10:00:00+08:00",
            },
        )
        self.history.update_runtime_state(self.pjob_code, self.exec_id, usage=self.usage)

        record = self.history.get_record(self.pjob_code, self.exec_id)

        assert record is not None
        assert record.usage == self.usage

    def test_legacy_record_without_usage_reads_as_none(self):
        self.history.write_runtime_state(
            self.pjob_code,
            self.exec_id,
            {
                "execution_id": self.exec_id,
                "pjob_code": self.pjob_code,
                "status": "success",
                "started_at": "2026-09-01T10:00:00+08:00",
            },
        )

        record = self.history.get_record(self.pjob_code, self.exec_id)

        assert record is not None
        assert record.usage is None

    def test_legacy_add_path_keeps_usage(self):
        record = ExecutionRecord(
            execution_id=self.exec_id,
            pjob_code=self.pjob_code,
            status="success",
            returncode=0,
            usage=self.usage,
        )

        self.history.add(record)

        assert self.history.get_record(self.pjob_code, self.exec_id).usage == self.usage
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_execution_history.py -k usage -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'usage'`

- [ ] **Step 3: 写最小实现**

`zima/execution/history.py`：

1. `_STATE_FILE_FIELDS` 列表增加 `"usage",`（放在 `"scan_pr_result",` 之后）。
2. `ExecutionRecord` 增加字段 `usage: Optional[dict] = None`（docstring 加一行 `usage: Usage ledger collected from pi session files (#213).`）。
3. `to_dict()` 末尾的返回改成与 `scan_pr_result` 一致的条件展开：

```python
            **({"scan_pr_result": self.scan_pr_result} if self.scan_pr_result is not None else {}),
            **({"usage": self.usage} if self.usage is not None else {}),
```

4. `from_dict()` 增加 `usage=data.get("usage"),`。
5. `from_result()` 增加 `usage=getattr(result, "usage", None),`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_execution_history.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add zima/execution/history.py tests/unit/test_execution_history.py
git commit -m "feat(history): persist usage ledger on execution records (#213)"
```

---

### Task 9: `background_runner` 转发 `usage`

**Files:**
- Modify: `zima/execution/background_runner.py:120-133`
- Test: `tests/unit/test_background_runner.py`

**Interfaces:**
- Consumes: `ExecutionResult.usage`（Task 10 会赋值，本任务先用假 result 打通转发）；`ExecutionHistory.update_runtime_state`
- Produces: 终态 JSON 含 `usage` 字段

- [ ] **Step 1: 写失败的测试**

`tests/unit/test_background_runner.py` 新增：

```python
class TestUsageForwarding:
    def _fake_result(self, usage):
        from types import SimpleNamespace

        return SimpleNamespace(
            stdout="",
            stderr="",
            status=SimpleNamespace(value="success"),
            returncode=0,
            duration_seconds=0.0,
            scan_pr_result=None,
            error_detail="",
            usage=usage,
        )

    def test_terminal_state_includes_usage(self, isolated_zima_home):
        from unittest.mock import MagicMock, patch

        from zima.execution.background_runner import run_pjob_in_background
        from zima.execution.history import ExecutionHistory

        pjob_code = "br-usage-pjob"
        execution_id = "b1b2b3b4"
        history = ExecutionHistory()
        history.write_runtime_state(
            pjob_code,
            execution_id,
            {
                "execution_id": execution_id,
                "pjob_code": pjob_code,
                "status": "running",
                "pid": None,
                "started_at": "2026-09-14T10:00:00+08:00",
                "log_path": "/tmp/br.log",
                "agent": "br-agent",
                "workflow": "br-wf",
            },
        )

        usage = {"collected": True, "totals": {"total_tokens": 42, "cost_usd": 0.001}}

        with patch("zima.execution.executor.PJobExecutor") as MockExecutor:
            MockExecutor.return_value.execute.return_value = self._fake_result(usage)

            rc = run_pjob_in_background(pjob_code, execution_id)

        assert rc == 0
        state = history.get_runtime_state(pjob_code, execution_id)
        assert state["usage"] == usage
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_background_runner.py -k usage -v`
Expected: FAIL — `assert None == {...}`（`state["usage"]` 为 None）

- [ ] **Step 3: 写最小实现**

`zima/execution/background_runner.py` 的 `history.update_runtime_state(...)` 调用增加一行参数：

```python
        scan_pr_result=result.scan_pr_result,
        usage=getattr(result, "usage", None),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_background_runner.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add zima/execution/background_runner.py tests/unit/test_background_runner.py
git commit -m "feat(executor): forward usage ledger to the terminal history record (#213)"
```

---

### Task 10: executor 在 temp 清理前采集

**Files:**
- Modify: `zima/execution/executor.py`（`ExecutionResult.usage` 字段 + `to_dict` + finally 块采集）
- Test: `tests/unit/test_executor_fixes.py`

**Interfaces:**
- Consumes: `collect_usage(session_dir, agent_type)`（Task 4）；`build_command(..., runtime_args=...)`（Task 7）
- Produces: `ExecutionResult.usage: Optional[dict] = None`；pi 执行后 `result.usage` 为采集结果

- [ ] **Step 1: 写失败的测试**

`tests/unit/test_executor_fixes.py` 新增：

```python
class TestUsageCollection:
    """Executor collects the usage ledger before deleting the temp dir (#213)."""

    SCRIPT = (
        "mkdir -p pi-sessions/subagent-artifacts && "
        "printf '%s\\n' "
        "'{\"type\":\"message\",\"message\":{\"role\":\"assistant\",\"provider\":\"zai-coding-cn\","
        "\"model\":\"glm-5.3\",\"usage\":{\"input\":100,\"output\":10,\"cacheRead\":0,"
        "\"cacheWrite\":0,\"totalTokens\":110,\"cost\":{\"total\":0.01}}}}' "
        "> pi-sessions/s.jsonl && "
        "printf '%s' "
        "'{\"agent\":\"checker\",\"model\":\"zai-coding-cn/glm-5.3-flash\","
        "\"usage\":{\"input\":900,\"output\":90,\"cacheRead\":0,\"cacheWrite\":0,"
        "\"cost\":0.09,\"turns\":2}}' "
        "> pi-sessions/subagent-artifacts/r1_checker_meta.json"
    )

    @pytest.fixture
    def pjob(self, isolated_zima_home, config_manager):
        from zima.models.pjob import PJobConfig
        from zima.models.workflow import WorkflowConfig

        config_manager.save_config(
            "agent",
            "ul-agent",
            {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "ul-agent", "name": "UL Agent"},
                "spec": {"type": "pi", "parameters": {"mockCommand": ["bash", "-c", self.SCRIPT]}},
            },
        )
        wf = WorkflowConfig.create(code="ul-wf", name="UL Workflow", template="do it",
                                   variables=[])
        config_manager.save_config("workflow", "ul-wf", wf.to_dict())
        pjob = PJobConfig.create(code="ul-pjob", name="UL PJob", agent="ul-agent",
                                workflow="ul-wf")
        config_manager.save_config("pjob", "ul-pjob", pjob.to_dict())
        return pjob

    def test_usage_collected_and_temp_removed(self, pjob, isolated_zima_home):
        executor = PJobExecutor()

        result = executor.execute("ul-pjob")

        assert result.status.value == "success"
        assert result.usage["collected"] is True
        assert result.usage["totals"]["total_tokens"] == 1100
        assert result.usage["by_role"]["parent"]["total_tokens"] == 110
        assert result.usage["by_role"]["children"]["total_tokens"] == 990
        assert result.usage["children_count"] == 1
        assert result.usage["cost_note"] == "estimated"
        assert result.temp_dir is None  # temp dir cleaned up
        assert not (get_zima_home() / "temp" / "pjobs" / f"ul-pjob-{result.execution_id}").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_executor_fixes.py -k usage -v`
Expected: FAIL — `AttributeError: 'ExecutionResult' object has no attribute 'usage'`

- [ ] **Step 3: 写最小实现**

`zima/execution/executor.py`：

1. 顶部 import：`from zima.execution.usage_collector import collect_usage`
2. `ExecutionResult` 增加字段（放在 `scan_pr_result` 之后）与 docstring 行 `usage: Usage ledger collected before temp cleanup (#213).`：

```python
    usage: Optional[dict] = None
```

3. `ExecutionResult.to_dict()` 增加：

```python
            "usage": self.usage,
```

4. `finally` 块中，在 `shutil.rmtree(temp_dir, ...)` **之前**插入：

```python
            # 14. Collect the usage ledger while the session files still exist
            # (the temp dir is removed right below). Fail-open by design (#213).
            try:
                _bundle_for_usage = locals().get("bundle")
                result.usage = collect_usage(
                    (temp_dir / "pi-sessions") if temp_dir else None,
                    agent_type=getattr(getattr(_bundle_for_usage, "agent", None), "type", ""),
                )
            except Exception:
                result.usage = {"collected": False, "reason": "parse_error"}
```

5. 在 finally 中现有的 temp 清理分支里显式保留 usage（清理逻辑本身不改）：确认 `shutil.rmtree` 与 `result.temp_dir = None` 仍在采集之后执行。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_executor_fixes.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add zima/execution/executor.py tests/unit/test_executor_fixes.py
git commit -m "feat(executor): collect usage ledger before temp cleanup (#213)"
```

---

### Task 11: CLI 详情展示

**Files:**
- Modify: `zima/commands/pjob.py`（detail 区块，约 1228 行 `Command:` 之后）
- Test: `tests/integration/test_pjob_lifecycle.py`（或新增用例到该文件）

**Interfaces:**
- Consumes: `format_usage_line`（Task 5）、`ExecutionRecord.usage`（Task 8）
- Produces: `zima pjob history <code> --detail <id>` 输出 `Usage:` 行

- [ ] **Step 1: 写失败的测试**

```python
def test_history_detail_shows_usage_line(monkeypatch, tmp_path):
    """`pjob history --detail` renders the usage ledger line (#213)."""
    from zima.execution.history import ExecutionHistory

    monkeypatch.setenv("ZIMA_HOME", str(tmp_path))

    ExecutionHistory().write_runtime_state(
        "usage-cli-pjob",
        "c1c2c3c4",
        {
            "execution_id": "c1c2c3c4",
            "pjob_code": "usage-cli-pjob",
            "status": "success",
            "returncode": 0,
            "command": ["pi", "-p"],
            "started_at": "2026-09-14T10:00:00+08:00",
            "finished_at": "2026-09-14T10:05:00+08:00",
            "duration_seconds": 300.0,
            "usage": {
                "collected": True,
                "totals": {"input": 6550000, "output": 10700, "cache_read": 0,
                           "cache_write": 0, "total_tokens": 6560700, "cost_usd": 0.4941},
                "by_role": {"parent": {"total_tokens": 17163},
                            "children": {"total_tokens": 6543537}},
                "by_model": [],
                "children_count": 12,
                "cost_note": "estimated",
            },
        },
    )

    result = runner.invoke(app, ["pjob", "history", "usage-cli-pjob", "--detail", "c1c2c3c4"])

    assert result.exit_code == 0
    assert "Usage:" in strip_ansi(result.output)
    assert "est. $0.49" in strip_ansi(result.output)
```

> `runner` 是该文件模块级已有的 `CliRunner()`；`strip_ansi` 从 `tests.conftest` 导入（若该文件尚未导入，在文件顶部加 `from tests.conftest import strip_ansi`）。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/integration/test_pjob_lifecycle.py -k usage -v`
Expected: FAIL — 输出中没有 `Usage:`

- [ ] **Step 3: 写最小实现**

`zima/commands/pjob.py` detail 区块中 `console.print(f"Command: {' '.join(record.command)}")` 之后插入：

```python
        console.print(format_usage_line(record.usage))
```

并在文件顶部 import：`from zima.execution.usage_collector import format_usage_line`。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/integration/test_pjob_lifecycle.py -k usage -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add zima/commands/pjob.py tests/integration/test_pjob_lifecycle.py
git commit -m "feat(cli): show usage ledger in pjob history detail (#213)"
```

---

### Task 12: 端到端集成测试

**Files:**
- Create: `tests/integration/test_usage_ledger.py`

**Interfaces:**
- Consumes: 全部实现（Task 1-11）
- Produces: 无（测试专有）

- [ ] **Step 1: 写测试（本任务即测试本身，先跑它观察失败）**

```python
"""End-to-end usage ledger test (#213).

A fake pi agent (mockCommand) writes session files into ``<cwd>/pi-sessions``,
mirroring what real pi does when the executor passes ``--session-dir``.
"""

from __future__ import annotations

import json

import pytest

from tests.base import TestIsolator
from zima.execution.executor import PJobExecutor
from zima.execution.history import ExecutionHistory
from zima.utils import get_zima_home

PARENT_SESSION = {
    "type": "message",
    "message": {
        "role": "assistant",
        "provider": "zai-coding-cn",
        "model": "glm-5.3",
        "usage": {
            "input": 17030,
            "output": 163,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 17193,
            "cost": {"total": 0.001529},
        },
    },
}

CHILD_META = {
    "agent": "checker",
    "model": "zai-coding-cn/glm-5.3-flash",
    "usage": {"input": 6533000, "output": 10537, "cacheRead": 76800, "cacheWrite": 0,
              "cost": 0.4926, "turns": 24},
}

FAKE_AGENT = (
    "mkdir -p pi-sessions/subagent-artifacts && "
    f"echo '{json.dumps(PARENT_SESSION)}' > pi-sessions/session.jsonl && "
    f"echo '{json.dumps(CHILD_META)}' > pi-sessions/subagent-artifacts/r1_checker_meta.json && "
    f"mkdir -p pi-sessions/forks && echo '{json.dumps(PARENT_SESSION)}' "
    "> pi-sessions/forks/child-fork.jsonl && "
    "echo benign-review-output"
)


class TestUsageLedgerEndToEnd(TestIsolator):
    @pytest.fixture
    def configs(self, isolated_zima_home, config_manager):
        from zima.models.pjob import PJobConfig
        from zima.models.workflow import WorkflowConfig

        config_manager.save_config(
            "agent",
            "e2e-agent",
            {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "e2e-agent", "name": "E2E Agent"},
                "spec": {"type": "pi", "parameters": {"mockCommand": ["bash", "-c", FAKE_AGENT]}},
            },
        )
        wf = WorkflowConfig.create(code="e2e-wf", name="E2E Workflow", template="review",
                                   variables=[])
        config_manager.save_config("workflow", "e2e-wf", wf.to_dict())
        pjob = PJobConfig.create(code="e2e-pjob", name="E2E PJob", agent="e2e-agent",
                                workflow="e2e-wf")
        config_manager.save_config("pjob", "e2e-pjob", pjob.to_dict())

    def test_ledger_recorded_and_no_double_count(self, configs):
        executor = PJobExecutor()

        result = executor.execute("e2e-pjob")

        assert result.status.value == "success"
        assert result.stdout.strip().endswith("benign-review-output")

        usage = result.usage
        assert usage["collected"] is True
        # forks/ copy excluded: 17193 (parent) + 6620337 (child) = 6637530
        assert usage["totals"]["total_tokens"] == 17193 + 6533000 + 10537 + 76800
        assert usage["by_role"]["parent"]["total_tokens"] == 17193
        assert usage["by_role"]["children"]["total_tokens"] == 6620337
        assert usage["children_count"] == 1
        assert usage["cost_note"] == "estimated"
        child_buckets = [b for b in usage["by_model"] if b["role"] == "child"]
        assert child_buckets[0]["agent"] == "checker"
        assert child_buckets[0]["provider"] == "zai-coding-cn"
        assert child_buckets[0]["model"] == "glm-5.3-flash"
        assert child_buckets[0]["turns"] == 24

    def test_temp_dir_cleaned_after_collection(self, configs):
        """Collection must happen before the temp dir is removed, not instead of it."""
        executor = PJobExecutor()

        result = executor.execute("e2e-pjob")

        assert result.usage["totals"]["total_tokens"] == 6637530
        assert result.usage["children_count"] == 1
        assert result.temp_dir is None
        tmp_root = get_zima_home() / "temp" / "pjobs"
        assert not any(
            p.name.startswith(f"e2e-pjob-{result.execution_id}")
            for p in (tmp_root.iterdir() if tmp_root.exists() else [])
        )
```

> `execution.execute()` 不负责写终态记录（`update_runtime_state` 对不存在的 state 文件是 no-op）。因此本文件只验证"采集结果正确 + temp 目录已清理"；"usage 随终态落盘"由 Task 8（读写）与 Task 9（转发）各自的单测覆盖，端到端持久化由合并后的真实执行 U1 验证。

- [ ] **Step 2: 运行测试**

Run: `uv run pytest tests/integration/test_usage_ledger.py -v`
Expected: PASS（若失败，按上方 note 调整断言范围，而不是放宽实现约束）

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_usage_ledger.py
git commit -m "test(observability): end-to-end usage ledger coverage (#213)"
```

---

### Task 13: 文档与 CHANGELOG

**Files:**
- Modify: `docs/architecture/data-and-runtime-reference.md:35`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: 全部实现
- Produces: 无

- [ ] **Step 1: 更新架构文档字段表**

`docs/architecture/data-and-runtime-reference.md` 第 35 行的 pi 参数列表：

```markdown
| `pi` | provider, model, thinking, sessionDir (injected), outputFormat, tools |
```

若同文件其他位置提到 `noSession` / `--no-session`，一并改为 `--session-dir` 并注明由 executor 注入。

- [ ] **Step 2: 更新 CHANGELOG（行为变更必须写明）**

在 `CHANGELOG.md` 的 Unreleased 段落追加：

```markdown
### Changed

- **Behavior change (pi agents)**: pi runs no longer pass `--no-session`; the executor now passes
  `--session-dir <execution temp dir>/pi-sessions`, so the session file is written inside the
  execution's own temporary directory and deleted with it. The global pi session store
  (`~/.pi/agent/sessions`) is never touched. The `noSession` agent parameter is retired and
  ignored if still present in configs (#213).
- Execution history now records a `usage` ledger (tokens in/out, cache, estimated cost, per-model
  breakdown covering the parent agent and all subagents). `zima pjob history <code> --detail <id>`
  renders a summary line. Cost is a price-table estimate, not a cash figure (#213).
```

- [ ] **Step 3: 全量验证**

Run:
```bash
uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60
uv run ruff check zima/ tests/
uv run black --check zima/ tests/ --line-length 100
```
Expected: 全绿

- [ ] **Step 4: 提交**

```bash
git add docs/architecture/data-and-runtime-reference.md CHANGELOG.md
git commit -m "docs: document session-dir behavior change and usage ledger (#213)"
```

---

## 验收追溯

| Spec 验收 ID | 覆盖任务 |
|--------------|----------|
| A1 | Task 6（`--session-dir` / `--no-session` 断言） |
| A2 | Task 6（默认参数 + 残留 `noSession` 忽略） |
| A3 | Task 1 |
| A4 | Task 2 |
| A5 | Task 4（`test_ignores_forks_and_transcripts`） |
| A6 | Task 3 |
| A7 | Task 4（fail-open 四态） |
| A8 | Task 8 |
| A9 | Task 8（legacy 记录） |
| A10 | Task 5 |
| A11 | Task 4（`unsupported_agent_type`） |
| A12 | Task 12 |
| A13 | Task 12（temp 清理断言） |
| A14 | Task 13（全量回归 + lint） |
| U1-U4 | 合并后用户实测（见 spec §10） |
