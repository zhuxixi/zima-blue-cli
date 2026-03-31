"""Integration tests for PMG CLI commands."""

import pytest
from typer.testing import CliRunner
from zima.cli import app
from tests.base import TestIsolator
from tests.conftest import strip_ansi


runner = CliRunner()


class TestPMGCreate(TestIsolator):
    """Test pmg create command."""
    
    def test_create_basic(self):
        """Test creating basic PMG."""
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "test-pmg",
            "--name", "Test PMG",
            "--for-type", "kimi"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "test-pmg" in result.output
        assert "kimi" in result.output
    
    def test_create_with_multiple_types(self):
        """Test creating PMG for multiple types."""
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "multi-pmg",
            "--name", "Multi PMG",
            "--for-type", "kimi",
            "--for-type", "claude"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
    
    def test_create_duplicate_code_fails(self):
        """Test creating with duplicate code fails."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "duplicate-pmg",
            "--name", "First",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "duplicate-pmg",
            "--name", "Second",
            "--for-type", "kimi"
        ])
        
        assert result.exit_code != 0
        assert "already exists" in result.output
    
    def test_create_invalid_code_fails(self):
        """Test creating with invalid code fails."""
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "Invalid_Code",
            "--name", "Test",
            "--for-type", "kimi"
        ])
        
        assert result.exit_code != 0
        assert "Invalid code" in result.output
    
    def test_create_invalid_type_fails(self):
        """Test creating with invalid type fails."""
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "test",
            "--name", "Test",
            "--for-type", "invalid"
        ])
        
        assert result.exit_code != 0
        assert "Invalid type" in result.output
    
    def test_create_from_existing(self):
        """Test creating from existing PMG."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "source-pmg",
            "--name", "Source",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "copied-pmg",
            "--name", "Copied",
            "--for-type", "kimi",
            "--from", "source-pmg"
        ])
        
        assert result.exit_code == 0
        assert "created from" in result.output
    
    def test_create_from_nonexistent_fails(self):
        """Test creating from nonexistent PMG fails."""
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "new-pmg",
            "--name", "New",
            "--for-type", "kimi",
            "--from", "nonexistent"
        ])
        
        assert result.exit_code != 0
        assert "not found" in result.output


class TestPMGList(TestIsolator):
    """Test pmg list command."""
    
    def test_list_empty(self):
        """Test listing when no PMGs exist."""
        result = runner.invoke(app, ["pmg", "list"])
        
        assert result.exit_code == 0
        assert "No PMGs found" in result.output
    
    def test_list_with_pmgs(self):
        """Test listing PMGs."""
        for i in range(3):
            runner.invoke(app, [
                "pmg", "create",
                "--code", f"pmg-{i}",
                "--name", f"PMG {i}",
                "--for-type", "kimi"
            ])
        
        result = runner.invoke(app, ["pmg", "list"])
        
        assert result.exit_code == 0
        for i in range(3):
            assert f"pmg-{i}" in result.output
            assert f"PMG {i}" in result.output
    
    def test_list_filter_by_type(self):
        """Test listing with type filter."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "kimi-pmg",
            "--name", "Kimi PMG",
            "--for-type", "kimi"
        ])
        
        runner.invoke(app, [
            "pmg", "create",
            "--code", "claude-pmg",
            "--name", "Claude PMG",
            "--for-type", "claude"
        ])
        
        result = runner.invoke(app, ["pmg", "list", "--for-type", "kimi"])
        
        assert result.exit_code == 0
        assert "kimi-pmg" in result.output
        assert "claude-pmg" not in result.output


class TestPMGShow(TestIsolator):
    """Test pmg show command."""
    
    def test_show_existing(self):
        """Test showing existing PMG."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "show-test",
            "--name", "Show Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, ["pmg", "show", "show-test"])
        
        assert result.exit_code == 0
        assert "show-test" in result.output
        assert "Show Test" in result.output
    
    def test_show_nonexistent(self):
        """Test showing nonexistent PMG."""
        result = runner.invoke(app, ["pmg", "show", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output
    
    def test_show_json_format(self):
        """Test showing in JSON format."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "json-pmg",
            "--name", "JSON Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "show", "json-pmg",
            "--format", "json"
        ])
        
        assert result.exit_code == 0
        assert '"code": "json-pmg"' in result.output or '"json-pmg"' in result.output


class TestPMGUpdate(TestIsolator):
    """Test pmg update command."""
    
    def test_update_name(self):
        """Test updating name."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "update-test",
            "--name", "Original Name",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "update", "update-test",
            "--name", "Updated Name"
        ])
        
        assert result.exit_code == 0
        assert "updated" in result.output
        
        result = runner.invoke(app, ["pmg", "show", "update-test"])
        assert "Updated Name" in result.output
    
    def test_update_raw(self):
        """Test updating raw string."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "raw-test",
            "--name", "Raw Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "update", "raw-test",
            "--raw", "--experimental"
        ])
        
        assert result.exit_code == 0
        assert "updated" in result.output
    
    def test_update_no_changes(self):
        """Test update with no changes."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "no-change",
            "--name", "No Change",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, ["pmg", "update", "no-change"])
        
        assert result.exit_code == 0
        assert "No changes" in result.output


