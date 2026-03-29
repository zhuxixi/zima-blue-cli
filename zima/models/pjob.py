"""PJob (Parameterized Job) model - execution layer for Agent tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from zima.models.base import BaseConfig, Metadata
from zima.utils import generate_timestamp, validate_code


@dataclass
class ExecutionOptions:
    """
    Execution options for PJob.
    
    Attributes:
        work_dir: Working directory for execution
        timeout: Timeout in seconds
        keep_temp: Keep temporary files after execution
        retries: Number of retries on failure
        async_: Whether to execute asynchronously
    """
    work_dir: str = ""
    timeout: int = 0  # 0 means no timeout
    keep_temp: bool = False
    retries: int = 0
    async_: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "workDir": self.work_dir,
            "timeout": self.timeout,
            "keepTemp": self.keep_temp,
            "retries": self.retries,
            "async": self.async_,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> ExecutionOptions:
        """Create from dictionary."""
        return cls(
            work_dir=data.get("workDir", ""),
            timeout=data.get("timeout", 0),
            keep_temp=data.get("keepTemp", False),
            retries=data.get("retries", 0),
            async_=data.get("async", False),
        )


@dataclass
class OutputOptions:
    """
    Output handling options for PJob.
    
    Attributes:
        save_to: Path to save output (supports template variables)
        append: Whether to append to existing file
        format: Output format processing (raw, json, extract-code-blocks)
    """
    save_to: str = ""
    append: bool = False
    format: str = "raw"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {"format": self.format}
        if self.save_to:
            result["saveTo"] = self.save_to
        if self.append:
            result["append"] = self.append
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> OutputOptions:
        """Create from dictionary."""
        return cls(
            save_to=data.get("saveTo", ""),
            append=data.get("append", False),
            format=data.get("format", "raw"),
        )


@dataclass
class Overrides:
    """
    Runtime overrides for PJob execution.
    
    These overrides have the highest priority in configuration resolution.
    
    Attributes:
        agent_params: Override Agent parameters
        variable_values: Override Variable values
        env_vars: Override/add environment variables
        pmg_params: Additional PMG parameters
    """
    agent_params: dict = field(default_factory=dict)
    variable_values: dict = field(default_factory=dict)
    env_vars: dict = field(default_factory=dict)
    pmg_params: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {}
        if self.agent_params:
            result["agentParams"] = self.agent_params
        if self.variable_values:
            result["variableValues"] = self.variable_values
        if self.env_vars:
            result["envVars"] = self.env_vars
        if self.pmg_params:
            result["pmgParams"] = self.pmg_params
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> Overrides:
        """Create from dictionary."""
        return cls(
            agent_params=data.get("agentParams", {}),
            variable_values=data.get("variableValues", {}),
            env_vars=data.get("envVars", {}),
            pmg_params=data.get("pmgParams", []),
        )
    
    def is_empty(self) -> bool:
        """Check if overrides are empty."""
        return not any([
            self.agent_params,
            self.variable_values,
            self.env_vars,
            self.pmg_params,
        ])


@dataclass
class PJobSpec:
    """
    PJob specification containing config references.
    
    Attributes:
        agent: Agent code (required)
        workflow: Workflow code (required)
        variable: Variable code (optional)
        env: Env code (optional)
        pmg: PMG code (optional)
        overrides: Runtime overrides
        execution: Execution options
        hooks: Pre/post execution hooks
        output: Output handling options
    """
    agent: str = ""
    workflow: str = ""
    variable: str = ""
    env: str = ""
    pmg: str = ""
    overrides: Overrides = field(default_factory=Overrides)
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)
    hooks: dict = field(default_factory=dict)
    output: OutputOptions = field(default_factory=OutputOptions)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "agent": self.agent,
            "workflow": self.workflow,
        }
        if self.variable:
            result["variable"] = self.variable
        if self.env:
            result["env"] = self.env
        if self.pmg:
            result["pmg"] = self.pmg
        if not self.overrides.is_empty():
            result["overrides"] = self.overrides.to_dict()
        if self.execution.work_dir or self.execution.timeout != 0:
            result["execution"] = self.execution.to_dict()
        if self.hooks:
            result["hooks"] = self.hooks
        if self.output.save_to or self.output.format != "raw":
            result["output"] = self.output.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> PJobSpec:
        """Create from dictionary."""
        return cls(
            agent=data.get("agent", ""),
            workflow=data.get("workflow", ""),
            variable=data.get("variable", ""),
            env=data.get("env", ""),
            pmg=data.get("pmg", ""),
            overrides=Overrides.from_dict(data.get("overrides", {})),
            execution=ExecutionOptions.from_dict(data.get("execution", {})),
            hooks=data.get("hooks", {}),
            output=OutputOptions.from_dict(data.get("output", {})),
        )


@dataclass
class PJobMetadata(Metadata):
    """
    Extended metadata for PJob with labels and annotations.
    
    Attributes:
        code: Unique identifier
        name: Human-readable name
        description: Optional description
        labels: Tags for categorization
        annotations: Additional metadata (key-value pairs)
    """
    labels: list[str] = field(default_factory=list)
    annotations: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = super().to_dict()
        if self.labels:
            result["labels"] = self.labels
        if self.annotations:
            result["annotations"] = self.annotations
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> PJobMetadata:
        """Create from dictionary."""
        return cls(
            code=data.get("code", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            labels=data.get("labels", []),
            annotations=data.get("annotations", {}),
        )


@dataclass
class PJobConfig(BaseConfig):
    """
    PJob (Parameterized Job) configuration model.
    
    PJob is the execution layer that orchestrates Agent, Workflow, Variable,
    Env, and PMG configurations into runnable tasks.
    
    Attributes:
        kind: Always "PJob"
        metadata: PJob metadata with labels and annotations
        spec: PJob specification with config references
    """
    kind: str = "PJob"
    metadata: PJobMetadata = field(default_factory=PJobMetadata)
    spec: PJobSpec = field(default_factory=PJobSpec)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": self.spec.to_dict(),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> PJobConfig:
        """Create from dictionary."""
        return cls(
            api_version=data.get("apiVersion", "zima.io/v1"),
            kind=data.get("kind", "PJob"),
            metadata=PJobMetadata.from_dict(data.get("metadata", {})),
            spec=PJobSpec.from_dict(data.get("spec", {})),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )
    
    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        agent: str,
        workflow: str,
        description: str = "",
        variable: str = "",
        env: str = "",
        pmg: str = "",
        labels: Optional[list[str]] = None,
        overrides: Optional[dict] = None,
        execution: Optional[dict] = None,
        hooks: Optional[dict] = None,
        output: Optional[dict] = None,
    ) -> PJobConfig:
        """
        Factory method to create a new PJobConfig.
        
        Args:
            code: Unique PJob code
            name: Display name
            agent: Agent code (required)
            workflow: Workflow code (required)
            description: Optional description
            variable: Variable code (optional)
            env: Env code (optional)
            pmg: PMG code (optional)
            labels: Tags for categorization
            overrides: Runtime overrides
            execution: Execution options
            hooks: Pre/post execution hooks
            output: Output handling options
            
        Returns:
            New PJobConfig instance
            
        Raises:
            ValueError: If required fields are missing
        """
        if not agent:
            raise ValueError("agent is required")
        if not workflow:
            raise ValueError("workflow is required")
        
        now = generate_timestamp()
        
        return cls(
            metadata=PJobMetadata(
                code=code,
                name=name,
                description=description,
                labels=labels or [],
            ),
            spec=PJobSpec(
                agent=agent,
                workflow=workflow,
                variable=variable,
                env=env,
                pmg=pmg,
                overrides=Overrides.from_dict(overrides or {}),
                execution=ExecutionOptions.from_dict(execution or {}),
                hooks=hooks or {},
                output=OutputOptions.from_dict(output or {}),
            ),
            created_at=now,
            updated_at=now,
        )
    
    def validate(self, resolve_refs: bool = False) -> list[str]:
        """
        Validate PJob configuration.
        
        Args:
            resolve_refs: If True, validate referenced configs exist
            
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Validate base fields
        if not self.metadata.code:
            errors.append("metadata.code is required")
        elif not validate_code(self.metadata.code):
            errors.append(f"metadata.code '{self.metadata.code}' has invalid format")
        
        if not self.metadata.name:
            errors.append("metadata.name is required")
        
        # Validate required references
        if not self.spec.agent:
            errors.append("spec.agent is required")
        if not self.spec.workflow:
            errors.append("spec.workflow is required")
        
        # Validate execution options
        if self.spec.execution.timeout < 0:
            errors.append("spec.execution.timeout must be non-negative")
        if self.spec.execution.retries < 0:
            errors.append("spec.execution.retries must be non-negative")
        
        # Validate output format
        valid_formats = {"raw", "json", "extract-code-blocks"}
        if self.spec.output.format not in valid_formats:
            errors.append(f"spec.output.format must be one of {valid_formats}")
        
        # Validate referenced configs exist (if requested)
        if resolve_refs:
            from zima.config.manager import ConfigManager
            manager = ConfigManager()
            
            if self.spec.agent and not manager.config_exists("agent", self.spec.agent):
                errors.append(f"referenced agent '{self.spec.agent}' not found")
            if self.spec.workflow and not manager.config_exists("workflow", self.spec.workflow):
                errors.append(f"referenced workflow '{self.spec.workflow}' not found")
            if self.spec.variable and not manager.config_exists("variable", self.spec.variable):
                errors.append(f"referenced variable '{self.spec.variable}' not found")
            if self.spec.env and not manager.config_exists("env", self.spec.env):
                errors.append(f"referenced env '{self.spec.env}' not found")
            if self.spec.pmg and not manager.config_exists("pmg", self.spec.pmg):
                errors.append(f"referenced pmg '{self.spec.pmg}' not found")
        
        return errors
    
    def get_config_refs(self) -> dict[str, str]:
        """
        Get all configuration references.
        
        Returns:
            Dictionary mapping config type to code
        """
        refs = {
            "agent": self.spec.agent,
            "workflow": self.spec.workflow,
        }
        if self.spec.variable:
            refs["variable"] = self.spec.variable
        if self.spec.env:
            refs["env"] = self.spec.env
        if self.spec.pmg:
            refs["pmg"] = self.spec.pmg
        return refs
