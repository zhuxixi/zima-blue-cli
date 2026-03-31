"""Utility functions"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def safe_print(text: str) -> None:
    """Print text safely handling encoding issues on Windows"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fall back to ASCII-only on encoding errors
        ascii_text = text.encode("ascii", "ignore").decode("ascii")
        print(ascii_text)


def icon(name: str) -> str:
    """Get an icon (or empty string on Windows to avoid encoding issues)"""
    if sys.platform == "win32":
        return ""

    icons = {
        "rocket": "🚀",
        "stop": "⏹️",
        "cycle": "🌅",
        "task": "🎯",
        "result": "📊",
        "sleep": "💤",
        "complete": "🎉",
        "warning": "⚠️",
        "check": "✓",
        "cross": "✗",
    }
    return icons.get(name, "")


# =============================================================================
# Configuration Management Utilities
# =============================================================================


def get_zima_home() -> Path:
    """
    Get Zima home directory.

    Priority:
    1. ZIMA_HOME environment variable
    2. ~/.zima (default)

    Returns:
        Path to Zima home directory
    """
    zima_home = os.environ.get("ZIMA_HOME")
    if zima_home:
        return Path(zima_home)
    return Path.home() / ".zima"


def get_config_dir() -> Path:
    """
    Get configuration directory.

    Returns:
        Path to configs directory (e.g., ~/.zima/configs)
    """
    return get_zima_home() / "configs"


def get_agents_config_dir() -> Path:
    """
    Get agents configuration directory.

    Returns:
        Path to agents configs directory
    """
    return get_config_dir() / "agents"


def get_workflows_config_dir() -> Path:
    """Get workflows configuration directory."""
    return get_config_dir() / "workflows"


def get_variables_config_dir() -> Path:
    """Get variables configuration directory."""
    return get_config_dir() / "variables"


def get_envs_config_dir() -> Path:
    """Get envs configuration directory."""
    return get_config_dir() / "envs"


def get_pmgs_config_dir() -> Path:
    """Get pmgs configuration directory."""
    return get_config_dir() / "pmgs"


# =============================================================================
# Validation Utilities
# =============================================================================


# Code format: lowercase letters, numbers, hyphens; must start with letter, cannot end with hyphen
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
CODE_MAX_LENGTH = 64


def validate_code(code: str) -> bool:
    """
    Validate configuration code format.

    Rules:
    - Must start with lowercase letter
    - Can contain lowercase letters, numbers, and hyphens
    - Cannot end with hyphen
    - Maximum 64 characters
    - No underscores, uppercase letters, or special chars

    Args:
        code: The code string to validate

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_code("test-agent")  # True
        >>> validate_code("Test-Agent")  # False (uppercase)
        >>> validate_code("test_agent")  # False (underscore)
        >>> validate_code("123-agent")   # False (starts with number)
        >>> validate_code("test-")       # False (ends with hyphen)
    """
    if not code:
        return False
    if len(code) > CODE_MAX_LENGTH:
        return False
    if code.endswith("-"):
        return False
    return bool(CODE_PATTERN.match(code))


def validate_code_with_error(code: str) -> tuple[bool, str]:
    """
    Validate code and return error message if invalid.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not code:
        return False, "Code cannot be empty"
    if len(code) > CODE_MAX_LENGTH:
        return False, f"Code too long (max {CODE_MAX_LENGTH} characters)"
    if code.endswith("-"):
        return False, "Code cannot end with hyphen"
    if not CODE_PATTERN.match(code):
        return False, (
            "Invalid code format. "
            "Must start with lowercase letter, "
            "contain only lowercase letters, numbers, and hyphens"
        )
    return True, ""


# =============================================================================
# Time Utilities
# =============================================================================


def generate_timestamp() -> str:
    """
    Generate ISO 8601 timestamp.

    Returns:
        ISO 8601 formatted string (e.g., "2026-03-26T14:30:00Z")
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_timestamp(timestamp: str) -> str:
    """
    Format ISO timestamp for display.

    Args:
        timestamp: ISO 8601 timestamp string

    Returns:
        Human readable format (e.g., "2026-03-26 14:30")
    """
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return timestamp


# =============================================================================
# Path Utilities
# =============================================================================


def ensure_dir(path: Path) -> Path:
    """
    Ensure directory exists, create if not.

    Args:
        path: Directory path

    Returns:
        The directory path
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_delete(path: Path) -> bool:
    """
    Safely delete a file or directory.

    Args:
        path: Path to delete

    Returns:
        True if deleted or didn't exist, False on error
    """
    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            import shutil

            shutil.rmtree(path)
        return True
    except Exception:
        return False


# =============================================================================
# Type Validation
# =============================================================================


VALID_AGENT_TYPES = {"kimi", "claude", "gemini"}


def validate_agent_type(agent_type: str) -> bool:
    """
    Validate agent type.

    Args:
        agent_type: Type string to validate

    Returns:
        True if valid agent type
    """
    return agent_type in VALID_AGENT_TYPES


def get_valid_agent_types() -> set[str]:
    """Get set of valid agent types."""
    return VALID_AGENT_TYPES.copy()
