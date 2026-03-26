"""Integration tests for agent CLI commands."""

import pytest
from typer.testing import CliRunner

from zima.cli import app
from tests.base import TestIsolator


runner = CliRunner()


class TestAgentCreate(TestIsolator):
    """Test zima agent create command."""
    
    def test_create_kimi_agent(self):
        """Test creating a Kimi agent."""
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Test Kimi Agent",
            "--code", "test-kimi",
            "--type", "kimi"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "test-kimi" in result.output
        assert "kimi" in result.output
    
    def test_create_claude_agent(self):
        """Test creating a Claude agent."""
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Test Claude Agent",
            "--code", "test-claude",
            "--type", "claude"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "claude" in result.output
    
    def test_create_gemini_agent(self):
        """Test creating a Gemini agent."""
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Test Gemini Agent",
            "--code", "test-gemini",
            "--type", "gemini"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "gemini" in result.output
    
    def test_create_with_description(self):
        """Test creating agent with description."""
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Test Agent",
            "--code", "test-desc",
            "--description", "This is a test agent"
        ])
        
        assert result.exit_code == 0
        assert "created successfully" in result.output
    
    def test_create_with_custom_model(self):
        """Test creating agent with custom model."""
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Custom Model Agent",
            "--code", "test-model",
            "--type", "kimi",
            "--model", "kimi-custom-model"
        ])
        
        assert result.exit_code == 0
    
    def test_create_duplicate_code(self):
        """Test creating agent with duplicate code fails."""
        # Create first agent
        runner.invoke(app, [
            "agent", "create",
            "--name", "First Agent",
            "--code", "duplicate-test"
        ])
        
        # Try to create second with same code
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Second Agent",
            "--code", "duplicate-test"
        ])
        
        assert result.exit_code != 0
        assert "already exists" in result.output
    
    def test_create_invalid_code_format(self):
        """Test creating agent with invalid code format."""
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Test",
            "--code", "Invalid_Code"
        ])
        
        assert result.exit_code != 0
        assert "Invalid code" in result.output
    
    def test_create_from_existing(self):
        """Test creating agent from existing."""
        # Create source agent
        runner.invoke(app, [
            "agent", "create",
            "--name", "Source Agent",
            "--code", "source-agent"
        ])
        
        # Create from source
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Copied Agent",
            "--code", "copied-agent",
            "--from", "source-agent"
        ])
        
        assert result.exit_code == 0
        assert "created from" in result.output
    
    def test_create_from_nonexistent(self):
        """Test creating from non-existent agent fails."""
        result = runner.invoke(app, [
            "agent", "create",
            "--name", "Test",
            "--code", "test",
            "--from", "nonexistent"
        ])
        
        assert result.exit_code != 0
        assert "not found" in result.output


class TestAgentList(TestIsolator):
    """Test zima agent list command."""
    
    def test_list_empty(self):
        """Test listing when no agents exist."""
        result = runner.invoke(app, ["agent", "list"])
        
        assert result.exit_code == 0
        assert "No agents found" in result.output
    
    def test_list_with_agents(self):
        """Test listing with agents."""
        # Create some agents
        runner.invoke(app, ["agent", "create", "--name", "Agent 1", "--code", "agent-1"])
        runner.invoke(app, ["agent", "create", "--name", "Agent 2", "--code", "agent-2"])
        
        result = runner.invoke(app, ["agent", "list"])
        
        assert result.exit_code == 0
        assert "agent-1" in result.output
        assert "agent-2" in result.output
        assert "Agent 1" in result.output
        assert "Agent 2" in result.output
    
    def test_list_filter_by_type(self):
        """Test listing with type filter."""
        runner.invoke(app, ["agent", "create", "--name", "Kimi", "--code", "k1", "--type", "kimi"])
        runner.invoke(app, ["agent", "create", "--name", "Claude", "--code", "c1", "--type", "claude"])
        
        result = runner.invoke(app, ["agent", "list", "--type", "kimi"])
        
        assert result.exit_code == 0
        assert "k1" in result.output
        assert "c1" not in result.output


