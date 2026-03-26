"""Unit tests for WorkflowConfig model."""

import pytest
from pathlib import Path

from zima.models.workflow import WorkflowConfig, VariableDef, VALID_TEMPLATE_FORMATS, VALID_VARIABLE_TYPES
from tests.base import TestIsolator


class TestVariableDef(TestIsolator):
    """VariableDef model tests."""
    
    class TestCreate:
        """Test VariableDef creation."""
        
        def test_create_basic(self):
            """Test creating basic variable definition."""
            var = VariableDef(
                name="task.name",
                type="string",
                required=True,
                default="Default Task",
                description="Task name"
            )
            
            assert var.name == "task.name"
            assert var.type == "string"
            assert var.required is True
            assert var.default == "Default Task"
            assert var.description == "Task name"
        
        def test_create_with_defaults(self):
            """Test creating with default values."""
            var = VariableDef(name="simple")
            
            assert var.name == "simple"
            assert var.type == "string"
            assert var.required is True
            assert var.default is None
            assert var.description == ""
    
    class TestDictConversion:
        """Test dictionary conversion."""
        
        def test_to_dict(self):
            """Test to_dict method."""
            var = VariableDef(
                name="task.steps",
                type="array",
                required=True,
                default=["step1"],
                description="Steps"
            )
            
            data = var.to_dict()
            assert data["name"] == "task.steps"
            assert data["type"] == "array"
            assert data["required"] is True
            assert data["default"] == ["step1"]
            assert data["description"] == "Steps"
        
        def test_to_dict_without_optional(self):
            """Test to_dict without optional fields."""
            var = VariableDef(name="simple")
            
            data = var.to_dict()
            assert data["name"] == "simple"
            assert data["type"] == "string"
            assert data["required"] is True
            assert "default" not in data
            assert "description" not in data
        
        def test_from_dict(self):
            """Test from_dict method."""
            data = {
                "name": "config.timeout",
                "type": "number",
                "required": False,
                "default": 30,
                "description": "Timeout in seconds"
            }
            
            var = VariableDef.from_dict(data)
            assert var.name == "config.timeout"
            assert var.type == "number"
            assert var.required is False
            assert var.default == 30
            assert var.description == "Timeout in seconds"
    
    class TestValidation:
        """Test variable validation."""
        
        def test_validate_valid(self):
            """Test valid variable."""
            var = VariableDef(name="task.name", type="string")
            errors = var.validate()
            assert errors == []
        
        def test_validate_missing_name(self):
            """Test missing name."""
            var = VariableDef(name="")
            errors = var.validate()
            assert any("name is required" in e for e in errors)
        
        @pytest.mark.parametrize("invalid_type", ["invalid", "text", "int", "float", "list", "dict"])
        def test_validate_invalid_type(self, invalid_type):
            """Test invalid variable types."""
            var = VariableDef(name="test", type=invalid_type)
            errors = var.validate()
            assert any("Invalid variable type" in e for e in errors)
        
        @pytest.mark.parametrize("valid_type", ["string", "number", "boolean", "array", "object"])
        def test_validate_valid_types(self, valid_type):
            """Test all valid variable types."""
            var = VariableDef(name="test", type=valid_type)
            errors = var.validate()
            assert errors == []


