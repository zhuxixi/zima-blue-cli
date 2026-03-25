"""Kimi CLI runner - executes kimi-cli via subprocess"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from zima.models import AgentConfig, CycleResult
from zima.utils import safe_print, icon


class KimiRunner:
    """Runs kimi-cli via subprocess"""
    
    def __init__(self, config: AgentConfig, agent_dir: Path):
        self.config = config
        self.agent_dir = agent_dir
        self.workspace = agent_dir / "workspace"
        self.prompts_dir = agent_dir / "prompts"
        self.logs_dir = agent_dir / "logs"
        
        # Ensure directories exist
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
    
    def run_cycle(
        self, 
        prompt: str, 
        cycle_num: int,
        task_name: str = ""
    ) -> CycleResult:
        """
        Run a single cycle with kimi-cli
        
        Args:
            prompt: The prompt to send to kimi
            cycle_num: Current cycle number
            task_name: Name of the current task
            
        Returns:
            CycleResult with execution results
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Prepare files
        prompt_file = self.prompts_dir / f"cycle_{timestamp}.md"
        log_file = self.logs_dir / f"cycle_{timestamp}.log"
        result_file = self.workspace / ".zima" / f"result_{timestamp}.json"
        
        result_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Inject result file path into prompt
        full_prompt = self._prepare_prompt(prompt, result_file, task_name)
        prompt_file.write_text(full_prompt, encoding="utf-8")
        
        # Ensure workspace exists with absolute path
        workspace_abs = self.workspace.resolve()
        workspace_abs.mkdir(parents=True, exist_ok=True)
        
        # Build command
        # Read prompt content for --prompt argument
        prompt_content = prompt_file.read_text(encoding="utf-8")
        
        cmd = [
            "kimi",
            "--print",  # Non-interactive mode
            "--yolo",   # Auto-approve
            "--prompt", prompt_content,
            "--work-dir", str(workspace_abs),
            "--max-steps-per-turn", str(self.config.max_steps_per_turn),
            "--max-ralph-iterations", "10",
        ]
        
        safe_print(f"{icon('rocket')} Starting cycle {cycle_num}")
        safe_print(f"   Prompt: {prompt_file.name}")
        safe_print(f"   Log: {log_file.name}")
        
        # Execute with real-time logging
        start_time = datetime.now()
        
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=self.config.max_execution_time,
                    cwd=self.workspace
                )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # Read result file if exists
            kimi_result = self._read_result_file(result_file)
            
            # If no result file, try to parse from log
            if not kimi_result:
                kimi_result = self._parse_from_log(log_file)
            
            return CycleResult(
                cycle_num=cycle_num,
                status=kimi_result.get("status", "unknown"),
                progress=kimi_result.get("progress", 0),
                summary=kimi_result.get("summary", ""),
                details=kimi_result.get("details", ""),
                next_action=kimi_result.get("next_action", "continue"),
                log_file=log_file,
                prompt_file=prompt_file,
                result_file=result_file if result_file.exists() else None,
                elapsed_time=elapsed,
                return_code=result.returncode
            )
            
        except subprocess.TimeoutExpired:
            # Handle timeout
            elapsed = self.config.max_execution_time
            progress = self._estimate_progress_from_log(log_file)
            
            safe_print(f"{icon('warning')} Cycle {cycle_num} timed out")
            
            return CycleResult(
                cycle_num=cycle_num,
                status="timeout",
                progress=progress,
                summary="Execution timed out, progress saved",
                next_action="continue",
                log_file=log_file,
                prompt_file=prompt_file,
                elapsed_time=elapsed,
                return_code=-1
            )
            
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            
            return CycleResult(
                cycle_num=cycle_num,
                status="error",
                summary=f"Execution error: {str(e)}",
                next_action="retry",
                log_file=log_file,
                prompt_file=prompt_file,
                elapsed_time=elapsed,
                return_code=-1
            )
    
    def _prepare_prompt(self, prompt: str, result_file: Path, task_name: str) -> str:
        """Prepare the full prompt with result file instruction"""
        return f"""{prompt}

---

## Output Requirements

When you complete the task, please write a result file at:
{result_file}

The result file should be a JSON object with this structure:
{{
  "status": "completed|partial|failed|async_started",
  "progress": 0-100,
  "summary": "Brief summary of what was done (1-2 sentences)",
  "details": "Detailed description (optional)",
  "next_action": "continue|wait|complete|fix"
}}

Guidelines:
- Use "completed" when the task is fully done
- Use "partial" when progress was made but not finished
- Use "async_started" when starting a long-running async task
- Use "failed" when the task cannot be completed
- progress: 0-100 indicating completion percentage
- next_action: what should happen in the next cycle

Current task: {task_name}
"""
    
    def _read_result_file(self, result_file: Path) -> Optional[dict]:
        """Read result file if it exists"""
        if not result_file.exists():
            return None
        
        try:
            content = result_file.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return None
    
    def _parse_from_log(self, log_file: Path) -> dict:
        """Parse result from log file as fallback"""
        if not log_file.exists():
            return {"status": "unknown", "progress": 0}
        
        try:
            content = log_file.read_text(encoding="utf-8").lower()
            
            # Heuristic detection
            if "completed" in content and "100" in content:
                return {"status": "completed", "progress": 100}
            elif "partial" in content:
                return {"status": "partial", "progress": 50}
            elif "failed" in content:
                return {"status": "failed", "progress": 0}
            else:
                return {"status": "unknown", "progress": 0}
        except IOError:
            return {"status": "unknown", "progress": 0}
    
    def _estimate_progress_from_log(self, log_file: Path) -> int:
        """Estimate progress from log file content"""
        if not log_file.exists():
            return 0
        
        try:
            content = log_file.read_text(encoding="utf-8").lower()
            
            # Simple heuristics
            if "git commit" in content:
                return 80
            elif "test" in content:
                return 60
            elif "write" in content or "edit" in content:
                return 40
            elif "read" in content:
                return 20
            return 50
        except IOError:
            return 0
