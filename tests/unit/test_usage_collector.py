"""Unit tests for usage ledger collection (#213)."""

from __future__ import annotations

import json

import pytest

from zima.execution.usage_collector import (
    _empty_totals,
    _human_count,
    collect_usage,
    format_usage_line,
    merge_usage,
    parse_child_usage,
    parse_parent_usage,
)


def _zero_totals():
    """Return a zeroed totals bucket for equality assertions."""
    return _empty_totals()


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
                "cost": {
                    "input": 0.0,
                    "output": 0.0,
                    "cacheRead": 0.0,
                    "cacheWrite": 0.0,
                    "total": cost,
                },
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
                _assistant(
                    "zai-coding-cn", "glm-5.3", input_tokens=1000, output=10, total=1010, cost=0.01
                ),
                _assistant(
                    "zai-coding-cn", "glm-5.3", input_tokens=2000, output=20, total=2020, cost=0.02
                ),
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
                _assistant(
                    "zai-coding-cn", "glm-5.3", input_tokens=10, output=1, total=11, cost=0.001
                ),
                _assistant(
                    "zai-coding-cn",
                    "glm-5.3-flash",
                    input_tokens=20,
                    output=2,
                    total=22,
                    cost=0.002,
                ),
                _assistant(
                    "zai-coding-cn", "glm-5.3", input_tokens=30, output=3, total=33, cost=0.003
                ),
            ],
        )

        result = parse_parent_usage([path])

        by_model = {(b["provider"], b["model"]): b for b in result["by_model"]}
        assert set(by_model) == {("zai-coding-cn", "glm-5.3"), ("zai-coding-cn", "glm-5.3-flash")}
        assert by_model[("zai-coding-cn", "glm-5.3")]["total_tokens"] == 44
        assert by_model[("zai-coding-cn", "glm-5.3-flash")]["total_tokens"] == 22


def _write_child_meta(
    artifacts_dir, run_id, agent, model, *, input_tokens, output, cache_read=0, cost=0.0, turns=1
):
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
        _write_child_meta(
            artifacts,
            "r1",
            "worker",
            "zai-coding-cn/glm-5.3-flash",
            input_tokens=1909,
            output=102,
            cache_read=2304,
            cost=0.0002,
            turns=1,
        )

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

    def test_mixed_turns_sets_bucket_turns_to_none(self, tmp_path):
        """One child without turns makes the bucket's turns unknown (None) —
        never a sum of only the known ones (#213)."""
        artifacts = tmp_path / "subagent-artifacts"
        _write_child_meta(
            artifacts,
            "r1",
            "checker",
            "zai-coding-cn/glm-5.3-flash",
            input_tokens=100,
            output=10,
            cost=0.001,
            turns=2,
        )
        _write_child_meta(
            artifacts,
            "r2",
            "checker",
            "zai-coding-cn/glm-5.3-flash",
            input_tokens=200,
            output=20,
            cost=0.002,
            turns=None,
        )

        result = parse_child_usage(artifacts)

        assert result["children_count"] == 2
        assert len(result["by_model"]) == 1
        bucket = result["by_model"][0]
        assert bucket["turns"] is None
        assert bucket["input"] == 300
        assert bucket["total_tokens"] == 330

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
        _write_child_meta(
            artifacts,
            "r1",
            "checker",
            "zai-coding-cn/glm-5.3-flash",
            input_tokens=100,
            output=10,
            cost=0.001,
            turns=2,
        )
        _write_child_meta(
            artifacts,
            "r2",
            "checker",
            "zai-coding-cn/glm-5.3-flash",
            input_tokens=200,
            output=20,
            cost=0.002,
            turns=3,
        )

        result = parse_child_usage(artifacts)

        assert result["children_count"] == 2
        assert result["totals"]["total_tokens"] == 330
        assert len(result["by_model"]) == 1
        assert result["by_model"][0]["input"] == 300
        assert result["by_model"][0]["turns"] == 5


