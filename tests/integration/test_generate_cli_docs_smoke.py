"""Smoke tests for the CLI reference generator against the real app (A10).

Unlike the unit tests (which use a synthetic click tree), these exercise the
actual ``zima.cli`` Typer app end-to-end: key commands exist in the extracted
tree, and the committed ``docs/cli-descriptions.yaml`` catalog covers the
extracted paths exactly (bidirectional set equality).
"""

from pathlib import Path

from typer.main import get_command

from scripts.generate_cli_docs import (
    extract_commands,
    load_descriptions,
    validate_descriptions,
)
from zima.cli import app

REPO = Path(__file__).resolve().parents[2]


def test_real_tree_key_commands_present():
    paths = {c.path for c in extract_commands(get_command(app))}
    for key in (
        "zima pjob actions add",
        "zima pjob run",
        "zima daemon start",
        "zima webhook-server",
        "zima quickstart",
    ):
        assert key in paths, key


def test_catalog_matches_extracted_tree_exactly():
    paths = {c.path for c in extract_commands(get_command(app))}
    catalog = load_descriptions(REPO / "docs" / "cli-descriptions.yaml")
    validate_descriptions(paths, catalog)  # raises on any mismatch
