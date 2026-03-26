"""Unit tests for VariableConfig model."""

import pytest
from pathlib import Path

from zima.models.variable import VariableConfig
from tests.base import TestIsolator


class TestVariableConfig(TestIsolator):
    """VariableConfig model tests."""
    
    class TestCreate:
        """Test VariableConfig creation."""
        
        def test_create_basic(self):
            """Test creating basic variable config."""
            var = VariableConfig.create(
                code="test-vars",
                name="Test Variables"
            )
            
            assert var.metadata.code == "test-vars"
            assert var.metadata.name == "Test Variables"
            assert var.for_workflow == ""
            assert var.values == {}
            assert var.kind == "Variable"
        
        def test_create_with_all_fields(self):
            """Test creating with all fields."""
            var = VariableConfig.create(
                code="full-vars",
                name="Full Variables",
                for_workflow="my-workflow",
                values={
                    "task": {
                        "name": "Test Task",
                        "steps": ["step1", "step2"]
                    },
                    "config": {"timeout": 30}
                },
                description="Complete variable set"
            )
            
            assert var.for_workflow == "my-workflow"
            assert var.values["task"]["name"] == "Test Task"
            assert var.values["config"]["timeout"] == 30
            assert var.metadata.description == "Complete variable set"
    
    class TestValidation:
        """Test variable validation."""
        
        def test_validate_valid(self):
            """Test valid variable config."""
            var = VariableConfig.create(
                code="valid-vars",
                name="Valid Variables"
            )
            errors = var.validate()
            assert errors == []
        
        def test_validate_missing_code(self):
            """Test missing code."""
            var = VariableConfig()
            var.metadata.code = ""
            errors = var.validate()
            assert any("code is required" in e for e in errors)
        
        def test_validate_invalid_code_format(self):
            """Test invalid code format."""
            var = VariableConfig.create(
                code="Invalid_Code",
                name="Test"
            )
            errors = var.validate()
            assert any("has invalid format" in e for e in errors)
        
        def test_validate_missing_name(self):
            """Test missing name."""
            var = VariableConfig.create(code="test", name="")
            var.metadata.name = ""
            errors = var.validate()
            assert any("name is required" in e for e in errors)
        
        def test_validate_invalid_for_workflow(self):
            """Test invalid for_workflow format."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                for_workflow="Invalid Workflow"
            )
            errors = var.validate()
            assert any("forWorkflow" in e and "invalid format" in e for e in errors)
        
        def test_validate_values_not_dict(self):
            """Test values not being a dictionary."""
            var = VariableConfig.create(code="test", name="Test")
            var.values = ["not", "a", "dict"]  # type: ignore
            errors = var.validate()
            assert any("must be a dictionary" in e for e in errors)
    
    class TestDictConversion:
        """Test dictionary conversion."""
        
        def test_to_dict(self):
            """Test to_dict method."""
            var = VariableConfig.create(
                code="dict-test",
                name="Dict Test",
                for_workflow="wf-code",
                values={"key": "value"}
            )
            
            data = var.to_dict()
            assert data["apiVersion"] == "zima.io/v1"
            assert data["kind"] == "Variable"
            assert data["metadata"]["code"] == "dict-test"
            assert data["spec"]["forWorkflow"] == "wf-code"
            assert data["spec"]["values"]["key"] == "value"
        
        def test_from_dict(self):
            """Test from_dict method."""
            data = {
                "apiVersion": "zima.io/v1",
                "kind": "Variable",
                "metadata": {
                    "code": "from-dict",
                    "name": "From Dict",
                    "description": "Test"
                },
                "spec": {
                    "forWorkflow": "target-workflow",
                    "values": {
                        "task": {"name": "Task"},
                        "items": ["a", "b"]
                    }
                },
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-01T00:00:00Z"
            }
            
            var = VariableConfig.from_dict(data)
            assert var.metadata.code == "from-dict"
            assert var.for_workflow == "target-workflow"
            assert var.values["task"]["name"] == "Task"
            assert var.values["items"] == ["a", "b"]
    
    class TestValueAccess:
        """Test value access methods."""
        
        def test_get_value_simple(self):
            """Test getting simple value."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={"name": "Test", "count": 42}
            )
            
            assert var.get_value("name") == "Test"
            assert var.get_value("count") == 42
        
        def test_get_value_nested(self):
            """Test getting nested value."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={
                    "task": {
                        "name": "Task Name",
                        "config": {
                            "timeout": 30
                        }
                    }
                }
            )
            
            assert var.get_value("task.name") == "Task Name"
            assert var.get_value("task.config.timeout") == 30
        
        def test_get_value_default(self):
            """Test getting value with default."""
            var = VariableConfig.create(code="test", name="Test")
            
            assert var.get_value("missing") is None
            assert var.get_value("missing", "default") == "default"
            assert var.get_value("missing.key", 123) == 123
        
        def test_get_value_nonexistent_path(self):
            """Test getting value from nonexistent path."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={"task": {"name": "Task"}}
            )
            
            assert var.get_value("nonexistent") is None
            assert var.get_value("task.nonexistent") is None
            assert var.get_value("task.name.sub") is None
        
        def test_set_value_simple(self):
            """Test setting simple value."""
            var = VariableConfig.create(code="test", name="Test")
            
            var.set_value("name", "New Name")
            assert var.values["name"] == "New Name"
        
        def test_set_value_nested(self):
            """Test setting nested value."""
            var = VariableConfig.create(code="test", name="Test")
            
            var.set_value("task.name", "Task Name")
            var.set_value("task.config.timeout", 60)
            
            assert var.values["task"]["name"] == "Task Name"
            assert var.values["task"]["config"]["timeout"] == 60
        
        def test_set_value_updates_timestamp(self):
            """Test setting value updates timestamp."""
            var = VariableConfig.create(code="test", name="Test")
            # Manually set old timestamp
            var.updated_at = "2026-01-01T00:00:00Z"
            old_updated = var.updated_at
            
            var.set_value("key", "value")
            
            assert var.updated_at != old_updated
        
        def test_has_value(self):
            """Test checking if value exists."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={
                    "task": {"name": "Task"},
                    "empty": None
                }
            )
            
            assert var.has_value("task") is True
            assert var.has_value("task.name") is True
            assert var.has_value("nonexistent") is False
            # None value returns None, which is falsy
            # But the key exists, so we might want to distinguish
            # For now, treat None as "no value"
            assert not var.has_value("empty")
    
    class TestMerge:
        """Test value merging."""
        
        def test_merge_values(self):
            """Test merging values."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={
                    "task": {"name": "Original", "status": "pending"},
                    "config": {"debug": True}
                }
            )
            
            var.merge_values({
                "task": {"status": "done", "priority": "high"},
                "new_key": "value"
            })
            
            assert var.values["task"]["name"] == "Original"  # Preserved
            assert var.values["task"]["status"] == "done"  # Updated
            assert var.values["task"]["priority"] == "high"  # Added
            assert var.values["new_key"] == "value"  # Added
            assert var.values["config"]["debug"] is True  # Preserved
        
        def test_deep_merge_nested(self):
            """Test deep merging nested structures."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={
                    "level1": {
                        "level2": {
                            "a": 1,
                            "b": 2
                        }
                    }
                }
            )
            
            var.merge_values({
                "level1": {
                    "level2": {
                        "b": 20,
                        "c": 30
                    }
                }
            })
            
            assert var.values["level1"]["level2"]["a"] == 1
            assert var.values["level1"]["level2"]["b"] == 20
            assert var.values["level1"]["level2"]["c"] == 30
    
    class TestFlatten:
        """Test flattening values."""
        
        def test_flatten_simple(self):
            """Test flattening simple values."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={"a": 1, "b": 2}
            )
            
            flat = var.flatten_values()
            assert flat == {"a": 1, "b": 2}
        
        def test_flatten_nested(self):
            """Test flattening nested values."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={
                    "task": {
                        "name": "Task",
                        "config": {"timeout": 30}
                    },
                    "items": ["a", "b"]
                }
            )
            
            flat = var.flatten_values()
            assert flat["task.name"] == "Task"
            assert flat["task.config.timeout"] == 30
            assert flat["items"] == ["a", "b"]
        
        def test_list_paths(self):
            """Test listing all paths."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={
                    "task": {"name": "Task"},
                    "config": {"debug": True}
                }
            )
            
            paths = var.list_paths()
            assert "task.name" in paths
            assert "config.debug" in paths
    
    class TestClear:
        """Test clearing values."""
        
        def test_clear_values(self):
            """Test clearing all values."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={"key": "value", "num": 42}
            )
            
            var.clear_values()
            
            assert var.values == {}
        
        def test_clear_updates_timestamp(self):
            """Test clearing updates timestamp."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                values={"key": "value"}
            )
            # Set to old timestamp
            var.updated_at = "2026-01-01T00:00:00Z"
            old_updated = var.updated_at
            
            var.clear_values()
            
            assert var.updated_at != old_updated
    
    class TestWorkflowReference:
        """Test workflow reference methods."""
        
        def test_update_for_workflow(self):
            """Test updating workflow reference."""
            var = VariableConfig.create(
                code="test",
                name="Test",
                for_workflow="old-workflow"
            )
            # Set to old timestamp
            var.updated_at = "2026-01-01T00:00:00Z"
            old_updated = var.updated_at
            
            var.update_for_workflow("new-workflow")
            
            assert var.for_workflow == "new-workflow"
            assert var.updated_at != old_updated
    
    class TestYamlFile:
        """Test YAML file operations."""
        
        def test_from_yaml_file(self, tmp_path):
            """Test loading from YAML file."""
            yaml_content = """
apiVersion: zima.io/v1
kind: Variable
metadata:
  code: yaml-test
  name: YAML Test
spec:
  forWorkflow: my-workflow
  values:
    task:
      name: From YAML
"""
            yaml_file = tmp_path / "test.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")
            
            var = VariableConfig.from_yaml_file(yaml_file)
            
            assert var.metadata.code == "yaml-test"
            assert var.for_workflow == "my-workflow"
            assert var.values["task"]["name"] == "From YAML"
        
        def test_from_yaml_file_not_found(self, tmp_path):
            """Test loading nonexistent file raises error."""
            with pytest.raises(FileNotFoundError):
                VariableConfig.from_yaml_file(tmp_path / "nonexistent.yaml")
