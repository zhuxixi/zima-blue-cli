"""Contract gate for the automated `spec-cross-review` skill (issue #254).

These tests lock the *external contracts* of the dispatched cross-review loop:

  1. Profile — `pi/agents/spec-reviewer.md` frontmatter (fresh context, no
     write/edit tools, no model field).
  2. Package registration — `pi.subagents.agents` exposes the agent dir.
  3. Dispatch contract — task-template placeholders + outputSchema fields.
  4. Skill orchestration — required sections + pinned literals.
  5. Report template — round-report / state-index fields, new Mode enum,
     verbatim JSON appendix.
  6. Edge cases — every failure branch the spec names.
  7. Step-4 wiring — auto-entry documented, markers ordered, Drafted kept.
  8. Portability — no hardcoded model literals or machine-private config.
  9. README registry — skill row updated, profile mentioned.

They assert *documentation contracts* only; real-session behavior is covered
by the U1/U2 pilots (issue #254 acceptance matrix).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = _REPO_ROOT / "pi" / "spec-cross-review"
AGENTS_DIR = _REPO_ROOT / "pi" / "agents"
FLOW = _REPO_ROOT / "pi" / "github-issue-driven" / "SKILL.md"
README = _REPO_ROOT / "pi" / "README.md"
PACKAGE_JSON = _REPO_ROOT / "package.json"

PROFILE = AGENTS_DIR / "spec-reviewer.md"
DISPATCH = SKILL_DIR / "references" / "dispatch-contract.md"

BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")

REQUIRED_SECTIONS = (
    "## 触发与前置",
    "## Preflight 门禁",
    "## 每轮编排",
    "## 写入归属",
    "## 发现分级",
    "## 收敛与轮次上限",
    "## 降级",
    "## 失败处理",
    "## 留痕纪律",
    "## 保证边界",
    "## 部署前置",
)

DEGRADE_PROMPT = "[spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。"
DEGRADE_PROMPT_2 = "请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。"

PROGRESS_LINE = "[spec-cross-review] 第 <k> 轮完成：复核者 <effective-model> (fresh)，真缺口 <N>、细化 <M>，报告 <绝对路径>。"
CONVERGED_LINE = (
    "[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestProfileContract:
    """A1: the spec-reviewer agent profile carries the contracted frontmatter."""

    @pytest.fixture(scope="class")
    def profile(self) -> str:
        return _read(PROFILE)

    def test_profile_file_exists(self) -> None:
        assert PROFILE.is_file()

    def test_frontmatter_fields(self, profile: str) -> None:
        assert profile.startswith("---\n")
        head = profile.split("---", 2)[1]
        assert "name: spec-reviewer" in head
        assert "description:" in head
        assert "defaultContext: fresh" in head
        assert "inheritProjectContext: true" in head
        assert "inheritSkills: false" in head
        assert "systemPromptMode: replace" in head
        assert "thinking: high" in head

    def test_no_model_field(self, profile: str) -> None:
        head = profile.split("---", 2)[1]
        assert "model:" not in head

    def test_tools_have_no_write_or_edit(self, profile: str) -> None:
        head = profile.split("---", 2)[1]
        tools_line = next(line for line in head.splitlines() if line.startswith("tools:"))
        tools = {item.strip() for item in tools_line.split(":", 1)[1].split(",")}
        assert "write" not in tools
        assert "edit" not in tools
        assert "bash" in tools  # sha256 对账与只读 git/gh 查询需要


class TestPackageRegistration:
    """A2: package.json exposes the agent directory to pi-subagents."""

    def test_pi_subagents_agents(self) -> None:
        pkg = json.loads(_read(PACKAGE_JSON))
        agents = pkg["pi"]["subagents"]["agents"]
        assert "./pi/agents" in agents


class TestDispatchContract:
    """A4: dispatch contract pins task template, variables and outputSchema."""

    @pytest.fixture(scope="class")
    def doc(self) -> str:
        return _read(DISPATCH)

    def test_file_exists(self) -> None:
        assert DISPATCH.is_file()

    @pytest.mark.parametrize(
        "placeholder",
        (
            "<REPO_ABS_PATH>",
            "<ROUND_K>",
            "<ISSUE_N>",
            "<SPEC_ABS_PATH>",
            "<EXPECTED_SHA256>",
            "<PREV_OPEN_FINDINGS>",
            "<CHECKLIST_CONTENT>",
        ),
    )
    def test_task_template_placeholders(self, doc: str, placeholder: str) -> None:
        assert placeholder in doc

    @pytest.mark.parametrize(
        "field",
        (
            "round",
            "reviewedSha256",
            "lenses",
            "findings",
            "counts",
            "convergence",
            "gaps",
            "details",
            "passes",
            "id",
            "level",
            "location",
            "why",
            "suggestion",
            "costIfSkipped",
        ),
    )
    def test_output_schema_fields(self, doc: str, field: str) -> None:
        assert f'"{field}"' in doc

    def test_finding_levels(self, doc: str) -> None:
        assert "真缺口" in doc
        assert "细化" in doc
        assert "核对通过" in doc

    def test_checklist_single_source(self, doc: str) -> None:
        # 五视角清单的单一定义源是 references/checklist.md，由父读盘后注入。
        assert "references/checklist.md" in doc

    def test_lens_enum_matches_checklist_headings(self, doc: str) -> None:
        checklist = _read(SKILL_DIR / "references" / "checklist.md")
        checklist_headings = [line for line in checklist.splitlines() if line.startswith("## ")]
        for lens in (
            "验收矩阵完备性",
            "可测性拆分可实现性 + 触发时序",
            "部署/执行路径真实性",
            "契约与边界",
            "命令与命名可追溯",
        ):
            assert f'"{lens}"' in doc, lens
            assert any(lens in heading for heading in checklist_headings), lens

    def test_lens_item_fields_and_verdict_enum(self, doc: str) -> None:
        for field in ("lens", "verdict", "findingIds", "converged", "summary"):
            assert f'"{field}"' in doc, field
        assert "核对通过" in doc
        assert "有发现" in doc


class TestSkillStructure:
    """A5: the rewritten SKILL.md carries the orchestration contract."""

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

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_sections(self, skill: str, section: str) -> None:
        assert section in skill


class TestPinnedLiterals:
    """A5 (continued): progress lines, degrade prompt and preflight markers."""

    @pytest.fixture(scope="class")
    def skill(self) -> str:
        return _read(SKILL_DIR / "SKILL.md")

    def test_progress_line_pinned(self, skill: str) -> None:
        assert PROGRESS_LINE in skill

    def test_converged_line_pinned(self, skill: str) -> None:
        assert CONVERGED_LINE in skill

    def test_degrade_prompt_pinned(self, skill: str) -> None:
        assert DEGRADE_PROMPT in skill
        assert DEGRADE_PROMPT_2 in skill

    def test_convergence_cap_is_four(self, skill: str) -> None:
        assert "默认上限 4 轮" in skill

    def test_preflight_markers(self, skill: str) -> None:
        assert "spec-reviewer" in skill
        assert "fail-closed" in skill
        assert "agentOverrides" in skill


class TestReportTemplate:
    """A6: the round-report / state-index template carries every field."""

    @pytest.fixture(scope="class")
    def template(self) -> str:
        return _read(SKILL_DIR / "references" / "report-template.md")

    def test_template_file_exists(self) -> None:
        assert (SKILL_DIR / "references" / "report-template.md").is_file()

    @pytest.mark.parametrize(
        "field",
        (
            "Round k",
            "Reviewer: spec-reviewer",
            "Drafter:",
            "Reviewed spec sha256:",
            "Mode:",
            "真缺口",
            "细化",
            "核对通过",
            "## 修订摘要",
            "当前状态",
            "Open findings",
            "已拒绝裁定",
        ),
    )
    def test_template_fields(self, template: str, field: str) -> None:
        assert field in template, field

    def test_template_pins_hash_command(self, template: str) -> None:
        assert "sha256sum" in template
        assert "不写回被计算的文件自身" in template

    def test_template_pins_mode_enum(self, template: str) -> None:
        assert "`cross-model (preflight verified)`" in template
        assert "`cross-model (post-hoc same-physical)`" in template
        assert "`degraded (same-model, user-confirmed)`" in template

    def test_template_has_verbatim_json_appendix(self, template: str) -> None:
        assert "verbatim" in template

    def test_template_pins_progress_lines(self, template: str) -> None:
        assert PROGRESS_LINE in template
        assert CONVERGED_LINE in template


class TestEdgeCaseCoverage:
    """A7: every failure branch the spec names must be documented."""

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
            "fail-closed",
            "未注册",
            "modelScope",
            "超时",
            "schema",
            "重建",
            "hash 不匹配",
            "Drafted:",
            "降级复核",
            "轮次上限",
            "复核零发现",
            "已收敛",
            "(unresolved)",
        ),
    )
    def test_edge_case_documented(self, edge: str, marker: str) -> None:
        assert marker in edge, marker


class TestFlowStep4:
    """A8: step 4 gates on the automated cross-review before the ⏸ pause."""

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

    def test_auto_entry_documented(self, flow: str) -> None:
        assert "自动进入" in flow


class TestNoHardcodedModels:
    """A3: skill docs and the agent profile must not name concrete models.

    Portable by design: a literal blacklist, no shape regex, and no
    machine-private config reference (same style as #250 R2-D3).
    """

    def _docs(self) -> list[tuple[str, str]]:
        docs: list[tuple[str, str]] = [("github-issue-driven/SKILL.md", _read(FLOW))]
        for path in sorted(SKILL_DIR.rglob("*.md")):
            docs.append((str(path.relative_to(_REPO_ROOT)), _read(path)))
        for path in sorted(AGENTS_DIR.rglob("*.md")):
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
    """A9: the pi package README registers the skill and mentions the profile."""

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

    def test_spec_reviewer_profile_mentioned(self, readme: str) -> None:
        assert "spec-reviewer" in readme
