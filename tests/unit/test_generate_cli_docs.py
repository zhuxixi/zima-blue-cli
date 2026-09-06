"""Unit tests for scripts.generate_cli_docs extraction core (A1)."""

import click
import pytest

from scripts.generate_cli_docs import extract_commands, normalize_parameter


def _build_tree() -> click.Group:
    """Synthetic click tree: root group + one leaf with option/flag/multiple/argument."""

    @click.group()
    def cli():
        """Root group."""

    @cli.command()
    @click.option("--model", "-m", default="kimi", help="Model name")
    @click.option("--yolo/--no-yolo", default=False)
    @click.option("--label", "-l", multiple=True)
    @click.argument("code")
    def create(model, yolo, label, code):
        """Create a thing."""

    return cli


def test_extract_includes_root_group_and_leaf():
    paths = [c.path for c in extract_commands(_build_tree(), "zima")]
    assert paths == ["zima", "zima create"]


def test_normalize_option_defaults_and_flag():
    cmd = _build_tree().commands["create"]
    by_name = {p.name: p for p in map(normalize_parameter, cmd.params)}
    assert by_name["model"].default == "kimi"
    assert by_name["model"].syntax == "--model, -m"
    assert by_name["yolo"].is_flag and by_name["yolo"].syntax == "--yolo / --no-yolo"
    assert by_name["label"].multiple is True
    assert by_name["code"].kind == "argument" and by_name["code"].required


def test_extract_no_side_effects():
    # extraction never invokes callbacks: a raising callback proves it
    import click as _c

    @_c.group()
    def cli2():
        """Root."""

    @cli2.command()
    def boom2():
        raise RuntimeError("callback must not run")

    cmds = extract_commands(cli2, "zima")
    assert any(c.path == "zima boom2" for c in cmds)  # no exception raised


def test_normalize_missing_default_renders_dash():
    """None / Sentinel defaults must normalize to the MISSING_VALUE dash."""

    @click.command()
    @click.option("--name", "-n", help="No default")
    def cmd(name):
        """Leaf."""

    by_name = {p.name: p for p in map(normalize_parameter, cmd.params)}
    assert by_name["name"].default == "—"


def test_choices_tuple_normalized():
    @click.command()
    @click.option("--fmt", "-f", type=click.Choice(["yaml", "json"]), default="yaml")
    def cmd(fmt):
        """Leaf."""

    by_name = {p.name: p for p in map(normalize_parameter, cmd.params)}
    assert by_name["fmt"].choices == ("yaml", "json")


def test_usage_line_composition():
    commands = {c.path: c for c in extract_commands(_build_tree(), "zima")}
    leaf = commands["zima create"]
    assert leaf.usage == "zima create [OPTIONS] CODE"
    root = commands["zima"]
    assert root.is_group is True
    # ported jfox logic: [OPTIONS] appears only when the command declares its own options
    assert root.usage == "zima COMMAND [ARGS]..."


def test_normalized_records_are_frozen():
    records = extract_commands(_build_tree(), "zima")
    with pytest.raises(Exception):
        records[0].path = "mutated"