class TestPMGDelete(TestIsolator):
    """Test pmg delete command."""
    
    def test_delete_existing(self):
        """Test deleting existing PMG."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "delete-test",
            "--name", "Delete Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "delete", "delete-test", "--force"
        ])
        
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
        
        result = runner.invoke(app, ["pmg", "show", "delete-test"])
        assert result.exit_code != 0
    
    def test_delete_nonexistent(self):
        """Test deleting nonexistent PMG."""
        result = runner.invoke(app, [
            "pmg", "delete", "nonexistent", "--force"
        ])
        
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPMGValidate(TestIsolator):
    """Test pmg validate command."""
    
    def test_validate_valid(self):
        """Test validating valid PMG."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "valid-pmg",
            "--name", "Valid PMG",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, ["pmg", "validate", "valid-pmg"])
        
        assert result.exit_code == 0
        assert "is valid" in result.output
    
    def test_validate_nonexistent(self):
        """Test validating nonexistent PMG."""
        result = runner.invoke(app, ["pmg", "validate", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output


class TestPMGAddParam(TestIsolator):
    """Test pmg add-param command."""
    
    def test_add_long_param(self):
        """Test adding long parameter."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "add-param-test",
            "--name", "Add Param Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "add-param", "add-param-test",
            "--name", "model",
            "--type", "long",
            "--value", "gpt-4"
        ])
        
        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "Parameter 'model' added" in clean

    def test_add_flag_param(self):
        """Test adding flag parameter."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "flag-test",
            "--name", "Flag Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "add-param", "flag-test",
            "--name", "verbose",
            "--type", "flag",
            "--enabled"
        ])
        
        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "Parameter 'verbose' added" in clean

    def test_add_repeatable_param(self):
        """Test adding repeatable parameter."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "repeatable-test",
            "--name", "Repeatable Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "add-param", "repeatable-test",
            "--name", "add-dir",
            "--type", "repeatable",
            "--values", "./src,./tests"
        ])
        
        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "Parameter 'add-dir' added" in clean

    def test_add_invalid_type_fails(self):
        """Test adding parameter with invalid type fails."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "invalid-type-test",
            "--name", "Invalid Type Test",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "add-param", "invalid-type-test",
            "--name", "test",
            "--type", "invalid",
            "--value", "test"
        ])
        
        assert result.exit_code != 0
        assert "Invalid type" in result.output


