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
        cycle_start = datetime.now()
        
        # Prepare files
        prompt_file = self.prompts_dir / f"cycle_{timestamp}.md"
        log_file = self.logs_dir / f"cycle_{timestamp}.log"
        result_file = self.workspace / ".zima" / f"result_{timestamp}.json"
        
        result_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write runtime info for kimi to query
        runtime_file = self.workspace / ".zima" / "runtime.json"
        runtime_info = {
            "cycle_start": cycle_start.isoformat(),
            "max_execution_time": self.config.max_execution_time,
            "cycle_interval": self.config.cycle_interval,
            "cycle_num": cycle_num,
            "task_name": task_name
        }
        runtime_file.write_text(json.dumps(runtime_info, indent=2), encoding="utf-8")
        
        # Inject result file path into prompt
        full_prompt = self._prepare_prompt(prompt, result_file, task_name)
        prompt_file.write_text(full_prompt, encoding="utf-8")
        
        # Ensure workspace exists with absolute path
        workspace_abs = self.workspace.resolve()
        workspace_abs.mkdir(parents=True, exist_ok=True)
        
        # Build command using AgentConfig's build_command method
        # This ensures all parameters (including --model) are properly passed
        cmd = self.config.build_command(
            prompt_file=prompt_file,
            work_dir=workspace_abs
        )
        
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
            
            # Parse result from log (kimi outputs JSON in response)
            kimi_result = self._parse_from_log(log_file)
            
            # Zima creates the result file (not kimi)
            result_file.parent.mkdir(parents=True, exist_ok=True)
            result_file.write_text(json.dumps(kimi_result, ensure_ascii=False, indent=2), encoding="utf-8")
            
            return CycleResult(
                cycle_num=cycle_num,
                status=kimi_result.get("status", "unknown"),
                progress=kimi_result.get("progress", 0),
                summary=kimi_result.get("summary", ""),
                details=kimi_result.get("details", ""),
                next_action=kimi_result.get("next_action", "continue"),
                log_file=log_file,
                prompt_file=prompt_file,
                result_file=result_file,
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
        """Prepare the full prompt with JSON output requirement"""
        return f"""{prompt}

---

## Output Requirements (IMPORTANT)

When you complete the task, you MUST output a JSON result block in your response.

The JSON should be in this exact format (wrap in ```json code block):

```json
{{
  "status": "completed|partial|failed|async_started",
  "progress": 0-100,
  "summary": "Brief summary of what was done (1-2 sentences)",
  "details": "Detailed description (optional)",
  "next_action": "continue|wait|complete|fix"
}}
```

Guidelines:
- Use "completed" when the task is fully done
- Use "partial" when progress was made but not finished
- Use "async_started" when starting a long-running async task
- Use "failed" when the task cannot be completed
- progress: 0-100 indicating completion percentage
- next_action: what should happen in the next cycle

Current task: {task_name}

NOTE: Do NOT create any result file. Just output the JSON in your response and Zima will handle the rest.
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
        """Parse result from log file - extract JSON block if present"""
        if not log_file.exists():
            return {"status": "unknown", "progress": 0}
        
        try:
            content = log_file.read_text(encoding="utf-8")
            
            # Try to extract JSON from code block
            import re
            json_pattern = r'```json\s*\n(.*?)\n```'
            match = re.search(json_pattern, content, re.DOTALL)
            
            if match:
                try:
                    result = json.loads(match.group(1))
                    return result
                except json.JSONDecodeError:
                    pass
            
            # Fallback: heuristic detection
            content_lower = content.lower()
            if "completed" in content_lower and "100" in content:
                return {"status": "completed", "progress": 100}
            elif "partial" in content_lower:
                return {"status": "partial", "progress": 50}
            elif "failed" in content_lower:
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
