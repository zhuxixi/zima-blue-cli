# session-finalize Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `pi/session-finalize` 技能：从 pi 会话 JSONL 抽取旅程摘要，编排 jfox 的两个 session 沉淀 skill。

**Architecture:** 技能文档负责编排（四段流程、幂等、失败分支），脚本负责确定性抽取（JSONL → 活动分支 → 阶段 → markdown/JSON）。脚本的纯函数与 IO 边界分离，测试按函数逐个锁定；技能文档由文本契约测试锁定。

**Tech Stack:** Python 3.10+、dataclasses、argparse、pytest、importlib（按路径加载脚本）。

## Global Constraints

- 设计文档：`docs/superpowers/specs/2026-11-24-session-finalize-design.md`（sha256 `c4be0b03fe751ce0697ae2f55fe9d1ab5a08144cea358813102a326cacfd76e2`）
- 不改 `package.json`、不改 jfox 仓库、不改 zima Python 包代码。
- 技能名固定 `session-finalize`；目录 `pi/session-finalize/`。
- 脚本入口固定 `python3 <skill-dir>/scripts/session_journey.py --file "$PI_SESSION_FILE" [--json] [--max-stages 8]`。
- 技能文档禁止出现硬编码模型名（`deepseek-v4` / `zai-coding-cn`）与本机绝对路径（`/home/elling`）。
- 单条摘要文本 ≤120 字符；每阶段 3 条 bullet。
- 所有命令在 worktree 根目录执行：`WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-279-session-finalize`。

---

### Task 1: 脚本骨架 + `load_records` + `select_active_branch`

**Files:**
- Create: `pi/session-finalize/scripts/session_journey.py`
- Create: `tests/unit/test_session_finalize_scripts.py`

**Interfaces:**
- Produces: `load_records(path: Path) -> tuple[list[dict], int]`；`select_active_branch(records: list[dict]) -> tuple[list[dict], bool]`；`MAX_TEXT: int = 120`；`MAX_STAGES: int = 8`。

- [ ] **Step 1: 写失败测试**

```python
"""Unit tests for the session-finalize journey extractor (issue #279)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = _REPO_ROOT / "pi" / "session-finalize" / "scripts" / "session_journey.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("session_journey", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


journey = _load_module()


def test_load_records_skips_malformed_lines(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text('{"id": "a"}\nnot json\n{"id": "b"}\n', encoding="utf-8")
    records, skipped = journey.load_records(path)
    assert [record["id"] for record in records] == ["a", "b"]
    assert skipped == 1


def test_load_records_missing_and_empty(tmp_path):
    assert journey.load_records(tmp_path / "missing.jsonl") == ([], 0)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert journey.load_records(empty) == ([], 0)


def test_select_active_branch_drops_abandoned_branch():
    records = [
        {"id": "a", "type": "session"},
        {"id": "b", "parentId": "a", "type": "message"},
        {"id": "c", "parentId": "b", "type": "message"},
        {"id": "d", "parentId": "b", "type": "message"},
    ]
    branch, fallback = journey.select_active_branch(records)
    assert [record["id"] for record in branch] == ["a", "b", "d"]
    assert fallback is False


def test_select_active_branch_broken_parent_falls_back():
    records = [
        {"id": "a", "type": "session"},
        {"id": "b", "parentId": "missing", "type": "message"},
    ]
    branch, fallback = journey.select_active_branch(records)
    assert [record["id"] for record in branch] == ["a", "b"]
    assert fallback is True


def test_select_active_branch_root_without_parent_is_normal():
    records = [{"id": "a", "type": "session"}, {"id": "b", "parentId": "a"}]
    branch, fallback = journey.select_active_branch(records)
    assert [record["id"] for record in branch] == ["a", "b"]
    assert fallback is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_session_finalize_scripts.py -q`
Expected: FAIL（`FileNotFoundError` / `module has no attribute`）

- [ ] **Step 3: 写最小实现**

