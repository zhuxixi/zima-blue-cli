"""Zima Blue CLI - Personal Agent Orchestration Platform"""

from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    """Get package version from pyproject.toml metadata.

    Returns:
        Version string (e.g. "0.1.1"), or "unknown" if package is not installed.
    """
    try:
        return version("zima-blue-cli")
    except PackageNotFoundError:
        return "unknown"
