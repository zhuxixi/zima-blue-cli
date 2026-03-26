"""Base models for all configuration types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from zima.utils import generate_timestamp


@dataclass
class Metadata:
    """
    Common metadata for all configurations.
    
    Attributes:
        code: Unique identifier (e.g., "my-agent")
        name: Human-readable name (e.g., "My Agent")
        description: Optional description
    """
    code: str = ""
    name: str = ""
    description: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Metadata:
        """Create from dictionary."""
        return cls(
            code=data.get("code", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
        )


@dataclass
class BaseConfig:
    """
    Base configuration class.
    
    All specific config types (AgentConfig, WorkflowConfig, etc.)
    should inherit from this class.
    
    Attributes:
        api_version: API version (e.g., "zima.io/v1")
        kind: Config kind (e.g., "Agent", "Workflow")
        metadata: Configuration metadata
        created_at: Creation timestamp (ISO 8601)
        updated_at: Last update timestamp (ISO 8601)
    """
    api_version: str = "zima.io/v1"
    kind: str = ""
    metadata: Metadata = field(default_factory=Metadata)
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        """Post-initialization processing."""
        # Ensure timestamps are set
        if not self.created_at:
            self.created_at = generate_timestamp()
        if not self.updated_at:
            self.updated_at = self.created_at
    
    def to_dict(self) -> dict:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
    
    def to_yaml(self) -> str:
        """
        Convert configuration to YAML string.
        
        Returns:
            YAML formatted string
        """
        return yaml.safe_dump(
            self.to_dict(),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False
        )
    
    @classmethod
    def from_dict(cls, data: dict) -> BaseConfig:
        """
        Create configuration from dictionary.
        
        Args:
            data: Dictionary with configuration data
            
        Returns:
            Configuration instance
        """
        return cls(
            api_version=data.get("apiVersion", "zima.io/v1"),
            kind=data.get("kind", ""),
            metadata=Metadata.from_dict(data.get("metadata", {})),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )
    
    @classmethod
    def from_yaml(cls, yaml_content: str) -> BaseConfig:
        """
        Create configuration from YAML string.
        
        Args:
            yaml_content: YAML formatted string
            
        Returns:
            Configuration instance
        """
        data = yaml.safe_load(yaml_content)
        return cls.from_dict(data or {})
    
    @classmethod
    def from_yaml_file(cls, path: Path) -> BaseConfig:
        """
        Load configuration from YAML file.
        
        Args:
            path: Path to YAML file
            
        Returns:
            Configuration instance
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        content = path.read_text(encoding="utf-8")
        return cls.from_yaml(content)
    
    def save_to_file(self, path: Path) -> None:
        """
        Save configuration to YAML file.
        
        Args:
            path: Target file path
        """
        # Update timestamp before saving
        self.updated_at = generate_timestamp()
        
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_yaml(), encoding="utf-8")
    
    def validate(self) -> list[str]:
        """
        Validate configuration.
        
        Returns:
            List of validation error messages. Empty list means valid.
        """
        errors = []
        
        if not self.metadata.code:
            errors.append("metadata.code is required")
        
        if not self.kind:
            errors.append("kind is required")
        
        return errors
    
    def is_valid(self) -> bool:
        """
        Check if configuration is valid.
        
        Returns:
            True if valid
        """
        return len(self.validate()) == 0
    
    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to current time."""
        self.updated_at = generate_timestamp()


# Type alias for config data
def convert_to_camel_case(snake_str: str) -> str:
    """
    Convert snake_case to camelCase.
    
    Used for YAML field name conversion.
    """
    components = snake_str.split('_')
    return components[0] + ''.join(x.capitalize() for x in components[1:])


def convert_to_snake_case(camel_str: str) -> str:
    """
    Convert camelCase to snake_case.
    
    Used for YAML field name conversion.
    """
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