class TestPMGRemoveParam(TestIsolator):
    """Test pmg remove-param command."""
    
    def test_remove_existing(self):
        """Test removing existing parameter."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "remove-test",
            "--name", "Remove Test",
            "--for-type", "kimi"
        ])
        runner.invoke(app, [
            "pmg", "add-param", "remove-test",
            "--name", "to-remove",
            "--type", "flag",
            "--enabled"
        ])
        
        result = runner.invoke(app, [
            "pmg", "remove-param", "remove-test",
            "--name", "to-remove"
        ])
        
        assert result.exit_code == 0
        assert "removed" in result.output
    
    def test_remove_nonexistent(self):
        """Test removing nonexistent parameter."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "remove-none",
            "--name", "Remove None",
            "--for-type", "kimi"
        ])
        
        result = runner.invoke(app, [
            "pmg", "remove-param", "remove-none",
            "--name", "nonexistent"
        ])
        
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestPMGBuild(TestIsolator):
    """Test pmg build command."""
    
    def test_build_list_format(self):
        """Test building in list format."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "build-test",
            "--name", "Build Test",
            "--for-type", "kimi"
        ])
        runner.invoke(app, [
            "pmg", "add-param", "build-test",
            "--name", "model",
            "--type", "long",
            "--value", "gpt-4"
        ])
        
        result = runner.invoke(app, [
            "pmg", "build", "build-test",
            "--format", "list"
        ])
        
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "gpt-4" in result.output
    
    def test_build_shell_format(self):
        """Test building in shell format."""
        runner.invoke(app, [
            "pmg", "create",
            "--code", "build-shell",
            "--name", "Build Shell",
            "--for-type", "kimi"
        ])
        runner.invoke(app, [
            "pmg", "add-param", "build-shell",
            "--name", "verbose",
            "--type", "flag",
            "--enabled"
        ])
        
        result = runner.invoke(app, [
            "pmg", "build", "build-shell",
            "--format", "shell"
        ])
        
        assert result.exit_code == 0
        assert "--verbose" in result.output


class TestPMGLifecycle(TestIsolator):
    """Test complete PMG lifecycle."""
    
    def test_full_lifecycle(self):
        """Test complete PMG lifecycle."""
        # Create
        result = runner.invoke(app, [
            "pmg", "create",
            "--code", "lifecycle-pmg",
            "--name", "Lifecycle PMG",
            "--for-type", "kimi",
            "--description", "For lifecycle testing"
        ])
        assert result.exit_code == 0
        
        # Add parameters
        result = runner.invoke(app, [
            "pmg", "add-param", "lifecycle-pmg",
            "--name", "model",
            "--type", "long",
            "--value", "kimi-k2"
        ])
        assert result.exit_code == 0
        
        result = runner.invoke(app, [
            "pmg", "add-param", "lifecycle-pmg",
            "--name", "verbose",
            "--type", "flag",
            "--enabled"
        ])
        assert result.exit_code == 0
        
        # List
        result = runner.invoke(app, ["pmg", "list"])
        assert result.exit_code == 0
        assert "lifecycle-pmg" in result.output
        
        # Show
        result = runner.invoke(app, ["pmg", "show", "lifecycle-pmg"])
        assert result.exit_code == 0
        assert "Lifecycle PMG" in result.output
        
        # Validate
        result = runner.invoke(app, ["pmg", "validate", "lifecycle-pmg"])
        assert result.exit_code == 0
        
        # Build
        result = runner.invoke(app, [
            "pmg", "build", "lifecycle-pmg",
            "--format", "shell"
        ])
        assert result.exit_code == 0
        assert "--model" in result.output
        assert "--verbose" in result.output
        
        # Update
        result = runner.invoke(app, [
            "pmg", "update", "lifecycle-pmg",
            "--name", "Updated Lifecycle"
        ])
        assert result.exit_code == 0
        
        # Remove parameter
        result = runner.invoke(app, [
            "pmg", "remove-param", "lifecycle-pmg",
            "--name", "verbose"
        ])
        assert result.exit_code == 0
        
        # Delete
        result = runner.invoke(app, [
            "pmg", "delete", "lifecycle-pmg", "--force"
        ])
        assert result.exit_code == 0
        
        # Verify deletion
        result = runner.invoke(app, ["pmg", "show", "lifecycle-pmg"])
        assert result.exit_code != 0
