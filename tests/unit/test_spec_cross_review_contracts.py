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
