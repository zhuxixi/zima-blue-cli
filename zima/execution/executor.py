"""PJob Executor - executes PJob with all configurations."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from zima.config.manager import ConfigManager
from zima.models.config_bundle import ConfigBundle
from zima.models.pjob import PJobConfig, Overrides
from zima.utils import generate_timestamp


class ExecutionStatus(Enum):
    """Execution status enum."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ExecutionResult:
    """
    Result of PJob execution.
    
    Attributes:
        pjob_code: PJob code
        status: Execution status
        returncode: Process return code
        stdout: Standard output
        stderr: Standard error
        error_detail: Detailed error information (stack trace for failures)
        command: Executed command
        env: Environment variables used
        work_dir: Working directory
        started_at: Start timestamp
        finished_at: Finish timestamp
        execution_id: Unique execution ID
        temp_dir: Temporary directory (if kept)
    """
    pjob_code: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    error_detail: str = ""  # Detailed error info including stack trace
    command: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)
    work_dir: str = ""
    started_at: str = ""
    finished_at: str = ""
    execution_id: str = ""
    temp_dir: Optional[Path] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pjob_code": self.pjob_code,
            "status": self.status.value,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_detail": self.error_detail,
            "command": self.command,
            "env": {k: v for k, v in self.env.items() if not k.lower().endswith("key")},
            "work_dir": self.work_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "execution_id": self.execution_id,
            "temp_dir": str(self.temp_dir) if self.temp_dir else None,
        }
    
    @property
    def duration_seconds(self) -> float:
        """Get execution duration in seconds."""
        if not self.started_at or not self.finished_at:
            return 0.0
        try:
            start = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.finished_at.replace("Z", "+00:00"))
            return (end - start).total_seconds()
        except:
            return 0.0


