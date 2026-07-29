"""Secret resolution and env export — IO adapters over EnvConfig data.

Moved out of ``zima.models`` so the domain layer stays free of ``subprocess``
and other IO. These functions operate on the pure data in
:class:`~zima.models.env.EnvConfig` / :class:`~zima.models.env.SecretDef`.

NOTE: :meth:`PJobExecutor._resolve_secret` (``zima/execution/executor.py``) is a
parallel, intentionally *lenient* implementation for the agent run path (shorter
timeout, returns ``None`` on failure, Windows ``_fix_shell_command`` shim). This
module serves the *strict* CLI ``env`` path (raises on failure). They are kept
separate on purpose.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from zima.models.env import EnvConfig, SecretDef


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


def resolve_env_all(env_config: EnvConfig, include_secrets: bool = True) -> dict[str, str]:
    """Resolve all environment variables (plain variables + secrets).

    Args:
        env_config: Env configuration holding variables and secret definitions.
        include_secrets: If True, resolve secret values; if False, emit masked placeholders.

    Returns:
        Dictionary of all environment variables.
    """
    result = dict(env_config.variables)

    if include_secrets:
        for secret in env_config.secrets:
            try:
                result[secret.name] = SecretResolver.resolve(secret)
            except ValueError as e:
                # If resolution fails, use placeholder
                result[secret.name] = f"<error:{str(e)}>"
    else:
        # Include masked secrets
        for secret in env_config.secrets:
            result[secret.name] = secret.get_masked_value()

    return result


def resolve_env_secret(env_config: EnvConfig, name: str) -> str:
    """Resolve a single secret value by name.

    Raises:
        ValueError: If the secret is not found or resolution fails.
    """
    secret = env_config.get_secret(name)
    if not secret:
        raise ValueError(f"Secret '{name}' not found")
    return SecretResolver.resolve(secret)


def export_env_dotenv(env_config: EnvConfig, resolve_secrets: bool = False) -> str:
    """Export an EnvConfig as dotenv format."""
    lines = [f"# {env_config.metadata.name}"]
    if env_config.metadata.description:
        lines.append(f"# {env_config.metadata.description}")
    lines.append("")

    env_vars = resolve_env_all(env_config, include_secrets=resolve_secrets)

    for key, value in sorted(env_vars.items()):
        # Quote value if it contains special characters
        if " " in value or "#" in value or "'" in value or '"' in value:
            escaped = value.replace('"', '\\"')
            value = f'"{escaped}"'
        lines.append(f"{key}={value}")

    return "\n".join(lines)


def export_env_shell(env_config: EnvConfig, resolve_secrets: bool = False) -> str:
    """Export an EnvConfig as a shell script."""
    lines = ["#!/bin/bash", ""]
    lines.append(f"# {env_config.metadata.name}")
    if env_config.metadata.description:
        lines.append(f"# {env_config.metadata.description}")
    lines.append("")

    env_vars = resolve_env_all(env_config, include_secrets=resolve_secrets)

    for key, value in sorted(env_vars.items()):
        # Escape special characters in value
        escaped = value.replace('"', '\\"').replace("$", "\\$")
        lines.append(f'export {key}="{escaped}"')

    return "\n".join(lines)


def export_env_json(env_config: EnvConfig, resolve_secrets: bool = False) -> str:
    """Export an EnvConfig as JSON."""
    env_vars = resolve_env_all(env_config, include_secrets=resolve_secrets)
    return json.dumps(env_vars, indent=2, ensure_ascii=False)
