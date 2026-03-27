"""Parameters Group (PMG) configuration model."""

from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from zima.models.base import BaseConfig, Metadata
from zima.utils import generate_timestamp, validate_code


# Valid parameter types
VALID_PARAM_TYPES = {
    "long", "short", "flag", "positional", 
    "repeatable", "json", "key-value"
}

# Valid agent types for PMG
VALID_PMG_FOR_TYPES = {"kimi", "claude", "gemini"}


@dataclass
class ParameterDef:
    """
    Parameter definition for PMG.
    
    Attributes:
        name: Parameter name
        type: Parameter type (long/short/flag/positional/repeatable/json/key-value)
        value: Single value (for long, short, positional, json, key-value types)
        values: Multiple values (for repeatable type)
        enabled: Whether flag is enabled (for flag type)
    """
    name: str
    type: str
    value: any = None
    values: list = field(default_factory=list)
    enabled: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "type": self.type,
        }
        
        if self.type == "flag":
            result["enabled"] = self.enabled
        elif self.type == "repeatable":
            if self.values:
                result["values"] = self.values
        elif self.value is not None:
            result["value"] = self.value
        
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> ParameterDef:
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            type=data.get("type", ""),
            value=data.get("value"),
            values=data.get("values", []),
            enabled=data.get("enabled", True)
        )
    
    def validate(self) -> list[str]:
        """Validate parameter definition."""
        errors = []
        
        if not self.name:
            errors.append("Parameter name is required")
        
        if not self.type:
            errors.append("Parameter type is required")
        elif self.type not in VALID_PARAM_TYPES:
            errors.append(f"Invalid parameter type: {self.type}. Valid: {VALID_PARAM_TYPES}")
        
        # Type-specific validation
        if self.type == "flag":
            # Flag type doesn't need value/values
            pass
        elif self.type == "repeatable":
            if not self.values:
                errors.append(f"Parameter '{self.name}': repeatable type requires 'values'")
        elif self.value is None:
            # Other types need value
            errors.append(f"Parameter '{self.name}': type '{self.type}' requires 'value'")
        
        return errors
    
    def render(self) -> list[str]:
        """
        Render parameter as command-line arguments.
        
        Returns:
            List of argument strings
        """
        if self.type == "long":
            return [f"--{self.name}", str(self.value)]
        
        elif self.type == "short":
            if isinstance(self.value, bool):
                return [f"-{self.name}"] if self.value else []
            else:
                return [f"-{self.name}", str(self.value)]
        
        elif self.type == "flag":
            return [f"--{self.name}"] if self.enabled else []
        
        elif self.type == "positional":
            return [str(self.value)]
        
        elif self.type == "repeatable":
            args = []
            for val in self.values:
                args.extend([f"--{self.name}", str(val)])
            return args
        
        elif self.type == "json":
            if isinstance(self.value, dict):
                json_str = json.dumps(self.value, separators=(',', ':'))
            else:
                json_str = str(self.value)
            return [f"--{self.name}", json_str]
        
        elif self.type == "key-value":
            if isinstance(self.value, dict):
                kv_str = ",".join(f"{k}={v}" for k, v in self.value.items())
            else:
                kv_str = str(self.value)
            return [f"--{self.name}", kv_str]
        
        return []


@dataclass
class ExtendDef:
    """PMG inheritance definition."""
    code: str
    override: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {"code": self.code}
        if self.override:
            result["override"] = True
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> ExtendDef:
        """Create from dictionary."""
        if isinstance(data, str):
            return cls(code=data)
        return cls(
            code=data.get("code", ""),
            override=data.get("override", False)
        )


@dataclass
class ConditionDef:
    """Condition definition for conditional parameters."""
    when: str
    parameters: list[ParameterDef] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "when": self.when,
            "parameters": [p.to_dict() for p in self.parameters]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> ConditionDef:
        """Create from dictionary."""
        params_data = data.get("parameters", [])
        parameters = [ParameterDef.from_dict(p) if isinstance(p, dict) else p for p in params_data]
        return cls(
            when=data.get("when", ""),
            parameters=parameters
        )


