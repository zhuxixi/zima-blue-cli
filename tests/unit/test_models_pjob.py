"""Unit tests for PJob models."""

import pytest
from pathlib import Path

from zima.models.pjob import (
    PJobConfig,
    PJobMetadata,
    PJobSpec,
    ExecutionOptions,
    OutputOptions,
    Overrides,
)


class TestPJobMetadata:
    """Tests for PJobMetadata."""
    
    def test_create_metadata(self):
        """Test creating metadata."""
        meta = PJobMetadata(
            code="test-pjob",
            name="Test PJob",
            description="A test PJob",
            labels=["test", "automation"],
            annotations={"key": "value"},
        )
        
        assert meta.code == "test-pjob"
        assert meta.name == "Test PJob"
        assert meta.description == "A test PJob"
        assert "test" in meta.labels
        assert meta.annotations["key"] == "value"
    
    def test_to_dict(self):
        """Test conversion to dict."""
        meta = PJobMetadata(
            code="test",
            name="Test",
            labels=["a", "b"],
            annotations={"k": "v"},
        )
        d = meta.to_dict()
        
        assert d["code"] == "test"
        assert d["name"] == "Test"
        assert d["labels"] == ["a", "b"]
        assert d["annotations"] == {"k": "v"}
    
    def test_from_dict(self):
        """Test creation from dict."""
        d = {
            "code": "from-dict",
            "name": "From Dict",
            "description": "Desc",
            "labels": ["x"],
            "annotations": {"a": "1"},
        }
        meta = PJobMetadata.from_dict(d)
        
        assert meta.code == "from-dict"
        assert meta.name == "From Dict"
        assert meta.description == "Desc"
        assert meta.labels == ["x"]
        assert meta.annotations == {"a": "1"}


class TestExecutionOptions:
    """Tests for ExecutionOptions."""
    
    def test_default_values(self):
        """Test default option values."""
        opts = ExecutionOptions()
        
        assert opts.work_dir == ""
        assert opts.timeout == 0  # Default: no timeout
        assert opts.keep_temp is False
        assert opts.retries == 0
        assert opts.async_ is False
    
    def test_custom_values(self):
        """Test custom option values."""
        opts = ExecutionOptions(
            work_dir="./work",
            timeout=1200,
            keep_temp=True,
            retries=3,
            async_=True,
        )
        
        assert opts.work_dir == "./work"
        assert opts.timeout == 1200
        assert opts.keep_temp is True
        assert opts.retries == 3
        assert opts.async_ is True


class TestOutputOptions:
    """Tests for OutputOptions."""
    
    def test_default_values(self):
        """Test default output options."""
        opts = OutputOptions()
        
        assert opts.save_to == ""
        assert opts.append is False
        assert opts.format == "raw"
    
    def test_valid_formats(self):
        """Test valid format values."""
        valid_formats = ["raw", "json", "extract-code-blocks"]
        for fmt in valid_formats:
            opts = OutputOptions(format=fmt)
            assert opts.format == fmt


class TestOverrides:
    """Tests for Overrides."""
    
    def test_empty_overrides(self):
        """Test empty overrides."""
        ov = Overrides()
        assert ov.is_empty() is True
    
    def test_non_empty_overrides(self):
        """Test non-empty overrides."""
        ov = Overrides(agent_params={"model": "test"})
        assert ov.is_empty() is False
    
    def test_to_dict(self):
        """Test conversion to dict."""
        ov = Overrides(
            agent_params={"model": "m"},
            env_vars={"KEY": "val"},
        )
        d = ov.to_dict()
        
        assert d["agentParams"] == {"model": "m"}
        assert d["envVars"] == {"KEY": "val"}


class TestPJobSpec:
    """Tests for PJobSpec."""
    
    def test_required_fields(self):
        """Test required spec fields."""
        spec = PJobSpec(agent="agent1", workflow="workflow1")
        
        assert spec.agent == "agent1"
        assert spec.workflow == "workflow1"
        assert spec.variable == ""
        assert spec.env == ""
        assert spec.pmg == ""
    
    def test_optional_refs(self):
        """Test optional references."""
        spec = PJobSpec(
            agent="a",
            workflow="w",
            variable="v",
            env="e",
            pmg="p",
        )
        
        assert spec.variable == "v"
        assert spec.env == "e"
        assert spec.pmg == "p"


