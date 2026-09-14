"""End-to-end usage ledger test (#213).

A fake pi agent (mockCommand) receives ``--session-dir`` from the executor —
the same flag real pi gets — parses it from its own argv and writes session
files there: one parent session file, one subagent artifact meta, and a
``forks/`` copy of the parent line that must NOT be counted twice.
"""

from __future__ import annotations

import json
import sys

import pytest

from tests.base import TestIsolator
from zima.execution.executor import PJobExecutor
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
    "usage": {
        "input": 6533000,
        "output": 10537,
        "cacheRead": 76800,
        "cacheWrite": 0,
        "cost": 0.4926,
        "turns": 24,
    },
}


def _fake_agent_command():
    """Build a mockCommand that mimics how real pi handles ``--session-dir``.

    The executor appends the pi flags to whatever base command mockCommand
    provides, so the fake agent sees ``--session-dir <temp>/pi-sessions`` in
    its argv. Payloads are embedded via ``repr(json.dumps(...))`` so no shell
    quoting is involved.
    """
    script = (
        "import pathlib, sys\n"
        "sess = None\n"
        "args = sys.argv[1:]\n"
        "for i, a in enumerate(args):\n"
        '    if a == "--session-dir" and i + 1 < len(args):\n'
        "        sess = args[i + 1]\n"
        "if sess:\n"
        "    root = pathlib.Path(sess)\n"
        '    (root / "subagent-artifacts").mkdir(parents=True, exist_ok=True)\n'
        '    (root / "forks").mkdir(parents=True, exist_ok=True)\n'
        '    (root / "session.jsonl").write_text('
        + repr(json.dumps(PARENT_SESSION))
        + ' + "\\n", encoding="utf-8")\n'
        '    (root / "subagent-artifacts" / "r1_checker_meta.json").write_text('
        + repr(json.dumps(CHILD_META))
        + ', encoding="utf-8")\n'
        # A copy of the parent history under forks/ — pi-subagents writes
        # these for forked children; counting them would double the parent.
        '    (root / "forks" / "child-fork.jsonl").write_text('
        + repr(json.dumps(PARENT_SESSION))
        + ' + "\\n", encoding="utf-8")\n'
        'print("benign-review-output")\n'
    )
    return [sys.executable, "-c", script]


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
                "spec": {"type": "pi", "parameters": {"mockCommand": _fake_agent_command()}},
            },
        )
        wf = WorkflowConfig.create(
            code="e2e-wf", name="E2E Workflow", template="review", variables=[]
        )
        config_manager.save_config("workflow", "e2e-wf", wf.to_dict())
        pjob = PJobConfig.create(
            code="e2e-pjob", name="E2E PJob", agent="e2e-agent", workflow="e2e-wf"
        )
        config_manager.save_config("pjob", "e2e-pjob", pjob.to_dict())

    def test_ledger_recorded_and_no_double_count(self, configs):
        executor = PJobExecutor()

        result = executor.execute("e2e-pjob")

        assert result.status.value == "success"
        assert result.stdout.strip().endswith("benign-review-output")

        usage = result.usage
        assert usage["collected"] is True
        # forks/ copy excluded: 17193 (parent) + 6620337 (child) = 6637530.
        # If the forked copy were counted, totals would be 6654723 instead.
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
