"""Integration tests for Workflow CLI commands."""

import pytest
from typer.testing import CliRunner
from zima.cli import app
from tests.base import TestIsolator


runner = CliRunner()


class TestWorkflowCreate(TestIsolator):
    """Test workflow create command."""
    
    def test_create_basic(self):
        """Test creating basic workflow."""
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "test-workflow",
            "--name", "Test Workflow"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "test-workflow" in result.output
        assert "jinja2" in result.output
    
    def test_create_with_template(self):
        """Test creating workflow with template."""
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "greeting",
            "--name", "Greeting Workflow",
            "--template", "Hello {{ name }}!",
            "--format", "jinja2"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
    
    def test_create_duplicate_code_fails(self):
        """Test creating workflow with duplicate code fails."""
        # Create first
        runner.invoke(app, [
            "workflow", "create",
            "--code", "duplicate-wf",
            "--name", "First"
        ])
        
        # Try to create second with same code
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "duplicate-wf",
            "--name", "Second"
        ])
        
        assert result.exit_code != 0
        assert "already exists" in result.output
    
    def test_create_invalid_code_fails(self):
        """Test creating workflow with invalid code fails."""
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "Invalid_Code",
            "--name", "Test"
        ])
        
        assert result.exit_code != 0
        assert "Invalid code" in result.output
    
    def test_create_invalid_format_fails(self):
        """Test creating workflow with invalid format fails."""
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "test",
            "--name", "Test",
            "--format", "invalid"
        ])
        
        assert result.exit_code != 0
        assert "Invalid format" in result.output
    
    def test_create_from_existing(self):
        """Test creating workflow from existing."""
        # Create source
        runner.invoke(app, [
            "workflow", "create",
            "--code", "source-wf",
            "--name", "Source",
            "--template", "Source Template"
        ])
        
        # Copy
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "copied-wf",
            "--name", "Copied",
            "--from", "source-wf"
        ])
        
        assert result.exit_code == 0
        assert "created from" in result.output
        
        # Verify copy worked
        result = runner.invoke(app, ["workflow", "show", "copied-wf"])
        assert "Source Template" in result.output
    
    def test_create_from_nonexistent_fails(self):
        """Test creating from nonexistent workflow fails."""
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "new-wf",
            "--name", "New",
            "--from", "nonexistent"
        ])
        
        assert result.exit_code != 0
        assert "not found" in result.output


class TestWorkflowList(TestIsolator):
    """Test workflow list command."""
    
    def test_list_empty(self):
        """Test listing when no workflows exist."""
        result = runner.invoke(app, ["workflow", "list"])
        
        assert result.exit_code == 0
        assert "No workflows found" in result.output
    
    def test_list_with_workflows(self):
        """Test listing workflows."""
        # Create some workflows
        for i in range(3):
            runner.invoke(app, [
                "workflow", "create",
                "--code", f"wf-{i}",
                "--name", f"Workflow {i}"
            ])
        
        result = runner.invoke(app, ["workflow", "list"])
        
        assert result.exit_code == 0
        for i in range(3):
            assert f"wf-{i}" in result.output
            assert f"Workflow {i}" in result.output
    
    def test_list_filter_by_tag(self):
        """Test listing with tag filter."""
        # Create workflows with different tags
        runner.invoke(app, [
            "workflow", "create",
            "--code", "tagged-wf",
            "--name", "Tagged"
        ])
        runner.invoke(app, [
            "workflow", "update", "tagged-wf",
            "--add-tag", "test-tag"
        ])
        
        runner.invoke(app, [
            "workflow", "create",
            "--code", "untagged-wf",
            "--name", "Untagged"
        ])
        
        result = runner.invoke(app, ["workflow", "list", "--tag", "test-tag"])
        
        assert result.exit_code == 0
        assert "tagged-wf" in result.output
        assert "untagged-wf" not in result.output


class TestWorkflowShow(TestIsolator):
    """Test workflow show command."""
    
    def test_show_existing(self):
        """Test showing existing workflow."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "show-test",
            "--name", "Show Test",
            "--template", "Test Template"
        ])
        
        result = runner.invoke(app, ["workflow", "show", "show-test"])
        
        assert result.exit_code == 0
        assert "show-test" in result.output
        assert "Show Test" in result.output
    
    def test_show_nonexistent(self):
        """Test showing nonexistent workflow."""
        result = runner.invoke(app, ["workflow", "show", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output
    
    def test_show_json_format(self):
        """Test showing workflow in JSON format."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "json-test",
            "--name", "JSON Test"
        ])
        
        result = runner.invoke(app, [
            "workflow", "show", "json-test",
            "--format", "json"
        ])
        
        assert result.exit_code == 0
        assert '"code": "json-test"' in result.output or '"json-test"' in result.output


