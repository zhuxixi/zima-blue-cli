"""State management for agents"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from zima.models import AgentState


class StateManager:
    """Manages agent state persistence"""

    def __init__(self, agent_dir: Path):
        self.agent_dir = agent_dir
        self.state_file = agent_dir / "state.json"
        self.sessions_dir = agent_dir / "sessions"
        self.checkpoints_dir = agent_dir / "checkpoints"

        # Ensure directories exist
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> AgentState:
        """Load agent state from file"""
        if not self.state_file.exists():
            # Create default state
            return AgentState(
                agent_id=self.agent_dir.name,
                started_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AgentState.from_dict(data)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ Error loading state: {e}")
            return AgentState(
                agent_id=self.agent_dir.name,
                started_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )

    def save_state(self, state: AgentState) -> None:
        """Save agent state to file"""
        state.updated_at = datetime.now().isoformat()

        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

    def create_session(
        self,
        cycle_num: int,
        agent_name: str,
        task: str,
        execution: str,
        result: str,
        learnings: str = "",
        next_steps: str = "",
    ) -> Path:
        """Create a session record"""
        from zima.models import Session

        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        session_id = f"session-{timestamp}"

        session = Session(
            id=session_id,
            cycle=cycle_num,
            agent=agent_name,
            date=datetime.now().isoformat(),
            task=task,
            execution=execution,
            result=result,
            learnings=learnings,
            next_steps=next_steps,
        )

        session_file = self.sessions_dir / f"{timestamp}.md"
        session_file.write_text(session.to_markdown(), encoding="utf-8")

        return session_file

    def get_recent_sessions(self, count: int = 3) -> list[str]:
        """Get content of recent session files"""
        sessions = sorted(self.sessions_dir.glob("*.md"), reverse=True)

        contents = []
        for session_file in sessions[:count]:
            try:
                contents.append(session_file.read_text(encoding="utf-8"))
            except IOError:
                continue

        return contents

    def create_checkpoint(self, state: AgentState, progress: int, log_file: Path) -> Path:
        """Create a checkpoint for timeout recovery"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_file = self.checkpoints_dir / f"checkpoint_{timestamp}.json"

        checkpoint = {
            "cycle": state.current_cycle,
            "timestamp": datetime.now().isoformat(),
            "reason": "timeout",
            "progress": progress,
            "log_file": str(log_file),
            "current_stage": state.current_stage,
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2, ensure_ascii=False)

        return checkpoint_file

    def get_latest_checkpoint(self) -> Optional[dict]:
        """Get the latest checkpoint if exists"""
        checkpoints = sorted(self.checkpoints_dir.glob("checkpoint_*.json"), reverse=True)

        if not checkpoints:
            return None

        try:
            with open(checkpoints[0], "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