```python
#!/usr/bin/env python3
"""Render a readable journey from a pi session JSONL file."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

MAX_TEXT = 120
MAX_STAGES = 8
MAX_FILES = 5
WRITE_TOOLS = frozenset({"write", "edit"})


@dataclass(frozen=True)
class ToolCall:
    name: str
    target: str
    is_write: bool


@dataclass(frozen=True)
class Turn:
    role: str
    timestamp: str
    text: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class Stage:
    index: int
    user_text: str
    turns: tuple[Turn, ...] = ()


def load_records(path: Path) -> tuple[list[dict], int]:
    """Parse a JSONL session file, skipping malformed lines."""
    records: list[dict] = []
    skipped = 0
    if not path.is_file():
        return [], 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                skipped += 1
    return records, skipped


def select_active_branch(records: list[dict]) -> tuple[list[dict], bool]:
    """Keep the parent chain ending at the last record.

    A root record (no parentId) ends the chain normally. A parentId that
    points at an absent record means the tree is incomplete: fall back to the
    file order and report it.
    """
    if not records:
        return [], False
    by_id = {record["id"]: record for record in records if isinstance(record.get("id"), str)}
    last_id = records[-1].get("id")
    if not isinstance(last_id, str) or last_id not in by_id:
        return list(records), True
    wanted: set[str] = set()
    current = last_id
    while True:
        if current in wanted or current not in by_id:
            return list(records), True
        wanted.add(current)
        parent = by_id[current].get("parentId")
        if parent is None:
            break
        if not isinstance(parent, str):
            return list(records), True
        current = parent
    return [record for record in records if record.get("id") in wanted], False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_session_finalize_scripts.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add pi/session-finalize/scripts/session_journey.py tests/unit/test_session_finalize_scripts.py
git commit -m "feat(skill): session-finalize journey extractor — records and active branch"
```

---

### Task 2: `load_turns` + `segment_stages`

**Files:**
- Modify: `pi/session-finalize/scripts/session_journey.py`
- Modify: `tests/unit/test_session_finalize_scripts.py`

**Interfaces:**
- Consumes: `Turn`、`MAX_TEXT`、`MAX_STAGES`（Task 1）
- Produces: `load_turns(records: Iterable[dict]) -> list[Turn]`；`segment_stages(turns: list[Turn], max_stages: int = MAX_STAGES) -> list[Stage]`

- [ ] **Step 1: 追加失败测试**

```python
def _message(rid, role, text="", calls=(), parent=None, ts="2026-01-01T00:00:00Z"):
    content = []
    if text:
        content.append({"type": "text", "text": text})
    for name, args in calls:
        content.append({"type": "toolCall", "name": name, "arguments": args})
    record = {"id": rid, "type": "message", "timestamp": ts, "message": {"role": role, "content": content}}
    if parent is not None:
        record["parentId"] = parent
    return record


def test_load_turns_keeps_only_user_and_assistant_text_and_calls():
    records = [
        {"id": "s", "type": "system", "message": {"role": "system", "content": [{"type": "text", "text": "rules"}]}},
        _message("u1", "user", "do the thing"),
        _message("a1", "assistant", "done", calls=[("write", {"path": "a.py"})]),
        {"id": "t", "type": "message", "message": {"role": "toolResult", "content": [{"type": "text", "text": "ok"}]}},
        {"id": "c", "type": "custom", "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]}},
    ]
    turns = journey.load_turns(records)
    assert [turn.role for turn in turns] == ["user", "assistant"]
    assert turns[0].text == "do the thing"
    assert turns[1].tool_calls == (journey.ToolCall(name="write", target="a.py", is_write=True),)


def test_load_turns_drops_thinking_only_assistant():
    records = [
        _message("u1", "user", "hi"),
        {"id": "a1", "type": "message", "message": {"role": "assistant", "content": [{"type": "thinking", "text": "hmm"}]}},
    ]
    assert [turn.role for turn in journey.load_turns(records)] == ["user"]


def test_segment_stages_one_per_user_turn():
    turns = journey.load_turns([
        _message("u1", "user", "first"),
        _message("a1", "assistant", "one"),
        _message("u2", "user", "second"),
        _message("a2", "assistant", "two"),
    ])
    stages = journey.segment_stages(turns)
    assert len(stages) == 2
    assert stages[0].user_text == "first"
    assert [turn.role for turn in stages[0].turns] == ["user", "assistant"]


def test_segment_stages_merges_shortest_adjacent_pair():
    texts = ["x", "ten chars!", "ten chars!", "ten chars!", "ten chars!", "ten chars!", "ten chars!", "ten chars!", "ten chars!"]
    turns = [journey.Turn(role="user", timestamp="", text=text) for text in texts]
    stages = journey.segment_stages(turns, max_stages=8)
    assert len(stages) == 8
    assert len(stages[0].turns) == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_session_finalize_scripts.py -q`
