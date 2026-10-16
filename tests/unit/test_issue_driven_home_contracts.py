"""Documentation contracts for the issue-driven archive-home migration (issue #259).

These tests pin the documentation wording for relocating the issue-driven
archive home from ``~/.claude`` to ``~/.github-issue-driven``:

  1. ``pi/**/*.md`` must not reference the old home ``~/.claude``.
  2. The three SKILL.md files must document the new home.
  3. ``pi/github-issue-driven/SKILL.md`` must document the
     ``GITHUB_ISSUE_DRIVEN_HOME`` env override.
  4. ``pi/README.md`` must document the new home.
  5. The old home literal is defined exactly once, inside the migration
     script ``scripts/migrate_issue_driven_home.py`` (zero hits in docs,
     at least one hit in the script).

They assert documentation contracts only. Historical documents outside
``pi/`` (``docs/superpowers/**``, ``tests/**`` fixtures) deliberately keep
the old literal and are out of scan scope.

Acceptance ID: A1. Written test-first: until the docs are migrated these
assertions fail on purpose, and every failure message names file and line
so the red run doubles as the Task-4 migration checklist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

_REPO_ROOT = Path(__file__).resolve().parents[2]
PI_DIR = _REPO_ROOT / "pi"

OLD_HOME = "~/.claude"
NEW_HOME = "~/.github-issue-driven"
ENV_OVERRIDE = "GITHUB_ISSUE_DRIVEN_HOME"

MIGRATION_SCRIPT = _REPO_ROOT / "scripts" / "migrate_issue_driven_home.py"
SKILL_DOCS = (
    PI_DIR / "github-issue-driven" / "SKILL.md",
    PI_DIR / "issue-research" / "SKILL.md",
    PI_DIR / "spec-cross-review" / "SKILL.md",
)
README = PI_DIR / "README.md"


def _pi_markdown_files() -> list[Path]:
    """Return every ``*.md`` under ``pi/`` via ``Path.rglob``.

    ripgrep is deliberately not used: ``pi/.ignore`` would shrink the scan
    surface and could fake a green run (spec §5 D5 records the measured
    difference). ``Path.rglob`` sees the real on-disk tree.
    """
    return sorted(PI_DIR.rglob("*.md"))


def _lines_containing(path: Path, needle: str) -> Iterator[tuple[int, str]]:
    """Yield ``(lineno, line)`` for every line of *path* containing *needle*."""
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            yield lineno, line


def _old_home_hits() -> list[str]:
    """Collect ``file:line`` pointers for every old-home reference in ``pi/**/*.md``."""
    hits: list[str] = []
    for md in _pi_markdown_files():
        for lineno, _line in _lines_containing(md, OLD_HOME):
            hits.append(f"{md.relative_to(_REPO_ROOT)}:{lineno}: contains {OLD_HOME}")
    return hits


def test_no_claude_home_reference() -> None:
    """No ``pi/**/*.md`` file may reference the old archive home ``~/.claude``."""
    hits = _old_home_hits()
    assert not hits, "old home still referenced by docs:\n" + "\n".join(hits)


def test_new_home_documented() -> None:
    """All three SKILL.md files must document the new archive home ``~/.github-issue-driven``."""
    missing = [
        str(skill.relative_to(_REPO_ROOT))
        for skill in SKILL_DOCS
        if NEW_HOME not in skill.read_text(encoding="utf-8")
    ]
    assert not missing, f"{NEW_HOME} not documented in: {', '.join(missing)}"


def test_env_override_documented() -> None:
    """``pi/github-issue-driven/SKILL.md`` must document the ``GITHUB_ISSUE_DRIVEN_HOME`` override."""
    skill = SKILL_DOCS[0]
    doc = skill.read_text(encoding="utf-8")
    assert ENV_OVERRIDE in doc, f"{skill.relative_to(_REPO_ROOT)}: does not document {ENV_OVERRIDE}"


def test_readme_documents_home() -> None:
    """``pi/README.md`` must document the new archive home ``~/.github-issue-driven``."""
    doc = README.read_text(encoding="utf-8")
    assert NEW_HOME in doc, f"{README.relative_to(_REPO_ROOT)}: does not document {NEW_HOME}"


def test_legacy_path_defined_once() -> None:
    """The old home literal lives only in the migration script.

    Two halves: ``pi/**/*.md`` has zero occurrences, and
    ``scripts/migrate_issue_driven_home.py`` keeps at least one occurrence
    (that script is the single definition site of the old path).
    """
    hits = _old_home_hits()
    assert (
        not hits
    ), "old home must be defined only in the migration script, found in docs:\n" + "\n".join(hits)
    script_hits = MIGRATION_SCRIPT.read_text(encoding="utf-8").count(OLD_HOME)
    assert (
        script_hits >= 1
    ), f"{MIGRATION_SCRIPT.relative_to(_REPO_ROOT)}: must reference {OLD_HOME} at least once, found {script_hits}"
