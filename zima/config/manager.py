"""Configuration manager - unified CRUD for all config types."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from zima.utils import (
    ensure_dir,
    generate_timestamp,
    get_config_dir,
    validate_code,
)


class ConfigManager:
    """
    Unified configuration manager for all Zima config types.

    Supports: agent, workflow, variable, env, pmg

    Example:
        >>> manager = ConfigManager()
        >>> manager.save_config("agent", "my-agent", {...})
        >>> config = manager.load_config("agent", "my-agent")
        >>> configs = manager.list_configs("agent")
    """

    # Supported configuration kinds
    KINDS = {"agent", "workflow", "variable", "env", "pmg", "pjob", "schedule"}

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize config manager.

        Args:
            config_dir: Custom config directory. If None, uses default.
        """
        self.config_dir = config_dir or get_config_dir()

    def _get_kind_dir(self, kind: str) -> Path:
        """
        Get directory for a specific config kind.

        Args:
            kind: Config kind (agent, workflow, etc.)

        Returns:
            Path to kind directory
        """
        if kind not in self.KINDS:
            raise ValueError(f"Unknown config kind: {kind}. Valid: {self.KINDS}")
        return ensure_dir(self.config_dir / f"{kind}s")

    def get_config_path(self, kind: str, code: str) -> Path:
        """
        Get full path to a config file.

        Args:
            kind: Config kind
            code: Config code

        Returns:
            Path to config file
        """
        return self._get_kind_dir(kind) / f"{code}.yaml"

    def config_exists(self, kind: str, code: str) -> bool:
        """
        Check if a config exists.

        Args:
            kind: Config kind
            code: Config code

        Returns:
            True if config exists
        """
        return self.get_config_path(kind, code).exists()

    def save_config(self, kind: str, code: str, data: dict) -> Path:
        """
        Save configuration to file.

        Automatically updates 'updatedAt' timestamp.

        Args:
            kind: Config kind
            code: Config code
            data: Configuration data dict

        Returns:
            Path to saved file

        Raises:
            ValueError: If kind is invalid or code format is wrong
        """
        if kind not in self.KINDS:
            raise ValueError(f"Unknown config kind: {kind}")

        if not validate_code(code):
            raise ValueError(f"Invalid code format: {code}")

        # Update timestamp
        data = data.copy()
        data["updatedAt"] = generate_timestamp()

        # Ensure createdAt is set for new configs
        if "createdAt" not in data or not data["createdAt"]:
            data["createdAt"] = data["updatedAt"]

        # Write to file
        config_path = self.get_config_path(kind, code)
        config_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

        return config_path

    def load_config(self, kind: str, code: str) -> dict:
        """
        Load configuration from file.

        Args:
            kind: Config kind
            code: Config code

        Returns:
            Configuration data dict

        Raises:
            FileNotFoundError: If config doesn't exist
        """
        config_path = self.get_config_path(kind, code)

        if not config_path.exists():
            raise FileNotFoundError(f"Config not found: {kind}/{code}")

        content = config_path.read_text(encoding="utf-8")
        return yaml.safe_load(content) or {}

    def delete_config(self, kind: str, code: str) -> bool:
        """
        Delete configuration file.

        Args:
            kind: Config kind
            code: Config code

        Returns:
            True if deleted, False if didn't exist
        """
        config_path = self.get_config_path(kind, code)

        if not config_path.exists():
            return False

        config_path.unlink()
        return True

    def list_configs(self, kind: str) -> list[dict]:
        """
        List all configurations of a kind.

        Args:
            kind: Config kind

        Returns:
            List of config data dicts
        """
        kind_dir = self._get_kind_dir(kind)
        configs = []

        if not kind_dir.exists():
            return configs

        for config_file in sorted(kind_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
                if data:
                    configs.append(data)
            except Exception:
                # Skip invalid files
                continue

        return configs

    def list_config_codes(self, kind: str) -> list[str]:
        """
        List all config codes of a kind.

        Args:
            kind: Config kind

        Returns:
            List of config codes
        """
        kind_dir = self._get_kind_dir(kind)

        if not kind_dir.exists():
            return []

        return sorted([f.stem for f in kind_dir.glob("*.yaml")])

    def copy_config(
        self, kind: str, from_code: str, to_code: str, new_name: Optional[str] = None
    ) -> bool:
        """
        Copy a configuration.

        Args:
            kind: Config kind
            from_code: Source config code
            to_code: Target config code
            new_name: New display name (optional)

        Returns:
            True if copied successfully

        Raises:
            FileNotFoundError: If source doesn't exist
            ValueError: If target already exists
        """
        # Load source
        source_data = self.load_config(kind, from_code)

        # Check target doesn't exist
        if self.config_exists(kind, to_code):
            raise ValueError(f"Target config already exists: {kind}/{to_code}")

        # Modify metadata
        source_data["metadata"] = source_data.get("metadata", {}).copy()
        source_data["metadata"]["code"] = to_code

        if new_name:
            source_data["metadata"]["name"] = new_name
        else:
            # Generate default name
            old_name = source_data["metadata"].get("name", from_code)
            source_data["metadata"]["name"] = f"{old_name} (Copy)"

        # Clear timestamps for new config
        source_data.pop("createdAt", None)
        source_data.pop("updatedAt", None)

        # Save
        self.save_config(kind, to_code, source_data)
        return True

    def get_config_summary(self, kind: str, code: str) -> Optional[dict]:
        """
        Get brief summary of a config.

        Args:
            kind: Config kind
            code: Config code

        Returns:
            Summary dict or None if not exists
        """
        try:
            data = self.load_config(kind, code)
            metadata = data.get("metadata", {})
            return {
                "code": metadata.get("code", code),
                "name": metadata.get("name", ""),
                "description": metadata.get("description", ""),
                "kind": kind,
                "updatedAt": data.get("updatedAt", ""),
            }
        except FileNotFoundError:
            return None
