"""Workflow configuration model with Jinja2 template support."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from jinja2 import BaseLoader, Environment, TemplateError, UndefinedError

from zima.models.base import BaseConfig, Metadata
from zima.utils import generate_timestamp, validate_code


# Valid template formats
VALID_TEMPLATE_FORMATS = {"jinja2", "mustache", "plain"}

# Valid variable types
VALID_VARIABLE_TYPES = {"string", "number", "boolean", "array", "object"}

# Standard template sections for agent task workflow
STANDARD_AGENT_SECTIONS = {
    "required": ["背景", "需求", "规则", "验收过程", "结束指标"],
    "optional": ["注意事项", "参考资料", "时间管理建议"],
    "aliases": {
        "背景": ["背景", "Context", "context", "项目背景"],
        "需求": ["需求", "Requirements", "requirements", "任务", "目标"],
        "规则": ["规则", "Rules", "rules", "约束", "守则"],
        "验收过程": ["验收过程", "Verification", "verification", "验收", "验证"],
        "结束指标": ["结束指标", "Completion Criteria", "completion criteria", "完成条件"],
    }
}


@dataclass
class VariableDef:
    """
    Variable definition for workflow templates.
    
    Attributes:
        name: Variable name (supports dot notation like 'task.name')
        type: Variable type (string, number, boolean, array, object)
        required: Whether the variable is required
        default: Default value if not provided
        description: Variable description
    """
    name: str
    type: str = "string"
    required: bool = True
    default: Any = None
    description: str = ""
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.description:
            result["description"] = self.description
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> VariableDef:
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            type=data.get("type", "string"),
            required=data.get("required", True),
            default=data.get("default"),
            description=data.get("description", ""),
        )
    
    def validate(self) -> list[str]:
        """Validate variable definition."""
        errors = []
        
        if not self.name:
            errors.append("Variable name is required")
        
        if self.type not in VALID_VARIABLE_TYPES:
            errors.append(f"Invalid variable type: {self.type}. Valid: {VALID_VARIABLE_TYPES}")
        
        return errors


@dataclass
class WorkflowConfig(BaseConfig):
    """
    Workflow configuration model with Jinja2 template support.
    
    Workflow defines the Prompt template that guides Agent execution.
    It uses Jinja2 syntax for variable interpolation and logic control.
    
    Attributes:
        format: Template format (jinja2, mustache, plain)
        template: Template content string
        variables: Variable definitions for the template
        tags: Tags for categorization
        author: Author of the workflow
        version: Workflow version
    """
    kind: str = "Workflow"
    format: str = "jinja2"
    template: str = ""
    variables: list[VariableDef] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    author: str = ""
    version: str = "1.0.0"
    
    def __post_init__(self):
        """Post-initialization processing."""
        super().__post_init__()
        # Ensure variables is a list
        if self.variables is None:
            self.variables = []
    
    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        template: str = "",
        description: str = "",
        format: str = "jinja2",
        variables: Optional[list[dict]] = None,
        tags: Optional[list[str]] = None,
        author: str = "",
        version: str = "1.0.0"
    ) -> WorkflowConfig:
        """
        Factory method to create a new WorkflowConfig.
        
        Args:
            code: Unique workflow code
            name: Display name
            template: Template content
            description: Optional description
            format: Template format (jinja2, mustache, plain)
            variables: Variable definitions as dicts
            tags: Tags for categorization
            author: Author name
            version: Workflow version
            
        Returns:
            New WorkflowConfig instance
            
        Raises:
            ValueError: If format is invalid
        """
        if format not in VALID_TEMPLATE_FORMATS:
            raise ValueError(
                f"Invalid template format: {format}. "
                f"Valid formats: {VALID_TEMPLATE_FORMATS}"
            )
        
        # Convert variable dicts to VariableDef objects
        var_defs = []
        if variables:
            for var_data in variables:
                if isinstance(var_data, dict):
                    var_defs.append(VariableDef.from_dict(var_data))
                elif isinstance(var_data, VariableDef):
                    var_defs.append(var_data)
        
        now = generate_timestamp()
        
        return cls(
            metadata=Metadata(
                code=code,
                name=name,
                description=description
            ),
            format=format,
            template=template,
            variables=var_defs,
            tags=tags or [],
            author=author,
            version=version,
            created_at=now,
            updated_at=now
        )
    
    def validate(self) -> list[str]:
        """
        Validate workflow configuration.
        
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
        
        # Validate format
        if self.format not in VALID_TEMPLATE_FORMATS:
            errors.append(f"spec.format '{self.format}' is not valid. Valid: {VALID_TEMPLATE_FORMATS}")
        
        # Validate template syntax (for Jinja2)
        if self.format == "jinja2" and self.template:
            try:
                self._get_jinja_env().parse(self.template)
            except TemplateError as e:
                errors.append(f"Template syntax error: {e}")
        
        # Validate variable definitions
        for var in self.variables:
            var_errors = var.validate()
            errors.extend([f"Variable '{var.name}': {e}" for e in var_errors])
        
        return errors
    
    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.validate()) == 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": {
                "format": self.format,
                "template": self.template,
                "variables": [v.to_dict() for v in self.variables],
                "tags": self.tags,
                "author": self.author,
                "version": self.version,
            },
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> WorkflowConfig:
        """Create from dictionary."""
        spec = data.get("spec", {})
        
        # Parse variable definitions
        var_data = spec.get("variables", [])
        variables = []
        if isinstance(var_data, list):
            for v in var_data:
                if isinstance(v, dict):
                    variables.append(VariableDef.from_dict(v))
        
        return cls(
            api_version=data.get("apiVersion", "zima.io/v1"),
            kind=data.get("kind", "Workflow"),
            metadata=Metadata.from_dict(data.get("metadata", {})),
            format=spec.get("format", "jinja2"),
            template=spec.get("template", ""),
            variables=variables,
            tags=spec.get("tags", []),
            author=spec.get("author", ""),
            version=spec.get("version", "1.0.0"),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )
    
    @classmethod
    def from_yaml_file(cls, path: Path) -> WorkflowConfig:
        """Load from YAML file."""
        import yaml
        
        if not path.exists():
            raise FileNotFoundError(f"Workflow config not found: {path}")
        
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return cls.from_dict(data or {})
    
    def _get_jinja_env(self) -> Environment:
        """Get Jinja2 environment with custom settings."""
        return Environment(
            loader=BaseLoader(),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
    
    def render(self, variables: dict[str, Any]) -> str:
        """
        Render template with provided variables.
        
        Args:
            variables: Dictionary of variable values
            
        Returns:
            Rendered template string
            
        Raises:
            ValueError: If template format is not supported
            TemplateError: If template rendering fails
        """
        if self.format == "plain":
            return self.template
        
        if self.format == "mustache":
            # Simple mustache support using string.Template as fallback
            import string
            template = string.Template(self.template)
            return template.safe_substitute(variables)
        
        if self.format == "jinja2":
            try:
                env = self._get_jinja_env()
                template = env.from_string(self.template)
                
                # Merge with defaults
                context = self._get_default_values()
                context.update(variables)
                
                return template.render(**context)
            except UndefinedError as e:
                raise ValueError(f"Undefined variable in template: {e}")
            except TemplateError as e:
                raise ValueError(f"Template rendering error: {e}")
        
        raise ValueError(f"Unsupported template format: {self.format}")
    
    def _get_default_values(self) -> dict[str, Any]:
        """Get default values from variable definitions."""
        defaults = {}
        for var in self.variables:
            if var.default is not None:
                # Handle dot notation (e.g., 'task.name')
                keys = var.name.split(".")
                current = defaults
                for key in keys[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[keys[-1]] = var.default
        return defaults
    
    def validate_variables(self, values: dict[str, Any]) -> list[str]:
        """
        Validate provided variable values against definitions.
        
        Args:
            values: Variable values to validate
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        for var in self.variables:
            # Get value (handle dot notation)
            val = self._get_nested_value(values, var.name)
            
            # Check required
            if var.required and val is None:
                errors.append(f"Required variable '{var.name}' is missing")
                continue
            
            # Skip further checks if value is None and not required
            if val is None:
                continue
            
            # Type validation
            type_errors = self._validate_type(var.name, val, var.type)
            errors.extend(type_errors)
        
        return errors
    
    def _get_nested_value(self, data: dict, path: str) -> Any:
        """Get value from nested dictionary using dot notation."""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
    def _validate_type(self, name: str, value: Any, expected_type: str) -> list[str]:
        """Validate value against expected type."""
        errors = []
        
        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"Variable '{name}' should be string, got {type(value).__name__}")
        
        elif expected_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"Variable '{name}' should be number, got {type(value).__name__}")
        
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"Variable '{name}' should be boolean, got {type(value).__name__}")
        
        elif expected_type == "array":
            if not isinstance(value, list):
                errors.append(f"Variable '{name}' should be array, got {type(value).__name__}")
        
        elif expected_type == "object":
            if not isinstance(value, dict):
                errors.append(f"Variable '{name}' should be object, got {type(value).__name__}")
        
        return errors
    
    def get_variable_names(self) -> list[str]:
        """Get list of all variable names."""
        return [var.name for var in self.variables]
    
    def get_required_variables(self) -> list[str]:
        """Get list of required variable names."""
        return [var.name for var in self.variables if var.required]
    
    def add_tag(self, tag: str) -> None:
        """Add a tag."""
        if tag not in self.tags:
            self.tags.append(tag)
            self.update_timestamp()
    
    def remove_tag(self, tag: str) -> bool:
        """Remove a tag. Returns True if removed."""
        if tag in self.tags:
            self.tags.remove(tag)
            self.update_timestamp()
            return True
        return False
    
    def update_template(self, new_template: str) -> None:
        """Update template content."""
        self.template = new_template
        self.update_timestamp()
    
    def add_variable(self, variable: VariableDef) -> None:
        """Add a variable definition."""
        self.variables.append(variable)
        self.update_timestamp()
    
    def validate_template_structure(self, enforce_standard: bool = False) -> list[str]:
        """
        Validate template structure for agent task workflows.
        
        Checks if the template contains required sections for the 
        5-module framework (背景, 需求, 规则, 验收过程, 结束指标).
        
        Args:
            enforce_standard: If True, strictly enforce all 5 required sections
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not self.template:
            errors.append("Template is empty")
            return errors
        
        template_lower = self.template.lower()
        
        # Check for required sections
        for section in STANDARD_AGENT_SECTIONS["required"]:
            aliases = STANDARD_AGENT_SECTIONS["aliases"].get(section, [section])
            found = False
            
            for alias in aliases:
                # Check for markdown heading format: ## Section
                patterns = [
                    f"## {alias}",
                    f"## {alias}（",
                    f"## {alias}(",
                    f"## {alias}\n",
                    f"## {alias} ",
                ]
                if any(pattern.lower() in template_lower for pattern in patterns):
                    found = True
                    break
            
            if not found:
                errors.append(f"Missing required section: '{section}' (or its aliases: {aliases})")
        
        return errors
    
    def get_template_completeness(self) -> dict[str, any]:
        """
        Get template completeness analysis.
        
        Returns:
            Dictionary with completeness metrics
        """
        result = {
            "has_all_required_sections": False,
            "missing_sections": [],
            "present_sections": [],
            "optional_sections_present": [],
            "completeness_score": 0.0,
        }
        
        if not self.template:
            return result
        
        template_lower = self.template.lower()
        
        # Check required sections
        required_count = 0
        for section in STANDARD_AGENT_SECTIONS["required"]:
            aliases = STANDARD_AGENT_SECTIONS["aliases"].get(section, [section])
            found = False
            
            for alias in aliases:
                patterns = [f"## {alias}", f"## {alias}（", f"## {alias}(", f"## {alias}\n", f"## {alias} "]
                if any(pattern.lower() in template_lower for pattern in patterns):
                    found = True
                    break
            
            if found:
                required_count += 1
                result["present_sections"].append(section)
            else:
                result["missing_sections"].append(section)
        
        # Check optional sections
        for section in STANDARD_AGENT_SECTIONS["optional"]:
            aliases = [section, section.lower()]
            for alias in aliases:
                if f"## {alias}".lower() in template_lower:
                    result["optional_sections_present"].append(section)
                    break
        
        result["has_all_required_sections"] = required_count == len(STANDARD_AGENT_SECTIONS["required"])
        result["completeness_score"] = required_count / len(STANDARD_AGENT_SECTIONS["required"])
        
        return result
    
    def is_standard_agent_template(self) -> bool:
        """Check if this workflow follows the standard 5-module agent template."""
        return len(self.validate_template_structure()) == 0