class PJobExecutor:
    """
    Executor for PJob.
    
    Handles the complete execution flow:
    1. Load PJob configuration
    2. Resolve and combine all referenced configs
    3. Render workflow template with variables
    4. Resolve environment variables and secrets
    5. Build agent command with parameters
    6. Execute pre-hooks
    7. Run agent command
    8. Execute post-hooks
    9. Handle output and cleanup
    """
    
    def __init__(self):
        """Initialize executor."""
        self.config_manager = ConfigManager()
        self._current_process: Optional[subprocess.Popen] = None
    
    def execute(
        self,
        pjob_code: str,
        overrides: Optional[Overrides] = None,
        dry_run: bool = False,
        keep_temp: bool = False,
    ) -> ExecutionResult:
        """
        Execute a PJob.
        
        Args:
            pjob_code: PJob code to execute
            overrides: Runtime overrides (optional)
            dry_run: If True, only show what would be executed
            keep_temp: Keep temporary files after execution
            
        Returns:
            ExecutionResult with details
        """
        execution_id = str(uuid.uuid4())[:8]
        result = ExecutionResult(
            pjob_code=pjob_code,
            execution_id=execution_id,
            started_at=generate_timestamp(),
        )
        temp_dir: Optional[Path] = None
        
        try:
            # 1. Load PJob configuration
            pjob = self._load_pjob(pjob_code)
            
            # 2. Resolve config bundle
            bundle = self._resolve_bundle(pjob, overrides)
            result.work_dir = bundle.work_dir
            
            # 3. Create temp directory
            temp_dir = self._create_temp_dir(pjob_code, execution_id)
            result.temp_dir = temp_dir
            
            # 4. Render workflow template
            prompt_file = self._render_workflow(bundle, temp_dir)
            
            # 5. Resolve environment variables
            env_vars = self._resolve_env(bundle)
            result.env = env_vars
            
            # 6. Build command
            command = bundle.build_command(prompt_file)
            result.command = command
            
            # 7. Dry run - just return
            if dry_run:
                result.status = ExecutionStatus.SUCCESS
                result.stdout = f"DRY RUN: Would execute:\n{' '.join(command)}"
                result.finished_at = generate_timestamp()
                return result
            
            # 8. Execute pre-hooks
            self._run_hooks(pjob.spec.hooks.get("preExec", []), env_vars, bundle.work_dir)
            
            # 9. Run main command
            result.status = ExecutionStatus.RUNNING
            self._current_process = None
            
            returncode, stdout, stderr = self._run_command(
                command=command,
                env=env_vars,
                work_dir=bundle.work_dir,
                timeout=pjob.spec.execution.timeout,
            )
            
            result.returncode = returncode
            result.stdout = stdout
            result.stderr = stderr
            result.status = ExecutionStatus.SUCCESS if returncode == 0 else ExecutionStatus.FAILED
            
            # 10. Execute post-hooks
            self._run_hooks(pjob.spec.hooks.get("postExec", []), env_vars, bundle.work_dir)
            
            # 11. Handle output
            if pjob.spec.output.save_to:
                self._save_output(result, pjob.spec.output)
            
        except subprocess.TimeoutExpired:
            result.status = ExecutionStatus.TIMEOUT
            result.stderr = "Execution timed out"
            result.error_detail = f"Timeout after {pjob.spec.execution.timeout}s"
        except KeyboardInterrupt:
            result.status = ExecutionStatus.CANCELLED
            result.stderr = "Execution cancelled by user (Ctrl+C)"
            # Attempt to terminate subprocess gracefully
            if self._current_process and self._current_process.poll() is None:
                self._current_process.terminate()
                try:
                    self._current_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._current_process.kill()
        except Exception as e:
            import traceback
            result.status = ExecutionStatus.FAILED
            result.stderr = str(e)
            result.error_detail = traceback.format_exc()
        finally:
            result.finished_at = generate_timestamp()
            
            # Cleanup temp directory
            if temp_dir and not (keep_temp or pjob.spec.execution.keep_temp):
                shutil.rmtree(temp_dir, ignore_errors=True)
                result.temp_dir = None
            
            self._current_process = None
        
        return result
    
    def _load_pjob(self, code: str) -> PJobConfig:
        """Load PJob configuration."""
        if not self.config_manager.config_exists("pjob", code):
            raise ValueError(f"PJob '{code}' not found")
        
        data = self.config_manager.load_config("pjob", code)
        return PJobConfig.from_dict(data)
    
    def _resolve_bundle(
        self,
        pjob: PJobConfig,
        overrides: Optional[Overrides] = None,
    ) -> ConfigBundle:
        """Resolve configuration bundle."""
        bundle = ConfigBundle.resolve(
            pjob_agent=pjob.spec.agent,
            pjob_workflow=pjob.spec.workflow,
            pjob_variable=pjob.spec.variable,
            pjob_env=pjob.spec.env,
            pjob_pmg=pjob.spec.pmg,
            pjob_work_dir=pjob.spec.execution.work_dir,
        )
        
        # Apply PJob overrides
        if pjob.spec.overrides and not pjob.spec.overrides.is_empty():
            bundle.apply_overrides(pjob.spec.overrides)
        
        # Apply runtime overrides (highest priority)
        if overrides and not overrides.is_empty():
            bundle.apply_overrides(overrides)
        
        return bundle
    
    def _create_temp_dir(self, pjob_code: str, execution_id: str) -> Path:
        """Create temporary directory for execution."""
        temp_dir = Path(tempfile.gettempdir()) / "zima-pjobs" / f"{pjob_code}-{execution_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    
    def _render_workflow(self, bundle: ConfigBundle, temp_dir: Path) -> Path:
        """Render workflow template to prompt file."""
        template = bundle.workflow.template
        variables = bundle.get_variable_values()
        
        # Render using Jinja2
        try:
            from jinja2 import Template
            jinja_template = Template(template)
            rendered = jinja_template.render(**variables)
        except Exception as e:
            # If rendering fails, use template as-is with a warning
            rendered = f"<!-- Template render error: {e} -->\n{template}"
        
        # Write to temp file
        prompt_file = temp_dir / "prompt.md"
        prompt_file.write_text(rendered, encoding="utf-8")
        
        return prompt_file
    
    def _resolve_env(self, bundle: ConfigBundle) -> dict[str, str]:
        """Resolve environment variables including secrets."""
        # Start with current environment
        env = dict(os.environ)
        
        if bundle.env:
            # Add plain variables
            for name, value in bundle.env.variables.items():
                env[name] = str(value)
            
            # Resolve secrets
            for secret in bundle.env.secrets:
                resolved_value = self._resolve_secret(secret)
                if resolved_value is not None:
                    env[secret.name] = resolved_value
        
        # Apply override env vars (highest priority)
        for name, value in bundle.overrides.env_vars.items():
            env[name] = str(value)
        
        return env
    
    def _resolve_secret(self, secret) -> Optional[str]:
        """Resolve a single secret from its source."""
        source = secret.source
        
        try:
            if source == "env":
                # Read from environment variable
                key = secret.key or secret.name
                return os.environ.get(key)
            
            elif source == "file":
                # Read from file
                path = Path(secret.path).expanduser()
                if path.exists():
                    return path.read_text().strip()
                return None
            
            elif source == "cmd":
                # Execute command and get output
                import subprocess
                result = subprocess.run(
                    secret.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
                return None
            
            elif source == "vault":
                # For vault, we'd need actual vault integration
                # For now, return a placeholder
                return None
            
        except Exception:
            return None
        
        return None
    
    def _run_hooks(
        self,
        hooks: list[str],
        env: dict[str, str],
        work_dir: str,
    ) -> None:
        """Execute hook commands."""
        for hook in hooks:
            if not hook.strip():
                continue
            try:
                subprocess.run(
                    hook,
                    shell=True,
                    env=env,
                    cwd=work_dir if work_dir and Path(work_dir).exists() else None,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as e:
                # Log warning but don't fail
                print(f"Warning: Hook failed: {hook}")
                print(f"  Error: {e}")
    
    def _run_command(
        self,
        command: list[str],
        env: dict[str, str],
        work_dir: str,
        timeout: int,
    ) -> tuple[int, str, str]:
        """
        Run the main agent command.
        
        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        import sys
        
        cwd = work_dir if work_dir and Path(work_dir).exists() else None
        
        # Run command with real-time output
        process = subprocess.Popen(
            command,
            env=env,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        
        self._current_process = process
        
        stdout_lines = []
        stderr_lines = []
        
        # Stream output in real-time with error protection
        if process.stdout:
            for line in process.stdout:
                stdout_lines.append(line)
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except (OSError, IOError) as e:
                    # Windows may raise [Errno 22] Invalid argument for certain output
                    # Continue execution without real-time display
                    pass
        
        if process.stderr:
            for line in process.stderr:
                stderr_lines.append(line)
                try:
                    sys.stderr.write(line)
                    sys.stderr.flush()
                except (OSError, IOError) as e:
                    # Windows may raise [Errno 22] Invalid argument for certain output
                    # Continue execution without real-time display
                    pass
        
        returncode = process.wait(timeout=timeout if timeout > 0 else None)
        
        return returncode, "".join(stdout_lines), "".join(stderr_lines)
    
    def _save_output(self, result: ExecutionResult, output_options) -> None:
        """Save output to file."""
        import re
        from datetime import datetime
        
        # Process template variables in path
        path_template = output_options.save_to
        now = datetime.now()
        
        # Replace {{date}} with current date
        path = path_template.replace("{{date}}", now.strftime("%Y-%m-%d"))
        path = path.replace("{{time}}", now.strftime("%H-%M-%S"))
        path = path.replace("{{pjob}}", result.pjob_code)
        path = path.replace("{{execution_id}}", result.execution_id)
        
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare content
        content = result.stdout
        
        if output_options.format == "json":
            import json
            content = json.dumps(result.to_dict(), indent=2)
        elif output_options.format == "extract-code-blocks":
            # Extract code blocks from markdown
            code_blocks = re.findall(r'```[\w]*\n(.*?)```', result.stdout, re.DOTALL)
            content = "\n\n".join(code_blocks)
        
        # Write file
        mode = "a" if output_options.append else "w"
        with open(output_path, mode, encoding="utf-8") as f:
            if output_options.append and output_path.exists():
                f.write("\n\n---\n\n")
            f.write(content)
    
    def cancel(self) -> bool:
        """
        Cancel the current execution.
        
        Returns:
            True if cancelled successfully
        """
        if self._current_process and self._current_process.poll() is None:
            self._current_process.terminate()
            try:
                self._current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._current_process.kill()
            return True
        return False
    
    def render_prompt(self, pjob_code: str, overrides: Optional[Overrides] = None) -> str:
        """
        Render the workflow template without executing.
        
        Args:
            pjob_code: PJob code
            overrides: Runtime overrides (optional)
            
        Returns:
            Rendered prompt content
        """
        pjob = self._load_pjob(pjob_code)
        bundle = self._resolve_bundle(pjob, overrides)
        
        template = bundle.workflow.template
        variables = bundle.get_variable_values()
        
        try:
            from jinja2 import Template
            jinja_template = Template(template)
            return jinja_template.render(**variables)
        except Exception as e:
            return f"<!-- Template render error: {e} -->\n{template}"
    
    def build_command(
        self,
        pjob_code: str,
        overrides: Optional[Overrides] = None,
    ) -> tuple[list[str], Path, dict[str, str]]:
        """
        Build the command without executing.
        
        Args:
            pjob_code: PJob code
            overrides: Runtime overrides (optional)
            
        Returns:
            Tuple of (command list, prompt file path, env vars)
        """
        pjob = self._load_pjob(pjob_code)
        bundle = self._resolve_bundle(pjob, overrides)
        
        temp_dir = self._create_temp_dir(pjob_code, "preview")
        prompt_file = self._render_workflow(bundle, temp_dir)
        env_vars = self._resolve_env(bundle)
        command = bundle.build_command(prompt_file)
        
        return command, prompt_file, env_vars
