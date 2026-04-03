"""Simple Agent Runner - single execution"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from zima.models import AgentConfig, RunResult


class AgentRunner:
    """Runs agent once via kimi-cli"""

    def __init__(self, config: AgentConfig, agent_dir: Path):
        self.config = config
        self.agent_dir = agent_dir
        self.workspace = config.workspace

    def run(self) -> RunResult:
        """Execute agent once"""
        cmd = self.config.get_kimi_cmd(self.agent_dir)

        # Prepare output files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.agent_dir / "logs" / f"run_{timestamp}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        print(f"🚀 Starting agent: {self.config.name}")
        print(f"   Workspace: {self.config.workspace}")
        print(f"   Log: {log_file}")

        start_time = datetime.now()

        try:
            with open(log_file, "w", encoding="utf-8") as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=self.config.max_execution_time,
                    cwd=self.workspace,
                )

            elapsed = (datetime.now() - start_time).total_seconds()

            # Read log for summary
            log_content = log_file.read_text(encoding="utf-8")

            # Simple result detection
            status = "completed" if result.returncode == 0 else "failed"
            if "<choice>STOP</choice>" in log_content:
                status = "completed"
            elif "<choice>CONTINUE</choice>" in log_content:
                status = "partial"

            return RunResult(
                status=status,
                summary=f"Agent finished with status: {status}",
                output=log_content[-2000:] if len(log_content) > 2000 else log_content,
                elapsed_time=elapsed,
                return_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return RunResult(
                status="timeout",
                summary="Execution timed out",
                elapsed_time=self.config.max_execution_time,
                return_code=-1,
            )
        except Exception as e:
            return RunResult(
                status="error", summary=f"Error: {str(e)}", elapsed_time=0, return_code=-1
            )
