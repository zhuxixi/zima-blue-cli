"""Contract gate for the one-shot gate authorization mechanism (issue #258).

These tests lock the *documentation contracts* of the tiered authorization
feature: three tiers, the gate branching rules, the authorization record
schema, the failure branches, and the precedence clause that resolves the
pinned spec-cross-review convergence line.

They assert documentation contracts only; runtime behaviour is covered by the
U1/U2 pilots (issue #258 acceptance matrix).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
FLOW = _REPO_ROOT / "pi" / "github-issue-driven" / "SKILL.md"
MONITOR = _REPO_ROOT / "pi" / "zima-pr-monitor" / "SKILL.md"
CROSS = _REPO_ROOT / "pi" / "spec-cross-review" / "SKILL.md"

TIERS = ("stepwise", "design-only", "auto")
BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")


def load_skill_texts(repo_root: Path = _REPO_ROOT) -> dict[str, str]:
    """Read every document this contract spans. Sole IO boundary."""
    paths = {
        "github-issue-driven/SKILL.md": repo_root / "pi" / "github-issue-driven" / "SKILL.md",
        "zima-pr-monitor/SKILL.md": repo_root / "pi" / "zima-pr-monitor" / "SKILL.md",
        "spec-cross-review/SKILL.md": repo_root / "pi" / "spec-cross-review" / "SKILL.md",
    }
    texts: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            pytest.fail(f"missing contract document: {path}")
        texts[name] = path.read_text(encoding="utf-8")
    return texts


def assert_three_tiers(text: str) -> None:
    """Three tier tokens exist and each is anchored in a tier-table row.

    Backtick anchoring is deliberate: the document already contains
    ``automated E2E`` (a bare ``auto`` substring), so a raw substring match
    would pass even after the tier table is deleted.
    """
    assert "| 档位 |" in text, "tier table header missing"
    for tier in TIERS:
        token = f"`{tier}`"
        if token not in text:
            raise AssertionError(f"tier token not documented: {token}")
        rows = [line for line in text.splitlines() if line.startswith("|") and token in line]
        if not rows:
            raise AssertionError(f"tier token {token} is not in a table row")
    default_row = [line for line in text.splitlines() if "`stepwise`" in line]
    assert default_row, "`stepwise` tier row missing"


class TestThreeTiers:
    @pytest.fixture(scope="class")
    def flow(self) -> str:
        return load_skill_texts()["github-issue-driven/SKILL.md"]

    def test_three_tiers_documented(self, flow: str) -> None:
        assert_three_tiers(flow)

    def test_loader_fails_loudly_on_missing_document(self, tmp_path: Path) -> None:
        with pytest.raises(BaseException, match="missing contract document"):
            load_skill_texts(tmp_path)

    def test_mutation_deleting_tier_row_breaks_assertion(self) -> None:
        flow = load_skill_texts()["github-issue-driven/SKILL.md"]
        mutated = "\n".join(line for line in flow.splitlines() if "`auto`" not in line)
        assert "automated E2E" in mutated, "mutation must keep the collision source"
        with pytest.raises(AssertionError):
            assert_three_tiers(mutated)

    def test_mutation_deleting_table_header_breaks_assertion(self) -> None:
        flow = load_skill_texts()["github-issue-driven/SKILL.md"]
        mutated = flow.replace("| 档位 |", "| 档位X |")
        with pytest.raises(AssertionError):
            assert_three_tiers(mutated)

    def test_mutation_backtick_stripped_tier_is_not_matched(self) -> None:
        flow = load_skill_texts()["github-issue-driven/SKILL.md"]
        mutated = flow.replace("`stepwise`", "stepwise")
        with pytest.raises(AssertionError):
            assert_three_tiers(mutated)