Expected: FAIL（`load_turns` / `segment_stages` 未定义）

- [ ] **Step 3: 实现**

```python
def _block_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
    return "\n".join(parts)


def _tool_calls(content: Any) -> tuple[ToolCall, ...]:
    if not isinstance(content, list):
        return ()
    calls = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "toolCall":
            continue
        name = block.get("name")
        if not isinstance(name, str):
            continue
        args = block.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        target = ""
        for key in ("path", "file_path", "command", "pattern", "url"):
            value = args.get(key)
            if isinstance(value, str) and value:
                target = value
                break
        calls.append(ToolCall(name=name, target=_truncate(target), is_write=name in WRITE_TOOLS))
    return tuple(calls)


def _truncate(value: str, limit: int = MAX_TEXT) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_turns(records: Iterable[dict]) -> list[Turn]:
    turns: list[Turn] = []
    for record in records:
        if record.get("type") != "message":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        content = message.get("content")
        text = _block_text(content).strip()
        calls = _tool_calls(content) if role == "assistant" else ()
        if not text and not calls:
            continue
        turns.append(
            Turn(role=role, timestamp=str(record.get("timestamp") or ""), text=text, tool_calls=calls)
        )
    return turns


def segment_stages(turns: list[Turn], max_stages: int = MAX_STAGES) -> list[Stage]:
    groups: list[list[Turn]] = []
    for turn in turns:
        if turn.role == "user" or not groups:
            groups.append([turn])
        else:
            groups[-1].append(turn)
    while len(groups) > max_stages and len(groups) > 1:
        lengths = [sum(len(turn.text) for turn in group) for group in groups]
        best = min(range(len(groups) - 1), key=lambda i: (lengths[i] + lengths[i + 1], i))
        groups[best : best + 2] = [groups[best] + groups[best + 1]]
    stages = []
    for index, group in enumerate(groups, start=1):
        user_text = next((turn.text for turn in group if turn.role == "user"), "")
        stages.append(Stage(index=index, user_text=user_text, turns=tuple(group)))
    return stages
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_session_finalize_scripts.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: Commit**

```bash
git add pi/session-finalize/scripts/session_journey.py tests/unit/test_session_finalize_scripts.py
git commit -m "feat(skill): session-finalize journey extractor — turns and stages"
```

---

### Task 3: `stage_summary` + `render_markdown` + `build_journey` + CLI

**Files:**
- Modify: `pi/session-finalize/scripts/session_journey.py`
- Modify: `tests/unit/test_session_finalize_scripts.py`

**Interfaces:**
- Consumes: `Stage`、`Turn`、`ToolCall`、`load_turns`、`segment_stages`
- Produces: `stage_summary(stage: Stage) -> dict`；`render_markdown(stages: list[Stage], meta: dict) -> str`；`build_journey(records: Iterable[dict], meta: dict, max_stages: int = MAX_STAGES) -> dict`；`main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 追加失败测试**

