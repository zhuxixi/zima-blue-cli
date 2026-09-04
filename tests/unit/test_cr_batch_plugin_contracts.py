"""Contract gate for the Claude Code plugin copy of `github-code-review-batch`.

Issue #221 synced the plugin skill under `plugins/pr-automation/skills/` from
the pi version. These tests lock the plugin-side external contracts:

  1. Trigger phrases — zima daemon invokes the skill by literal phrase.
  2. Status report 3-state `Status:` enum as documented in SKILL.md.
  3. `<zima-review>` XML trailer requirement — the zima executor postExec
     path parses it (claude-type agents exit 0 regardless of verdict).
  4. `cc-cr-meta` round-trip: metadata written by build_review_body must
     parse back via parse_metadata, with zero pi-side literal residue.
  5. `gh` CLI path — SKILL.md still prescribes it.

Scripts are exercised as subprocess black boxes — the same way the skill
invokes them — mirroring the pi-side contract test's pattern without sharing
code with it. Python adds the script's own directory to ``sys.path``, so the
``issue_policy`` sibling import resolves when run as a subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/unit/<this> -> repo root
PLUGIN_ROOT = _REPO_ROOT / "plugins" / "pr-automation" / "skills" / "github-code-review-batch"
SCRIPTS = PLUGIN_ROOT / "scripts"

HEAD_SHA_A = "a" * 40


def _script(name: str) -> Path:
    return SCRIPTS / name


def _run(script: Path, stdin: str, *args: str) -> subprocess.CompletedProcess:
    """Run a plugin skill script, feeding `stdin`, returning the completed process."""
    return subprocess.run(
        [sys.executable, str(script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_json(script: Path, obj, *args: str) -> str:
    return _run(script, json.dumps(obj), *args).stdout


# A minimal Round-1 payload with one open blocking issue. Fields follow the
# issue_policy normalization contract: severity high -> blocking true.
ROUND1_INPUT = {
    "round": 1,
    "pr_number": 123,
    "head_sha": HEAD_SHA_A,
    "previous_head_sha": None,
    "repo_owner": "owner",
    "repo_name": "repo",
    "timestamp": "2026-09-04T08:00:00Z",
    "issues": [
        {
            "id": "issue-1",
            "description": "Missing error handling for OAuth callback",
            "reason": "bug",
            "file": "src/auth.ts",
            "lines": "67-72",
            "status": "open",
            "first_round": 1,
            "severity": "high",
        }
    ],
}


class TestCcPluginContracts:
    """External-contract gate for the pr-automation plugin skill (issue #221)."""

    @pytest.fixture(scope="class")
    def skill_md(self) -> str:
        return (PLUGIN_ROOT / "SKILL.md").read_text(encoding="utf-8")

    # -- Contract 1: trigger phrases (literal external contract) --------------

    @pytest.mark.parametrize(
        "phrase", ["batch review pr", "review pr batch", "scheduled review pr"]
    )
    def test_trigger_phrase_present(self, skill_md, phrase):
        assert phrase in skill_md, f"trigger phrase {phrase!r} vanished from plugin SKILL.md"

    # -- Contract 2: status report 3-state enum -------------------------------

    @pytest.mark.parametrize("status", ["NEEDS_FIX", "PASS", "NO_NEW_COMMITS"])
    def test_status_enum_documented(self, skill_md, status):
        assert status in skill_md, f"Status enum value {status!r} missing from plugin SKILL.md"

    # -- Contract 3: <zima-review> XML trailer requirement --------------------

    def test_zima_review_trailer_documented(self, skill_md):
        assert "<zima-review>" in skill_md, (
            "plugin SKILL.md must document the <zima-review> XML trailer — "
            "the zima executor postExec path parses it for label transitions"
        )

    # -- Contract 5: gh CLI path -----------------------------------------------

    def test_skill_md_prescribes_gh_cli(self, skill_md):
        assert "gh pr" in skill_md, "plugin SKILL.md must still prescribe the gh CLI path"

    # -- Contract 4: cc-cr-meta round-trip -------------------------------------

    def test_build_emits_cc_markers_and_no_pi_residue(self):
        body = _run_json(_script("build_review_body.py"), ROUND1_INPUT)
        assert "<!-- cc-cr-meta" in body
        assert "Generated with Claude Code" in body
        # The sync task's core risk is leftover pi-side literals — none may
        # survive in emitted artifacts.
        assert "pi-cr-meta" not in body
        assert "pi-coding-agent" not in body

    def test_build_then_parse_round_trip(self):
        body = _run_json(_script("build_review_body.py"), ROUND1_INPUT)
        reviews = {"reviews": [{"body": body, "submittedAt": "2026-09-04T08:01:00Z"}]}
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews))

        assert parsed.get("round") == 1
        assert parsed.get("pr_number") == 123
        assert parsed.get("head_sha") == HEAD_SHA_A
        assert parsed.get("total_issues") == 1
        assert parsed.get("new_count") == 1
        # One open high-severity finding normalizes to one blocking finding.
        assert parsed.get("blocking_open_count") == 1
        assert parsed.get("blocking_new_count") == 1
        assert parsed.get("advisory_open_count") == 0
        assert parsed.get("advisory_new_count") == 0
        issues = parsed.get("issues", [])
        assert isinstance(issues, list) and len(issues) == 1
        assert issues[0]["id"] == "issue-1"
        assert issues[0]["blocking"] is True

    def test_parse_ignores_pi_and_kimi_history(self):
        """Only Claude-Code-signed cc-cr-meta comments are consumed (#221 flip)."""
        pi_body = (
            f"<!-- pi-cr-meta\n{json.dumps({'round': 9, 'head_sha': HEAD_SHA_A})}\n-->\n"
            "🤖 Generated with pi-coding-agent\n"
        )
        kimi_body = "<!-- kimi-cr-meta\n{}\n-->\nGenerated with Kimi\n"
        cc_body = _run_json(_script("build_review_body.py"), ROUND1_INPUT)
        reviews = {
            "reviews": [
                {"body": pi_body, "submittedAt": "2026-09-04T08:00:00Z"},
                {"body": kimi_body, "submittedAt": "2026-09-04T08:00:30Z"},
                {"body": cc_body, "submittedAt": "2026-09-04T08:01:00Z"},
            ]
        }
        parsed = json.loads(_run_json(_script("parse_metadata.py"), reviews))
        assert parsed.get("round") == 1
        assert parsed.get("pr_number") == 123

    def test_parse_empty_reviews_returns_empty_object(self):
        parsed = json.loads(_run_json(_script("parse_metadata.py"), {"reviews": []}))
        assert parsed == {}

    # -- run_tool_layer --files smoke (#174 changed-file scoping) -------------

    def test_run_tool_layer_files_smoke(self):
        """`--files` scoping (#174) must be accepted: exit 0 + JSON on stdout.

        The tool layer degrades gracefully (missing binaries contribute no
        issues), so the contract is exit code + parseable JSON — never the
        issue count. `pyproject.toml` always exists at the repo root.
        """
        payload = {"repo_root": str(_REPO_ROOT), "changed_files": ["pyproject.toml"]}
        proc = _run(_script("run_tool_layer.py"), json.dumps(payload), "--files", "pyproject.toml")
        assert proc.returncode == 0, proc.stderr
        parsed = json.loads(proc.stdout)
        assert isinstance(parsed, list)