class ConditionEvaluator:
    """Evaluator for condition expressions."""
    
    @staticmethod
    def evaluate(expression: str) -> bool:
        """
        Evaluate a condition expression.
        
        Supported variables:
        - os: Operating system (windows, linux, darwin)
        - arch: Architecture (amd64, arm64)
        - env.XXX: Environment variable
        
        Supported operators:
        - ==, !=
        - && (and), || (or)
        
        Args:
            expression: Condition expression string
            
        Returns:
            True if condition is satisfied
        """
        if not expression:
            return True
        
        # Get system info
        context = ConditionEvaluator._build_context()
        
        # Replace variables with values
        expr = ConditionEvaluator._substitute_variables(expression, context)
        
        # Evaluate simple boolean expression
        try:
            # Security: only allow safe characters
            if not re.match(r'^[\s\w\'"=!=&|().]+$', expr):
                return False
            
            # Replace Python operators
            expr = expr.replace("&&", " and ").replace("||", " or ")
            
            return eval(expr, {"__builtins__": {}}, {})
        except Exception:
            return False
    
    @staticmethod
    def _build_context() -> dict:
        """Build evaluation context with system info."""
        system = platform.system().lower()
        os_map = {
            "windows": "windows",
            "linux": "linux",
            "darwin": "darwin"
        }
        
        machine = platform.machine().lower()
        arch_map = {
            "amd64": "amd64",
            "x86_64": "amd64",
            "arm64": "arm64",
            "aarch64": "arm64"
        }
        
        return {
            "os": os_map.get(system, system),
            "arch": arch_map.get(machine, machine)
        }
    
    @staticmethod
    def _substitute_variables(expression: str, context: dict) -> str:
        """Substitute variables in expression with their values."""
        result = expression
        
        # Replace os variable
        result = re.sub(r'\bos\b', f"'{context.get('os', '')}'", result)
        
        # Replace arch variable
        result = re.sub(r'\barch\b', f"'{context.get('arch', '')}'", result)
        
        # Replace env.XXX variables
        def replace_env_var(match):
            var_name = match.group(1)
            value = __import__('os').environ.get(var_name, "")
            return f"'{value}'"
        
        result = re.sub(r'\benv\.(\w+)\b', replace_env_var, result)
        
        return result


