"""Agent configuration model - supports multiple agent types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from zima.models.base import BaseConfig, Metadata
from zima.utils import generate_timestamp, validate_code

# Agent-specific parameters templates
AGENT_PARAMETER_TEMPLATES = {
    "kimi": {
        "model": "kimi-code/kimi-for-coding",
        "maxStepsPerTurn": 50,
        "maxRalphIterations": 10,
        "maxRetriesPerStep": 3,
        "yolo": True,
        "workDir": "./workspace",
        "addDirs": [],
        "outputFormat": "text",
    },
    "claude": {
        "model": "claude-sonnet-4-6",
        "maxTurns": 100,
        "permissionMode": "plan",
        "outputFormat": "stream-json",
        "allowedTools": [],
        "disallowedTools": [],
        "systemPrompt": "",
        "appendSystemPrompt": "",
        "workDir": "./workspace",
        "addDirs": [],
    },
    "gemini": {
        "model": "gemini-2.5-flash",
        "approvalMode": "default",
        "checkpointing": False,
        "workDir": "./workspace",
        "addDirs": [],
        "outputFormat": "text",
    },
}

VALID_AGENT_TYPES = {"kimi", "claude", "gemini"}


@dataclass
class AgentConfig(BaseConfig):
    """
    Agent configuration model.

    Supports multiple agent types: kimi, claude, gemini

    Attributes:
        type: Agent type (kimi/claude/gemini)
        parameters: Type-specific parameters
        defaults: Default workflow/variable/env/pmg references
    """

    kind: str = "Agent"
    type: str = "kimi"
    parameters: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)

    def __post_init__(self):
        """Post-initialization: merge default parameters."""
        super().__post_init__()
        self._merge_default_parameters()

    def _merge_default_parameters(self) -> None:
        """Merge type-specific default parameters."""
        if self.type in AGENT_PARAMETER_TEMPLATES:
            template = AGENT_PARAMETER_TEMPLATES[self.type].copy()
            # User parameters override defaults
            template.update(self.parameters)
            self.parameters = template

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        agent_type: str = "kimi",
        description: str = "",
        parameters: Optional[dict] = None,
        defaults: Optional[dict] = None,
    ) -> AgentConfig:
        """
        Factory method to create a new AgentConfig.

        Args:
            code: Unique agent code
            name: Display name
            agent_type: Agent type (kimi/claude/gemini)
            description: Optional description
            parameters: Custom parameters (override defaults)
            defaults: Default workflow/variable/env/pmg references

        Returns:
            New AgentConfig instance

        Raises:
            ValueError: If agent_type is invalid
        """
        if agent_type not in VALID_AGENT_TYPES:
            raise ValueError(
                f"Invalid agent type: {agent_type}. " f"Valid types: {VALID_AGENT_TYPES}"
            )

        now = generate_timestamp()

        return cls(
            metadata=Metadata(code=code, name=name, description=description),
            type=agent_type,
            parameters=parameters or {},
            defaults=defaults or {},
            created_at=now,
            updated_at=now,
        )

    def validate(self) -> list[str]:
        """
        Validate agent configuration.

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

        # Validate type
        if not self.type:
            errors.append("spec.type is required")
        elif self.type not in VALID_AGENT_TYPES:
            errors.append(f"spec.type '{self.type}' is not valid. Valid: {VALID_AGENT_TYPES}")

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
                "type": self.type,
                "parameters": self.parameters,
                "defaults": self.defaults,
            },
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AgentConfig:
        """Create from dictionary."""
        spec = data.get("spec", {})

        return cls(
            api_version=data.get("apiVersion", "zima.io/v1"),
            kind=data.get("kind", "Agent"),
            metadata=Metadata.from_dict(data.get("metadata", {})),
            type=spec.get("type", "kimi"),
            parameters=spec.get("parameters", {}),
            defaults=spec.get("defaults", {}),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )

    @classmethod
    def from_yaml_file(cls, path: Path) -> AgentConfig:
        """Load from YAML file."""
        import yaml

        if not path.exists():
            raise FileNotFoundError(f"Agent config not found: {path}")

        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        return cls.from_dict(data or {})

    def get_cli_command_template(self) -> list[str]:
        """
        Get base CLI command template for this agent type.

        If ``mockCommand`` is set in parameters, returns that command as a
        list (intended for test use only).  ``mockCommand`` accepts either a
        string or a list of strings.  Otherwise returns the type-based
        template.

        Returns:
            Base command list (e.g., ["kimi", "--print", "--yolo"])
        """
        # Mock override: if mockCommand is set, use it instead of real CLI
        if self.parameters.get("mockCommand"):
            cmd = self.parameters["mockCommand"]
            return cmd if isinstance(cmd, list) else [str(cmd)]

        templates = {
            "kimi": ["kimi", "--print", "--yolo"],
            "claude": ["claude", "-p"],
            "gemini": ["gemini", "--yolo"],
        }
        return templates.get(self.type, [])

    def build_command(
        self,
        prompt_file: Optional[Path] = None,
        work_dir: Optional[Path] = None,
        extra_args: Optional[dict] = None,
    ) -> list[str]:
        """
        Build complete CLI command.

        Args:
            prompt_file: Path to prompt file
            work_dir: Working directory
            extra_args: Additional arguments to override parameters

        Returns:
            Complete command list
        """
        cmd = self.get_cli_command_template()

        # Merge parameters with extra args
        params = self.parameters.copy()
        if extra_args:
            params.update(extra_args)

        # Add type-specific parameters
        if self.type == "kimi":
            cmd = self._build_kimi_command(cmd, params)
        elif self.type == "claude":
            cmd = self._build_claude_command(cmd, params)
        elif self.type == "gemini":
            cmd = self._build_gemini_command(cmd, params)

        # Add prompt file - agent-type-specific handling
        # Claude Code: prompt passed via stdin pipe, not as CLI argument
        # Kimi: uses --prompt flag
        # Gemini: uses positional argument
        if prompt_file:
            if self.type == "kimi":
                cmd.extend(["--prompt", str(prompt_file)])
            elif self.type == "gemini":
                cmd.extend(["-p", str(prompt_file)])
            # Claude: prompt_file is passed via stdin pipe by the executor, not added to cmd

        if work_dir:
            if self.type == "gemini":
                cmd.extend(["--worktree", str(work_dir)])
            else:
                cmd.extend(["--work-dir", str(work_dir)])

        return cmd

    def _build_kimi_command(self, cmd: list[str], params: dict) -> list[str]:
        """Build Kimi-specific command arguments."""
        if params.get("model"):
            cmd.extend(["--model", str(params["model"])])

        if params.get("maxStepsPerTurn"):
            cmd.extend(["--max-steps-per-turn", str(params["maxStepsPerTurn"])])

        if params.get("maxRalphIterations"):
            cmd.extend(["--max-ralph-iterations", str(params["maxRalphIterations"])])

        if params.get("maxRetriesPerStep"):
            cmd.extend(["--max-retries-per-step", str(params["maxRetriesPerStep"])])

        # Handle addDirs
        for add_dir in params.get("addDirs", []):
            cmd.extend(["--add-dir", str(add_dir)])

        if params.get("outputFormat"):
            cmd.extend(["--output-format", str(params["outputFormat"])])

        return cmd

    def _build_claude_command(self, cmd: list[str], params: dict) -> list[str]:
        """Build Claude Code-specific command arguments.

        Claude Code CLI flags (from official docs):
          -p              : Print mode (non-interactive), reads prompt from stdin
          --model         : Model selection (sonnet, opus, haiku, or full name)
          --max-turns     : Limit agentic turns (print mode only)
          --permission-mode : Unattended execution (plan, bypassPermissions, etc.)
          --output-format : Output format (text, json, stream-json)
          --allowedTools  : Tool whitelist
          --disallowedTools : Tool blacklist
          --system-prompt : Replace system prompt
          --append-system-prompt : Append to default system prompt
          --add-dir       : Additional working directories
          --verbose       : Verbose logging (debug)
          --max-tokens    : Max output tokens
        """
        if params.get("model"):
            cmd.extend(["--model", str(params["model"])])

        if params.get("maxTurns"):
            cmd.extend(["--max-turns", str(params["maxTurns"])])

        if params.get("permissionMode"):
            cmd.extend(["--permission-mode", str(params["permissionMode"])])

        if params.get("outputFormat"):
            cmd.extend(["--output-format", str(params["outputFormat"])])

        if params.get("allowedTools"):
            tools = params["allowedTools"]
            if isinstance(tools, list) and tools:
                cmd.extend(["--allowedTools", ",".join(str(t) for t in tools)])

        if params.get("disallowedTools"):
            tools = params["disallowedTools"]
            if isinstance(tools, list) and tools:
                cmd.extend(["--disallowedTools", ",".join(str(t) for t in tools)])

        if params.get("systemPrompt"):
            cmd.extend(["--system-prompt", str(params["systemPrompt"])])

        if params.get("appendSystemPrompt"):
            cmd.extend(["--append-system-prompt", str(params["appendSystemPrompt"])])

        # Handle addDirs
        for add_dir in params.get("addDirs", []):
            cmd.extend(["--add-dir", str(add_dir)])

        if params.get("verbose"):
            cmd.append("--verbose")

        return cmd

    def _build_gemini_command(self, cmd: list[str], params: dict) -> list[str]:
        """Build Gemini-specific command arguments."""
        if params.get("model"):
            cmd.extend(["-m", str(params["model"])])

        if params.get("approvalMode") and params["approvalMode"] != "default":
            cmd.extend(["--approval-mode", str(params["approvalMode"])])

        if params.get("checkpointing"):
            cmd.append("--checkpointing")

        # Handle addDirs (for Gemini: --include-directories)
        for add_dir in params.get("addDirs", []):
            cmd.extend(["--include-directories", str(add_dir)])

        if params.get("outputFormat"):
            cmd.extend(["--output-format", str(params["outputFormat"])])

        return cmd

    @property
    def needs_stdin_pipe(self) -> bool:
        """Whether this agent type receives prompt via stdin pipe instead of CLI argument."""
        return self.type == "claude"

    def get_default(self, key: str, default: any = None) -> any:
        """
        Get default workflow/variable/env/pmg reference.

        Args:
            key: Key to look up (e.g., 'workflow', 'env')
            default: Default value if not found

        Returns:
            Default reference code or default value
        """
        return self.defaults.get(key, default)

    def set_default(self, key: str, code: str) -> None:
        """
        Set default workflow/variable/env/pmg reference.

        Args:
            key: Key to set (e.g., 'workflow', 'env')
            code: Reference code
        """
        self.defaults[key] = code
        self.update_timestamp()

    # Runtime properties for convenience
    @property
    def max_execution_time(self) -> int:
        """Get max execution time in seconds (default: 600)."""
        return self.parameters.get("maxExecutionTime", 600)

    @max_execution_time.setter
    def max_execution_time(self, value: int) -> None:
        """Set max execution time."""
        self.parameters["maxExecutionTime"] = value
        self.update_timestamp()

    @property
    def cycle_interval(self) -> int:
        """Get cycle interval in seconds (default: 900)."""
        return self.parameters.get("cycleInterval", 900)

    @cycle_interval.setter
    def cycle_interval(self, value: int) -> None:
        """Set cycle interval."""
        self.parameters["cycleInterval"] = value
        self.update_timestamp()

    @property
    def max_steps_per_turn(self) -> int:
        """Get max steps per turn (default: 50)."""
        return self.parameters.get("maxStepsPerTurn", 50)

    @max_steps_per_turn.setter
    def max_steps_per_turn(self, value: int) -> None:
        """Set max steps per turn."""
        self.parameters["maxStepsPerTurn"] = value
        self.update_timestamp()


