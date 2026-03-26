"""Agent data models - Simplified v2"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class AgentConfig:
    """Agent configuration - manages Kimi CLI launch parameters"""
    
    # Metadata (核心元数据)
    name: str
    description: str = ""
    
    # Workspace (工作目录)
    workspace: Path = field(default_factory=lambda: Path("./workspace"))
    
    # Prompt Configuration (提示词配置)
    prompt_file: str = "prompt.md"  # 主提示词文件
    prompt_vars: dict = field(default_factory=dict)  # 提示词变量
    
    # Kimi CLI Parameters (Kimi 启动参数)
    max_execution_time: int = 900  # 最大执行时间(秒)
    max_steps_per_turn: int = 50   # 每轮最大步数
    max_ralph_iterations: int = 10 # Ralph迭代次数
    
    @classmethod
    def from_yaml(cls, path: Path) -> AgentConfig:
        """Load config from agent.yaml"""
        import yaml
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        agent_dir = path.parent
        spec = data.get("spec", {})
        
        # Resolve workspace
        workspace_rel = spec.get("workspace", "./workspace")
        workspace = (agent_dir / workspace_rel).resolve()
        
        return cls(
            name=data.get("metadata", {}).get("name", "unnamed-agent"),
            description=data.get("metadata", {}).get("description", ""),
            workspace=workspace,
            prompt_file=spec.get("prompt", {}).get("file", "prompt.md"),
            prompt_vars=spec.get("prompt", {}).get("vars", {}),
            max_execution_time=spec.get("execution", {}).get("maxTime", 900),
            max_steps_per_turn=spec.get("execution", {}).get("maxStepsPerTurn", 50),
            max_ralph_iterations=spec.get("execution", {}).get("maxRalphIterations", 10),
        )
    
    def get_kimi_cmd(self, agent_dir: Path) -> list[str]:
        """Generate kimi CLI command"""
        prompt_path = agent_dir / self.prompt_file
        
        return [
            "kimi",
            "--print",
            "--yolo",
            "--prompt", str(prompt_path),
            "--work-dir", str(self.workspace),
            "--max-steps-per-turn", str(self.max_steps_per_turn),
            "--max-ralph-iterations", str(self.max_ralph_iterations),
        ]


@dataclass
class AgentState:
    """Minimal agent state"""
    
    agent_id: str
    status: str = "idle"  # idle, running, completed, failed
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_run: Optional[dict] = None  # 上次运行记录
    
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
    """Result of a single run"""
    
    status: str  # completed, failed, timeout
    summary: str = ""
    output: str = ""  # stdout内容
    elapsed_time: float = 0.0
    return_code: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "summary": self.summary,
            "elapsedTime": self.elapsed_time,
            "returnCode": self.return_code,
            "timestamp": self.timestamp,
        }
