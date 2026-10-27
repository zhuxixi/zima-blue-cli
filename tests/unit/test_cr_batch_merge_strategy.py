"""Tests for the merge-strategy probe (issue #253).

Pure classification is tested directly. The `gh` IO shell is tested through an
injected `run` stub, so these tests never touch the network or real `gh`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = _REPO_ROOT / "pi" / "github-code-review-batch" / "scripts"
SCRIPT_PATH = _SCRIPT_DIR / "merge_strategy.py"

sys.path.insert(0, str(_SCRIPT_DIR))
import merge_strategy  # type: ignore[import-not-found]  # noqa: E402

ALL_FLAGS = {"squash": True, "merge": True, "rebase": True}


def _squash_row(number: int) -> tuple[int, str]:
    return number, f"docs: change {number} (#{number})"


def _merge_row(number: int) -> tuple[int, str]:
    return number, f"Merge pull request #{number} from o/r"


def _rebase_row(number: int) -> tuple[int, str]:
    return number, f"fix: change {number} (issue #{number})"


def _history_payload(rows: list[tuple[int, str]]) -> str:
    nodes = [
        {"number": number, "mergeCommit": {"message": f"{headline}\n\nbody paragraph"}}
        for number, headline in rows
    ]
    return json.dumps({"data": {"repository": {"pullRequests": {"nodes": nodes}}}})


def _ok(argv: list[str], stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, 0, stdout, "")


class TestClassifyFlags:
    @pytest.mark.parametrize(
        ("flags", "expected"),
        [
            ({"squash": True, "merge": False, "rebase": False}, ("squash", "flags")),
            ({"squash": False, "merge": False, "rebase": True}, ("rebase", "flags")),
            ({"squash": False, "merge": True, "rebase": False}, ("merge", "flags")),
            (ALL_FLAGS, None),
            ({"squash": False, "merge": False, "rebase": False}, None),
            ({}, None),
        ],
    )
    def test_single_flag_decides_and_multiple_do_not(self, flags, expected):
        assert merge_strategy.classify_flags(flags) == expected


class TestClassifyHeadline:
    def test_merge_commit(self):
        assert merge_strategy.classify_headline(248, "Merge pull request #248 from x/y") == "merge"

    def test_squash_suffix(self):
        headline = "docs: foo (issue #245) (#249)"
        assert merge_strategy.classify_headline(249, headline) == "squash"

    def test_rebase_without_automatic_suffix(self):
        assert merge_strategy.classify_headline(239, "fix: bar (issue #239)") == "rebase"

    def test_truncated_headline_is_never_squash(self):
        # messageHeadline truncates at 70 chars with "…"; such input loses the
        # "(#N)" suffix and can only degrade to rebase, never a false squash.
        assert merge_strategy.classify_headline(249, "docs: foo (issue #245)…") == "rebase"


class TestClassifyHistory:
    def test_n10_nine_squash_one_merge(self):
        rows = [_merge_row(248)] + [_squash_row(n) for n in range(249, 258)]
        strategy, basis, buckets = merge_strategy.classify_history(rows)
        assert (strategy, basis) == ("squash", "history")
        assert buckets["squash"] == 9
        assert buckets["merge"] == 1
        assert buckets["merged_sampled"] == 10

    def test_n5_all_squash_uses_ceil(self):
        # ceil(0.8 * 5) == 4, so five squash rows clear the threshold.
        rows = [_squash_row(n) for n in range(240, 245)]
        assert merge_strategy.classify_history(rows)[:2] == ("squash", "history")

    def test_n5_four_squash_one_merge_clears_threshold(self):
        rows = [_squash_row(n) for n in range(240, 244)] + [_merge_row(244)]
        assert merge_strategy.classify_history(rows)[:2] == ("squash", "history")

    def test_n5_split_below_threshold_is_ambiguous(self):
        rows = [_squash_row(n) for n in range(240, 243)] + [_rebase_row(n) for n in range(243, 245)]
        assert merge_strategy.classify_history(rows)[:2] == ("unknown", "history-ambiguous")

    def test_rebase_majority(self):
        rows = [_rebase_row(n) for n in range(240, 250)]
        assert merge_strategy.classify_history(rows)[:2] == ("rebase", "history")

    def test_n4_is_ambiguous(self):
        rows = [_squash_row(n) for n in range(240, 244)]
        strategy, basis, buckets = merge_strategy.classify_history(rows)
        assert (strategy, basis) == ("unknown", "history-ambiguous")
        assert buckets["merged_sampled"] == 4

    def test_n10_split_five_five_is_ambiguous(self):
        rows = [_squash_row(n) for n in range(240, 245)] + [_merge_row(n) for n in range(245, 250)]
        assert merge_strategy.classify_history(rows)[:2] == ("unknown", "history-ambiguous")


class TestRenderPolicy:
    @pytest.mark.parametrize(
        ("strategy", "inject", "check_pr_title"),
        [
            ("squash", False, True),
            ("rebase", True, False),
            ("merge", True, False),
            ("unknown", False, True),
        ],
    )
    def test_policy_matrix(self, strategy, inject, check_pr_title):
        assert merge_strategy.render_policy(strategy) == {
            "inject_branch_subjects": inject,
            "check_pr_title": check_pr_title,
            "metadata_max_severity": "low",
        }

    @pytest.mark.parametrize("strategy", ["squash", "rebase", "merge", "unknown"])
    def test_metadata_is_always_advisory(self, strategy):
        assert merge_strategy.render_policy(strategy)["metadata_max_severity"] == "low"


class TestDecide:
    def test_probe_failed_is_unknown(self):
        payload = merge_strategy.decide("o/r", 251, ALL_FLAGS, None)
        assert payload["strategy"] == "unknown"
        assert payload["basis"] == "probe-failed"
        assert payload["policy"] == merge_strategy.render_policy("unknown")

    def test_ambiguous_history_is_unknown(self):
        rows = [_squash_row(n) for n in range(240, 245)] + [_merge_row(n) for n in range(245, 250)]
        payload = merge_strategy.decide("o/r", 251, ALL_FLAGS, rows)
        assert payload["strategy"] == "unknown"
        assert payload["basis"] == "history-ambiguous"

    def test_single_flag_wins_basis_flags(self):
        flags = {"squash": True, "merge": False, "rebase": False}
        payload = merge_strategy.decide("o/r", 251, flags, None)
        assert (payload["strategy"], payload["basis"]) == ("squash", "flags")

    def test_history_verdict_carries_policy_and_evidence(self):
        rows = [_merge_row(248)] + [_squash_row(n) for n in range(249, 258)]
        payload = merge_strategy.decide("o/r", 251, ALL_FLAGS, rows)
        assert payload["schema"] == 1
        assert (payload["repo"], payload["pr"]) == ("o/r", 251)
        assert (payload["strategy"], payload["basis"]) == ("squash", "history")
        assert payload["policy"] == merge_strategy.render_policy("squash")
        assert payload["evidence"]["merged_sampled"] == 10
        assert payload["evidence"]["buckets"] == {"squash": 9, "rebase": 0, "merge": 1}
        assert payload["evidence"]["sample_prs"] == [248, 249, 250]


class TestProbe:
    def test_happy_path_writes_json_and_prints_one_line(self, tmp_path, capsys, monkeypatch):
        rows = [_merge_row(248)] + [_squash_row(n) for n in range(249, 258)]
        calls: list[tuple[list[str], dict]] = []

        def fake_run(argv, **kwargs):
            calls.append((list(argv), kwargs))
            if argv[1:3] == ["api", "graphql"]:
                return _ok(argv, _history_payload(rows))
            return _ok(argv, json.dumps(ALL_FLAGS))

        monkeypatch.setattr(merge_strategy.subprocess, "run", fake_run)
        out_path = tmp_path / "merge-strategy.json"

        code = merge_strategy.main(["--repo", "o/r", "--pr", "251", "--json-out", str(out_path)])

        assert code == 0
        stdout_lines = capsys.readouterr().out.splitlines()
        assert stdout_lines == ["merge_strategy=squash basis=history"]

        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert payload["strategy"] == "squash"
        assert payload["basis"] == "history"
        assert payload["policy"] == merge_strategy.render_policy("squash")
        assert payload["evidence"]["sample_prs"] == [248, 249, 250]

        flags_cmd, flags_kwargs = calls[0]
        assert flags_cmd[:4] == ["gh", "api", "repos/o/r", "--jq"]
        assert "allow_squash_merge" in flags_cmd[4]
        assert "allow_merge_commit" in flags_cmd[4]
        assert "allow_rebase_merge" in flags_cmd[4]
        assert flags_kwargs["capture_output"] is True
        assert flags_kwargs["text"] is True
        assert flags_kwargs["check"] is False
        assert flags_kwargs["stdin"] is subprocess.DEVNULL
        assert flags_kwargs["timeout"] > 0

        graphql_cmd, _ = calls[1]
        assert graphql_cmd[:3] == ["gh", "api", "graphql"]
        joined = " ".join(graphql_cmd)
        assert "mergeCommit" in joined
        assert "message" in joined
        assert "messageHeadline" not in joined
        assert "first: 10" in joined
        assert "last:" not in joined

    def test_single_flag_skips_history_query(self, tmp_path, capsys, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return _ok(argv, json.dumps({"squash": False, "merge": False, "rebase": True}))

        monkeypatch.setattr(merge_strategy.subprocess, "run", fake_run)
        out_path = tmp_path / "merge-strategy.json"
        code = merge_strategy.main(["--repo", "o/r", "--pr", "251", "--json-out", str(out_path)])

        assert code == 0
        assert len(calls) == 1
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert (payload["strategy"], payload["basis"]) == ("rebase", "flags")
        assert payload["policy"]["inject_branch_subjects"] is True
        assert capsys.readouterr().out.splitlines() == ["merge_strategy=rebase basis=flags"]

    def test_probe_failure_never_raises(self, tmp_path, capsys, monkeypatch):
        def failing_run(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, "", "gh: not authenticated")

        monkeypatch.setattr(merge_strategy.subprocess, "run", failing_run)
        out_path = tmp_path / "merge-strategy.json"
        code = merge_strategy.main(["--repo", "o/r", "--pr", "251", "--json-out", str(out_path)])

        assert code == 0
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert (payload["strategy"], payload["basis"]) == ("unknown", "probe-failed")
        assert payload["policy"] == merge_strategy.render_policy("unknown")
        assert capsys.readouterr().out.splitlines() == ["merge_strategy=unknown basis=probe-failed"]

    def test_probe_swallows_subprocess_oserror(self):
        calls: list[list[str]] = []

        def missing_gh(argv, **kwargs):
            calls.append(list(argv))
            raise OSError("gh not installed")

        payload = merge_strategy.probe("o/r", 251, run=missing_gh)
        assert calls and calls[0][0] == "gh"
        assert (payload["strategy"], payload["basis"]) == ("unknown", "probe-failed")

    def test_probe_swallows_bad_json(self):
        def bad_json(argv, **kwargs):
            return _ok(argv, "not json")

        payload = merge_strategy.probe("o/r", 251, run=bad_json)
        assert (payload["strategy"], payload["basis"]) == ("unknown", "probe-failed")

    def test_probe_swallows_invalid_repo(self):
        calls: list[list[str]] = []

        def all_flags(argv, **kwargs):
            calls.append(list(argv))
            return _ok(argv, json.dumps(ALL_FLAGS))

        payload = merge_strategy.probe("not-a-repo", 251, run=all_flags)
        assert len(calls) == 1  # invalid repo fails before the GraphQL call
        assert (payload["strategy"], payload["basis"]) == ("unknown", "probe-failed")


class TestScriptPortability:
    def test_no_harness_literals(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "pi-cr" not in source
        assert "cc-cr" not in source

    def test_history_query_never_requests_truncated_headline(self):
        assert "messageHeadline" not in merge_strategy.HISTORY_QUERY
        assert "mergeCommit { message }" in merge_strategy.HISTORY_QUERY
        # `last` with a DESC order returns the OLDEST N rows; the probe must
        # sample the newest merged PRs, so the connection uses `first`.
        assert f"first: {merge_strategy.HISTORY_SAMPLE}" in merge_strategy.HISTORY_QUERY
        assert "last:" not in merge_strategy.HISTORY_QUERY
