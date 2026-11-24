"""Contract gate for the `session-finalize` skill (issue #279).

Locks the documentation contracts: frontmatter, four-phase orchestration,
ordering of the two jfox skills, idempotency, failure branches, degradation
prompts, and registry entries. Runtime behaviour is covered by U1–U5.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL = _REPO_ROOT / "pi" / "session-finalize" / "SKILL.md"
SCRIPT = _REPO_ROOT / "pi" / "session-finalize" / "scripts" / "session_journey.py"
README = _REPO_ROOT / "pi" / "README.md"
CHANGELOG = _REPO_ROOT / "CHANGELOG.md"

BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn", "/home/elling")

REQUIRED_SECTIONS = (
    "## 何时使用",
    "## 前置检查（第 0 段）",
    "## 第 1 段：旅程回放",
    "## 第 2 段：主线判定",
    "## 第 3 段：执行沉淀",
    "## 第 4 段：收尾展示",
    "## 幂等与重复触发",
    "## 失败与降级",
)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing contract document: {path}"
    return path.read_text(encoding="utf-8")


def test_frontmatter_declares_name_and_description():
    text = _text(SKILL)
    assert text.startswith("---\n")
    head = text.split("---\n", 2)[1]
    assert "name: session-finalize" in head
    assert "description:" in head
    assert "finalize" in head and "会话收尾" in head


def test_required_sections_present():
    text = _text(SKILL)
    for section in REQUIRED_SECTIONS:
        assert section in text, f"missing section: {section}"


def test_jfox_skills_are_named_in_order():
    text = _text(SKILL)
    permanent = text.find("jfox-session-to-permanent")
    summary = text.find("jfox-session-summary")
    assert permanent != -1 and summary != -1
    assert permanent < summary


def test_state_and_degradation_tokens():
    text = _text(SKILL)
    for token in ("PI_SESSION_FILE", "session_file", "--include-archived", "--session-path"):
        assert token in text
    assert "旅程回放降级：未找到会话文件" in text


def test_failure_branches_are_documented():
    text = _text(SKILL)
    assert "permanent 任一写入失败" in text and "不写 summary" in text
    assert "全部跳过" in text and "不等于失败" in text
    assert "不重试" in text and "不静默" in text


def test_no_hardcoded_models_or_machine_paths():
    text = _text(SKILL)
    for banned in BANNED_LITERALS:
        assert banned not in text


def test_readme_and_changelog_register_the_skill():
    assert "`session-finalize`" in _text(README)
    unreleased = _text(CHANGELOG).split("## [Unreleased]", 1)[1].split("## [", 1)[0]
    assert "session-finalize" in unreleased


def test_script_exists():
    assert SCRIPT.is_file()
