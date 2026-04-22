"""Generic YAML serialization utilities for dataclasses."""

from __future__ import annotations

import re
from dataclasses import MISSING, fields, is_dataclass
from typing import Union, get_args, get_origin


def convert_to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split("_")
    return components[0] + "".join(x.capitalize() for x in components[1:])


def convert_to_snake_case(camel_str: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", camel_str)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _unwrap_optional(t):
    """Return the inner type if t is Optional[X], else None."""
    origin = get_origin(t)
    if origin is Union:
        args = get_args(t)
        if len(args) == 2 and type(None) in args:
            return args[0] if args[1] is type(None) else args[1]
    return None


def _is_list_of_dataclasses(t):
    """Check if t is list[X] or Optional[list[X]] where X is a dataclass."""
    inner = _unwrap_optional(t)
    if inner is not None:
        t = inner
    origin = get_origin(t)
    if origin is list:
        args = get_args(t)
        if args and is_dataclass(args[0]):
            return True
    return False


def _get_item_type_from_list(t):
    """Extract the dataclass type from list[X] or Optional[list[X]]."""
    inner = _unwrap_optional(t)
    if inner is not None:
        t = inner
    args = get_args(t)
    return args[0] if args else None


# Fields that are part of BaseConfig and should NOT go into spec dict
BASE_CONFIG_FIELDS = {"api_version", "kind", "metadata", "created_at", "updated_at"}


class YamlSerializable:
    """Mixin class that provides to_dict/from_dict for dataclasses."""

    FIELD_ALIASES: dict[str, str] = {}

    def to_dict(self) -> dict:
        """Serialize to dictionary with automatic case conversion."""
        return serialize(self, self.FIELD_ALIASES)

    @classmethod
    def from_dict(cls, data: dict):
        """Deserialize from dictionary with automatic case conversion."""
        return deserialize(cls, data, cls.FIELD_ALIASES)


def serialize(obj, aliases=None) -> dict:
    """Serialize a dataclass instance to a dictionary.

    For each field:
    - Use alias override if present, else auto snake_to_camel.
    - Recursively serialize nested dataclasses (call their to_dict()).
    - Recursively serialize lists of dataclasses.
    """
    if aliases is None:
        aliases = getattr(obj, "FIELD_ALIASES", {}) if hasattr(obj, "FIELD_ALIASES") else {}

    result = {}
    for f in fields(obj):
        key = aliases.get(f.name, convert_to_camel_case(f.name))
        value = getattr(obj, f.name)

        if is_dataclass(f.type):
            if value is not None:
                value = value.to_dict()
        elif _is_list_of_dataclasses(f.type):
            if value is not None:
                item_type = _get_item_type_from_list(f.type)
                if item_type is not None and hasattr(item_type, "to_dict"):
                    value = [v.to_dict() if hasattr(v, "to_dict") else v for v in value]

        result[key] = value

    return result


def deserialize(cls, data, aliases=None):
    """Deserialize a dictionary to a dataclass instance.

    For each field:
    - Match YAML key: aliases override first, else auto camel_to_snake.
    - Recursively deserialize nested dataclasses.
    - Recursively deserialize lists of dataclasses.
    - Use field defaults for missing values.
    """
    if aliases is None:
        aliases = getattr(cls, "FIELD_ALIASES", {}) if hasattr(cls, "FIELD_ALIASES") else {}

    kwargs = {}
    for f in fields(cls):
        # Determine the expected key in the input data
        expected_key = aliases.get(f.name, convert_to_camel_case(f.name))

        if expected_key in data:
            value = data[expected_key]
        else:
            # Try reverse alias lookup or camel_to_snake fallback
            snake_key = convert_to_snake_case(expected_key)
            if snake_key in data:
                value = data[snake_key]
            elif f.name in data:
                value = data[f.name]
            else:
                # Use default
                if f.default is not MISSING:
                    value = f.default
                elif f.default_factory is not MISSING:
                    value = f.default_factory()
                else:
                    value = None
                kwargs[f.name] = value
                continue

        # Recursively deserialize nested dataclasses
        if is_dataclass(f.type):
            inner = _unwrap_optional(f.type)
            target_cls = inner if inner is not None else f.type
            if value is not None and is_dataclass(target_cls):
                if isinstance(value, dict):
                    value = deserialize(target_cls, value)
        elif _is_list_of_dataclasses(f.type):
            item_type = _get_item_type_from_list(f.type)
            if item_type is not None and value is not None:
                value = [deserialize(item_type, v) if isinstance(v, dict) else v for v in value]

        kwargs[f.name] = value

    return cls(**kwargs)


def serialize_spec(obj, aliases=None) -> dict:
    """Serialize only non-BaseConfig fields into a spec dict.

    Iterates over fields(obj), skips BASE_CONFIG_FIELDS, and uses the same
    mapping/recursion logic as serialize.
    """
    if aliases is None:
        aliases = getattr(obj, "FIELD_ALIASES", {}) if hasattr(obj, "FIELD_ALIASES") else {}

    result = {}
    for f in fields(obj):
        if f.name in BASE_CONFIG_FIELDS:
            continue

        key = aliases.get(f.name, convert_to_camel_case(f.name))
        value = getattr(obj, f.name)

        if is_dataclass(f.type):
            if value is not None:
                value = value.to_dict()
        elif _is_list_of_dataclasses(f.type):
            if value is not None:
                item_type = _get_item_type_from_list(f.type)
                if item_type is not None and hasattr(item_type, "to_dict"):
                    value = [v.to_dict() if hasattr(v, "to_dict") else v for v in value]

        result[key] = value

    return result


def deserialize_spec(cls, spec_data, aliases=None) -> dict:
    """Deserialize spec fields from a dict into kwargs dict.

    Iterates over fields(cls), skips BASE_CONFIG_FIELDS, and uses the same
    mapping/recursion logic as deserialize. Returns a kwargs dict suitable
    for passing to the class constructor.
    """
    if aliases is None:
        aliases = getattr(cls, "FIELD_ALIASES", {}) if hasattr(cls, "FIELD_ALIASES") else {}

    kwargs = {}
    for f in fields(cls):
        if f.name in BASE_CONFIG_FIELDS:
            continue

        expected_key = aliases.get(f.name, convert_to_camel_case(f.name))

        if expected_key in spec_data:
            value = spec_data[expected_key]
        else:
            snake_key = convert_to_snake_case(expected_key)
            if snake_key in spec_data:
                value = spec_data[snake_key]
            elif f.name in spec_data:
                value = spec_data[f.name]
            else:
                if f.default is not MISSING:
                    value = f.default
                elif f.default_factory is not MISSING:
                    value = f.default_factory()
                else:
                    value = None
                kwargs[f.name] = value
                continue

        # Recursively deserialize nested dataclasses
        if is_dataclass(f.type):
            inner = _unwrap_optional(f.type)
            target_cls = inner if inner is not None else f.type
            if value is not None and is_dataclass(target_cls):
                if isinstance(value, dict):
                    value = deserialize(target_cls, value)
        elif _is_list_of_dataclasses(f.type):
            item_type = _get_item_type_from_list(f.type)
            if item_type is not None and value is not None:
                value = [deserialize(item_type, v) if isinstance(v, dict) else v for v in value]

        kwargs[f.name] = value

    return kwargs


def omit_empty(data: dict) -> dict:
    """Remove entries with None, '', [], or {}."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}