class TestAgentShow(TestIsolator):
    """Test zima agent show command."""
    
    def test_show_existing(self):
        """Test showing existing agent."""
        runner.invoke(app, [
            "agent", "create",
            "--name", "Show Test",
            "--code", "show-test",
            "--description", "Test description"
        ])
        
        result = runner.invoke(app, ["agent", "show", "show-test"])
        
        assert result.exit_code == 0
        assert "show-test" in result.output
        assert "Test description" in result.output
    
    def test_show_nonexistent(self):
        """Test showing non-existent agent fails."""
        result = runner.invoke(app, ["agent", "show", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output
    
    def test_show_json_format(self):
        """Test showing agent in JSON format."""
        runner.invoke(app, ["agent", "create", "--name", "JSON Test", "--code", "json-test"])
        
        result = runner.invoke(app, ["agent", "show", "json-test", "--format", "json"])
        
        assert result.exit_code == 0
        assert '"code": "json-test"' in result.output or '"json-test"' in result.output


class TestAgentUpdate(TestIsolator):
    """Test zima agent update command."""
    
    def test_update_name(self):
        """Test updating agent name."""
        runner.invoke(app, ["agent", "create", "--name", "Old Name", "--code", "update-test"])
        
        result = runner.invoke(app, [
            "agent", "update", "update-test",
            "--name", "New Name"
        ])
        
        assert result.exit_code == 0
        assert "updated" in result.output
        
        # Verify
        show_result = runner.invoke(app, ["agent", "show", "update-test"])
        assert "New Name" in show_result.output
    
    def test_update_param(self):
        """Test updating agent parameter."""
        runner.invoke(app, ["agent", "create", "--name", "Test", "--code", "param-test"])
        
        result = runner.invoke(app, [
            "agent", "update", "param-test",
            "--set-param", "model=new-model",
            "--set-param", "yolo=false"
        ])
        
        assert result.exit_code == 0
    
    def test_update_nonexistent(self):
        """Test updating non-existent agent fails."""
        result = runner.invoke(app, ["agent", "update", "nonexistent", "--name", "New"])
        
        assert result.exit_code != 0
        assert "not found" in result.output
    
    def test_update_no_changes(self):
        """Test update with no changes."""
        runner.invoke(app, ["agent", "create", "--name", "Test", "--code", "no-change-test"])
        
        result = runner.invoke(app, ["agent", "update", "no-change-test"])
        
        assert result.exit_code == 0
        assert "No changes" in result.output


class TestAgentDelete(TestIsolator):
    """Test zima agent delete command."""
    
    def test_delete_existing(self):
        """Test deleting existing agent."""
        runner.invoke(app, ["agent", "create", "--name", "To Delete", "--code", "delete-test"])
        
        result = runner.invoke(app, ["agent", "delete", "delete-test", "--force"])
        
        assert result.exit_code == 0
        assert "deleted" in result.output
        
        # Verify it's gone
        list_result = runner.invoke(app, ["agent", "list"])
        assert "delete-test" not in list_result.output
    
    def test_delete_nonexistent(self):
        """Test deleting non-existent agent."""
        result = runner.invoke(app, ["agent", "delete", "nonexistent", "--force"])
        
        # Should succeed (idempotent) or show not found
        assert result.exit_code == 0 or "not found" in result.output


class TestAgentValidate(TestIsolator):
    """Test zima agent validate command."""
    
    def test_validate_valid(self):
        """Test validating valid agent."""
        runner.invoke(app, ["agent", "create", "--name", "Valid", "--code", "valid-test"])
        
        result = runner.invoke(app, ["agent", "validate", "valid-test"])
        
        assert result.exit_code == 0
        assert "is valid" in result.output
    
    def test_validate_nonexistent(self):
        """Test validating non-existent agent."""
        result = runner.invoke(app, ["agent", "validate", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output


class TestAgentTest(TestIsolator):
    """Test zima agent test command."""
    
    def test_test_command(self):
        """Test agent test command."""
        runner.invoke(app, ["agent", "create", "--name", "Test", "--code", "test-cmd"])
        
        result = runner.invoke(app, ["agent", "test", "test-cmd"])
        
        assert result.exit_code == 0
        assert "Generated Command" in result.output
        assert "kimi" in result.output  # Default type
    
    def test_test_nonexistent(self):
        """Test testing non-existent agent."""
        result = runner.invoke(app, ["agent", "test", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output
