"""Agent data models"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class AgentStatus(Enum):
    """Agent runtime status"""
    IDLE = "idle"
    RUNNING = "running"
    WAITING_ASYNC = "waiting_async"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class PipelineStage:
    """Pipeline stage definition"""
    name: str
    description: str
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict] = None


@dataclass
class AsyncTask:
    """Async task state"""
    name: str
    status: str  # idle, running, completed
    process_id: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict] = None


@dataclass
class AgentConfig:
    """Agent configuration from agent.yaml"""
    
    # Metadata
    name: str
    description: str = ""
    
    # Paths
    workspace: Path = field(default_factory=lambda: Path("./workspace"))
    
    # Cycle configuration
    cycle_interval: int = 900  # 15 minutes in seconds
    max_execution_time: int = 840  # 14 minutes in seconds
    early_completion: bool = True
    
    # Timeout configuration
    max_cycles: int = 100
    max_duration: str = "24h"
    max_retries: int = 3
    
    # Initial task
    initial_task: dict = field(default_factory=dict)
    
    # Pipeline
    pipeline: list[dict] = field(default_factory=list)
    
    # Tools
    tools: list[str] = field(default_factory=lambda: [
        "file/read", "file/write", "file/replace", "shell/powershell"
    ])
    
    # Model configuration
    max_steps_per_turn: int = 50
    
    @classmethod
    def from_yaml(cls, path: Path) -> AgentConfig:
        """Load config from YAML file"""
        import yaml
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        spec = data.get("spec", {})
        
        # Resolve workspace to absolute path (relative to agent directory)
        agent_dir = path.parent
        workspace_rel = spec.get("workspace", "./workspace")
        workspace = (agent_dir / workspace_rel).resolve()
        
        return cls(
            name=data.get("metadata", {}).get("name", "unnamed-agent"),
            description=data.get("metadata", {}).get("description", ""),
            workspace=workspace,
            cycle_interval=spec.get("cycle", {}).get("interval", 900),
            max_execution_time=spec.get("cycle", {}).get("maxExecutionTime", 840),
            early_completion=spec.get("cycle", {}).get("earlyCompletion", True),
            max_cycles=spec.get("timeout", {}).get("maxCycles", 100),
            max_duration=spec.get("timeout", {}).get("maxDuration", "24h"),
            max_retries=spec.get("timeout", {}).get("maxRetries", 3),
            initial_task=spec.get("initialTask", {}),
            pipeline=spec.get("pipeline", []),
            tools=spec.get("capabilities", {}).get("tools", []),
            max_steps_per_turn=spec.get("runtime", {}).get("maxStepsPerTurn", 50),
        )
    
    def to_yaml(self, path: Path) -> None:
        """Save config to YAML file"""
        import yaml
        
        data = {
            "apiVersion": "zima.io/v1",
            "kind": "Agent",
            "metadata": {
                "name": self.name,
                "description": self.description,
            },
            "spec": {
                "workspace": str(self.workspace),
                "cycle": {
                    "interval": self.cycle_interval,
                    "maxExecutionTime": self.max_execution_time,
                    "earlyCompletion": self.early_completion,
                },
                "timeout": {
                    "maxCycles": self.max_cycles,
                    "maxDuration": self.max_duration,
                    "maxRetries": self.max_retries,
                },
                "initialTask": self.initial_task,
                "pipeline": self.pipeline,
                "capabilities": {
                    "tools": self.tools,
                },
                "runtime": {
                    "maxStepsPerTurn": self.max_steps_per_turn,
                },
            },
        }
        
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


@dataclass
class AgentState:
    """Agent runtime state (persisted to state.json)"""
    
    agent_id: str
    current_cycle: int = 0
    status: str = "idle"
    current_stage: str = ""
    stages: list[dict] = field(default_factory=list)
    async_tasks: dict = field(default_factory=dict)
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    retry_count: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "agentId": self.agent_id,
            "currentCycle": self.current_cycle,
            "status": self.status,
            "currentStage": self.current_stage,
            "stages": self.stages,
            "asyncTasks": self.async_tasks,
            "startedAt": self.started_at,
            "updatedAt": self.updated_at,
            "retryCount": self.retry_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> AgentState:
        """Create from dictionary"""
        return cls(
            agent_id=data.get("agentId", "unknown"),
            current_cycle=data.get("currentCycle", 0),
            status=data.get("status", "idle"),
            current_stage=data.get("currentStage", ""),
            stages=data.get("stages", []),
            async_tasks=data.get("asyncTasks", {}),
            started_at=data.get("startedAt"),
            updated_at=data.get("updatedAt"),
            retry_count=data.get("retryCount", {}),
        )


@dataclass
class CycleResult:
    """Result of a single cycle execution"""
    
    cycle_num: int
    status: str  # completed, partial, timeout, error, async_started
    progress: int  # 0-100
    summary: str = ""
    details: str = ""
    next_action: str = "continue"  # continue, wait, complete, fix
    log_file: Optional[Path] = None
    prompt_file: Optional[Path] = None
    result_file: Optional[Path] = None
    elapsed_time: float = 0.0
    return_code: int = 0
    
    @property
    def is_early_completion(self) -> bool:
        """Check if this cycle completed early"""
        return self.status in ("completed", "async_started") and self.elapsed_time < 600


@dataclass
class Session:
    """Session record (one per cycle)"""
    
    id: str
    cycle: int
    agent: str
    date: str
    task: str = ""
    execution: str = ""
    result: str = ""
    learnings: str = ""
    next_steps: str = ""
    
    def to_markdown(self) -> str:
        """Convert to markdown format"""
        return f"""---
id: {self.id}
cycle: {self.cycle}
agent: {self.agent}
date: {self.date}
type: session
---

# Session {self.date}

## Task
{self.task}

## Execution
{self.execution}

## Result
{self.result}

## Learnings
{self.learnings}

## Next Steps
{self.next_steps}
"""
