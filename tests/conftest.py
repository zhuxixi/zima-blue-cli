"""Pytest global fixtures and configuration."""

import shutil
import tempfile
import uuid
from pathlib import Path

import pytest


@pytest.fixture(scope="function")
def temp_dir():
    """Provide temporary directory that's cleaned up after test."""
    path = Path(tempfile.mkdtemp(prefix="zima-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="function")
def isolated_zima_home(monkeypatch, temp_dir):
    """
    Set up isolated ZIMA_HOME environment.
    
    This fixture:
    - Sets ZIMA_HOME to a temp directory
    - Creates necessary subdirectories
    - Cleans up after test
    """
    # Set environment
    monkeypatch.setenv("ZIMA_HOME", str(temp_dir))
    
    # Create subdirectories
    for kind in ["agents", "workflows", "variables", "envs", "pmgs"]:
        (temp_dir / "configs" / kind).mkdir(parents=True, exist_ok=True)
    
    yield temp_dir


@pytest.fixture
def config_manager(isolated_zima_home):
    """Provide ConfigManager with isolated environment."""
    from zima.config.manager import ConfigManager
    return ConfigManager()


@pytest.fixture
def sample_agent_dict():
    """Provide sample agent configuration as dict."""
    return {
        "apiVersion": "zima.io/v1",
        "kind": "Agent",
        "metadata": {
            "code": "test-agent",
            "name": "Test Agent",
            "description": "For testing"
        },
        "spec": {
            "type": "kimi",
            "parameters": {
                "model": "kimi-k2-072515-preview",
                "yolo": True
            },
            "defaults": {}
        }
    }


@pytest.fixture
def cli_runner():
    """Provide Typer CLI test runner."""
    from typer.testing import CliRunner
    return CliRunner()


@pytest.fixture
def unique_code():
    """Generate unique code for test resources."""
    return f"test-{uuid.uuid4().hex[:8]}"


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection."""
    # Add integration marker to tests in integration folder
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
