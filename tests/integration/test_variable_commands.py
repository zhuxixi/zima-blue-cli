"""Integration tests for Variable CLI commands."""

import pytest
from typer.testing import CliRunner
from zima.cli import app
from tests.base import TestIsolator
from tests.conftest import strip_ansi


runner = CliRunner()


class TestVariableCreate(TestIsolator):
    """Test variable create command."""
    
    def test_create_basic(self):
        """Test creating basic variable config."""
        result = runner.invoke(app, [
            "variable", "create",
            "--code", "test-vars",
            "--name", "Test Variables"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
    
    def test_create_with_workflow(self):
        """Test creating variable config for specific workflow."""
        # Create workflow first
        runner.invoke(app, [
            "workflow", "create",
            "--code", "target-wf",
            "--name", "Target Workflow"
        ])
        
        result = runner.invoke(app, [
            "variable", "create",
            "--code", "wf-vars",
            "--name", "WF Variables",
            "--for-workflow", "target-wf"
        ])
        
        assert result.exit_code == 0
        assert "Target Workflow" in result.output or "target-wf" in result.output
    
    def test_create_duplicate_code_fails(self):
        """Test creating variable with duplicate code fails."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "duplicate-var",
            "--name", "First"
        ])
        
        result = runner.invoke(app, [
            "variable", "create",
            "--code", "duplicate-var",
            "--name", "Second"
        ])
        
        assert result.exit_code != 0
        assert "already exists" in result.output
    
    def test_create_invalid_workflow_fails(self):
        """Test creating variable for nonexistent workflow fails."""
        result = runner.invoke(app, [
            "variable", "create",
            "--code", "bad-wf-var",
            "--name", "Bad WF Var",
            "--for-workflow", "nonexistent"
        ])
        
        assert result.exit_code != 0
        assert "not found" in result.output
    
    def test_create_from_existing(self):
        """Test creating variable from existing."""
        # Create source
        runner.invoke(app, [
            "variable", "create",
            "--code", "source-var",
            "--name", "Source Var"
        ])
        runner.invoke(app, [
            "variable", "set", "source-var",
            "--key", "key1",
            "--value", "value1"
        ])
        
        # Copy
        result = runner.invoke(app, [
            "variable", "create",
            "--code", "copied-var",
            "--name", "Copied Var",
            "--from", "source-var"
        ])
        
        assert result.exit_code == 0
        assert "created from" in result.output


class TestVariableList(TestIsolator):
    """Test variable list command."""
    
    def test_list_empty(self):
        """Test listing when no variables exist."""
        result = runner.invoke(app, ["variable", "list"])
        
        assert result.exit_code == 0
        assert "No variable configs found" in result.output
    
    def test_list_with_variables(self):
        """Test listing variables."""
        for i in range(3):
            runner.invoke(app, [
                "variable", "create",
                "--code", f"vars-{i}",
                "--name", f"Variables {i}"
            ])
        
        result = runner.invoke(app, ["variable", "list"])
        
        assert result.exit_code == 0
        for i in range(3):
            assert f"vars-{i}" in result.output
    
    def test_list_filter_by_workflow(self):
        """Test listing with workflow filter."""
        # Create workflow
        runner.invoke(app, [
            "workflow", "create",
            "--code", "filter-wf",
            "--name", "Filter WF"
        ])
        
        # Create variable for workflow
        runner.invoke(app, [
            "variable", "create",
            "--code", "wf-specific",
            "--name", "WF Specific",
            "--for-workflow", "filter-wf"
        ])
        
        # Create variable without workflow
        runner.invoke(app, [
            "variable", "create",
            "--code", "generic",
            "--name", "Generic"
        ])
        
        result = runner.invoke(app, [
            "variable", "list",
            "--for-workflow", "filter-wf"
        ])
        
        assert result.exit_code == 0
        assert "wf-specific" in result.output
        assert "generic" not in result.output


class TestVariableShow(TestIsolator):
    """Test variable show command."""
    
    def test_show_existing(self):
        """Test showing existing variable config."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "show-var",
            "--name", "Show Variable"
        ])
        
        result = runner.invoke(app, ["variable", "show", "show-var"])
        
        assert result.exit_code == 0
        assert "show-var" in result.output
        assert "Show Variable" in result.output
    
    def test_show_nonexistent(self):
        """Test showing nonexistent variable config."""
        result = runner.invoke(app, ["variable", "show", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output


class TestVariableUpdate(TestIsolator):
    """Test variable update command."""
    
    def test_update_name(self):
        """Test updating variable config name."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "update-var",
            "--name", "Original Name"
        ])
        
        result = runner.invoke(app, [
            "variable", "update", "update-var",
            "--name", "Updated Name"
        ])
        
        assert result.exit_code == 0
        assert "updated" in result.output
        
        # Verify
        result = runner.invoke(app, ["variable", "show", "update-var"])
        assert "Updated Name" in result.output
    
    def test_update_workflow(self):
        """Test updating target workflow."""
        # Create workflow
        runner.invoke(app, [
            "workflow", "create",
            "--code", "new-wf",
            "--name", "New Workflow"
        ])
        
        runner.invoke(app, [
            "variable", "create",
            "--code", "wf-update",
            "--name", "WF Update"
        ])
        
        result = runner.invoke(app, [
            "variable", "update", "wf-update",
            "--for-workflow", "new-wf"
        ])
        
        assert result.exit_code == 0
        assert "new-wf" in result.output


class TestVariableDelete(TestIsolator):
    """Test variable delete command."""
    
    def test_delete_existing(self):
        """Test deleting existing variable config."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "delete-var",
            "--name", "Delete Variable"
        ])
        
        result = runner.invoke(app, [
            "variable", "delete", "delete-var", "--force"
        ])
        
        assert result.exit_code == 0
        assert "deleted" in result.output
        
        # Verify deletion
        result = runner.invoke(app, ["variable", "show", "delete-var"])
        assert result.exit_code != 0


