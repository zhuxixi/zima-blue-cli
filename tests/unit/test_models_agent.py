"""Unit tests for AgentConfig model."""

from pathlib import Path

import pytest

from tests.base import TestIsolator
from zima.models.agent import AGENT_PARAMETER_TEMPLATES, VALID_AGENT_TYPES, AgentConfig, Metadata


class TestAgentConfigCreation(TestIsolator):
    """Test AgentConfig creation."""

    def test_create_kimi_agent(self):
        """Test creating Kimi agent."""
        config = AgentConfig.create(code="kimi-agent", name="Kimi Agent", agent_type="kimi")

        assert config.metadata.code == "kimi-agent"
        assert config.metadata.name == "Kimi Agent"
        assert config.type == "kimi"
        assert "model" not in config.parameters
        assert config.parameters["yolo"] is True
        assert config.parameters["maxStepsPerTurn"] == 50

    def test_create_claude_agent(self):
        """Test creating Claude agent."""
        config = AgentConfig.create(code="claude-agent", name="Claude Agent", agent_type="claude")

        assert config.type == "claude"
        assert "model" not in config.parameters
        assert config.parameters["maxTurns"] == 100

    def test_create_with_custom_params(self):
        """Test creating with custom parameters."""
        config = AgentConfig.create(
            code="custom",
            name="Custom",
            agent_type="kimi",
            parameters={"model": "kimi-custom", "yolo": False, "customParam": "value"},
        )

        assert config.parameters["model"] == "kimi-custom"
        assert config.parameters["yolo"] is False
        assert config.parameters["customParam"] == "value"
        # Other defaults still present
        assert "maxStepsPerTurn" in config.parameters

    def test_create_with_defaults(self):
        """Test creating with default references."""
        config = AgentConfig.create(
            code="test",
            name="Test",
            agent_type="kimi",
            defaults={"workflow": "default-workflow", "env": "default-env"},
        )

        assert config.defaults["workflow"] == "default-workflow"
        assert config.defaults["env"] == "default-env"

    def test_create_with_description(self):
        """Test creating with description."""
        config = AgentConfig.create(
            code="test", name="Test", agent_type="kimi", description="Test description"
        )

        assert config.metadata.description == "Test description"

    def test_create_invalid_type(self):
        """Test creating with invalid agent type."""
        with pytest.raises(ValueError, match="Invalid agent type"):
            AgentConfig.create(code="test", name="Test", agent_type="invalid")

    def test_create_openai_not_supported(self):
        """Test that openai type is not supported."""
        with pytest.raises(ValueError, match="Invalid agent type"):
            AgentConfig.create(code="test", name="Test", agent_type="openai")

    def test_create_custom_not_supported(self):
        """Test that custom type is not supported."""
        with pytest.raises(ValueError, match="Invalid agent type"):
            AgentConfig.create(code="test", name="Test", agent_type="custom")


class TestAgentConfigValidation(TestIsolator):
    """Test AgentConfig validation."""

    def test_validate_valid_kimi(self):
        """Test valid Kimi config."""
        config = AgentConfig.create("test", "Test", "kimi")
        errors = config.validate()
        assert errors == []

    def test_validate_valid_claude(self):
        """Test valid Claude config."""
        config = AgentConfig.create("test", "Test", "claude")
        errors = config.validate()
        assert errors == []

    def test_validate_missing_code(self):
        """Test validation with missing code."""
        config = AgentConfig(type="kimi", metadata=Metadata(name="Test"))
        errors = config.validate()
        assert any("code is required" in e for e in errors)

    def test_validate_missing_name(self):
        """Test validation with missing name."""
        config = AgentConfig(type="kimi", metadata=Metadata(code="test"))
        errors = config.validate()
        assert any("name is required" in e for e in errors)

    def test_validate_invalid_code_format(self):
        """Test validation with invalid code format."""
        config = AgentConfig.create("Invalid_Code", "Test", "kimi")
        errors = config.validate()
        assert any("invalid format" in e for e in errors)

    def test_validate_missing_type(self):
        """Test validation with missing type."""
        config = AgentConfig(metadata=Metadata(code="test", name="Test"), type="")
        errors = config.validate()
        assert any("type is required" in e for e in errors)

    def test_validate_invalid_type(self):
        """Test validation with invalid type."""
        # Direct creation to bypass type check in create()
        config = AgentConfig(metadata=Metadata(code="test", name="Test"), type="invalid")
        errors = config.validate()
        assert any("not valid" in e for e in errors)

    def test_is_valid_true(self):
        """Test is_valid returns True."""
        config = AgentConfig.create("test", "Test", "kimi")
        assert config.is_valid() is True

    def test_is_valid_false(self):
        """Test is_valid returns False."""
        config = AgentConfig()  # Missing required fields
        assert config.is_valid() is False


class TestAgentConfigSerialization(TestIsolator):
    """Test AgentConfig serialization."""

    def test_to_dict(self):
        """Test converting to dictionary."""
        config = AgentConfig.create(
            "test", "Test", "kimi", description="Desc", defaults={"workflow": "wf1"}
        )

        data = config.to_dict()

        assert data["kind"] == "Agent"
        assert data["metadata"]["code"] == "test"
        assert data["metadata"]["name"] == "Test"
        assert data["metadata"]["description"] == "Desc"
        assert data["spec"]["type"] == "kimi"
        assert data["spec"]["defaults"]["workflow"] == "wf1"
        assert "parameters" in data["spec"]

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {"code": "from-dict", "name": "From Dict", "description": "Test"},
            "spec": {
                "type": "claude",
                "parameters": {"model": "custom"},
                "defaults": {"env": "env1"},
            },
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }

        config = AgentConfig.from_dict(data)

        assert config.metadata.code == "from-dict"
        assert config.type == "claude"
        assert config.parameters["model"] == "custom"
        assert config.defaults["env"] == "env1"

    def test_from_yaml_file(self, tmp_path):
        """Test loading from YAML file."""
        yaml_content = """
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: yaml-agent
  name: YAML Agent
  description: From YAML
spec:
  type: claude
  parameters:
    model: claude-sonnet
  defaults:
    workflow: wf1
"""
        yaml_file = tmp_path / "agent.yaml"
        yaml_file.write_text(yaml_content)

        config = AgentConfig.from_yaml_file(yaml_file)

        assert config.metadata.code == "yaml-agent"
        assert config.type == "claude"
        assert config.parameters["model"] == "claude-sonnet"

    def test_from_yaml_file_not_found(self, tmp_path):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            AgentConfig.from_yaml_file(tmp_path / "nonexistent.yaml")


