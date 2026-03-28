"""Unit tests for ConfigBundle."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from zima.models.config_bundle import ConfigBundle
from zima.models.pjob import Overrides


class TestConfigBundle:
    """Tests for ConfigBundle."""
    
    @pytest.fixture
    def mock_configs(self):
        """Create mock configs for testing."""
        return {
            "agent": {
                "apiVersion": "zima.io/v1",
                "kind": "Agent",
                "metadata": {"code": "test-agent", "name": "Test Agent"},
                "spec": {
                    "type": "kimi",
                    "parameters": {"model": "kimi-test"},
                    "defaults": {"variable": "default-var", "env": "default-env"},
                },
            },
            "workflow": {
                "apiVersion": "zima.io/v1",
                "kind": "Workflow",
                "metadata": {"code": "test-workflow", "name": "Test Workflow"},
                "spec": {
                    "format": "jinja2",
                    "template": "Hello {{ name }}",
                },
            },
            "variable": {
                "apiVersion": "zima.io/v1",
                "kind": "Variable",
                "metadata": {"code": "test-var", "name": "Test Variable"},
                "spec": {
                    "values": {"name": "World"},
                },
            },
            "env": {
                "apiVersion": "zima.io/v1",
                "kind": "Env",
                "metadata": {"code": "test-env", "name": "Test Env"},
                "spec": {
                    "forType": "kimi",
                    "variables": {"DEBUG": "false"},
                    "secrets": [],
                },
            },
            "pmg": {
                "apiVersion": "zima.io/v1",
                "kind": "PMG",
                "metadata": {"code": "test-pmg", "name": "Test PMG"},
                "spec": {
                    "forTypes": ["kimi"],
                    "parameters": [
                        {"name": "model", "type": "long", "value": "kimi-k2"},
                    ],
                },
            },
        }
    
    def test_resolve_basic(self, mock_configs):
        """Test basic config resolution."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            manager.load_config.side_effect = lambda kind, code: mock_configs.get(kind, {}).get(code, mock_configs.get(kind, {}))
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
            )
            
            assert bundle.agent.metadata.code == "test-agent"
            assert bundle.workflow.metadata.code == "test-workflow"
    
    def test_resolve_with_optional_refs(self, mock_configs):
        """Test resolution with optional references."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            def load_config(kind, code):
                if kind == "agent":
                    return mock_configs["agent"]
                elif kind == "workflow":
                    return mock_configs["workflow"]
                elif kind == "variable":
                    return mock_configs["variable"]
                elif kind == "env":
                    return mock_configs["env"]
                elif kind == "pmg":
                    return mock_configs["pmg"]
                return {}
            manager.load_config.side_effect = load_config
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
                pjob_variable="test-var",
                pjob_env="test-env",
                pjob_pmg="test-pmg",
            )
            
            assert bundle.variable.metadata.code == "test-var"
            assert bundle.env.metadata.code == "test-env"
            assert bundle.pmg.metadata.code == "test-pmg"
    
    def test_resolve_agent_defaults(self, mock_configs):
        """Test that agent defaults are used when pjob refs not specified."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            def load_config(kind, code):
                if kind == "agent":
                    return mock_configs["agent"]
                elif kind == "workflow":
                    return mock_configs["workflow"]
                elif kind == "variable" and code == "default-var":
                    return mock_configs["variable"]
                elif kind == "env" and code == "default-env":
                    return mock_configs["env"]
                return {}
            manager.load_config.side_effect = load_config
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
                # variable and env not specified, should use agent defaults
            )
            
            assert bundle.variable.metadata.code == "test-var"
            assert bundle.env.metadata.code == "test-env"
    
    def test_resolve_missing_agent_raises(self):
        """Test that missing agent raises error."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = False
            MockManager.return_value = manager
            
            with pytest.raises(ValueError, match="Agent 'missing-agent' not found"):
                ConfigBundle.resolve(
                    pjob_agent="missing-agent",
                    pjob_workflow="workflow",
                )
    
    def test_resolve_missing_workflow_raises(self):
        """Test that missing workflow raises error."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            def exists(kind, code):
                return kind == "agent" and code == "test-agent"
            manager.config_exists.side_effect = exists
            MockManager.return_value = manager
            
            with pytest.raises(ValueError, match="Workflow 'missing-workflow' not found"):
                ConfigBundle.resolve(
                    pjob_agent="test-agent",
                    pjob_workflow="missing-workflow",
                )
    
    def test_apply_overrides(self, mock_configs):
        """Test applying overrides."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            manager.load_config.side_effect = lambda kind, code: mock_configs.get(kind, {})
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
            )
            
            overrides = Overrides(
                agent_params={"model": "overridden-model"},
                env_vars={"DEBUG": "true"},
            )
            bundle.apply_overrides(overrides)
            
            assert bundle.agent.parameters["model"] == "overridden-model"
            assert bundle.overrides.env_vars["DEBUG"] == "true"
    
    def test_get_variable_values(self, mock_configs):
        """Test getting variable values."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            def load_config(kind, code):
                if kind == "agent":
                    return mock_configs["agent"]
                elif kind == "workflow":
                    return mock_configs["workflow"]
                elif kind == "variable":
                    return mock_configs["variable"]
                return {}
            manager.load_config.side_effect = load_config
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
                pjob_variable="test-var",
            )
            
            values = bundle.get_variable_values()
            assert values["name"] == "World"
    
    def test_get_env_variables(self, mock_configs):
        """Test getting environment variables."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            def load_config(kind, code):
                if kind == "agent":
                    return mock_configs["agent"]
                elif kind == "workflow":
                    return mock_configs["workflow"]
                elif kind == "env":
                    return mock_configs["env"]
                return {}
            manager.load_config.side_effect = load_config
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
                pjob_env="test-env",
            )
            
            env_vars = bundle.get_env_variables()
            assert env_vars["DEBUG"] == "false"
    
    def test_build_kimi_command(self, mock_configs):
        """Test building Kimi command."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            def load_config(kind, code):
                if kind == "agent":
                    return mock_configs["agent"]
                elif kind == "workflow":
                    return mock_configs["workflow"]
                return {}
            manager.load_config.side_effect = load_config
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
            )
            
            prompt_file = Path("/tmp/prompt.md")
            cmd = bundle.build_command(prompt_file)
            
            assert "kimi" in cmd
            assert "--print" in cmd
            assert "--prompt" in cmd
            assert str(prompt_file) in cmd
    
    def test_to_summary(self, mock_configs):
        """Test getting summary."""
        with patch("zima.models.config_bundle.ConfigManager") as MockManager:
            manager = Mock()
            manager.config_exists.return_value = True
            manager.load_config.side_effect = lambda kind, code: mock_configs.get(kind, {})
            MockManager.return_value = manager
            
            bundle = ConfigBundle.resolve(
                pjob_agent="test-agent",
                pjob_workflow="test-workflow",
                pjob_variable="test-var",
                pjob_env="test-env",
                pjob_pmg="test-pmg",
            )
            
            summary = bundle.to_summary()
            
            assert summary["agent"]["code"] == "test-agent"
            assert summary["workflow"]["code"] == "test-workflow"
            assert summary["variable"]["code"] == "test-var"
            assert summary["env"]["code"] == "test-env"
            assert summary["pmg"]["code"] == "test-pmg"
