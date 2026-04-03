"""Variable configuration model for workflow variable values."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from zima.models.base import BaseConfig, Metadata
from zima.utils import generate_timestamp, validate_code


@dataclass
class VariableConfig(BaseConfig):
    """
    Variable configuration model.

    Provides values for Workflow templates, enabling separation of
    template structure from data content.

    Attributes:
        for_workflow: Reference to the workflow this variable set is for
        values: Variable values dictionary
    """

    kind: str = "Variable"
    for_workflow: str = ""  # workflow code reference
    values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Post-initialization processing."""
        super().__post_init__()
        # Ensure values is a dict
        if self.values is None:
            self.values = {}

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        for_workflow: str = "",
        values: Optional[dict[str, Any]] = None,
        description: str = "",
    ) -> VariableConfig:
        """
        Factory method to create a new VariableConfig.

        Args:
            code: Unique variable code
            name: Display name
            for_workflow: Target workflow code (optional)
            values: Variable values dictionary
            description: Optional description

        Returns:
            New VariableConfig instance
        """
        now = generate_timestamp()

        return cls(
            metadata=Metadata(code=code, name=name, description=description),
            for_workflow=for_workflow,
            values=values or {},
            created_at=now,
            updated_at=now,
        )

    def validate(self) -> list[str]:
        """
        Validate variable configuration.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Validate base fields
        if not self.metadata.code:
            errors.append("metadata.code is required")
        elif not validate_code(self.metadata.code):
            errors.append(f"metadata.code '{self.metadata.code}' has invalid format")

        if not self.metadata.name:
            errors.append("metadata.name is required")

        # Validate for_workflow if provided
        if self.for_workflow and not validate_code(self.for_workflow):
            errors.append(f"spec.forWorkflow '{self.for_workflow}' has invalid format")

        # Validate values is a dict
        if self.values is not None and not isinstance(self.values, dict):
            errors.append("spec.values must be a dictionary")

        return errors

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.validate()) == 0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": {
                "forWorkflow": self.for_workflow,
                "values": self.values,
            },
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VariableConfig:
        """Create from dictionary."""
        spec = data.get("spec", {})

        return cls(
            api_version=data.get("apiVersion", "zima.io/v1"),
            kind=data.get("kind", "Variable"),
            metadata=Metadata.from_dict(data.get("metadata", {})),
            for_workflow=spec.get("forWorkflow", ""),
            values=spec.get("values", {}),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )

    @classmethod
    def from_yaml_file(cls, path: Path) -> VariableConfig:
        """Load from YAML file."""
        import yaml

        if not path.exists():
            raise FileNotFoundError(f"Variable config not found: {path}")

        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return cls.from_dict(data or {})

    def get_value(self, path: str, default: Any = None) -> Any:
        """
        Get value by dot-notation path.

        Args:
            path: Dot-notation path (e.g., "task.name")
            default: Default value if not found

        Returns:
            Value at path or default
        """
        keys = path.split(".")
        current = self.values

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    def set_value(self, path: str, value: Any) -> None:
        """
        Set value by dot-notation path.

        Args:
            path: Dot-notation path (e.g., "task.name")
            value: Value to set
        """
        keys = path.split(".")
        current = self.values

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value
        self.update_timestamp()

    def has_value(self, path: str) -> bool:
        """Check if value exists at path."""
        return self.get_value(path) is not None

    def merge_values(self, other: dict[str, Any]) -> None:
        """
        Merge another values dict into current values.

        Args:
            other: Dictionary to merge
        """
        self._deep_merge(self.values, other)
        self.update_timestamp()

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def flatten_values(self) -> dict[str, Any]:
        """
        Flatten nested values to dot-notation keys.

        Returns:
            Flattened dictionary
        """
        result = {}
        self._flatten_dict(self.values, "", result)
        return result

    def _flatten_dict(self, data: dict, prefix: str, result: dict) -> None:
        """Helper for flattening dictionary."""
        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._flatten_dict(value, new_key, result)
            else:
                result[new_key] = value

    def list_paths(self) -> list[str]:
        """Get list of all value paths (dot-notation)."""
        return list(self.flatten_values().keys())

    def clear_values(self) -> None:
        """Clear all values."""
        self.values = {}
        self.update_timestamp()

    def update_for_workflow(self, workflow_code: str) -> None:
        """Update the target workflow reference."""
        self.for_workflow = workflow_code
        self.update_timestamp()