class TestVariableSet(TestIsolator):
    """Test variable set command."""
    
    def test_set_simple_value(self):
        """Test setting simple value."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "set-test",
            "--name", "Set Test"
        ])
        
        result = runner.invoke(app, [
            "variable", "set", "set-test",
            "--key", "simple_key",
            "--value", "simple_value"
        ])
        
        assert result.exit_code == 0
        assert "simple_key" in result.output
    
    def test_set_nested_value(self):
        """Test setting nested value."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "nested-set",
            "--name", "Nested Set"
        ])
        
        result = runner.invoke(app, [
            "variable", "set", "nested-set",
            "--key", "task.name",
            "--value", "Task Name"
        ])
        
        assert result.exit_code == 0
        assert "task.name" in result.output
    
    def test_set_json_value(self):
        """Test setting JSON value."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "json-set",
            "--name", "JSON Set"
        ])
        
        result = runner.invoke(app, [
            "variable", "set", "json-set",
            "--key", "config",
            "--value", '{"timeout": 30, "retries": 3}'
        ])
        
        assert result.exit_code == 0
        
        # Verify with get
        result = runner.invoke(app, [
            "variable", "get", "json-set", "config"
        ])
        assert "30" in result.output


class TestVariableGet(TestIsolator):
    """Test variable get command."""
    
    def test_get_simple_value(self):
        """Test getting simple value."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "get-test",
            "--name", "Get Test"
        ])
        runner.invoke(app, [
            "variable", "set", "get-test",
            "--key", "my_key",
            "--value", "my_value"
        ])
        
        result = runner.invoke(app, [
            "variable", "get", "get-test", "my_key"
        ])
        
        assert result.exit_code == 0
        assert "my_value" in result.output
    
    def test_get_nested_value(self):
        """Test getting nested value."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "nested-get",
            "--name", "Nested Get"
        ])
        runner.invoke(app, [
            "variable", "set", "nested-get",
            "--key", "task.config.timeout",
            "--value", "60"
        ])
        
        result = runner.invoke(app, [
            "variable", "get", "nested-get", "task.config.timeout"
        ])
        
        assert result.exit_code == 0
        assert "60" in result.output
    
    def test_get_nonexistent(self):
        """Test getting nonexistent key."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "missing-key",
            "--name", "Missing Key"
        ])
        
        result = runner.invoke(app, [
            "variable", "get", "missing-key", "nonexistent"
        ])
        
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestVariableValidate(TestIsolator):
    """Test variable validate command."""
    
    def test_validate_valid(self):
        """Test validating valid variable config."""
        runner.invoke(app, [
            "variable", "create",
            "--code", "valid-var",
            "--name", "Valid Variable"
        ])
        
        result = runner.invoke(app, ["variable", "validate", "valid-var"])
        
        assert result.exit_code == 0
        assert "is valid" in result.output


class TestVariableMerge(TestIsolator):
    """Test variable merge command."""
    
    def test_merge_values(self):
        """Test merging values from another config."""
        # Create source
        runner.invoke(app, [
            "variable", "create",
            "--code", "merge-source",
            "--name", "Merge Source"
        ])
        runner.invoke(app, [
            "variable", "set", "merge-source",
            "--key", "shared_key",
            "--value", "source_value"
        ])
        runner.invoke(app, [
            "variable", "set", "merge-source",
            "--key", "source_only",
            "--value", "only_in_source"
        ])
        
        # Create target
        runner.invoke(app, [
            "variable", "create",
            "--code", "merge-target",
            "--name", "Merge Target"
        ])
        runner.invoke(app, [
            "variable", "set", "merge-target",
            "--key", "shared_key",
            "--value", "target_value"
        ])
        runner.invoke(app, [
            "variable", "set", "merge-target",
            "--key", "target_only",
            "--value", "only_in_target"
        ])
        
        # Merge
        result = runner.invoke(app, [
            "variable", "merge", "merge-target",
            "--from", "merge-source"
        ])
        
        assert result.exit_code == 0
        assert "Merged" in result.output


class TestVariableWorkflowLifecycle(TestIsolator):
    """Test variable with workflow integration."""
    
    def test_variable_workflow_integration(self):
        """Test variable integration with workflow."""
        # Create workflow with variables
        runner.invoke(app, [
            "workflow", "create",
            "--code", "integrated-wf",
            "--name", "Integrated Workflow",
            "--template", "Task: {{ task.name }}, Steps: {{ task.steps | join(', ') }}"
        ])
        runner.invoke(app, [
            "workflow", "add-var", "integrated-wf",
            "--name", "task.name",
            "--type", "string",
            "--required"
        ])
        runner.invoke(app, [
            "workflow", "add-var", "integrated-wf",
            "--name", "task.steps",
            "--type", "array",
            "--required"
        ])
        
        # Create variable config
        runner.invoke(app, [
            "variable", "create",
            "--code", "integrated-vars",
            "--name", "Integrated Variables",
            "--for-workflow", "integrated-wf"
        ])
        runner.invoke(app, [
            "variable", "set", "integrated-vars",
            "--key", "task.name",
            "--value", "Integration Test"
        ])
        runner.invoke(app, [
            "variable", "set", "integrated-vars",
            "--key", "task.steps",
            "--value", '["step1", "step2", "step3"]'
        ])
        
        # Render workflow with variables
        result = runner.invoke(app, [
            "workflow", "render", "integrated-wf",
            "--variable", "integrated-vars"
        ])
        
        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "Task: Integration Test" in clean
        assert "step1, step2, step3" in clean