class TestMergeUsage:
    def test_combines_parent_and_children(self):
        parent = {
            "totals": {
                "input": 100,
                "output": 10,
                "cache_read": 0,
                "cache_write": 0,
                "total_tokens": 110,
                "cost_usd": 0.01,
            },
            "by_model": [{"role": "parent"}],
        }
        children = {
            "totals": {
                "input": 900,
                "output": 90,
                "cache_read": 0,
                "cache_write": 0,
                "total_tokens": 990,
                "cost_usd": 0.09,
            },
            "by_model": [{"role": "child"}],
            "children_count": 3,
        }

        merged = merge_usage(parent, children)

        assert merged["collected"] is True
        # Integer counters must match exactly; cost is a float sum, so it is
        # compared with approx (binary floats cannot represent 0.1 exactly).
        assert merged["totals"]["input"] == 1000
        assert merged["totals"]["output"] == 100
        assert merged["totals"]["cache_read"] == 0
        assert merged["totals"]["cache_write"] == 0
        assert merged["totals"]["total_tokens"] == 1100
        assert merged["totals"]["cost_usd"] == pytest.approx(0.1)
        assert merged["by_role"]["parent"]["total_tokens"] == 110
        assert merged["by_role"]["children"]["total_tokens"] == 990
        assert merged["by_model"] == [{"role": "parent"}, {"role": "child"}]
        assert merged["children_count"] == 3
        assert merged["cost_note"] == "estimated"

    def test_no_children(self):
        parent = {
            "totals": {
                "input": 5,
                "output": 5,
                "cache_read": 0,
                "cache_write": 0,
                "total_tokens": 10,
                "cost_usd": 0.0,
            },
            "by_model": [],
        }
        children = {"totals": _empty_totals(), "by_model": [], "children_count": 0}

        merged = merge_usage(parent, children)

        assert merged["totals"]["total_tokens"] == 10
        assert merged["children_count"] == 0


class TestCollectUsage:
    def test_collects_parent_and_children_from_session_dir(self, tmp_path):
        session_dir = tmp_path / "pi-sessions"
        session_dir.mkdir()
        _write_session(
            session_dir,
            "s.jsonl",
            [
                _assistant(
                    "zai-coding-cn", "glm-5.3", input_tokens=100, output=10, total=110, cost=0.01
                )
            ],
        )
        _write_child_meta(
            session_dir / "subagent-artifacts",
            "r1",
            "checker",
            "zai-coding-cn/glm-5.3-flash",
            input_tokens=900,
            output=90,
            cost=0.09,
            turns=2,
        )

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


class TestFormatUsageLine:
    def test_collected_line(self):
        usage = {
            "collected": True,
            "totals": {
                "input": 6_550_000,
                "output": 10_700,
                "cache_read": 0,
                "cache_write": 0,
                "total_tokens": 6_560_700,
                "cost_usd": 0.4941,
            },
            "by_role": {
                "parent": {"total_tokens": 17_163},
                "children": {"total_tokens": 6_543_537},
            },
            "by_model": [],
            "children_count": 12,
            "cost_note": "estimated",
        }

        line = format_usage_line(usage)

        assert line == (
            "Usage:  in 6.55M / out 10.70K  ·  est. $0.49  ·  " "parent 0% / children 100%"
        )

    def test_none_record_is_unknown(self):
        assert format_usage_line(None) == "Usage:  unknown (not_collected)"

    def test_failed_collection_shows_reason(self):
        line = format_usage_line({"collected": False, "reason": "no_session_dir"})

        assert line == "Usage:  unknown (no_session_dir)"

    def test_failed_collection_without_reason_falls_back(self):
        assert format_usage_line({"collected": False}) == "Usage:  unknown (not_collected)"

    def test_human_count_plain_number(self):
        assert _human_count(999) == "999"
        assert _human_count(1500) == "1.50K"
        assert _human_count(2_500_000) == "2.50M"

    def test_parent_exceeding_total_is_clamped(self):
        usage = {
            "collected": True,
            "totals": {
                "input": 100,
                "output": 0,
                "cache_read": 0,
                "cache_write": 0,
                "total_tokens": 100,
                "cost_usd": 0.0,
            },
            "by_role": {"parent": {"total_tokens": 150}, "children": {"total_tokens": 0}},
            "by_model": [],
            "children_count": 0,
            "cost_note": "estimated",
        }

        assert "parent 100% / children 0%" in format_usage_line(usage)

        usage["by_role"]["parent"]["total_tokens"] = -50
        assert "parent 0% / children 100%" in format_usage_line(usage)

    def test_zero_total_does_not_divide_by_zero(self):
        usage = {
            "collected": True,
            "totals": {
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_write": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
            },
            "by_role": {"parent": {"total_tokens": 0}, "children": {"total_tokens": 0}},
            "by_model": [],
            "children_count": 0,
            "cost_note": "estimated",
        }

        assert "parent 0% / children 0%" in format_usage_line(usage)

    def test_partially_formed_dict_does_not_raise(self):
        usage = {"collected": True, "totals": "garbage", "by_role": []}

        assert format_usage_line(usage) == (
            "Usage:  in 0 / out 0  ·  est. $0.00  ·  parent 0% / children 0%"
        )