class TestWorkflowUpdate(TestIsolator):
    """Test workflow update command."""
    
    def test_update_name(self):
        """Test updating workflow name."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "update-test",
            "--name", "Original Name"
        ])
        
        result = runner.invoke(app, [
            "workflow", "update", "update-test",
            "--name", "Updated Name"
        ])
        
        assert result.exit_code == 0
        assert "updated" in result.output
        
        # Verify update
        result = runner.invoke(app, ["workflow", "show", "update-test"])
        assert "Updated Name" in result.output
    
    def test_update_add_tags(self):
        """Test adding tags."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "tag-test",
            "--name", "Tag Test"
        ])
        
        result = runner.invoke(app, [
            "workflow", "update", "tag-test",
            "--add-tag", "tag1",
            "--add-tag", "tag2"
        ])
        
        assert result.exit_code == 0
        assert "tag1" in result.output or "tag2" in result.output
    
    def test_update_no_changes(self):
        """Test update with no changes."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "no-change",
            "--name", "No Change"
        ])
        
        result = runner.invoke(app, ["workflow", "update", "no-change"])
        
        assert result.exit_code == 0
        assert "No changes" in result.output


class TestWorkflowDelete(TestIsolator):
    """Test workflow delete command."""
    
    def test_delete_existing(self):
        """Test deleting existing workflow."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "delete-test",
            "--name", "Delete Test"
        ])
        
        result = runner.invoke(app, [
            "workflow", "delete", "delete-test", "--force"
        ])
        
        assert result.exit_code == 0
        assert "deleted" in result.output
        
        # Verify deletion
        result = runner.invoke(app, ["workflow", "show", "delete-test"])
        assert result.exit_code != 0
    
    def test_delete_nonexistent(self):
        """Test deleting nonexistent workflow."""
        result = runner.invoke(app, [
            "workflow", "delete", "nonexistent", "--force"
        ])
        
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestWorkflowValidate(TestIsolator):
    """Test workflow validate command."""
    
    def test_validate_valid(self):
        """Test validating valid workflow."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "valid-wf",
            "--name", "Valid Workflow"
        ])
        
        result = runner.invoke(app, ["workflow", "validate", "valid-wf"])
        
        assert result.exit_code == 0
        assert "is valid" in result.output
    
    def test_validate_nonexistent(self):
        """Test validating nonexistent workflow."""
        result = runner.invoke(app, ["workflow", "validate", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output


class TestWorkflowRender(TestIsolator):
    """Test workflow render command."""
    
    def test_render_simple(self):
        """Test rendering simple template."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "render-test",
            "--name", "Render Test",
            "--template", "Hello {{ name }}!"
        ])
        
        result = runner.invoke(app, [
            "workflow", "render", "render-test",
            "--var", "name=World"
        ])
        
        assert result.exit_code == 0
        assert "Hello World!" in result.output
    
    def test_render_with_variable_config(self):
        """Test rendering with variable config."""
        # Create workflow
        runner.invoke(app, [
            "workflow", "create",
            "--code", "wf-with-vars",
            "--name", "WF with Vars",
            "--template", "Task: {{ task.name }}"
        ])
        
        # Create variable config
        runner.invoke(app, [
            "variable", "create",
            "--code", "my-vars",
            "--name", "My Variables"
        ])
        runner.invoke(app, [
            "variable", "set", "my-vars",
            "--key", "task.name",
            "--value", "Test Task"
        ])
        
        # Render
        result = runner.invoke(app, [
            "workflow", "render", "wf-with-vars",
            "--variable", "my-vars"
        ])
        
        assert result.exit_code == 0
        assert "Task: Test Task" in result.output
    
    def test_render_validation_failure(self):
        """Test render with validation failure."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "validate-render",
            "--name", "Validate Render",
            "--template", "{{ required_var }}"
        ])
        runner.invoke(app, [
            "workflow", "add-var", "validate-render",
            "--name", "required_var",
            "--type", "string",
            "--required"
        ])
        
        result = runner.invoke(app, [
            "workflow", "render", "validate-render"
        ])
        
        assert result.exit_code != 0
        assert "Variable validation failed" in result.output


class TestWorkflowAddVar(TestIsolator):
    """Test workflow add-var command."""
    
    def test_add_variable(self):
        """Test adding variable to workflow."""
        runner.invoke(app, [
            "workflow", "create",
            "--code", "add-var-test",
            "--name", "Add Var Test"
        ])
        
        result = runner.invoke(app, [
            "workflow", "add-var", "add-var-test",
            "--name", "new_var",
            "--type", "string",
            "--required",
            "--default", "default_value"
        ])
        
        assert result.exit_code == 0
        assert "Variable 'new_var' added" in result.output


class TestWorkflowLifecycle(TestIsolator):
    """Test complete workflow lifecycle."""
    
    def test_full_lifecycle(self):
        """Test complete workflow lifecycle."""
        # Create
        result = runner.invoke(app, [
            "workflow", "create",
            "--code", "lifecycle-wf",
            "--name", "Lifecycle Workflow",
            "--template", "Hello {{ name }}!",
            "--description", "For lifecycle testing"
        ])
        assert result.exit_code == 0
        
        # List
        result = runner.invoke(app, ["workflow", "list"])
        assert result.exit_code == 0
        assert "lifecycle-wf" in result.output
        
        # Show
        result = runner.invoke(app, ["workflow", "show", "lifecycle-wf"])
        assert result.exit_code == 0
        assert "Lifecycle Workflow" in result.output
        
        # Validate
        result = runner.invoke(app, ["workflow", "validate", "lifecycle-wf"])
        assert result.exit_code == 0
        
        # Render
        result = runner.invoke(app, [
            "workflow", "render", "lifecycle-wf",
            "--var", "name=World"
        ])
        assert result.exit_code == 0
        assert "Hello World!" in result.output
        
        # Update
        result = runner.invoke(app, [
            "workflow", "update", "lifecycle-wf",
            "--name", "Updated Lifecycle"
        ])
        assert result.exit_code == 0
        
        # Delete
        result = runner.invoke(app, [
            "workflow", "delete", "lifecycle-wf", "--force"
        ])
        assert result.exit_code == 0
        
        # Verify deletion
        result = runner.invoke(app, ["workflow", "show", "lifecycle-wf"])
        assert result.exit_code != 0