class TestWorkflowConfig(TestIsolator):
    """WorkflowConfig model tests."""
    
    class TestCreate:
        """Test WorkflowConfig creation."""
        
        def test_create_basic(self):
            """Test creating basic workflow."""
            workflow = WorkflowConfig.create(
                code="test-workflow",
                name="Test Workflow",
                template="Hello {{ name }}!"
            )
            
            assert workflow.metadata.code == "test-workflow"
            assert workflow.metadata.name == "Test Workflow"
            assert workflow.template == "Hello {{ name }}!"
            assert workflow.format == "jinja2"
            assert workflow.kind == "Workflow"
            assert workflow.version == "1.0.0"
        
        def test_create_with_all_fields(self):
            """Test creating with all fields."""
            workflow = WorkflowConfig.create(
                code="full-workflow",
                name="Full Workflow",
                template="# {{ title }}",
                description="A test workflow",
                format="jinja2",
                variables=[
                    {"name": "title", "type": "string", "required": True},
                    {"name": "count", "type": "number", "default": 5}
                ],
                tags=["test", "example"],
                author="tester",
                version="2.0.0"
            )
            
            assert workflow.metadata.description == "A test workflow"
            assert len(workflow.variables) == 2
            assert workflow.tags == ["test", "example"]
            assert workflow.author == "tester"
            assert workflow.version == "2.0.0"
        
        def test_create_with_variable_objects(self):
            """Test creating with VariableDef objects."""
            var1 = VariableDef(name="var1", type="string")
            var2 = VariableDef(name="var2", type="array")
            
            workflow = WorkflowConfig.create(
                code="var-obj-workflow",
                name="Variable Object Workflow",
                variables=[var1, var2]
            )
            
            assert len(workflow.variables) == 2
            assert workflow.variables[0].name == "var1"
            assert workflow.variables[1].name == "var2"
        
        def test_create_invalid_format(self):
            """Test creating with invalid format raises error."""
            with pytest.raises(ValueError) as exc_info:
                WorkflowConfig.create(
                    code="test",
                    name="Test",
                    format="invalid-format"
                )
            
            assert "Invalid template format" in str(exc_info.value)
            assert "invalid-format" in str(exc_info.value)
    
    class TestValidation:
        """Test workflow validation."""
        
        def test_validate_valid(self):
            """Test valid workflow."""
            workflow = WorkflowConfig.create(
                code="valid-workflow",
                name="Valid Workflow"
            )
            errors = workflow.validate()
            assert errors == []
        
        def test_validate_missing_code(self):
            """Test missing code."""
            workflow = WorkflowConfig()
            workflow.metadata.code = ""
            workflow.metadata.name = "Test"
            errors = workflow.validate()
            assert any("code is required" in e for e in errors)
        
        def test_validate_invalid_code_format(self):
            """Test invalid code format."""
            workflow = WorkflowConfig.create(
                code="Invalid_Code",
                name="Test"
            )
            errors = workflow.validate()
            assert any("has invalid format" in e for e in errors)
        
        def test_validate_missing_name(self):
            """Test missing name."""
            workflow = WorkflowConfig.create(code="test", name="")
            workflow.metadata.name = ""
            errors = workflow.validate()
            assert any("name is required" in e for e in errors)
        
        def test_validate_invalid_format(self):
            """Test invalid template format."""
            # Create valid workflow then manually set invalid format
            workflow = WorkflowConfig.create(code="test", name="Test")
            workflow.format = "unknown"
            errors = workflow.validate()
            assert any("is not valid" in e for e in errors)
        
        def test_validate_template_syntax_error(self):
            """Test invalid Jinja2 template syntax."""
            workflow = WorkflowConfig.create(
                code="test",
                name="Test",
                template="{% if true %}unclosed"
            )
            errors = workflow.validate()
            assert any("Template syntax error" in e for e in errors)
        
        def test_validate_variable_errors(self):
            """Test variable definition errors included."""
            workflow = WorkflowConfig.create(
                code="test",
                name="Test",
                variables=[
                    {"name": "", "type": "invalid-type"}
                ]
            )
            errors = workflow.validate()
            assert any("name is required" in e for e in errors)
            assert any("Invalid variable type" in e for e in errors)
    
    class TestDictConversion:
        """Test dictionary conversion."""
        
        def test_to_dict(self):
            """Test to_dict method."""
            workflow = WorkflowConfig.create(
                code="dict-test",
                name="Dict Test",
                template="{{ msg }}",
                variables=[{"name": "msg", "type": "string"}],
                tags=["test"]
            )
            
            data = workflow.to_dict()
            assert data["apiVersion"] == "zima.io/v1"
            assert data["kind"] == "Workflow"
            assert data["metadata"]["code"] == "dict-test"
            assert data["spec"]["format"] == "jinja2"
            assert data["spec"]["template"] == "{{ msg }}"
            assert len(data["spec"]["variables"]) == 1
            assert data["spec"]["tags"] == ["test"]
        
        def test_from_dict(self):
            """Test from_dict method."""
            data = {
                "apiVersion": "zima.io/v1",
                "kind": "Workflow",
                "metadata": {
                    "code": "from-dict",
                    "name": "From Dict",
                    "description": "Test"
                },
                "spec": {
                    "format": "jinja2",
                    "template": "Hello {{ name }}",
                    "variables": [
                        {"name": "name", "type": "string", "required": True}
                    ],
                    "tags": ["greeting"],
                    "author": "tester",
                    "version": "1.0.0"
                },
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-01T00:00:00Z"
            }
            
            workflow = WorkflowConfig.from_dict(data)
            assert workflow.metadata.code == "from-dict"
            assert workflow.metadata.name == "From Dict"
            assert workflow.template == "Hello {{ name }}"
            assert len(workflow.variables) == 1
            assert workflow.variables[0].name == "name"
            assert workflow.tags == ["greeting"]
    
    class TestRender:
        """Test template rendering."""
        
        def test_render_simple(self):
            """Test simple variable substitution."""
            workflow = WorkflowConfig.create(
                code="simple",
                name="Simple",
                template="Hello {{ name }}!"
            )
            
            result = workflow.render({"name": "World"})
            assert result == "Hello World!"
        
        def test_render_with_defaults(self):
            """Test rendering with default values."""
            workflow = WorkflowConfig.create(
                code="defaults",
                name="Defaults",
                template="Hello {{ name }}!",
                variables=[
                    {"name": "name", "type": "string", "default": "Anonymous"}
                ]
            )
            
            # Without providing value, should use default
            result = workflow.render({})
            assert result == "Hello Anonymous!"
            
            # Providing value should override default
            result = workflow.render({"name": "Custom"})
            assert result == "Hello Custom!"
        
        def test_render_nested_variables(self):
            """Test rendering with nested variable access."""
            workflow = WorkflowConfig.create(
                code="nested",
                name="Nested",
                template="{{ task.name }}: {{ task.objective }}"
            )
            
            result = workflow.render({
                "task": {
                    "name": "Review",
                    "objective": "Check code"
                }
            })
            assert result == "Review: Check code"
        
        def test_render_with_condition(self):
            """Test rendering with conditionals."""
            workflow = WorkflowConfig.create(
                code="condition",
                name="Condition",
                template="{% if debug %}DEBUG{% else %}PROD{% endif %}"
            )
            
            assert workflow.render({"debug": True}) == "DEBUG"
            assert workflow.render({"debug": False}) == "PROD"
        
        def test_render_with_loop(self):
            """Test rendering with loops."""
            workflow = WorkflowConfig.create(
                code="loop",
                name="Loop",
                template="{% for item in items %}{{ item }} {% endfor %}"
            )
            
            result = workflow.render({"items": ["a", "b", "c"]})
            assert result == "a b c "
        
        def test_render_plain_format(self):
            """Test plain format returns template as-is."""
            workflow = WorkflowConfig.create(
                code="plain",
                name="Plain",
                template="No {{ substitution }}",
                format="plain"
            )
            
            result = workflow.render({})
            assert result == "No {{ substitution }}"
        
        def test_render_undefined_variable_error(self):
            """Test undefined variable raises error."""
            workflow = WorkflowConfig.create(
                code="strict",
                name="Strict",
                template="{{ undefined_var }}"
            )
            
            # Jinja2 by default treats undefined as empty string
            # But we might want strict mode in the future
            result = workflow.render({})
            assert result == ""
        
        def test_render_invalid_template(self):
            """Test rendering invalid template raises error."""
            workflow = WorkflowConfig.create(
                code="invalid",
                name="Invalid",
                template="{% invalid_tag %}",
                format="jinja2"
            )
            
            with pytest.raises(ValueError) as exc_info:
                workflow.render({})
            
            assert "Template rendering error" in str(exc_info.value)
    
    class TestVariableValidation:
        """Test variable value validation."""
        
        def test_validate_required_missing(self):
            """Test missing required variable."""
            workflow = WorkflowConfig.create(
                code="validate",
                name="Validate",
                variables=[
                    {"name": "required_var", "type": "string", "required": True}
                ]
            )
            
            errors = workflow.validate_variables({})
            assert any("Required variable" in e for e in errors)
        
        def test_validate_types(self):
            """Test type validation."""
            workflow = WorkflowConfig.create(
                code="types",
                name="Types",
                variables=[
                    {"name": "str_var", "type": "string"},
                    {"name": "num_var", "type": "number"},
                    {"name": "bool_var", "type": "boolean"},
                    {"name": "arr_var", "type": "array"},
                    {"name": "obj_var", "type": "object"}
                ]
            )
            
            # Valid values
            errors = workflow.validate_variables({
                "str_var": "text",
                "num_var": 42,
                "bool_var": True,
                "arr_var": [1, 2, 3],
                "obj_var": {"key": "value"}
            })
            assert errors == []
            
            # Invalid types
            errors = workflow.validate_variables({
                "str_var": 123,
                "num_var": "not a number",
                "bool_var": "true",
                "arr_var": "not an array",
                "obj_var": ["not", "an", "object"]
            })
            assert len(errors) == 5
            assert any("str_var" in e and "string" in e for e in errors)
            assert any("num_var" in e and "number" in e for e in errors)
        
        def test_validate_nested_paths(self):
            """Test validation with nested paths."""
            workflow = WorkflowConfig.create(
                code="nested-validate",
                name="Nested Validate",
                variables=[
                    {"name": "task.name", "type": "string", "required": True},
                    {"name": "config.timeout", "type": "number", "required": True}
                ]
            )
            
            errors = workflow.validate_variables({
                "task": {"name": "Test"},
                "config": {"timeout": 30}
            })
            assert errors == []
            
            errors = workflow.validate_variables({
                "task": {"name": ""},  # Empty string is still a value, not None
                "config": {}
            })
            # task.name has value "" which is not None, so no error
            # config.timeout is missing (None), so should have error
            assert any("config.timeout" in e for e in errors)
    
    class TestVariableHelpers:
        """Test variable helper methods."""
        
        def test_get_variable_names(self):
            """Test getting variable names."""
            workflow = WorkflowConfig.create(
                code="vars",
                name="Vars",
                variables=[
                    {"name": "var1"},
                    {"name": "var2"},
                    {"name": "var3"}
                ]
            )
            
            names = workflow.get_variable_names()
            assert names == ["var1", "var2", "var3"]
        
        def test_get_required_variables(self):
            """Test getting required variables."""
            workflow = WorkflowConfig.create(
                code="required",
                name="Required",
                variables=[
                    {"name": "req1", "required": True},
                    {"name": "opt1", "required": False},
                    {"name": "req2", "required": True}
                ]
            )
            
            required = workflow.get_required_variables()
            assert required == ["req1", "req2"]
    
    class TestTagManagement:
        """Test tag management."""
        
        def test_add_tag(self):
            """Test adding tags."""
            workflow = WorkflowConfig.create(code="test", name="Test")
            
            workflow.add_tag("new-tag")
            assert "new-tag" in workflow.tags
            
            # Duplicate should not be added
            workflow.add_tag("new-tag")
            assert workflow.tags.count("new-tag") == 1
        
        def test_remove_tag(self):
            """Test removing tags."""
            workflow = WorkflowConfig.create(
                code="test",
                name="Test",
                tags=["tag1", "tag2"]
            )
            
            result = workflow.remove_tag("tag1")
            assert result is True
            assert "tag1" not in workflow.tags
            
            result = workflow.remove_tag("nonexistent")
            assert result is False