```python
def test_stage_summary_counts_tools_and_dedups_writes():
    stage = journey.Stage(
        index=1,
        user_text="ship it",
        turns=(
            journey.Turn(role="user", timestamp="", text="ship it"),
            journey.Turn(
                role="assistant",
                timestamp="",
                text="done",
                tool_calls=(
                    journey.ToolCall(name="write", target="a.py", is_write=True),
                    journey.ToolCall(name="edit", target="a.py", is_write=True),
                    journey.ToolCall(name="read", target="b.py", is_write=False),
                    journey.ToolCall(name="bash", target="pytest", is_write=False),
                ),
            ),
        ),
    )
    summary = journey.stage_summary(stage)
    assert summary["tool_counts"] == {"write": 1, "edit": 1, "read": 1, "bash": 1}
    assert summary["written_files"] == ["a.py"]
    assert summary["last_assistant_text"] == "done"


def test_render_markdown_has_three_bullets_and_truncates():
    stage = journey.Stage(
        index=1,
        user_text="x" * 200,
        turns=(journey.Turn(role="user", timestamp="", text="x" * 200),),
    )
    meta = {"user_turns": 1, "first_ts": "a", "last_ts": "b", "changed_files": 0}
    text = journey.render_markdown([stage], meta)
    bullets = [line for line in text.splitlines() if line.startswith("- ")]
    assert len(bullets) == 3
    assert all(len(line) <= 130 for line in bullets)


def test_build_journey_meta_and_stages():
    records = [
        _message("u1", "user", "one"),
        _message("a1", "assistant", "two", calls=[("write", {"path": "x.py"})]),
        _message("u2", "user", "three"),
    ]
    meta = {"records": 3, "skipped_lines": 0, "first_ts": "a", "last_ts": "b", "branch_fallback": False}
    payload = journey.build_journey(records, meta)
    assert payload["meta"]["user_turns"] == 2
    assert payload["meta"]["changed_files"] == 1
    assert len(payload["stages"]) == 2


def test_main_exit_codes_and_json(tmp_path, capsys):
    missing = tmp_path / "missing.jsonl"
    assert journey.main(["--file", str(missing)]) == 2
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert journey.main(["--file", str(empty)]) == 2
    valid = tmp_path / "valid.jsonl"
    valid.write_text(
        json.dumps(_message("u1", "user", "hello"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    assert journey.main(["--file", str(valid), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["meta"]["user_turns"] == 1
    assert payload["stages"][0]["user_request"] == "hello"
```

同时在文件顶部补 `import json`。

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_session_finalize_scripts.py -q`
Expected: FAIL（`stage_summary` / `render_markdown` / `build_journey` / `main` 未定义）

- [ ] **Step 3: 实现**

```python
def stage_summary(stage: Stage) -> dict:
    tool_counts: dict[str, int] = {}
    written: list[str] = []
    for turn in stage.turns:
        for call in turn.tool_calls:
            tool_counts[call.name] = tool_counts.get(call.name, 0) + 1
            if call.is_write and call.target and call.target not in written:
                written.append(call.target)
    last_text = ""
    for turn in reversed(stage.turns):
        if turn.role == "assistant" and turn.text.strip():
            last_text = _truncate(turn.text)
            break
    return {
        "index": stage.index,
        "user_request": _truncate(stage.user_text),
        "tool_counts": tool_counts,
        "written_files": written[:MAX_FILES],
        "last_assistant_text": last_text,
    }


