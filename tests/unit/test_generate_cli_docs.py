"""Unit tests for scripts.generate_cli_docs extraction core (A1) + catalog (A2)."""

import click
import pytest

from scripts.generate_cli_docs import (
    extract_commands,
    load_descriptions,
    normalize_parameter,
    validate_descriptions,
)

VALID_CATALOG = """\
commands:
  "zima":
    description: "Zima Blue CLI."
  "zima pjob run":
    description: "Execute a PJob."
"""


def _write_catalog(tmp_path, text: str):
    path = tmp_path / "cli-descriptions.yaml"
    path.write_text(text, encoding="utf-8")
    return path


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


class TestLoadDescriptions:
    def test_happy_path_returns_exact_dict(self, tmp_path):
        path = _write_catalog(tmp_path, VALID_CATALOG)
        assert load_descriptions(path) == {
            "zima": "Zima Blue CLI.",
            "zima pjob run": "Execute a PJob.",
        }

    def test_descriptions_are_stripped(self, tmp_path):
        text = 'commands:\n  "zima":\n    description: "  padded  "\n'
        path = _write_catalog(tmp_path, text)
        assert load_descriptions(path) == {"zima": "padded"}

    def test_duplicate_keys_rejected(self, tmp_path):
        text = (
            "commands:\n"
            '  "zima":\n'
            '    description: "First."\n'
            '  "zima":\n'
            '    description: "Second."\n'
        )
        path = _write_catalog(tmp_path, text)
        with pytest.raises(ValueError, match="duplicate YAML key"):
            load_descriptions(path)

    def test_missing_commands_key_rejected(self, tmp_path):
        path = _write_catalog(tmp_path, "notcommands:\n  {}\n")
        with pytest.raises(ValueError, match="commands"):
            load_descriptions(path)

    def test_non_dict_top_level_rejected(self, tmp_path):
        path = _write_catalog(tmp_path, "- just\n- a list\n")
        with pytest.raises(ValueError, match="commands"):
            load_descriptions(path)

    def test_unsupported_top_level_field_rejected(self, tmp_path):
        path = _write_catalog(tmp_path, VALID_CATALOG + "extra: 1\n")
        with pytest.raises(ValueError, match="unsupported top-level fields"):
            load_descriptions(path)

    def test_non_string_key_rejected(self, tmp_path):
        path = _write_catalog(tmp_path, 'commands:\n  1:\n    description: "x"\n')
        with pytest.raises(ValueError, match="keys must be strings"):
            load_descriptions(path)

    def test_non_mapping_entry_rejected(self, tmp_path):
        path = _write_catalog(tmp_path, 'commands:\n  "zima": "just a string"\n')
        with pytest.raises(ValueError, match="must be a mapping"):
            load_descriptions(path)

    def test_unsupported_entry_field_rejected(self, tmp_path):
        text = "commands:\n" '  "zima":\n' '    description: "ok"\n' '    summary: "nope"\n'
        path = _write_catalog(tmp_path, text)
        with pytest.raises(ValueError, match="unsupported fields"):
            load_descriptions(path)

    def test_empty_description_rejected(self, tmp_path):
        path = _write_catalog(tmp_path, 'commands:\n  "zima":\n    description: ""\n')
        with pytest.raises(ValueError, match="non-empty"):
            load_descriptions(path)

    def test_whitespace_only_description_rejected(self, tmp_path):
        path = _write_catalog(tmp_path, 'commands:\n  "zima":\n    description: "   "\n')
        with pytest.raises(ValueError, match="non-empty"):
            load_descriptions(path)

    def test_missing_file_wrapped_as_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="failed to parse descriptions file"):
            load_descriptions(tmp_path / "nope.yaml")


class TestValidateDescriptions:
    def test_exact_match_passes(self):
        validate_descriptions(["zima", "zima pjob run"], {"zima": "a", "zima pjob run": "b"})

    def test_duplicate_paths_in_tree_are_fine(self):
        validate_descriptions(["zima", "zima"], {"zima": "a"})

    def test_missing_catalog_entry_reports_missing(self):
        with pytest.raises(ValueError, match="Missing English CLI descriptions"):
            validate_descriptions(["zima", "zima pjob run"], {"zima": "a"})

    def test_unknown_catalog_entry_reports_unknown(self):
        with pytest.raises(ValueError, match="Unknown CLI description entries"):
            validate_descriptions(["zima"], {"zima": "a", "zima ghost": "b"})

    def test_both_directions_listed_sorted(self):
        paths = ["zima b", "zima a", "zima c"]
        descriptions = {"zima d": "x", "zima e": "y", "zima a": "z"}
        with pytest.raises(ValueError) as excinfo:
            validate_descriptions(paths, descriptions)
        message = str(excinfo.value)
        assert "Missing English CLI descriptions: zima b, zima c" in message
        assert "Unknown CLI description entries: zima d, zima e" in message
