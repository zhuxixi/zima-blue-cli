"""Zima Blue CLI reference generator (structure from Typer command tree; descriptions from docs/cli-descriptions.yaml)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Mapping

import click
import yaml

# Enable direct execution (`python scripts/generate_cli_docs.py`, as the CI
# gate and subprocess tests do): make the repo root importable so the
# `scripts.*` sibling modules resolve and `zima` imports work.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

MISSING_VALUE = "—"


@dataclass(frozen=True)
class NormalizedParameter:
    """Serializable display representation of a Click parameter."""

    name: str
    kind: str
    syntax: str
    type_name: str
    required: bool
    default: str
    choices: tuple[str, ...]
    multiple: bool
    is_flag: bool


@dataclass(frozen=True)
class NormalizedCommand:
    """Serializable display representation of a CLI command."""

    path: str
    is_group: bool
    usage: str
    description_key: str
    parameters: tuple[NormalizedParameter, ...]


def _format_value(value: object) -> str:
    if value is None:
        return MISSING_VALUE
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, tuple)):
        return ", ".join(_format_value(item) for item in value)
    return str(value)


def _type_name(parameter: click.Parameter) -> str:
    if isinstance(parameter, click.Option) and parameter.is_flag:
        return "BOOL"
    type_name = getattr(parameter.type, "name", None)
    if type_name:
        return str(type_name).upper()
    return type(parameter.type).__name__.upper()


def _metavar(parameter: click.Parameter) -> str:
    metavar = getattr(parameter, "metavar", None)
    if metavar:
        return str(metavar)
    name = parameter.name or "value"
    return name.upper().replace("-", "_")


def _option_syntax(parameter: click.Option) -> str:
    opts = list(parameter.opts)
    secondary_opts = list(parameter.secondary_opts)
    if secondary_opts:
        primary = ", ".join(opts)
        secondary = ", ".join(secondary_opts)
        return f"{primary} / {secondary}"
    return ", ".join(opts)


def normalize_parameter(parameter: click.Parameter) -> NormalizedParameter:
    """Convert a Click argument or option to a renderer-independent record."""
    is_option = isinstance(parameter, click.Option)
    kind = "option" if is_option else "argument"
    if is_option:
        syntax = _option_syntax(parameter)
    else:
        syntax = _metavar(parameter)

    choices = tuple(str(choice) for choice in getattr(parameter.type, "choices", ()) or ())
    is_flag = bool(getattr(parameter, "is_flag", False))
    raw_default = getattr(parameter, "default", None)
    if raw_default is None or raw_default.__class__.__name__ == "Sentinel":
        default = MISSING_VALUE
    else:
        default = _format_value(raw_default)
    return NormalizedParameter(
        name=parameter.name or "value",
        kind=kind,
        syntax=syntax,
        type_name=_type_name(parameter),
        required=bool(parameter.required),
        default=default,
        choices=choices,
        multiple=bool(getattr(parameter, "multiple", False)),
        is_flag=is_flag,
    )


def _command_usage(command: click.Command, path: str) -> str:
    parameters = tuple(normalize_parameter(param) for param in command.params)
    options = any(parameter.kind == "option" for parameter in parameters)
    arguments = [
        parameter.syntax if parameter.required else f"[{parameter.syntax}]"
        for parameter in parameters
        if parameter.kind == "argument"
    ]
    suffix: list[str] = []
    if options:
        suffix.append("[OPTIONS]")
    suffix.extend(arguments)
    if isinstance(command, click.Group):
        suffix.extend(["COMMAND", "[ARGS]..."])
    return " ".join([path, *suffix])


def _walk_commands(command: click.Command, path: str) -> list[NormalizedCommand]:
    normalized = NormalizedCommand(
        path=path,
        is_group=isinstance(command, click.Group),
        usage=_command_usage(command, path),
        description_key=path,
        parameters=tuple(normalize_parameter(param) for param in command.params),
    )
    records = [normalized]
    if isinstance(command, click.Group):
        for name, child in sorted(command.commands.items()):
            records.extend(_walk_commands(child, f"{path} {name}"))
    return records


def extract_commands(
    root_command: click.Command, root_name: str = "zima"
) -> tuple[NormalizedCommand, ...]:
    """Extract the root and every nested command without invoking callbacks."""
    return tuple(_walk_commands(root_command, root_name))


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_descriptions(path: Path) -> dict[str, str]:
    """Load and validate the English command catalog."""
    try:
        with path.open(encoding="utf-8") as stream:
            data = yaml.load(stream, Loader=_UniqueKeyLoader)
    except ValueError:
        raise
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"failed to parse descriptions file {path}: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("commands"), dict):
        raise ValueError("descriptions file must contain a top-level 'commands' mapping")
    unsupported_top_level = sorted(set(data) - {"commands"})
    if unsupported_top_level:
        raise ValueError("unsupported top-level fields: " + ", ".join(unsupported_top_level))

    descriptions: dict[str, str] = {}
    for command_path, entry in data["commands"].items():
        if not isinstance(command_path, str):
            raise ValueError("command description keys must be strings")
        if not isinstance(entry, dict):
            raise ValueError(f"description entry must be a mapping: {command_path}")
        unsupported = sorted(set(entry) - {"description"})
        if unsupported:
            raise ValueError(f"unsupported fields for {command_path}: {', '.join(unsupported)}")
        description = entry.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"description must be a non-empty string: {command_path}")
        descriptions[command_path] = description.strip()
    return descriptions


def validate_descriptions(command_paths: Collection[str], descriptions: Mapping[str, str]) -> None:
    """Ensure the catalog exactly covers the extracted command paths."""
    expected = set(command_paths)
    actual = set(descriptions)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    errors = []
    if missing:
        errors.append(f"Missing English CLI descriptions: {', '.join(missing)}")
    if unknown:
        errors.append(f"Unknown CLI description entries: {', '.join(unknown)}")
    if errors:
        raise ValueError("\n".join(errors))


def main() -> int:
    """CLI entry point (extended by later tasks with catalog validation)."""
    parser = argparse.ArgumentParser(description="Generate the Zima Blue CLI reference")
    parser.add_argument("--output", type=Path, default=Path("docs/cli-reference.md"))
    parser.add_argument("--descriptions", type=Path, default=Path("docs/cli-descriptions.yaml"))
    parser.parse_args()
    raise SystemExit(
        "generate_cli_docs: rendering not implemented yet (catalog + renderer land in later tasks)"
    )


if __name__ == "__main__":
    raise SystemExit(main())