def render_markdown(stages: list[Stage], meta: dict) -> str:
    lines = [
        f"本会话共 {meta.get('user_turns', 0)} 轮、"
        f"{meta.get('first_ts') or '?'} → {meta.get('last_ts') or '?'}，"
        f"改动 {meta.get('changed_files', 0)} 个文件。"
    ]
    for stage in stages:
        summary = stage_summary(stage)
        request = summary["user_request"] or "（无用户消息）"
        actions = "、".join(
            f"{name} ×{count}" for name, count in sorted(summary["tool_counts"].items())
        )
        detail = actions or "无工具调用"
        if summary["written_files"]:
            detail += "；写入 " + " / ".join(summary["written_files"])
        lines.extend(
            [
                "",
                f"### 阶段 {stage.index} — {request}",
                f"- 诉求：{request}",
                f"- 动作：{detail}",
                f"- 结论：{summary['last_assistant_text'] or '（无）'}",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_journey(records: Iterable[dict], meta: dict, max_stages: int = MAX_STAGES) -> dict:
    turns = load_turns(records)
    stages = segment_stages(turns, max_stages=max_stages)
    summaries = [stage_summary(stage) for stage in stages]
    files = sorted({path for summary in summaries for path in summary["written_files"]})
    payload_meta = dict(meta)
    payload_meta["user_turns"] = sum(1 for turn in turns if turn.role == "user")
    payload_meta["changed_files"] = len(files)
    return {"meta": payload_meta, "stages": summaries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a pi session journey")
    parser.add_argument("--file", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--max-stages", type=int, default=MAX_STAGES)
    args = parser.parse_args(argv)

    path = Path(args.file).expanduser()
    records, skipped = load_records(path)
    if not records:
        print(f"no session records: {path}", file=sys.stderr)
        return 2

    branch, fallback = select_active_branch(records)
    timestamps = [str(record["timestamp"]) for record in branch if record.get("timestamp")]
    meta = {
        "file": str(path),
        "records": len(branch),
        "skipped_lines": skipped,
        "first_ts": timestamps[0] if timestamps else "",
        "last_ts": timestamps[-1] if timestamps else "",
        "branch_fallback": fallback,
    }
    if args.as_json:
        print(json.dumps(build_journey(branch, meta, args.max_stages), ensure_ascii=False, indent=2))
    else:
        payload = build_journey(branch, meta, args.max_stages)
        stages = segment_stages(load_turns(branch), args.max_stages)
        print(render_markdown(stages, payload["meta"]), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/unit/test_session_finalize_scripts.py -q`
Expected: PASS（13 passed）

- [ ] **Step 5: 对真实会话冒烟（只读）**

Run: `python3 pi/session-finalize/scripts/session_journey.py --file "$PI_SESSION_FILE" --max-stages 8 | head -20`
Expected: 输出以 `本会话共 N 轮` 开头，无 traceback。

- [ ] **Step 6: Commit**

```bash
git add pi/session-finalize/scripts/session_journey.py tests/unit/test_session_finalize_scripts.py
git commit -m "feat(skill): session-finalize journey extractor — summaries and CLI"
```

---

### Task 4: `SKILL.md` + README + CHANGELOG + 契约测试

**Files:**
- Create: `pi/session-finalize/SKILL.md`
- Create: `tests/unit/test_session_finalize_contracts.py`
- Modify: `pi/README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: 脚本路径 `pi/session-finalize/scripts/session_journey.py`（Task 3）
- Produces: 可被 pi 发现的技能 `session-finalize`

- [ ] **Step 1: 写失败测试**

```python
"""Contract gate for the `session-finalize` skill (issue #279).

Locks the documentation contracts: frontmatter, four-phase orchestration,
ordering of the two jfox skills, idempotency, failure branches, degradation
prompts, and registry entries. Runtime behaviour is covered by U1–U5.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = _REPO_ROOT / "pi" / "session-finalize" / "SKILL.md"
SCRIPT = _REPO_ROOT / "pi" / "session-finalize" / "scripts" / "session_journey.py"
README = _REPO_ROOT / "pi" / "README.md"
CHANGELOG = _REPO_ROOT / "CHANGELOG.md"

BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn", "/home/elling")

REQUIRED_SECTIONS = (
    "## 何时使用",
    "## 前置检查（第 0 段）",
    "## 第 1 段：旅程回放",
    "## 第 2 段：主线判定",
    "## 第 3 段：执行沉淀",
    "## 第 4 段：收尾展示",
    "## 幂等与重复触发",
    "## 失败与降级",
)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing contract document: {path}"
    return path.read_text(encoding="utf-8")


def test_frontmatter_declares_name_and_description():
    text = _text(SKILL)
    assert text.startswith("---\n")
    head = text.split("---\n", 2)[1]
    assert "name: session-finalize" in head
    assert "description:" in head
    assert "finalize" in head and "会话收尾" in head


def test_required_sections_present():
    text = _text(SKILL)
    for section in REQUIRED_SECTIONS:
        assert section in text, f"missing section: {section}"


def test_jfox_skills_are_named_in_order():
    text = _text(SKILL)
    permanent = text.find("jfox-session-to-permanent")
    summary = text.find("jfox-session-summary")
    assert permanent != -1 and summary != -1
    assert permanent < summary


def test_state_and_degradation_tokens():
    text = _text(SKILL)
    for token in ("PI_SESSION_FILE", "session_file", "--include-archived", "--session-path"):
        assert token in text
    assert "旅程回放降级：未找到会话文件" in text


def test_failure_branches_are_documented():
    text = _text(SKILL)
    assert "permanent 任一写入失败" in text and "不写 summary" in text
    assert "全部跳过" in text and "不等于失败" in text
    assert "不重试" in text and "不静默" in text


def test_no_hardcoded_models_or_machine_paths():
    text = _text(SKILL)
    for banned in BANNED_LITERALS:
        assert banned not in text


def test_readme_and_changelog_register_the_skill():
    assert "`session-finalize`" in _text(README)
    unreleased = _text(CHANGELOG).split("## [Unreleased]", 1)[1].split("## [", 1)[0]
    assert "session-finalize" in unreleased


def test_script_exists():
    assert SCRIPT.is_file()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/unit/test_session_finalize_contracts.py -q`
Expected: FAIL（`SKILL.md` 不存在）

- [ ] **Step 3: 写 `SKILL.md`**

```markdown
---
name: session-finalize
description: |
  会话收尾编排：回放当前会话旅程 → 归纳主线任务并确认是否结束 → 已结束则依次执行
  jfox-session-to-permanent 与 jfox-session-summary → 展示总结与写入结果。
  Use when the user wants to wrap up or finalize the current session, save it to the
  knowledge base, or says "finalize", "session finalize", "会话收尾", "收尾", "结束会话",
  "沉淀这个会话".
  Triggers: "finalize", "session finalize", "会话收尾", "收尾", "结束会话", "沉淀这个会话".
---

# Session Finalize

会话收尾的唯一入口：先把「这个会话干了什么」讲清楚，确认主线是否结束，结束后把现状与历史沉淀进 jfox，最后展示写入结果。本技能只做编排，不改 `jfox-session-to-permanent` / `jfox-session-summary` 的规则。

## 何时使用

- 用户说 `finalize`、`session finalize`、`会话收尾`、`收尾`、`结束会话`、`沉淀这个会话`
- 长会话结束前，用户想先看旅程再决定是否沉淀

## 前置检查（第 0 段）

逐项检查，任一失败即停并给出指引：

1. `jfox kb current --json` 必须成功；失败 → 提示先用 `/skill:jfox-common` 初始化知识库。
2. 可用技能列表里必须同时有 `jfox-session-to-permanent` 与 `jfox-session-summary`；缺任一 → 提示安装 jfox pi 技能包。
3. 读 `$PI_SESSION_FILE`；为空或文件不存在 → **不停止**，第 1 段降级（见「失败与降级」）。

## 第 1 段：旅程回放

运行技能目录下的脚本（必须用绝对路径 + `python3` 前缀；触发会话的 cwd 通常是别的项目）：

```bash
python3 <skill-dir>/scripts/session_journey.py --file "$PI_SESSION_FILE" --json
```

读取 JSON 后，用中文写 3–8 个阶段：

```markdown
本会话共 <N> 轮、跨 <时长>，改动 <M> 个文件。

### 阶段 1 — <一句话诉求>
- 诉求：<用户原话摘要>
- 动作：bash ×12、read ×8、edit ×5；写入 a.py / b.md
- 结论：<该阶段最后一条 assistant 叙述>
```

纪律：

- 只呈现「用户在推动什么、做了什么、落到哪里」，不复述 toolResult，不读 `thinking`。
- 阶段划分以用户消息为边界；脚本已按「合并最短相邻对」处理超过 8 个阶段的情况。
- 每阶段最多 3 条 bullet，单条不超过 120 字。

降级：`$PI_SESSION_FILE` 为空、文件不存在或脚本失败时，用当前会话上下文 + `git status --short` 回放，并输出一行 `旅程回放降级：未找到会话文件`（脚本失败时改为 `旅程回放降级：脚本不可用`）。降级不阻止后续段落。

## 第 2 段：主线判定

先给结论，再列证据：

```markdown
主线：<一句话，动词开头，说明这个会话要达成的结果>

当前进度：
- <证据 1>
- <证据 2>

这条主线是否已经结束？
```

证据来源顺序：会话内 todo → `git status --short` / `git log --oneline -5` → `gh pr view`（若涉及 PR）→ issue 状态。取不到的证据标注「未确认」，不编造。

然后用 `question` 工具提问，三个选项：`已结束` / `未结束` / `其他`。

- **已结束** → 进入第 3 段。
- **未结束** → 只输出「未收尾」报告（主线 / 卡点 / 下一步），再问一次：`只报状态` / `也写 session 笔记`。默认不写任何笔记；用户选后者时只走 `jfox-session-summary`，**不写 permanent**。
- **其他** → 请用户说明，按说明处置后重新提问。

## 第 3 段：执行沉淀

顺序固定：先 permanent，后 summary。

### 3.1 幂等检查

```bash
jfox list --type session --limit 50 --format json --include-archived
```

按 `$PI_SESSION_FILE` 匹配 `session_file`：

| 结果 | 处置 |
|------|------|
| 命中（活跃） | `question`：更新已有笔记 / 跳过 session 笔记 / 另建一条 |
| 命中（已归档） | 同样三选一，并提示该笔记已归档 |
| 未命中 | 直接继续 |
| 老笔记无 `session_file` | 退化为标题匹配 `Session: <topic>`；仍无结论则继续 |

### 3.2 permanent

按名定位已安装的 `jfox-session-to-permanent` skill，读其 `SKILL.md` 并完整遵循：去重、分批（每批 ≤5）、`question` 审阅、落库。不重复、不放宽它的规则。

### 3.3 summary

按 `jfox-session-summary` 生成并直接写入。两条硬要求：

1. 写入命令必须带 `--session-path "$PI_SESSION_FILE"`、`--agent pi-coding-agent`、`--agent-model "${PI_PROVIDER}/${PI_MODEL}"`（变量为空则省略）与标题 `Session: <topic>`。`session_file` 只在传了 `--session-path` 时存在，它是 3.1 幂等的唯一依据。
2. 若本次写入了 permanent 笔记，在「完成的工作」下补一条 `- 沉淀永久笔记：<标题>（<ID>）`。

### 3.4 失败处理

| 失败点 | 行为 |
|--------|------|
| permanent 任一写入失败 | 停止链路，不写 summary；报告失败笔记与重试命令 |
| permanent 被用户全部跳过 | 继续 summary（用户全部跳过不等于失败） |
| summary 写入失败 | 报告 permanent 已写入的结果 + 错误；不重试、不静默 |
| 重复触发且用户选择「跳过」 | 跳过 summary，仍展示上次写入的笔记信息 |

## 第 4 段：收尾展示

```markdown
## 收尾完成

### 会话总结
<summary 全文>

### 本次写入
| 类型 | 标题 | ID |
|------|------|----|
| session | Session: ... | ... |
| permanent | ... | ... |

### 未完成事项
- <...>

### 下一步
<一句话>
```

## 幂等与重复触发

- 写入前必做 3.1；命中同一 `session_file` 时由用户选择更新、跳过或另建。
- 选「跳过」不报错，按成功收尾展示上次笔记。
- 同一会话第二次 finalize 时主线重新判定，不复用上一次结论。

## 失败与降级

| 情形 | 行为 | 用户可见提示 |
|------|------|--------------|
| `$PI_SESSION_FILE` 为空 | 用上下文 + git 回放 | `旅程回放降级：未找到会话文件` |
| 文件不存在 / 为空 / 0 条有效消息 | 同上 | 同上 |
| `python3` 或脚本不可用 | 用上下文回放 | `旅程回放降级：脚本不可用` |
| `jfox kb current` 失败 | 第 0 段停止 | 初始化指引 |
| 缺任一 jfox skill | 第 0 段停止 | 安装指引 |

## 与两个 jfox skill 的边界

- 本技能只决定「何时调用、以什么顺序调用、失败怎么办」，不复制它们的去重阈值、审阅交互或写入格式。
- `jfox-session-to-permanent` 记现状（事实 / 决策 / 文件位置），`jfox-session-summary` 记行为历史（做了什么）；两者都写，顺序不可颠倒。
```

- [ ] **Step 4: 更新 README 与 CHANGELOG**

`pi/README.md` 技能表追加一行：

```markdown
| `session-finalize` | 会话收尾编排（旅程回放 → 主线判定 → jfox 沉淀 + 总结） | 独立入口（任意长会话末尾手动触发） |
```

`pi/README.md` 前置依赖追加：

```markdown
- jfox pi 技能包（提供 `jfox-session-to-permanent` / `jfox-session-summary`）
```

`CHANGELOG.md` 的 `## [Unreleased]` → `### Features` 追加：

```markdown
- **skill**: 新增 `session-finalize`——会话收尾编排（旅程回放 → 主线判定 → jfox 沉淀 + 总结）
```

- [ ] **Step 5: 跑全部相关测试**

Run: `uv run pytest tests/unit/test_session_finalize_scripts.py tests/unit/test_session_finalize_contracts.py -q`
Expected: PASS（21 passed）

- [ ] **Step 6: Commit**

```bash
git add pi/session-finalize/SKILL.md pi/README.md CHANGELOG.md tests/unit/test_session_finalize_contracts.py
git commit -m "feat(skill): session-finalize orchestration doc and registry entries"
```
