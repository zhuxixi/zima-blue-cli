"""Unit tests for the session-finalize journey extractor (issue #279).

The script is loaded by path because `pi/` is a skill directory, not an
installable Python package. Tests cover the pure helpers plus the CLI
boundary; the real `$PI_SESSION_FILE` is never read (not reproducible).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = _REPO_ROOT / "pi" / "session-finalize" / "scripts" / "session_journey.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("session_journey", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


journey = _load_module()


def _message(rid, role, text="", calls=(), parent=None, ts="2026-01-01T00:00:00Z"):
    content = []
    if text:
        content.append({"type": "text", "text": text})
    for name, args in calls:
        content.append({"type": "toolCall", "name": name, "arguments": args})
    record = {
        "id": rid,
        "type": "message",
        "timestamp": ts,
        "message": {"role": role, "content": content},
    }
    if parent is not None:
        record["parentId"] = parent
    return record


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


def test_load_turns_keeps_only_user_and_assistant_text_and_calls():
    records = [
        {
            "id": "s",
            "type": "system",
            "message": {"role": "system", "content": [{"type": "text", "text": "rules"}]},
        },
        _message("u1", "user", "do the thing"),
        _message("a1", "assistant", "done", calls=[("write", {"path": "a.py"})]),
        {
            "id": "t",
            "type": "message",
            "message": {"role": "toolResult", "content": [{"type": "text", "text": "ok"}]},
        },
        {
            "id": "c",
            "type": "custom",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}]},
        },
    ]
    turns = journey.load_turns(records)
    assert [turn.role for turn in turns] == ["user", "assistant"]
    assert turns[0].text == "do the thing"
    assert turns[1].tool_calls == (journey.ToolCall(name="write", target="a.py", is_write=True),)


def test_load_turns_drops_thinking_only_assistant():
    records = [
        _message("u1", "user", "hi"),
        {
            "id": "a1",
            "type": "message",
            "message": {"role": "assistant", "content": [{"type": "thinking", "text": "hmm"}]},
        },
    ]
    assert [turn.role for turn in journey.load_turns(records)] == ["user"]


def test_segment_stages_one_per_user_turn():
    turns = journey.load_turns(
        [
            _message("u1", "user", "first"),
            _message("a1", "assistant", "one"),
            _message("u2", "user", "second"),
            _message("a2", "assistant", "two"),
            _message("u3", "user", "third"),
        ]
    )
    stages = journey.segment_stages(turns)
    assert len(stages) == 3
    assert stages[0].user_text == "first"
    assert [turn.role for turn in stages[0].turns] == ["user", "assistant"]
    assert stages[2].user_text == "third"


def test_segment_stages_merges_shortest_adjacent_pair():
    texts = [
        "x",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
        "ten chars!",
    ]
    turns = [journey.Turn(role="user", timestamp="", text=text) for text in texts]
    stages = journey.segment_stages(turns, max_stages=8)
    assert len(stages) == 8
    assert len(stages[0].turns) == 2


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
    meta = {
        "records": 3,
        "skipped_lines": 0,
        "first_ts": "a",
        "last_ts": "b",
        "branch_fallback": False,
    }
    payload = journey.build_journey(records, meta)
    assert payload["meta"]["user_turns"] == 2
    assert payload["meta"]["changed_files"] == 1
    assert len(payload["stages"]) == 2


def test_build_journey_counts_all_writes_before_truncation():
    calls = [("write", {"path": f"f{index}.py"}) for index in range(6)]
    records = [
        _message("u1", "user", "one"),
        _message("a1", "assistant", "done", calls=calls),
    ]
    payload = journey.build_journey(records, {"records": 2})
    assert payload["meta"]["changed_files"] == 6
    assert len(payload["stages"][0]["written_files"]) == 5


def test_main_rejects_non_message_records(tmp_path):
    path = tmp_path / "only-meta.jsonl"
    path.write_text('{"type": "session", "id": "a"}\n', encoding="utf-8")
    assert journey.main(["--file", str(path)]) == 2


def test_load_records_tolerates_invalid_utf8(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(b'{"id": "a", "type": "session"}\n\xff\xfe\n')
    records, skipped = journey.load_records(path)
    assert [record["id"] for record in records] == ["a"]
    assert skipped >= 1


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