@dataclass
class PMGConfig(BaseConfig):
    """
    Parameters Group configuration model.
    
    Defines command-line parameters for Agent execution.
    Supports parameter inheritance and conditional parameters.
    
    Attributes:
        for_types: List of agent types this PMG applies to
        parameters: List of parameter definitions
        raw: Raw parameter string to append
        extends: List of PMGs to inherit from
        conditions: List of conditional parameter groups
    """
    kind: str = "PMG"
    for_types: list[str] = field(default_factory=list)
    parameters: list[ParameterDef] = field(default_factory=list)
    raw: str = ""
    extends: list[ExtendDef] = field(default_factory=list)
    conditions: list[ConditionDef] = field(default_factory=list)
    
    def __post_init__(self):
        """Post-initialization processing."""
        super().__post_init__()
        # Ensure lists
        if self.for_types is None:
            self.for_types = []
        if self.parameters is None:
            self.parameters = []
        if self.extends is None:
            self.extends = []
        if self.conditions is None:
            self.conditions = []
    
    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        for_types: list[str],
        description: str = "",
        parameters: Optional[list[dict]] = None,
        raw: str = "",
        extends: Optional[list[dict]] = None,
        conditions: Optional[list[dict]] = None
    ) -> PMGConfig:
        """
        Factory method to create a new PMGConfig.
        
        Args:
            code: Unique PMG code
            name: Display name
            for_types: List of agent types
            description: Optional description
            parameters: Parameter definitions
            raw: Raw parameter string
            extends: Inheritance definitions
            conditions: Conditional parameter groups
            
        Returns:
            New PMGConfig instance
        """
        # Convert parameter dicts to ParameterDef objects
        param_defs = []
        if parameters:
            for param_data in parameters:
                if isinstance(param_data, dict):
                    param_defs.append(ParameterDef.from_dict(param_data))
                elif isinstance(param_data, ParameterDef):
                    param_defs.append(param_data)
        
        # Convert extend dicts to ExtendDef objects
        extend_defs = []
        if extends:
            for ext_data in extends:
                if isinstance(ext_data, dict):
                    extend_defs.append(ExtendDef.from_dict(ext_data))
                elif isinstance(ext_data, str):
                    extend_defs.append(ExtendDef(code=ext_data))
                elif isinstance(ext_data, ExtendDef):
                    extend_defs.append(ext_data)
        
        # Convert condition dicts to ConditionDef objects
        condition_defs = []
        if conditions:
            for cond_data in conditions:
                if isinstance(cond_data, dict):
                    condition_defs.append(ConditionDef.from_dict(cond_data))
                elif isinstance(cond_data, ConditionDef):
                    condition_defs.append(cond_data)
        
        now = generate_timestamp()
        
        return cls(
            metadata=Metadata(
                code=code,
                name=name,
                description=description
            ),
            for_types=for_types,
            parameters=param_defs,
            raw=raw,
            extends=extend_defs,
            conditions=condition_defs,
            created_at=now,
            updated_at=now
        )
    
    def validate(self) -> list[str]:
        """
        Validate PMG configuration.
        
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
        
        # Validate for_types
        if not self.for_types:
            errors.append("spec.forTypes is required")
        else:
            for ft in self.for_types:
                if ft not in VALID_PMG_FOR_TYPES:
                    errors.append(f"Invalid forType: {ft}. Valid: {VALID_PMG_FOR_TYPES}")
        
        # Validate parameters
        param_names = set()
        for param in self.parameters:
            param_errors = param.validate()
            errors.extend(param_errors)
            
            # Check for duplicate names
            if param.name in param_names:
                errors.append(f"Duplicate parameter name: {param.name}")
            param_names.add(param.name)
        
        # Validate conditions
        for cond in self.conditions:
            if not cond.when:
                errors.append("Condition 'when' expression is required")
            for param in cond.parameters:
                param_errors = param.validate()
                errors.extend(param_errors)
        
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
                "forTypes": self.for_types,
                "parameters": [p.to_dict() for p in self.parameters],
                "raw": self.raw,
                "extends": [e.to_dict() for e in self.extends],
                "conditions": [c.to_dict() for c in self.conditions],
            },
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> PMGConfig:
        """Create from dictionary."""
        spec = data.get("spec", {})
        
        # Parse parameters
        param_data = spec.get("parameters", [])
        parameters = [ParameterDef.from_dict(p) if isinstance(p, dict) else p for p in param_data]
        
        # Parse extends
        extend_data = spec.get("extends", [])
        extends = []
        for e in extend_data:
            if isinstance(e, dict):
                extends.append(ExtendDef.from_dict(e))
            elif isinstance(e, str):
                extends.append(ExtendDef(code=e))
        
        # Parse conditions
        condition_data = spec.get("conditions", [])
        conditions = [ConditionDef.from_dict(c) if isinstance(c, dict) else c for c in condition_data]
        
        return cls(
            api_version=data.get("apiVersion", "zima.io/v1"),
            kind=data.get("kind", "PMG"),
            metadata=Metadata.from_dict(data.get("metadata", {})),
            for_types=spec.get("forTypes", []),
            parameters=parameters,
            raw=spec.get("raw", ""),
            extends=extends,
            conditions=conditions,
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )
    
    @classmethod
    def from_yaml_file(cls, path: Path) -> PMGConfig:
        """Load from YAML file."""
        import yaml
        
        if not path.exists():
            raise FileNotFoundError(f"PMG config not found: {path}")
        
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return cls.from_dict(data or {})
    
    # ========================================================================
    # Parameter Management
    # ========================================================================
    
    def add_parameter(self, parameter: ParameterDef) -> None:
        """
        Add a parameter.
        
        Args:
            parameter: Parameter definition
        """
        # Remove existing parameter with same name
        self.parameters = [p for p in self.parameters if p.name != parameter.name]
        self.parameters.append(parameter)
        self.update_timestamp()
    
    def remove_parameter(self, name: str) -> bool:
        """
        Remove a parameter.
        
        Args:
            name: Parameter name
            
        Returns:
            True if removed, False if not found
        """
        original_len = len(self.parameters)
        self.parameters = [p for p in self.parameters if p.name != name]
        
        if len(self.parameters) < original_len:
            self.update_timestamp()
            return True
        return False
    
    def get_parameter(self, name: str) -> Optional[ParameterDef]:
        """Get a parameter by name."""
        for param in self.parameters:
            if param.name == name:
                return param
        return None
    
    def list_parameters(self) -> list[str]:
        """List all parameter names."""
        return [p.name for p in self.parameters]
    
    # ========================================================================
    # Build Command
    # ========================================================================
    
    def build_command(
        self, 
        eval_conditions: bool = True,
        loaded_pmgs: Optional[dict[str, 'PMGConfig']] = None
    ) -> list[str]:
        """
        Build command-line arguments.
        
        Args:
            eval_conditions: Whether to evaluate conditions
            loaded_pmgs: Dict of already loaded PMGs for inheritance
            
        Returns:
            List of command-line arguments
        """
        args = []
        processed_params = {}  # name -> ParameterDef
        
        # Process inheritance first
        if loaded_pmgs:
            for extend in self.extends:
                parent = loaded_pmgs.get(extend.code)
                if parent:
                    parent_args = parent.build_command(eval_conditions=False, loaded_pmgs=loaded_pmgs)
                    # Convert back to params (simplified)
                    for param in parent.parameters:
                        if extend.override or param.name not in processed_params:
                            processed_params[param.name] = param
        
        # Add own parameters
        for param in self.parameters:
            processed_params[param.name] = param
        
        # Render parameters
        for param in processed_params.values():
            args.extend(param.render())
        
        # Process conditions
        if eval_conditions:
            for cond in self.conditions:
                if ConditionEvaluator.evaluate(cond.when):
                    for param in cond.parameters:
                        args.extend(param.render())
        
        # Add raw string
        if self.raw:
            args.extend(self.raw.split())
        
        return args
    
    def build_command_string(
        self, 
        eval_conditions: bool = True,
        loaded_pmgs: Optional[dict[str, 'PMGConfig']] = None
    ) -> str:
        """
        Build command-line arguments as a string.
        
        Args:
            eval_conditions: Whether to evaluate conditions
            loaded_pmgs: Dict of already loaded PMGs for inheritance
            
        Returns:
            Command-line string
        """
        args = self.build_command(eval_conditions, loaded_pmgs)
        return " ".join(args)
