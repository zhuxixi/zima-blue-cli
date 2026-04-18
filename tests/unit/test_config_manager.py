"""Unit tests for ConfigManager."""

import pytest

from tests.base import TestIsolator
from zima.config.manager import ConfigManager


class TestConfigManagerBasics(TestIsolator):
    """Test ConfigManager basic operations."""

    def test_init_default_dir(self):
        """Test initialization with default directory."""
        manager = ConfigManager()
        assert "zima-test-" in str(manager.config_dir)

    def test_init_custom_dir(self, tmp_path):
        """Test initialization with custom directory."""
        custom = tmp_path / "custom-config"
        manager = ConfigManager(custom)
        assert manager.config_dir == custom

    def test_kinds_constant(self):
        """Test KINDS constant."""
        assert ConfigManager.KINDS == {
            "agent",
            "workflow",
            "variable",
            "env",
            "pmg",
            "pjob",
            "schedule",
        }


class TestConfigManagerCRUD(TestIsolator):
    """Test ConfigManager CRUD operations."""

    @pytest.fixture
    def manager(self):
        """Provide ConfigManager instance."""
        return ConfigManager()

    def test_save_and_load_config(self, manager):
        """Test saving and loading configuration."""
        config = {"metadata": {"code": "test", "name": "Test"}, "spec": {"type": "kimi"}}

        # Save
        path = manager.save_config("agent", "test", config)
        assert path.exists()

        # Load
        loaded = manager.load_config("agent", "test")
        assert loaded["metadata"]["code"] == "test"
        assert loaded["spec"]["type"] == "kimi"

    def test_config_exists(self, manager):
        """Test config existence check."""
        assert not manager.config_exists("agent", "nonexistent")

        manager.save_config("agent", "exists", {"metadata": {"code": "exists"}})
        assert manager.config_exists("agent", "exists")

    def test_delete_config(self, manager):
        """Test deleting configuration."""
        manager.save_config("agent", "to-delete", {"metadata": {"code": "to-delete"}})
        assert manager.config_exists("agent", "to-delete")

        result = manager.delete_config("agent", "to-delete")
        assert result is True
        assert not manager.config_exists("agent", "to-delete")

    def test_delete_nonexistent_config(self, manager):
        """Test deleting non-existent configuration."""
        result = manager.delete_config("agent", "nonexistent")
        assert result is False

    def test_load_nonexistent_config(self, manager):
        """Test loading non-existent configuration."""
        with pytest.raises(FileNotFoundError):
            manager.load_config("agent", "nonexistent")

    def test_list_configs(self, manager):
        """Test listing configurations."""
        # Create multiple configs
        for i in range(3):
            manager.save_config(
                "agent", f"agent-{i}", {"metadata": {"code": f"agent-{i}", "name": f"Agent {i}"}}
            )

        configs = manager.list_configs("agent")
        assert len(configs) == 3

        codes = [c["metadata"]["code"] for c in configs]
        assert "agent-0" in codes
        assert "agent-1" in codes
        assert "agent-2" in codes

    def test_list_configs_empty(self, manager):
        """Test listing empty configurations."""
        configs = manager.list_configs("agent")
        assert configs == []

    def test_list_config_codes(self, manager):
        """Test listing config codes."""
        manager.save_config("agent", "agent-a", {"metadata": {"code": "agent-a"}})
        manager.save_config("agent", "agent-b", {"metadata": {"code": "agent-b"}})

        codes = manager.list_config_codes("agent")
        assert codes == ["agent-a", "agent-b"]


