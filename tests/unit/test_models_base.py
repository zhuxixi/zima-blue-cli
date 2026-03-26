"""Unit tests for base models."""

import pytest
from pathlib import Path
from dataclasses import dataclass, field

from zima.models.base import BaseConfig, Metadata


class TestMetadata:
    """Test Metadata class."""
    
    def test_default_values(self):
        """Test default values."""
        meta = Metadata()
        assert meta.code == ""
        assert meta.name == ""
        assert meta.description == ""
    
    def test_custom_values(self):
        """Test custom values."""
        meta = Metadata(code="test", name="Test", description="Desc")
        assert meta.code == "test"
        assert meta.name == "Test"
        assert meta.description == "Desc"
    
    def test_to_dict(self):
        """Test to_dict method."""
        meta = Metadata(code="test", name="Test")
        result = meta.to_dict()
        
        assert result == {
            "code": "test",
            "name": "Test",
            "description": ""
        }
    
    def test_from_dict(self):
        """Test from_dict method."""
        data = {"code": "test", "name": "Test", "description": "Desc"}
        meta = Metadata.from_dict(data)
        
        assert meta.code == "test"
        assert meta.name == "Test"
        assert meta.description == "Desc"
    
    def test_from_dict_partial(self):
        """Test from_dict with partial data."""
        data = {"code": "test"}
        meta = Metadata.from_dict(data)
        
        assert meta.code == "test"
        assert meta.name == ""
        assert meta.description == ""
    
    def test_from_dict_empty(self):
        """Test from_dict with empty dict."""
        meta = Metadata.from_dict({})
        assert meta.code == ""
        assert meta.name == ""