class TestPJobConfig:
    """Tests for PJobConfig."""
    
    def test_create_minimal(self):
        """Test creating minimal PJob."""
        config = PJobConfig.create(
            code="minimal",
            name="Minimal PJob",
            agent="test-agent",
            workflow="test-workflow",
        )
        
        assert config.metadata.code == "minimal"
        assert config.metadata.name == "Minimal PJob"
        assert config.spec.agent == "test-agent"
        assert config.spec.workflow == "test-workflow"
        assert config.kind == "PJob"
    
    def test_create_full(self):
        """Test creating full PJob."""
        config = PJobConfig.create(
            code="full",
            name="Full PJob",
            agent="agent1",
            workflow="workflow1",
            description="A full PJob",
            variable="var1",
            env="env1",
            pmg="pmg1",
            labels=["test", "auto"],
        )
        
        assert config.spec.variable == "var1"
        assert config.spec.env == "env1"
        assert config.spec.pmg == "pmg1"
        assert "test" in config.metadata.labels
    
    def test_create_missing_agent_raises(self):
        """Test that missing agent raises error."""
        with pytest.raises(ValueError, match="agent is required"):
            PJobConfig.create(
                code="test",
                name="Test",
                agent="",
                workflow="workflow",
            )
    
    def test_create_missing_workflow_raises(self):
        """Test that missing workflow raises error."""
        with pytest.raises(ValueError, match="workflow is required"):
            PJobConfig.create(
                code="test",
                name="Test",
                agent="agent",
                workflow="",
            )
    
    def test_validate_required_fields(self):
        """Test validation of required fields."""
        config = PJobConfig()  # Empty config
        errors = config.validate()
        
        assert any("code is required" in e for e in errors)
        assert any("name is required" in e for e in errors)
        assert any("agent is required" in e for e in errors)
        assert any("workflow is required" in e for e in errors)
    
    def test_validate_invalid_code(self):
        """Test validation of invalid code."""
        config = PJobConfig.create(
            code="INVALID_CODE",
            name="Test",
            agent="agent",
            workflow="workflow",
        )
        errors = config.validate()
        
        assert any("invalid format" in e for e in errors)
    
    def test_validate_invalid_timeout(self):
        """Test validation of negative timeout."""
        config = PJobConfig.create(
            code="test",
            name="Test",
            agent="agent",
            workflow="workflow",
            execution={"timeout": -1},
        )
        errors = config.validate()
        
        assert any("timeout must be non-negative" in e for e in errors)
    
    def test_validate_invalid_output_format(self):
        """Test validation of invalid output format."""
        config = PJobConfig.create(
            code="test",
            name="Test",
            agent="agent",
            workflow="workflow",
            output={"format": "invalid"},
        )
        errors = config.validate()
        
        assert any("format must be one of" in e for e in errors)
    
    def test_to_dict(self):
        """Test conversion to dict."""
        config = PJobConfig.create(
            code="test",
            name="Test",
            agent="agent1",
            workflow="workflow1",
        )
        d = config.to_dict()
        
        assert d["kind"] == "PJob"
        assert d["metadata"]["code"] == "test"
        assert d["spec"]["agent"] == "agent1"
        assert d["spec"]["workflow"] == "workflow1"
    
    def test_from_dict(self):
        """Test creation from dict."""
        d = {
            "apiVersion": "zima.io/v1",
            "kind": "PJob",
            "metadata": {
                "code": "from-dict",
                "name": "From Dict",
                "labels": ["a", "b"],
            },
            "spec": {
                "agent": "agent1",
                "workflow": "wf1",
                "variable": "var1",
            },
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        config = PJobConfig.from_dict(d)
        
        assert config.metadata.code == "from-dict"
        assert config.metadata.name == "From Dict"
        assert config.spec.agent == "agent1"
        assert config.spec.variable == "var1"
        assert "a" in config.metadata.labels
    
    def test_get_config_refs(self):
        """Test getting config references."""
        config = PJobConfig.create(
            code="test",
            name="Test",
            agent="agent1",
            workflow="workflow1",
            variable="var1",
            env="env1",
        )
        refs = config.get_config_refs()
        
        assert refs["agent"] == "agent1"
        assert refs["workflow"] == "workflow1"
        assert refs["variable"] == "var1"
        assert refs["env"] == "env1"
        assert "pmg" not in refs