class TestConfigManagerTimestamp(TestIsolator):
    """Test timestamp handling."""

    def test_created_at_set_on_save(self):
        """Test createdAt is set when saving."""
        manager = ConfigManager()
        config = {"metadata": {"code": "test"}}

        manager.save_config("agent", "test", config)
        loaded = manager.load_config("agent", "test")

        assert "createdAt" in loaded
        assert loaded["createdAt"] != ""

    def test_updated_at_auto_update(self):
        """Test updatedAt is updated on save."""
        manager = ConfigManager()
        config = {
            "metadata": {"code": "test"},
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        manager.save_config("agent", "test", config)

        # Modify and save again
        config["metadata"]["name"] = "Updated"
        manager.save_config("agent", "test", config)

        loaded = manager.load_config("agent", "test")
        assert loaded["updatedAt"] != "2026-01-01T00:00:00Z"

    def test_created_at_preserved(self):
        """Test createdAt is preserved on update."""
        manager = ConfigManager()
        config = {"metadata": {"code": "test"}}

        manager.save_config("agent", "test", config)
        first_loaded = manager.load_config("agent", "test")
        created_at = first_loaded["createdAt"]

        # Update
        first_loaded["metadata"]["name"] = "Updated"
        manager.save_config("agent", "test", first_loaded)

        second_loaded = manager.load_config("agent", "test")
        assert second_loaded["createdAt"] == created_at


class TestConfigManagerCopy(TestIsolator):
    """Test config copy functionality."""

    def test_copy_config_success(self):
        """Test successful config copy."""
        manager = ConfigManager()

        source = {
            "metadata": {"code": "source", "name": "Source", "description": "Desc"},
            "spec": {"type": "kimi", "model": "k2"},
        }
        manager.save_config("agent", "source", source)

        result = manager.copy_config("agent", "source", "target", "Target Name")
        assert result is True

        copied = manager.load_config("agent", "target")
        assert copied["metadata"]["code"] == "target"
        assert copied["metadata"]["name"] == "Target Name"
        assert copied["metadata"]["description"] == "Desc"
        assert copied["spec"]["type"] == "kimi"

    def test_copy_config_target_exists(self):
        """Test copy when target exists."""
        manager = ConfigManager()
        manager.save_config("agent", "source", {"metadata": {"code": "source"}})
        manager.save_config("agent", "target", {"metadata": {"code": "target"}})

        with pytest.raises(ValueError, match="already exists"):
            manager.copy_config("agent", "source", "target")

    def test_copy_config_source_not_exists(self):
        """Test copy when source doesn't exist."""
        manager = ConfigManager()

        with pytest.raises(FileNotFoundError):
            manager.copy_config("agent", "nonexistent", "target")

    def test_copy_config_default_name(self):
        """Test copy generates default name."""
        manager = ConfigManager()
        manager.save_config("agent", "source", {"metadata": {"code": "source", "name": "Original"}})

        manager.copy_config("agent", "source", "target")
        copied = manager.load_config("agent", "target")

        assert "(Copy)" in copied["metadata"]["name"]


class TestConfigManagerValidation(TestIsolator):
    """Test input validation."""

    def test_invalid_kind(self):
        """Test invalid config kind."""
        manager = ConfigManager()

        with pytest.raises(ValueError, match="Unknown config kind"):
            manager.save_config("invalid-kind", "test", {})

    def test_invalid_code_format(self):
        """Test invalid code format."""
        manager = ConfigManager()

        with pytest.raises(ValueError, match="Invalid code format"):
            manager.save_config("agent", "Invalid_Code", {})

    def test_empty_code(self):
        """Test empty code."""
        manager = ConfigManager()

        with pytest.raises(ValueError, match="Invalid code format"):
            manager.save_config("agent", "", {})


class TestConfigManagerSummary(TestIsolator):
    """Test config summary functionality."""

    def test_get_config_summary(self):
        """Test getting config summary."""
        manager = ConfigManager()
        manager.save_config(
            "agent",
            "test",
            {
                "metadata": {"code": "test", "name": "Test Agent", "description": "Desc"},
                "spec": {"type": "kimi"},
            },
        )

        summary = manager.get_config_summary("agent", "test")
        assert summary["code"] == "test"
        assert summary["name"] == "Test Agent"
        assert summary["description"] == "Desc"
        assert summary["kind"] == "agent"

    def test_get_config_summary_not_exists(self):
        """Test getting summary for non-existent config."""
        manager = ConfigManager()

        summary = manager.get_config_summary("agent", "nonexistent")
        assert summary is None


class TestConfigManagerPath(TestIsolator):
    """Test path-related methods."""

    def test_get_config_path(self):
        """Test getting config file path."""
        manager = ConfigManager()
        path = manager.get_config_path("agent", "my-agent")

        assert path.name == "my-agent.yaml"
        assert "agents" in str(path)

    def test_get_kind_dir(self):
        """Test getting kind directory."""
        manager = ConfigManager()
        kind_dir = manager._get_kind_dir("agent")

        assert kind_dir.name == "agents"
        assert kind_dir.exists()


class TestConfigManagerKinds(TestIsolator):
    """Test all config kinds work correctly."""

    @pytest.mark.parametrize("kind", ["agent", "workflow", "variable", "env", "pmg"])
    def test_all_kinds(self, kind):
        """Test each kind can save and load."""
        manager = ConfigManager()

        data = {"metadata": {"code": f"test-{kind}"}}
        manager.save_config(kind, f"test-{kind}", data)

        loaded = manager.load_config(kind, f"test-{kind}")
        assert loaded["metadata"]["code"] == f"test-{kind}"
