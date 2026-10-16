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


def assert_gate_branching(text: str) -> None:
    """Gate decision rules + the audit marker + prose (non-question) confirmation."""
    assert "[auth] gate=" in text, "audit marker missing"
    for fragment in ("读本 issue 的 `authorization.md`", "**不停**", "暂停等许可", "落盘"):
        if fragment not in text:
            raise AssertionError(f"gate branching fragment missing: {fragment}")
    for fragment in ("散文", "不默认弹结构化 `question`"):
        if fragment not in text:
            raise AssertionError(f"confirmation-style fragment missing: {fragment}")


def assert_authorization_schema(text: str) -> None:
    """Record path template, schema keys, and the lifecycle rules."""
    assert (
        "~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/authorization.md" in text
    ), "authorization record path missing"
    for key in (
        "Gate:",
        "Granted-by-user-quote:",
        "Granted-at:",
        "Session:",
        "Scope:",
        "Merge: requires-explicit-user-approval",
    ):
        if key not in text:
            raise AssertionError(f"authorization schema key missing: {key}")
    for fragment in ("文件不存在 = 未授权", "Amended-at:", "视为 `stepwise`"):
        if fragment not in text:
            raise AssertionError(f"lifecycle rule missing: {fragment}")


def assert_failure_branches(text: str) -> None:
    """The three failure branches that guard against silent authorization."""
    for fragment in (
        "issue 号与当前 issue 不一致",
        "停下报告",
        "非交互宿主",
    ):
        if fragment not in text:
            raise AssertionError(f"failure branch missing: {fragment}")


def assert_precedence_clause(text: str) -> None:
    """Tier rules outrank every ⏸ statement inside spec-cross-review."""
    for fragment in (
        "唯一权威",
        "`pi/spec-cross-review/SKILL.md`",
        ":16",
        ":62",
        ":64",
        ":86",
        "edge-cases.md:19",
        "进度提示",
    ):
        if fragment not in text:
            raise AssertionError(f"precedence clause fragment missing: {fragment}")


def assert_authorization_discipline(text: str) -> None:
    """The 关键纪律 entry: authorization must be written down to count."""
    for fragment in ("授权落盘", "口头授权不落盘等于没有授权"):
        if fragment not in text:
            raise AssertionError(f"discipline entry missing: {fragment}")


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


class TestGateRules:
    @pytest.fixture(scope="class")
    def flow(self) -> str:
        return load_skill_texts()["github-issue-driven/SKILL.md"]

    def test_gate_branching_documented(self, flow: str) -> None:
        assert_gate_branching(flow)

    def test_authorization_schema_documented(self, flow: str) -> None:
        assert_authorization_schema(flow)

    def test_failure_branches_documented(self, flow: str) -> None:
        assert_failure_branches(flow)

    def test_precedence_clause_documented(self, flow: str) -> None:
        assert_precedence_clause(flow)

    def test_authorization_discipline_documented(self, flow: str) -> None:
        assert_authorization_discipline(flow)

    def test_mutation_dropping_schema_key_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("Merge: requires-explicit-user-approval", "Merge: auto")
        with pytest.raises(AssertionError):
            assert_authorization_schema(mutated)

    def test_mutation_dropping_audit_marker_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("[auth] gate=", "")
        with pytest.raises(AssertionError):
            assert_gate_branching(mutated)

    def test_mutation_dropping_failure_branch_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("停下报告", "继续")
        with pytest.raises(AssertionError):
            assert_failure_branches(mutated)

    def test_mutation_dropping_precedence_scope_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("edge-cases.md:19", "")
        with pytest.raises(AssertionError):
            assert_precedence_clause(mutated)

    def test_mutation_dropping_discipline_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("口头授权不落盘等于没有授权", "授权可以口头说说")
        with pytest.raises(AssertionError):
            assert_authorization_discipline(mutated)


def assert_step4_pause_substring_preserved(text: str) -> None:
    """The pinned step-4 pause sentence survives, still after the cross-review marker."""
    marker = "REQUIRED SUB-SKILL: Use spec-cross-review"
    pinned = "收敛后才 ⏸ 暂停等待用户确认设计"
    if marker not in text or pinned not in text:
        raise AssertionError("pinned step-4 strings missing")
    if text.index(marker) > text.index(pinned):
        raise AssertionError("cross-review marker no longer precedes the pause sentence")


def assert_step9_gate_tier_qualified(text: str) -> None:
    """Step 9 keeps both the pause fallback and the tier-qualified phrasing."""
    for fragment in ("按授权档位判定", "未授权 = 暂停等许可", "zima:needs-review", "前台阻塞等待"):
        if fragment not in text:
            raise AssertionError(f"step-9 fragment missing: {fragment}")


class TestStepWiring:
    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        return load_skill_texts()

    def test_step4_pinned_substring_preserved(self, texts: dict[str, str]) -> None:
        assert_step4_pause_substring_preserved(texts["github-issue-driven/SKILL.md"])

    def test_step9_gate_tier_qualified(self, texts: dict[str, str]) -> None:
        assert_step9_gate_tier_qualified(texts["github-issue-driven/SKILL.md"])

    def test_step4_no_unconditional_pause_left(self, texts: dict[str, str]) -> None:
        flow = texts["github-issue-driven/SKILL.md"]
        assert "收敛后才进入本步的 ⏸。" not in flow

    def test_cross_review_pause_lines_are_tier_qualified(self, texts: dict[str, str]) -> None:
        cross = texts["spec-cross-review/SKILL.md"]
        assert "收敛后输出并进入 ⏸（`auto` 档不停" in cross
        assert "细化项改完即进 ⏸（`auto` 档不停" in cross

    def test_cross_review_pinned_lines_untouched(self, texts: dict[str, str]) -> None:
        cross = texts["spec-cross-review/SKILL.md"]
        assert (
            "[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。"
            in cross
        )

    def test_mutation_stripping_step9_pause_breaks_assertion(self, texts: dict[str, str]) -> None:
        mutated = texts["github-issue-driven/SKILL.md"].replace(
            "未授权 = 暂停等许可", "未授权 = 继续"
        )
        with pytest.raises(AssertionError):
            assert_step9_gate_tier_qualified(mutated)

    def test_mutation_reordering_pinned_strings_breaks_assertion(
        self, texts: dict[str, str]
    ) -> None:
        flow = texts["github-issue-driven/SKILL.md"]
        marker = "REQUIRED SUB-SKILL: Use spec-cross-review"
        pinned = "收敛后才 ⏸ 暂停等待用户确认设计"
        mstart = flow.index(marker)
        mend = mstart + len(marker)
        pstart = flow.index(pinned)
        pend = pstart + len(pinned)
        reordered = (
            flow[:mstart] + flow[pstart:pend] + flow[mend:pstart] + flow[mstart:mend] + flow[pend:]
        )
        with pytest.raises(AssertionError):
            assert_step4_pause_substring_preserved(reordered)
