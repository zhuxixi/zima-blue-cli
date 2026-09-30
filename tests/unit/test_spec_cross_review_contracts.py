"""Contract gate for the `spec-cross-review` skill (issue #250).

These tests lock the *external contracts* of the new step-4 cross-review skill:

  1. Structure — frontmatter, required sections, references files.
  2. Pinned literals — the degrade prompt and the two handoff lines.
  3. Step-4 wiring — REQUIRED SUB-SKILL marker precedes the pause sentence.
  4. Portability — no hardcoded model literals in the touched skill docs.
  5. Report template — the fields a round report must carry.
  6. README registry — the skill table lists the new skill and cr-batch.

They assert *documentation contracts* only; semantic quality and real-session
behavior are covered by the U1 pilot (issue #250 acceptance matrix).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = _REPO_ROOT / "pi" / "spec-cross-review"
FLOW = _REPO_ROOT / "pi" / "github-issue-driven" / "SKILL.md"
README = _REPO_ROOT / "pi" / "README.md"

BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")

REQUIRED_SECTIONS = (
    "## 触发与前置",
    "## 模型判定与分流",
    "## 复核轮硬规则",
    "## 发现分级",
    "## 收敛与轮次上限",
    "## 留痕纪律",
    "## 保证边界",
)

DEGRADE_PROMPT = "[spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。"
DEGRADE_PROMPT_2 = "请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。"

NEXT_STEP_LINE = "[spec-cross-review] 下一步：切到 <provider>/<model>，然后说 spec-cross-review（第 <k> 轮复核）。"
CONVERGED_LINE = (
    "[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestSkillStructure:
    """A1: the skill bundle exists and carries the contracted skeleton."""

    @pytest.fixture(scope="class")
    def skill(self) -> str:
        return _read(SKILL_DIR / "SKILL.md")

    def test_skill_file_exists(self) -> None:
        assert (SKILL_DIR / "SKILL.md").is_file()

    def test_frontmatter(self, skill: str) -> None:
        assert skill.startswith("---\n")
        head = skill.split("---", 2)[1]
        assert "name: spec-cross-review" in head
        assert "description:" in head
        assert len(head.split("description:", 1)[1].strip()) > 20

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_sections(self, skill: str, section: str) -> None:
        assert section in skill


class TestPinnedLiterals:
    """A1 (continued): the degrade prompt and handoff lines are verbatim."""

    @pytest.fixture(scope="class")
    def skill(self) -> str:
        return _read(SKILL_DIR / "SKILL.md")

    def test_degrade_prompt_pinned(self, skill: str) -> None:
        assert DEGRADE_PROMPT in skill
        assert DEGRADE_PROMPT_2 in skill

    def test_handoff_lines_pinned(self, skill: str) -> None:
        assert NEXT_STEP_LINE in skill
        assert CONVERGED_LINE in skill

    def test_convergence_cap_is_four(self, skill: str) -> None:
        assert "默认上限 4 轮" in skill


class TestReportTemplate:
    """A4: the round-report / state-index template carries every field."""

    @pytest.fixture(scope="class")
    def template(self) -> str:
        return _read(SKILL_DIR / "references" / "report-template.md")

    def test_template_file_exists(self) -> None:
        assert (SKILL_DIR / "references" / "report-template.md").is_file()

    @pytest.mark.parametrize(
        "field",
        (
            "Round k",
            "Reviewer:",
            "Drafter:",
            "Reviewed spec sha256:",
            "Mode:",
            "真缺口",
            "细化",
            "核对通过",
            "## 修订摘要",
            "当前状态",
            "Open findings",
        ),
    )
    def test_template_fields(self, template: str, field: str) -> None:
        assert field in template, field

    def test_template_pins_hash_command(self, template: str) -> None:
        assert "sha256sum" in template
        assert "不写回被计算的文件自身" in template

    def test_template_pins_mode_enum(self, template: str) -> None:
        assert "`cross-model`" in template
        assert "`degraded (same-model)`" in template
        assert "`cross-model (post-hoc same-physical)`" in template


class TestEdgeCaseCoverage:
    """Review Focus: every scenario the spec names must be documented.

    These assertions prove the doc *mentions* the case; real behavior is
    covered by the U1 pilot only.
    """

    def test_checklist_file_exists(self) -> None:
        assert (SKILL_DIR / "references" / "checklist.md").is_file()

    def test_edge_cases_file_exists(self) -> None:
        assert (SKILL_DIR / "references" / "edge-cases.md").is_file()

    @pytest.fixture(scope="class")
    def edge(self) -> str:
        return _read(SKILL_DIR / "references" / "edge-cases.md")

    @pytest.mark.parametrize(
        "marker",
        (
            "自然语言",
            "重建",
            "hash 不匹配",
            "Drafted:",
            "降级复核",
            "轮次上限",
            "复核零发现",
        ),
    )
    def test_edge_case_documented(self, edge: str, marker: str) -> None:
        assert marker in edge, marker


class TestFlowStep4:
    """A2: step 4 must gate on the cross-review before the ⏸ pause."""

    @pytest.fixture(scope="class")
    def flow(self) -> str:
        return _read(FLOW)

    def test_required_sub_skill_marker(self, flow: str) -> None:
        assert "REQUIRED SUB-SKILL: Use spec-cross-review" in flow

    def test_marker_precedes_pause_sentence(self, flow: str) -> None:
        before = flow.index("REQUIRED SUB-SKILL: Use spec-cross-review")
        after = flow.index("收敛后才 ⏸ 暂停等待用户确认设计")
        assert before < after

    def test_drafted_header_requirement(self, flow: str) -> None:
        assert "Drafted:" in flow
        assert "Revised:" in flow


class TestNoHardcodedModels:
    """A3: skill docs must not name concrete models (deployment policy).

    Portable by design: a literal blacklist (same style as
    test_cr_batch_contracts.py::test_docs_no_hardcoded_deepseek_models),
    no shape regex (paths like tests/unit/x.py would false-positive),
    and no machine-private config (§250 R1-G3 / R2-D3).
    """

    def _docs(self) -> list[tuple[str, str]]:
        docs: list[tuple[str, str]] = [("github-issue-driven/SKILL.md", _read(FLOW))]
        for path in sorted(SKILL_DIR.rglob("*.md")):
            docs.append((str(path.relative_to(_REPO_ROOT)), _read(path)))
        return docs

    @pytest.mark.parametrize("literal", BANNED_LITERALS)
    def test_no_hardcoded_banned_literal(self, literal: str) -> None:
        for name, text in self._docs():
            assert literal not in text, f"{literal!r} found in {name}"

    def test_no_hardcoded_machine_private_config_reference(self) -> None:
        for name, text in self._docs():
            assert "~/.pi/" not in text, name


class TestReadmeTable:
    """A6: the pi package README registers both skills."""

    @pytest.fixture(scope="class")
    def readme(self) -> str:
        return _read(README)

    @pytest.mark.parametrize("skill", ("spec-cross-review", "github-code-review-batch"))
    def test_skill_row_present(self, readme: str, skill: str) -> None:
        rows = [line for line in readme.splitlines() if line.startswith("|") and skill in line]
        assert rows, f"no table row for {skill}"
        cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
        assert len(cells) >= 3
        assert all(cells[1:3]), f"empty role/step cell for {skill}"
