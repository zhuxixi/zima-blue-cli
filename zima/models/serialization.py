"""Generic YAML serialization utilities for dataclasses."""

from __future__ import annotations

import re
import types
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
    """Return the inner type if t is Optional[X] or X | None, else None."""
    origin = get_origin(t)
    if origin is Union or origin is types.UnionType:
        args = get_args(t)
        if len(args) == 2 and type(None) in args:
            return args[0] if args[1] is type(None) else args[1]
    return None


def _resolve_type(t, field_name, cls=None):
    """Resolve a type annotation that may be a string (from PEP 563)."""
    if isinstance(t, str) and cls is not None:
        try:
            import inspect

            t = inspect.get_annotations(cls, eval_str=True).get(field_name, t)
        except Exception:
            pass
    return t


def _is_list_of_dataclasses(t, cls=None, field_name=None):
    """Check if t is list[X] or Optional[list[X]] where X is a dataclass."""
    t = _resolve_type(t, field_name, cls)
    inner = _unwrap_optional(t)
    if inner is not None:
        t = inner
    origin = get_origin(t)
    if origin is list:
        args = get_args(t)
        if args and is_dataclass(args[0]):
            return True
    return False


def _get_item_type_from_list(t, cls=None, field_name=None):
    """Extract the dataclass type from list[X] or Optional[list[X]]."""
    t = _resolve_type(t, field_name, cls)
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

    Args:
        obj: Dataclass instance to serialize.
        aliases: Optional dict mapping field names to YAML keys. Missing fields
            are auto-converted from snake_case to camelCase.

    Returns:
        Dictionary with camelCase keys and recursively serialized values.
    """
    if aliases is None:
        aliases = getattr(obj, "FIELD_ALIASES", {}) if hasattr(obj, "FIELD_ALIASES") else {}

    cls = type(obj)
    result = {}
    for f in fields(obj):
        key = aliases.get(f.name, convert_to_camel_case(f.name))
        value = getattr(obj, f.name)
        resolved_type = _resolve_type(f.type, f.name, cls)

        # Unwrap Optional before checking is_dataclass
        inner = _unwrap_optional(resolved_type)
        if inner is not None:
            resolved_type = inner

        if is_dataclass(resolved_type):
            if value is not None:
                value = value.to_dict()
        elif _is_list_of_dataclasses(f.type, cls, f.name):
            if value is not None:
                item_type = _get_item_type_from_list(f.type, cls, f.name)
                if item_type is not None and hasattr(item_type, "to_dict"):
                    value = [v.to_dict() if hasattr(v, "to_dict") else v for v in value]

        result[key] = value

    return result


def deserialize(cls, data, aliases=None):
    """Deserialize a dictionary to a dataclass instance.

    Args:
        cls: Dataclass type to instantiate.
        data: Dictionary with camelCase keys.
        aliases: Optional dict mapping field names to YAML keys. Missing fields
            are auto-converted from snake_case to camelCase.

    Returns:
        Instance of ``cls`` with fields populated from ``data``.

    Raises:
        TypeError: If a nested value or list item has the wrong type.
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

        resolved_type = _resolve_type(f.type, f.name, cls)
        inner = _unwrap_optional(resolved_type)
        if inner is not None:
            resolved_type = inner

        # Recursively deserialize nested dataclasses via their from_dict()
        if is_dataclass(resolved_type):
            if value is not None:
                if isinstance(value, resolved_type):
                    pass  # already the right type
                elif isinstance(value, dict):
                    if hasattr(resolved_type, "from_dict"):
                        value = resolved_type.from_dict(value)
                    else:
                        value = deserialize(resolved_type, value)
                else:
                    raise TypeError(
                        f"Expected dict or {resolved_type.__name__} for field '{f.name}', "
                        f"got {type(value).__name__}"
                    )
        elif _is_list_of_dataclasses(f.type, cls, f.name):
            item_type = _get_item_type_from_list(f.type, cls, f.name)
            if item_type is not None and value is not None:
                items = []
                for v in value:
                    if isinstance(v, item_type):
                        items.append(v)
                    elif hasattr(item_type, "from_dict"):
                        items.append(item_type.from_dict(v))
                    else:
                        items.append(deserialize(item_type, v))
                value = items

        kwargs[f.name] = value

    return cls(**kwargs)