class TestAgentConfigCommandBuilding(TestIsolator):
    """Test CLI command building."""

    def test_get_cli_template_kimi(self):
        """Test getting Kimi command template."""
        config = AgentConfig.create("test", "Test", "kimi")
        template = config.get_cli_command_template()

        assert "kimi" in template
        assert "--print" in template
        assert "--yolo" in template

    def test_get_cli_template_claude(self):
        """Test getting Claude command template."""
        config = AgentConfig.create("test", "Test", "claude")
        template = config.get_cli_command_template()

        assert "claude" in template
        assert "-p" in template

    def test_build_kimi_command(self):
        """Test building Kimi command."""
        config = AgentConfig.create(
            "test", "Test", "kimi", parameters={"model": "kimi-custom", "maxStepsPerTurn": 100}
        )

        cmd = config.build_command(prompt_file="/tmp/prompt.md", work_dir="/tmp/workspace")

        assert "kimi" in cmd
        assert "--prompt" in cmd
        assert "/tmp/prompt.md" in cmd
        assert "--work-dir" in cmd
        assert "/tmp/workspace" in cmd
        assert "--model" in cmd
        assert "kimi-custom" in cmd
        assert "--max-steps-per-turn" in cmd
        assert "100" in cmd

    def test_build_claude_command(self):
        """Test building Claude command."""
        config = AgentConfig.create("test", "Test", "claude", parameters={"maxTurns": 50})

        cmd = config.build_command(
            prompt_file=Path("/tmp/prompt.md"), work_dir=Path("/tmp/workspace")
        )

        assert "claude" in cmd
        assert "-p" in cmd
        # Claude receives prompt via stdin pipe, not --prompt flag
        assert "--prompt" not in cmd
        assert "--cwd" in cmd
        assert str(Path("/tmp/workspace")) in cmd
        assert "--max-turns" in cmd
        assert "50" in cmd

    def test_build_command_with_add_dirs(self):
        """Test building command with additional directories."""
        config = AgentConfig.create(
            "test", "Test", "kimi", parameters={"addDirs": ["./src", "./tests"]}
        )

        cmd = config.build_command()

        assert "--add-dir" in cmd
        assert "./src" in cmd
        assert "./tests" in cmd

    def test_build_command_with_extra_args(self):
        """Test building command with extra arguments."""
        config = AgentConfig.create("test", "Test", "kimi")

        cmd = config.build_command(extra_args={"model": "overridden-model"})

        assert "overridden-model" in cmd

    def test_build_kimi_command_no_model_by_default(self):
        """Test that --model is omitted when no model is set."""
        config = AgentConfig.create("test", "Test", "kimi")
        cmd = config.build_command()

        assert "--model" not in cmd

    def test_build_kimi_command_explicit_model(self):
        """Test that --model is included when explicitly set."""
        config = AgentConfig.create("test", "Test", "kimi", parameters={"model": "kimi-k2"})
        cmd = config.build_command()

        assert "--model" in cmd
        assert "kimi-k2" in cmd

    def test_build_claude_command_no_model_by_default(self):
        """Test that --model is omitted for claude when no model is set."""
        config = AgentConfig.create("test", "Test", "claude")
        cmd = config.build_command()

        assert "--model" not in cmd


class TestAgentConfigDefaults(TestIsolator):
    """Test default references management."""

    def test_get_default_existing(self):
        """Test getting existing default."""
        config = AgentConfig.create("test", "Test", "kimi", defaults={"workflow": "wf1"})

        assert config.get_default("workflow") == "wf1"

    def test_get_default_missing(self):
        """Test getting missing default."""
        config = AgentConfig.create("test", "Test", "kimi")

        assert config.get_default("workflow") is None
        assert config.get_default("workflow", "fallback") == "fallback"

    def test_set_default(self):
        """Test setting default."""
        config = AgentConfig.create("test", "Test", "kimi")

        config.set_default("workflow", "new-wf")

        assert config.defaults["workflow"] == "new-wf"

    def test_set_default_updates_timestamp(self):
        """Test that set_default updates timestamp."""
        import time

        config = AgentConfig.create("test", "Test", "kimi")
        old_timestamp = config.updated_at

        time.sleep(1.1)
        config.set_default("workflow", "wf1")

        assert config.updated_at != old_timestamp


class TestValidAgentTypes(TestIsolator):
    """Test valid agent types constant."""

    def test_valid_types(self):
        """Test that only kimi and claude are valid."""
        assert VALID_AGENT_TYPES == {"kimi", "claude"}
        assert "openai" not in VALID_AGENT_TYPES
        assert "custom" not in VALID_AGENT_TYPES

    def test_parameter_templates(self):
        """Test that parameter templates exist for all valid types."""
        for agent_type in VALID_AGENT_TYPES:
            assert agent_type in AGENT_PARAMETER_TEMPLATES
            assert "workDir" in AGENT_PARAMETER_TEMPLATES[agent_type]