class TestBaseConfig:
    """Test BaseConfig class."""
    
    def test_default_values(self):
        """Test default values."""
        config = BaseConfig()
        assert config.api_version == "zima.io/v1"
        assert config.kind == ""
        assert isinstance(config.metadata, Metadata)
        assert config.created_at != ""
        assert config.updated_at != ""
    
    def test_custom_values(self):
        """Test custom values."""
        config = BaseConfig(
            api_version="v2",
            kind="Test",
            metadata=Metadata(code="test")
        )
        assert config.api_version == "v2"
        assert config.kind == "Test"
        assert config.metadata.code == "test"
    
    def test_post_init_sets_timestamps(self):
        """Test __post_init__ sets timestamps."""
        config = BaseConfig()
        assert config.created_at != ""
        assert config.updated_at != ""
        assert config.created_at == config.updated_at
    
    def test_to_dict(self):
        """Test to_dict method."""
        config = BaseConfig(
            kind="Agent",
            metadata=Metadata(code="test", name="Test")
        )
        result = config.to_dict()
        
        assert result["kind"] == "Agent"
        assert result["metadata"]["code"] == "test"
        assert result["apiVersion"] == "zima.io/v1"
        assert "createdAt" in result
        assert "updatedAt" in result
    
    def test_to_yaml(self):
        """Test to_yaml method."""
        config = BaseConfig(kind="Agent", metadata=Metadata(code="test"))
        yaml_str = config.to_yaml()
        
        assert "kind: Agent" in yaml_str
        assert "code: test" in yaml_str
        assert "apiVersion" in yaml_str
    
    def test_from_dict(self):
        """Test from_dict method."""
        data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "test", "name": "Test"},
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z"
        }
        config = BaseConfig.from_dict(data)
        
        assert config.kind == "Agent"
        assert config.metadata.code == "test"
        assert config.created_at == "2026-01-01T00:00:00Z"
    
    def test_from_yaml(self):
        """Test from_yaml method."""
        yaml_content = """
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: test-agent
  name: Test Agent
"""
        config = BaseConfig.from_yaml(yaml_content)
        
        assert config.kind == "Agent"
        assert config.metadata.code == "test-agent"
        assert config.metadata.name == "Test Agent"
    
    def test_from_yaml_file(self, tmp_path):
        """Test from_yaml_file method."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("""
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: test
""")
        
        config = BaseConfig.from_yaml_file(config_file)
        assert config.kind == "Agent"
        assert config.metadata.code == "test"
    
    def test_from_yaml_file_not_found(self, tmp_path):
        """Test from_yaml_file with non-existent file."""
        with pytest.raises(FileNotFoundError):
            BaseConfig.from_yaml_file(tmp_path / "nonexistent.yaml")
    
    def test_save_to_file(self, tmp_path):
        """Test save_to_file method."""
        config = BaseConfig(kind="Agent", metadata=Metadata(code="test"))
        config_file = tmp_path / "config.yaml"
        
        config.save_to_file(config_file)
        
        assert config_file.exists()
        content = config_file.read_text()
        assert "kind: Agent" in content
        assert "code: test" in content
    
    def test_save_updates_timestamp(self, tmp_path):
        """Test save_to_file updates timestamp."""
        config = BaseConfig(kind="Agent", metadata=Metadata(code="test"))
        old_updated = config.updated_at
        
        import time
        time.sleep(1.1)  # Delay > 1s to ensure different timestamp (Windows has 1s precision)
        
        config.save_to_file(tmp_path / "config.yaml")
        
        assert config.updated_at != old_updated
    
    def test_validate_valid(self):
        """Test validate with valid config."""
        config = BaseConfig(
            kind="Agent",
            metadata=Metadata(code="test")
        )
        errors = config.validate()
        assert errors == []
    
    def test_validate_missing_code(self):
        """Test validate with missing code."""
        config = BaseConfig(kind="Agent")
        errors = config.validate()
        assert any("code is required" in e for e in errors)
    
    def test_validate_missing_kind(self):
        """Test validate with missing kind."""
        config = BaseConfig(metadata=Metadata(code="test"))
        errors = config.validate()
        assert any("kind is required" in e for e in errors)
    
    def test_is_valid_true(self):
        """Test is_valid returns True."""
        config = BaseConfig(kind="Agent", metadata=Metadata(code="test"))
        assert config.is_valid() is True
    
    def test_is_valid_false(self):
        """Test is_valid returns False."""
        config = BaseConfig()  # Missing code and kind
        assert config.is_valid() is False
    
    def test_update_timestamp(self):
        """Test update_timestamp method."""
        config = BaseConfig()
        old_timestamp = config.updated_at
        
        import time
        time.sleep(1.1)  # Delay > 1s to ensure different timestamp (Windows has 1s precision)
        
        config.update_timestamp()
        
        assert config.updated_at != old_timestamp


class TestBaseConfigInheritance:
    """Test BaseConfig inheritance."""
    
    def test_custom_config_class(self):
        """Test creating custom config class."""
        @dataclass
        class CustomConfig(BaseConfig):
            kind: str = "Custom"
            custom_field: str = "default"
        
        config = CustomConfig(metadata=Metadata(code="test"))
        
        assert config.kind == "Custom"
        assert config.custom_field == "default"
        assert config.metadata.code == "test"
    
    def test_custom_config_to_dict(self):
        """Test custom config to_dict."""
        @dataclass
        class CustomConfig(BaseConfig):
            kind: str = "Custom"
            custom_field: str = "value"
        
        config = CustomConfig(metadata=Metadata(code="test"))
        result = config.to_dict()
        
        # Base fields
        assert result["kind"] == "Custom"
        assert result["metadata"]["code"] == "test"
        # Note: custom_field won't be in result unless we override to_dict


class TestHelperFunctions:
    """Test helper functions in base module."""
    
    def test_convert_to_camel_case(self):
        """Test snake_case to camelCase conversion."""
        from zima.models.base import convert_to_camel_case
        
        assert convert_to_camel_case("snake_case") == "snakeCase"
        assert convert_to_camel_case("my_var_name") == "myVarName"
        assert convert_to_camel_case("simple") == "simple"
    
    def test_convert_to_snake_case(self):
        """Test camelCase to snake_case conversion."""
        from zima.models.base import convert_to_snake_case
        
        assert convert_to_snake_case("camelCase") == "camel_case"
        assert convert_to_snake_case("myVarName") == "my_var_name"
        assert convert_to_snake_case("simple") == "simple"