def serialize_spec(obj, aliases=None) -> dict:
    """Serialize only non-BaseConfig fields into a spec dict.

    Skips ``BASE_CONFIG_FIELDS`` (``apiVersion``, ``kind``, ``metadata``,
    ``createdAt``, ``updatedAt``) and applies the same mapping/recursion
    logic as :func:`serialize`.

    Args:
        obj: Dataclass instance to serialize.
        aliases: Optional dict mapping field names to YAML keys.

    Returns:
        Dictionary with spec fields only, using camelCase keys.
    """
    if aliases is None:
        aliases = getattr(obj, "FIELD_ALIASES", {}) if hasattr(obj, "FIELD_ALIASES") else {}

    cls = type(obj)
    result = {}
    for f in fields(obj):
        if f.name in BASE_CONFIG_FIELDS:
            continue

        key = aliases.get(f.name, convert_to_camel_case(f.name))
        value = getattr(obj, f.name)
        resolved_type = _resolve_type(f.type, f.name, cls)

        # Unwrap Optional before checking is_dataclass
        inner = _unwrap_optional(resolved_type)
        if inner is not None:
            resolved_type = inner

        if is_dataclass(resolved_type):
            if value is not None:
                value = value.to_dict()
        elif _is_list_of_dataclasses(f.type, cls, f.name):
            if value is not None:
                item_type = _get_item_type_from_list(f.type, cls, f.name)
                if item_type is not None and hasattr(item_type, "to_dict"):
                    value = [v.to_dict() if hasattr(v, "to_dict") else v for v in value]

        result[key] = value

    return result


def deserialize_spec(cls, spec_data, aliases=None) -> dict:
    """Deserialize spec fields from a dict into kwargs dict.

    Skips ``BASE_CONFIG_FIELDS`` and applies the same mapping/recursion
    logic as :func:`deserialize`.

    Args:
        cls: Dataclass type to instantiate.
        spec_data: Dictionary with spec data (camelCase keys).
        aliases: Optional dict mapping field names to YAML keys.

    Returns:
        kwargs dict suitable for passing to the class constructor.

    Raises:
        TypeError: If a nested value or list item has the wrong type.
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

        resolved_type = _resolve_type(f.type, f.name, cls)
        inner = _unwrap_optional(resolved_type)
        if inner is not None:
            resolved_type = inner

        # Recursively deserialize nested dataclasses via their from_dict()
        if is_dataclass(resolved_type):
            if value is not None:
                if isinstance(value, resolved_type):
                    pass  # already the right type
                elif isinstance(value, dict):
                    if hasattr(resolved_type, "from_dict"):
                        value = resolved_type.from_dict(value)
                    else:
                        value = deserialize(resolved_type, value)
                else:
                    raise TypeError(
                        f"Expected dict or {resolved_type.__name__} for field '{f.name}', "
                        f"got {type(value).__name__}"
                    )
        elif _is_list_of_dataclasses(f.type, cls, f.name):
            item_type = _get_item_type_from_list(f.type, cls, f.name)
            if item_type is not None and value is not None:
                items = []
                for v in value:
                    if isinstance(v, item_type):
                        items.append(v)
                    elif hasattr(item_type, "from_dict"):
                        items.append(item_type.from_dict(v))
                    else:
                        items.append(deserialize(item_type, v))
                value = items

        kwargs[f.name] = value

    return kwargs


def omit_empty(data: dict) -> dict:
    """Remove entries with falsy sentinel values.

    Removes entries where the value is exactly ``None``, ``""``, ``[]``,
    or ``{}``. Preserves ``0`` and ``False`` since they are meaningful.

    Args:
        data: Dictionary to filter.

    Returns:
        Dictionary with sentinel-empty entries removed.
    """
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}
