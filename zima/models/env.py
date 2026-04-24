"""Environment configuration model with secret management."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from zima.models.base import BaseConfig, Metadata
from zima.utils import generate_timestamp, validate_code

# Valid secret sources
VALID_SECRET_SOURCES = {"env", "file", "cmd", "vault"}

# Valid agent types that can have env configs
VALID_ENV_FOR_TYPES = {"kimi", "claude"}


@dataclass
class SecretDef:
    """
    Secret definition for sensitive environment variables.

    Attributes:
        name: Environment variable name
        source: Source type (env, file, cmd, vault)
        key: For source=env: the source environment variable name
        path: For source=file/vault: the file path or vault path
        command: For source=cmd: the command to execute
        field: For source=vault: the field to extract from vault response
    """

    name: str
    source: str
    key: Optional[str] = None
    path: Optional[str] = None
    command: Optional[str] = None
    field: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "source": self.source,
        }
        if self.key:
            result["key"] = self.key
        if self.path:
            result["path"] = self.path
        if self.command:
            result["command"] = self.command
        if self.field:
            result["field"] = self.field
        return result

    @classmethod
    def from_dict(cls, data: dict) -> SecretDef:
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            source=data.get("source", ""),
            key=data.get("key"),
            path=data.get("path"),
            command=data.get("command"),
            field=data.get("field"),
        )

    def validate(self) -> list[str]:
        """Validate secret definition."""
        errors = []

        if not self.name:
            errors.append("Secret name is required")

        if not self.source:
            errors.append("Secret source is required")
        elif self.source not in VALID_SECRET_SOURCES:
            errors.append(f"Invalid secret source: {self.source}. Valid: {VALID_SECRET_SOURCES}")

        # Validate source-specific fields
        if self.source == "env" and not self.key:
            errors.append(f"Secret '{self.name}': source='env' requires 'key' field")

        if self.source == "file" and not self.path:
            errors.append(f"Secret '{self.name}': source='file' requires 'path' field")

        if self.source == "cmd" and not self.command:
            errors.append(f"Secret '{self.name}': source='cmd' requires 'command' field")

        if self.source == "vault":
            if not self.path:
                errors.append(f"Secret '{self.name}': source='vault' requires 'path' field")

        return errors

    def get_masked_value(self) -> str:
        """Get masked representation for display."""
        return f"<secret:{self.source}>"


class SecretResolver:
    """Resolver for secret values from various sources."""

    @staticmethod
    def resolve(secret: SecretDef) -> str:
        """
        Resolve secret value from its source.

        Args:
            secret: Secret definition

        Returns:
            Resolved secret value

        Raises:
            ValueError: If resolution fails
        """
        if secret.source == "env":
            return SecretResolver._resolve_env(secret)
        elif secret.source == "file":
            return SecretResolver._resolve_file(secret)
        elif secret.source == "cmd":
            return SecretResolver._resolve_cmd(secret)
        elif secret.source == "vault":
            return SecretResolver._resolve_vault(secret)
        else:
            raise ValueError(f"Unknown secret source: {secret.source}")

    @staticmethod
    def _resolve_env(secret: SecretDef) -> str:
        """Resolve from environment variable."""
        if not secret.key:
            raise ValueError(f"Secret '{secret.name}': 'key' is required for env source")

        value = os.environ.get(secret.key)
        if value is None:
            raise ValueError(f"Secret '{secret.name}': Environment variable '{secret.key}' not set")
        return value

    @staticmethod
    def _resolve_file(secret: SecretDef) -> str:
        """Resolve from file."""
        if not secret.path:
            raise ValueError(f"Secret '{secret.name}': 'path' is required for file source")

        file_path = Path(secret.path).expanduser()

        if not file_path.exists():
            raise ValueError(f"Secret '{secret.name}': File not found: {file_path}")

        try:
            content = file_path.read_text(encoding="utf-8").strip()
            return content
        except Exception as e:
            raise ValueError(f"Secret '{secret.name}': Failed to read file: {e}")

    @staticmethod
    def _resolve_cmd(secret: SecretDef) -> str:
        """Resolve from command output."""
        if not secret.command:
            raise ValueError(f"Secret '{secret.name}': 'command' is required for cmd source")

        try:
            result = subprocess.run(
                secret.command, shell=True, capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                raise ValueError(
                    f"Secret '{secret.name}': Command failed with exit code {result.returncode}: {result.stderr}"
                )

            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise ValueError(f"Secret '{secret.name}': Command timed out after 30s")
        except Exception as e:
            raise ValueError(f"Secret '{secret.name}': Failed to execute command: {e}")

    @staticmethod
    def _resolve_vault(secret: SecretDef) -> str:
        """Resolve from HashiCorp Vault."""
        # For now, vault is not fully implemented
        # This would require hvac library and vault connection
        raise ValueError(
            f"Secret '{secret.name}': Vault source not yet implemented. "
            "Please use env, file, or cmd source."
        )


@dataclass
class EnvConfig(BaseConfig):
    """
    Environment configuration model.

    Defines environment variables to inject when running an Agent.
    Supports both plain variables and secrets from various sources.

    Attributes:
        for_type: Target agent type (kimi/claude)
        variables: Plain environment variables (key-value pairs)
        secrets: Secret definitions (resolved at runtime)
        override_existing: Whether to override existing env vars
    """

    kind: str = "Env"
    SPEC_FIELD_ALIASES = {
        "for_type": "forType",
        "override_existing": "overrideExisting",
    }
    for_type: str = "kimi"
    variables: dict[str, str] = field(default_factory=dict)
    secrets: list[SecretDef] = field(default_factory=list)
    override_existing: bool = False

    def __post_init__(self):
        """Post-initialization processing."""
        super().__post_init__()
        # Ensure variables is a dict
        if self.variables is None:
            self.variables = {}
        # Ensure secrets is a list
        if self.secrets is None:
            self.secrets = []

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        for_type: str = "kimi",
        description: str = "",
        variables: Optional[dict[str, str]] = None,
        secrets: Optional[list[dict]] = None,
        override_existing: bool = False,
    ) -> EnvConfig:
        """
        Factory method to create a new EnvConfig.

        Args:
            code: Unique env code
            name: Display name
            for_type: Target agent type
            description: Optional description
            variables: Plain environment variables
            secrets: Secret definitions as dicts
            override_existing: Whether to override existing env vars

        Returns:
            New EnvConfig instance

        Raises:
            ValueError: If for_type is invalid
        """
        if for_type not in VALID_ENV_FOR_TYPES:
            raise ValueError(f"Invalid for_type: {for_type}. Valid: {VALID_ENV_FOR_TYPES}")

        # Convert secret dicts to SecretDef objects
        secret_defs = []
        if secrets:
            for secret_data in secrets:
                if isinstance(secret_data, dict):
                    secret_defs.append(SecretDef.from_dict(secret_data))
                elif isinstance(secret_data, SecretDef):
                    secret_defs.append(secret_data)

        now = generate_timestamp()

        return cls(
            metadata=Metadata(code=code, name=name, description=description),
            for_type=for_type,
            variables=variables or {},
            secrets=secret_defs,
            override_existing=override_existing,
            created_at=now,
            updated_at=now,
        )

    def validate(self) -> list[str]:
        """
        Validate env configuration.

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

        # Validate for_type
        if not self.for_type:
            errors.append("spec.forType is required")
        elif self.for_type not in VALID_ENV_FOR_TYPES:
            errors.append(
                f"spec.forType '{self.for_type}' is not valid. Valid: {VALID_ENV_FOR_TYPES}"
            )

        # Validate variables is a dict
        if self.variables is None:
            self.variables = {}
        elif not isinstance(self.variables, dict):
            errors.append("spec.variables must be a dictionary")

        # Validate secret definitions
        for secret in self.secrets:
            secret_errors = secret.validate()
            errors.extend(secret_errors)

        # Check for duplicate secret names
        secret_names = [s.name for s in self.secrets]
        if len(secret_names) != len(set(secret_names)):
            errors.append("Duplicate secret names found")

        # Check for conflicts between variables and secrets (only if variables is a dict)
        if isinstance(self.variables, dict):
            var_keys = set(self.variables.keys())
            secret_keys = set(secret_names)
            conflicts = var_keys & secret_keys
            if conflicts:
                errors.append(f"Keys conflict between variables and secrets: {conflicts}")

        return errors

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.validate()) == 0

    @classmethod
    def from_yaml_file(cls, path: Path) -> EnvConfig:
        """Load from YAML file."""
        import yaml

        if not path.exists():
            raise FileNotFoundError(f"Env config not found: {path}")

        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return cls.from_dict(data or {})

    # ========================================================================
    # Variable Management
    # ========================================================================

    def set_variable(self, key: str, value: str) -> None:
        """
        Set a plain environment variable.

        Args:
            key: Variable name
            value: Variable value
        """
        # Check if key exists in secrets
        if any(s.name == key for s in self.secrets):
            raise ValueError(f"Key '{key}' already exists as a secret. Use unset_secret first.")

        self.variables[key] = value
        self.update_timestamp()

    def unset_variable(self, key: str) -> bool:
        """
        Remove a plain environment variable.

        Args:
            key: Variable name

        Returns:
            True if removed, False if not found
        """
        if key in self.variables:
            del self.variables[key]
            self.update_timestamp()
            return True
        return False

    def get_variable(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a plain variable value."""
        return self.variables.get(key, default)

    def set_secret(
        self,
        name: str,
        source: str,
        key: Optional[str] = None,
        path: Optional[str] = None,
        command: Optional[str] = None,
        field: Optional[str] = None,
    ) -> None:
        """
        Set a secret environment variable.

        Args:
            name: Environment variable name
            source: Source type (env, file, cmd, vault)
            key: For env source: source variable name
            path: For file/vault source: file/vault path
            command: For cmd source: command string
            field: For vault source: field name
        """
        # Check if name exists in variables
        if name in self.variables:
            raise ValueError(
                f"Key '{name}' already exists as a variable. Use unset_variable first."
            )

        # Remove existing secret with same name
        self.secrets = [s for s in self.secrets if s.name != name]

        # Add new secret
        self.secrets.append(
            SecretDef(name=name, source=source, key=key, path=path, command=command, field=field)
        )
        self.update_timestamp()

    def unset_secret(self, name: str) -> bool:
        """
        Remove a secret.

        Args:
            name: Secret name

        Returns:
            True if removed, False if not found
        """
        original_len = len(self.secrets)
        self.secrets = [s for s in self.secrets if s.name != name]

        if len(self.secrets) < original_len:
            self.update_timestamp()
            return True
        return False

    def get_secret(self, name: str) -> Optional[SecretDef]:
        """Get a secret definition."""
        for secret in self.secrets:
            if secret.name == name:
                return secret
        return None

    # ========================================================================
    # Resolution and Export
    # ========================================================================

    def resolve_all(self, include_secrets: bool = True) -> dict[str, str]:
        """
        Resolve all environment variables.

        Args:
            include_secrets: Whether to resolve secret values

        Returns:
            Dictionary of all environment variables
        """
        result = dict(self.variables)

        if include_secrets:
            for secret in self.secrets:
                try:
                    result[secret.name] = SecretResolver.resolve(secret)
                except ValueError as e:
                    # If resolution fails, use placeholder
                    result[secret.name] = f"<error:{str(e)}>"
        else:
            # Include masked secrets
            for secret in self.secrets:
                result[secret.name] = secret.get_masked_value()

        return result

    def resolve_secret(self, name: str) -> str:
        """
        Resolve a single secret value.

        Args:
            name: Secret name

        Returns:
            Resolved value

        Raises:
            ValueError: If secret not found or resolution fails
        """
        secret = self.get_secret(name)
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        return SecretResolver.resolve(secret)

    def list_variables(self) -> list[str]:
        """List all plain variable keys."""
        return list(self.variables.keys())

    def list_secrets(self) -> list[str]:
        """List all secret names."""
        return [s.name for s in self.secrets]

    def list_all_keys(self) -> list[str]:
        """List all keys (variables and secrets)."""
        return self.list_variables() + self.list_secrets()

    # ========================================================================
    # Export Formats
    # ========================================================================

    def export_dotenv(self, resolve_secrets: bool = False) -> str:
        """
        Export as dotenv format.

        Args:
            resolve_secrets: Whether to resolve secret values

        Returns:
            Dotenv formatted string
        """
        lines = [f"# {self.metadata.name}"]
        if self.metadata.description:
            lines.append(f"# {self.metadata.description}")
        lines.append("")

        env_vars = self.resolve_all(include_secrets=resolve_secrets)

        for key, value in sorted(env_vars.items()):
            # Quote value if it contains special characters
            if " " in value or "#" in value or "'" in value or '"' in value:
                escaped = value.replace('"', '\\"')
                value = f'"{escaped}"'
            lines.append(f"{key}={value}")

        return "\n".join(lines)

    def export_shell(self, resolve_secrets: bool = False) -> str:
        """
        Export as shell script format.

        Args:
            resolve_secrets: Whether to resolve secret values

        Returns:
            Shell script formatted string
        """
        lines = ["#!/bin/bash", ""]
        lines.append(f"# {self.metadata.name}")
        if self.metadata.description:
            lines.append(f"# {self.metadata.description}")
        lines.append("")

        env_vars = self.resolve_all(include_secrets=resolve_secrets)

        for key, value in sorted(env_vars.items()):
            # Escape special characters in value
            escaped = value.replace('"', '\\"').replace("$", "\\$")
            lines.append(f'export {key}="{escaped}"')

        return "\n".join(lines)

    def export_json(self, resolve_secrets: bool = False) -> str:
        """
        Export as JSON format.

        Args:
            resolve_secrets: Whether to resolve secret values

        Returns:
            JSON formatted string
        """
        import json

        env_vars = self.resolve_all(include_secrets=resolve_secrets)
        return json.dumps(env_vars, indent=2, ensure_ascii=False)
