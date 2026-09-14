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