# =============================================================================
# Legacy Models (for backward compatibility)
# =============================================================================

from dataclasses import field as _field  # noqa: E402
from datetime import datetime as _datetime  # noqa: E402
from typing import Optional as _Optional  # noqa: E402


@dataclass
class AgentState:
    """Minimal agent state (legacy)."""

    agent_id: str
    status: str = "idle"  # idle, running, completed, failed
    created_at: _Optional[str] = None
    updated_at: _Optional[str] = None
    last_run: _Optional[dict] = None  # 上次运行记录

    def to_dict(self) -> dict:
        return {
            "agentId": self.agent_id,
            "status": self.status,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "lastRun": self.last_run,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AgentState:
        return cls(
            agent_id=data.get("agentId", "unknown"),
            status=data.get("status", "idle"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            last_run=data.get("lastRun"),
        )


@dataclass
class RunResult:
    """Result of a single run (legacy)."""

    status: str  # completed, failed, timeout
    summary: str = ""
    output: str = ""  # stdout内容
    elapsed_time: float = 0.0
    return_code: int = 0
    timestamp: str = _field(default_factory=lambda: _datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "summary": self.summary,
            "elapsedTime": self.elapsed_time,
            "returnCode": self.return_code,
            "timestamp": self.timestamp,
        }


@dataclass
class CycleResult:
    """Result of a single agent cycle execution."""

    cycle_num: int
    status: str  # completed, partial, failed, timeout, error, unknown
    progress: int = 0  # 0-100
    summary: str = ""
    details: str = ""
    next_action: str = "continue"  # continue, wait, complete, fix, retry
    log_file: _Optional[Path] = None
    prompt_file: _Optional[Path] = None
    result_file: _Optional[Path] = None
    elapsed_time: float = 0.0
    return_code: int = 0

    def to_dict(self) -> dict:
        result = {
            "cycleNum": self.cycle_num,
            "status": self.status,
            "progress": self.progress,
            "summary": self.summary,
            "nextAction": self.next_action,
            "elapsedTime": self.elapsed_time,
            "returnCode": self.return_code,
        }
        if self.details:
            result["details"] = self.details
        if self.log_file:
            result["logFile"] = str(self.log_file)
        if self.prompt_file:
            result["promptFile"] = str(self.prompt_file)
        if self.result_file:
            result["resultFile"] = str(self.result_file)
        return result
