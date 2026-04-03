"""Test base classes and utilities."""

import shutil
import uuid
from pathlib import Path

import pytest

from zima.utils import ensure_dir


class TestIsolator:
    """
    Test isolation base class.

    All tests should inherit from this class to get automatic
    test data isolation and cleanup.

    Example:
        class TestMyFeature(TestIsolator):
            def test_something(self):
                # This test runs in isolated environment
                pass
    """

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch):
        """
        Automatically setup isolated environment for each test.

        This fixture:
        1. Creates a temporary directory
        2. Sets ZIMA_HOME to the temp directory
        3. Creates necessary subdirectories
        4. Cleans up after test
        """
        # Generate unique test ID
        self.test_id = str(uuid.uuid4())[:8]
        self.temp_dir = Path("/tmp") / f"zima-test-{self.test_id}"

        # Windows fallback
        if not Path("/tmp").exists():
            import tempfile

            self.temp_dir = Path(tempfile.gettempdir()) / f"zima-test-{self.test_id}"

        # Create directory
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Backup and set environment
        self.original_zima_home = ensure_dir(Path.home() / ".zima")
        monkeypatch.setenv("ZIMA_HOME", str(self.temp_dir))

        # Create config subdirectories
        for kind in ["agents", "workflows", "variables", "envs", "pmgs"]:
            ensure_dir(self.temp_dir / "configs" / kind)

        yield

        # Cleanup
        self._cleanup()

    def _cleanup(self):
        """Clean up test data."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

        # Verify cleanup
        assert not self.temp_dir.exists(), f"Failed to cleanup: {self.temp_dir}"

    def get_test_path(self, *parts) -> Path:
        """Get path within test directory."""
        return self.temp_dir.joinpath(*parts)

    def get_config_path(self, kind: str, code: str) -> Path:
        """Get config file path in test environment."""
        return self.temp_dir / "configs" / f"{kind}s" / f"{code}.yaml"

    def assert_no_residual_data(self):
        """Assert no test data remains."""
        configs_dir = self.temp_dir / "configs"
        if configs_dir.exists():
            yaml_files = list(configs_dir.rglob("*.yaml"))
            assert len(yaml_files) == 0, f"Residual test data: {yaml_files}"


class AgentTestIsolator(TestIsolator):
    """Test isolator with Agent-specific helpers."""

    @pytest.fixture
    def sample_agent_data(self) -> dict:
        """Provide sample agent configuration data."""
        return {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {
                "code": "sample-agent",
                "name": "Sample Agent",
                "description": "For testing",
            },
            "spec": {
                "type": "kimi",
                "parameters": {
                    "model": "kimi-k2-072515-preview",
                    "yolo": True,
                    "maxStepsPerTurn": 50,
                },
                "defaults": {},
            },
            "createdAt": "2026-03-26T10:00:00Z",
            "updatedAt": "2026-03-26T10:00:00Z",
        }

    @pytest.fixture
    def create_test_agent(self, sample_agent_data):
        """Factory to create test agents."""
        from zima.config.manager import ConfigManager

        manager = ConfigManager()

        def _create(
            code: str = None, name: str = None, agent_type: str = "kimi", parameters: dict = None
        ):
            data = sample_agent_data.copy()

            if code:
                data["metadata"]["code"] = code
                if not name:
                    name = f"Test {code}"

            if name:
                data["metadata"]["name"] = name

            if agent_type:
                data["spec"]["type"] = agent_type

            if parameters:
                data["spec"]["parameters"].update(parameters)

            actual_code = data["metadata"]["code"]
            manager.save_config("agent", actual_code, data)
            return data

        return _create
