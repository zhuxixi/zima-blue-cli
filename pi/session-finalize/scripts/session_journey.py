#!/usr/bin/env python3
"""Render a readable journey from a pi session JSONL file.

The extractor keeps three layers apart: record loading (IO), pure
normalisation/segmentation, and rendering. Only `load_records` and `main`
touch the filesystem, which keeps the rest unit-testable with plain dicts.
"""

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
    with path.open(encoding="utf-8", errors="replace") as handle:
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
    """Keep the parent chain that ends at the last record.

    A root record (missing or null `parentId`) is a normal terminus. A
    `parentId` that points at a record absent from the file means the tree is
    incomplete: fall back to file order and report it via the boolean.
    """
    if not records:
        return [], False
    by_id = {record["id"]: record for record in records if isinstance(record.get("id"), str)}
    last_id = records[-1].get("id")
    if not isinstance(last_id, str) or last_id not in by_id:
        return list(records), True
    wanted: set[str] = set()
    current: str | None = last_id
    while current is not None:
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


def _truncate(value: str, limit: int = MAX_TEXT) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
            Turn(
                role=role,
                timestamp=str(record.get("timestamp") or ""),
                text=text,
                tool_calls=calls,
            )
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
    written = {
        call.target for turn in turns for call in turn.tool_calls if call.is_write and call.target
    }
    payload_meta = dict(meta)
    payload_meta["user_turns"] = sum(1 for turn in turns if turn.role == "user")
    payload_meta["changed_files"] = len(written)
    return {"meta": payload_meta, "stages": summaries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a pi session journey")
    parser.add_argument("--file", required=True)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--max-stages", type=int, default=MAX_STAGES)
    args = parser.parse_args(argv)

    path = Path(args.file).expanduser()
    records, skipped = load_records(path)
    if not records or not any(record.get("type") == "message" for record in records):
        print(f"no session records: {path}", file=sys.stderr)
        return 2

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    payload = build_journey(branch, meta, args.max_stages)
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        stages = segment_stages(load_turns(branch), args.max_stages)
        print(render_markdown(stages, payload["meta"]), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
