"""ConfigBundle - resolves and combines all configurations for PJob execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from zima.config.manager import ConfigManager
from zima.models.agent import AgentConfig
from zima.models.env import EnvConfig
from zima.models.pmg import PMGConfig
from zima.models.pjob import Overrides
from zima.models.variable import VariableConfig
from zima.models.workflow import WorkflowConfig


@dataclass
class ConfigBundle:
    """
    Resolved configuration bundle for PJob execution.
    
    Combines all referenced configurations with proper priority resolution:
    1. PJob.spec.overrides (highest)
    2. PJob.spec.* (explicit refs)
    3. Agent.spec.defaults
    4. System defaults (lowest)
    
    Attributes:
        agent: Resolved Agent config
        workflow: Resolved Workflow config
        variable: Resolved Variable config (optional)
        env: Resolved Env config (optional)
        pmg: Resolved PMG config (optional)
        overrides: Runtime overrides from PJob
        work_dir: Final working directory
    """
    agent: AgentConfig = field(default_factory=lambda: AgentConfig())
    workflow: WorkflowConfig = field(default_factory=lambda: WorkflowConfig())
    variable: Optional[VariableConfig] = None
    env: Optional[EnvConfig] = None
    pmg: Optional[PMGConfig] = None
    overrides: Overrides = field(default_factory=Overrides)
    work_dir: str = ""
    
    @classmethod
    def resolve(
        cls,
        pjob_agent: str,
        pjob_workflow: str,
        pjob_variable: str = "",
        pjob_env: str = "",
        pjob_pmg: str = "",
        pjob_overrides: Optional[Overrides] = None,
        pjob_work_dir: str = "",
    ) -> ConfigBundle:
        """
        Resolve all configurations for PJob execution.
        
        This method implements the configuration priority logic:
        1. Load agent and get its defaults
        2. Use PJob refs if specified, otherwise use agent defaults
        3. Apply overrides on top
        
        Args:
            pjob_agent: Agent code from PJob (required)
            pjob_workflow: Workflow code from PJob (required)
            pjob_variable: Variable code from PJob (optional)
            pjob_env: Env code from PJob (optional)
            pjob_pmg: PMG code from PJob (optional)
            pjob_overrides: Overrides from PJob (optional)
            pjob_work_dir: Work dir from PJob (optional)
            
        Returns:
            Resolved ConfigBundle
            
        Raises:
            ValueError: If required configs not found
        """
        manager = ConfigManager()
        bundle = cls()
        bundle.overrides = pjob_overrides or Overrides()
        
        # 1. Load required Agent
        if not manager.config_exists("agent", pjob_agent):
            raise ValueError(f"Agent '{pjob_agent}' not found")
        agent_data = manager.load_config("agent", pjob_agent)
        bundle.agent = AgentConfig.from_dict(agent_data)
        
        # 2. Load required Workflow
        if not manager.config_exists("workflow", pjob_workflow):
            raise ValueError(f"Workflow '{pjob_workflow}' not found")
        workflow_data = manager.load_config("workflow", pjob_workflow)
        bundle.workflow = WorkflowConfig.from_dict(workflow_data)
        
        # 3. Resolve Variable (PJob > Agent defaults)
        variable_code = pjob_variable or bundle.agent.defaults.get("variable", "")
        if variable_code and manager.config_exists("variable", variable_code):
            variable_data = manager.load_config("variable", variable_code)
            bundle.variable = VariableConfig.from_dict(variable_data)
        
        # 4. Resolve Env (PJob > Agent defaults)
        env_code = pjob_env or bundle.agent.defaults.get("env", "")
        if env_code and manager.config_exists("env", env_code):
            env_data = manager.load_config("env", env_code)
            bundle.env = EnvConfig.from_dict(env_data)
        
        # 5. Resolve PMG (PJob > Agent defaults)
        pmg_code = pjob_pmg or bundle.agent.defaults.get("pmg", "")
        if pmg_code and manager.config_exists("pmg", pmg_code):
            pmg_data = manager.load_config("pmg", pmg_code)
            bundle.pmg = PMGConfig.from_dict(pmg_data)
        
        # 6. Resolve work_dir (PJob > Agent params > current dir)
        if pjob_work_dir:
            bundle.work_dir = pjob_work_dir
        elif bundle.agent.parameters.get("workDir"):
            bundle.work_dir = bundle.agent.parameters["workDir"]
        else:
            bundle.work_dir = "."
        
        return bundle
    
    def apply_overrides(self, overrides: Overrides) -> None:
        """
        Apply runtime overrides to the bundle.
        
        Overrides have the highest priority and modify the resolved configs.
        
        Args:
            overrides: Overrides to apply
        """
        if overrides.is_empty():
            return
        
        self.overrides = overrides
        
        # Apply agent parameter overrides
        if overrides.agent_params:
            self.agent.parameters.update(overrides.agent_params)
        
        # Apply variable value overrides
        if overrides.variable_values and self.variable:
            self._deep_update(self.variable.values, overrides.variable_values)
        
        # Apply env var overrides (stored in bundle, applied at execution)
        # PMG params are handled during command building
    
    def _deep_update(self, base: dict, update: dict) -> None:
        """Deep update dictionary."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    def get_variable_values(self) -> dict:
        """
        Get merged variable values for template rendering.
        
        Returns:
            Dictionary of variable values
        """
        if self.variable:
            return self.variable.values.copy()
        return {}
    
    def get_env_variables(self) -> dict[str, str]:
        """
        Get resolved environment variables.
        
        Returns:
            Dictionary of environment variables
        """
        env_vars = {}
        
        if self.env:
            # Get plain variables
            env_vars.update(self.env.variables)
            
            # Resolve secrets (this would need actual implementation)
            # For now, return the variable names with placeholder values
            # Real implementation would resolve from env/file/cmd/vault
        
        # Apply overrides (highest priority)
        env_vars.update(self.overrides.env_vars)
        
        return env_vars
    
    def build_agent_params(self) -> list[str]:
        """
        Build command-line parameters for Agent.
        
        Combines PMG parameters with override parameters.
        
        Returns:
            List of command-line arguments
        """
        params = []
        
        # Get PMG parameters
        if self.pmg:
            params.extend(self.pmg.build_params())
        
        # Add override PMG params
        for param_def in self.overrides.pmg_params:
            param_str = self._format_pmg_param(param_def)
            if param_str:
                params.append(param_str)
        
        return params
    
    def _format_pmg_param(self, param_def: dict) -> str:
        """Format a single PMG parameter definition."""
        param_type = param_def.get("type", "long")
        name = param_def.get("name", "")
        value = param_def.get("value")
        values = param_def.get("values", [])
        enabled = param_def.get("enabled", True)
        
        if not name:
            return ""
        
        if param_type == "long":
            return f"--{name} {value}" if value is not None else f"--{name}"
        elif param_type == "short":
            return f"-{name}"
        elif param_type == "flag":
            return f"--{name}" if enabled else ""
        elif param_type == "positional":
            return str(value) if value is not None else ""
        elif param_type == "repeatable":
            return " ".join(f"--{name} {v}" for v in values)
        elif param_type == "json":
            import json
            return f"--{name} '{json.dumps(value)}'" if value is not None else ""
        elif param_type == "key-value":
            if isinstance(value, dict):
                kv_str = ",".join(f"{k}={v}" for k, v in value.items())
                return f"--{name} {kv_str}"
        
        return ""
    
    def build_command(
        self,
        prompt_file: Path,
        work_dir: Optional[str] = None,
    ) -> list[str]:
        """
        Build the complete agent command.

        Delegates type-specific command building to AgentConfig.build_command()
        which handles each agent's unique CLI flags and prompt passing mechanism.
        Then appends PMG parameters on top.

        Args:
            prompt_file: Path to the rendered prompt file
            work_dir: Override work directory (optional)

        Returns:
            Command as list of arguments (for subprocess)
        """
        # Delegate to AgentConfig for type-specific command building
        cmd = self.agent.build_command(
            prompt_file=prompt_file,
            work_dir=Path(work_dir) if work_dir else None,
        )

        # Append PMG parameters (generic, agent-agnostic)
        pmg_params = self.build_agent_params()
        cmd.extend(pmg_params)

        return cmd
    
    def to_summary(self) -> dict:
        """
        Get summary of resolved configurations.
        
        Returns:
            Summary dictionary
        """
        return {
            "agent": {
                "code": self.agent.metadata.code,
                "type": self.agent.type,
                "name": self.agent.metadata.name,
            },
            "workflow": {
                "code": self.workflow.metadata.code,
                "name": self.workflow.metadata.name,
            },
            "variable": {
                "code": self.variable.metadata.code if self.variable else None,
                "name": self.variable.metadata.name if self.variable else None,
            },
            "env": {
                "code": self.env.metadata.code if self.env else None,
                "name": self.env.metadata.name if self.env else None,
            },
            "pmg": {
                "code": self.pmg.metadata.code if self.pmg else None,
                "name": self.pmg.metadata.name if self.pmg else None,
            },
            "work_dir": self.work_dir,
            "has_overrides": not self.overrides.is_empty(),
        }
