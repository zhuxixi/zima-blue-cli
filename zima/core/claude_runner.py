"""Claude Code CLI runner - executes Claude Code via subprocess with stream-json parsing."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from zima.models import AgentConfig, CycleResult
from zima.utils import icon, safe_print


class ClaudeRunner:
    """Runs Claude Code CLI via subprocess with stream-json NDJSON parsing.

    Unlike KimiRunner which drives external cycles, ClaudeRunner leverages
    Claude Code's built-in agentic loop (--max-turns). A single run_cycle() call
    executes the full agentic workflow in one subprocess invocation.

    NOTE: Currently used via PJobExecutor for PJob-based execution (stdin pipe path).
    This runner provides a KimiRunner-compatible run_cycle() interface for future
    cycle-based execution patterns (daemon/scheduler). The NDJSON parsing and
    CycleResult extraction logic are tested independently.

    Stream-JSON format (NDJSON, one JSON object per line):
      {"type": "system", ...}            - System messages
      {"type": "assistant", "message": {}}  - Claude text responses
      {"type": "tool_use", ...}          - Tool invocations (Bash, Read, Edit, etc.)
      {"type": "tool_result", ...}       - Tool outputs
      {"type": "result", ...}            - Final result (cost_usd, duration, session_id)
    """

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
        task_name: str = "",
    ) -> CycleResult:
        """Execute a single cycle using Claude Code's built-in agentic loop.

        This is the main entry point, compatible with KimiRunner's interface.

        Args:
            prompt: The prompt to send to Claude Code
            cycle_num: Current cycle number
            task_name: Name of the current task

        Returns:
            CycleResult with execution results
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        datetime.now()

        # Prepare files
        prompt_file = self.prompts_dir / f"cycle_{timestamp}.md"
        log_file = self.logs_dir / f"cycle_{timestamp}.log"

        # Write prompt to file (will be piped as stdin)
        prompt_file.write_text(prompt, encoding="utf-8")

        # Ensure workspace exists with absolute path
        workspace_abs = self.workspace.resolve()
        workspace_abs.mkdir(parents=True, exist_ok=True)

        # Build command using AgentConfig's build_command method
        cmd = self.config.build_command(
            prompt_file=prompt_file,
            work_dir=workspace_abs,
        )

        safe_print(f"{icon('rocket')} Starting Claude Code cycle {cycle_num}")
        safe_print(f"   Prompt: {prompt_file.name}")
        safe_print(f"   Log: {log_file.name}")
        safe_print(f"   Command: {' '.join(cmd)}")

        # Execute with stream-json parsing
        start_time = datetime.now()
        process = None

        try:
            with open(prompt_file, "r", encoding="utf-8") as stdin_handle:
                process = subprocess.Popen(
                    cmd,
                    stdin=stdin_handle,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(workspace_abs),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                events = []
                with open(log_file, "w", encoding="utf-8") as log_f:
                    for line in process.stdout:
                        # Write raw line to log
                        log_f.write(line)
                        log_f.flush()

                        # Parse NDJSON
                        event = self._parse_ndjson_line(line)
                        if event:
                            events.append(event)

                        # Also display to console
                        try:
                            sys.stdout.write(line)
                            sys.stdout.flush()
                        except (OSError, IOError):
                            pass

                returncode = process.wait()

            elapsed = (datetime.now() - start_time).total_seconds()

            # Extract result from accumulated events
            result_data = self._extract_result(events, returncode)

            return CycleResult(
                cycle_num=cycle_num,
                status=result_data["status"],
                progress=result_data["progress"],
                summary=result_data["summary"],
                details=result_data["details"],
                next_action=result_data["next_action"],
                log_file=log_file,
                prompt_file=prompt_file,
                elapsed_time=elapsed,
                return_code=returncode,
            )

        except subprocess.TimeoutExpired:
            elapsed = (datetime.now() - start_time).total_seconds()
            if process:
                process.kill()
                process.wait()

            return CycleResult(
                cycle_num=cycle_num,
                status="timeout",
                progress=50,
                summary="Claude Code execution timed out",
                next_action="retry",
                log_file=log_file,
                prompt_file=prompt_file,
                elapsed_time=elapsed,
                return_code=-1,
            )

        except KeyboardInterrupt:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

            elapsed = (datetime.now() - start_time).total_seconds()

            return CycleResult(
                cycle_num=cycle_num,
                status="error",
                summary="Execution cancelled by user (Ctrl+C)",
                next_action="retry",
                log_file=log_file,
                prompt_file=prompt_file,
                elapsed_time=elapsed,
                return_code=-1,
            )

        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()

            return CycleResult(
                cycle_num=cycle_num,
                status="error",
                summary=f"Claude Code execution error: {e}",
                next_action="retry",
                log_file=log_file,
                prompt_file=prompt_file,
                elapsed_time=elapsed,
                return_code=-1,
            )

    def _parse_ndjson_line(self, line: str) -> Optional[dict]:
        """Parse a single NDJSON line from stream-json output.

        Returns:
            Parsed dict or None if line is not valid JSON.
        """
        line = line.strip()
        if not line:
            return None

        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _extract_result(self, events: list[dict], returncode: int) -> dict:
        """Extract final result from accumulated stream events.

        Maps Claude Code stream-json events to Zima's CycleResult fields.

        Returns:
            dict with keys: status, progress, summary, details, next_action
        """
        result = {
            "status": "unknown",
            "progress": 0,
            "summary": "",
            "details": "",
            "next_action": "continue",
        }

        # Find the final "result" event
        final_result = None
        for event in reversed(events):
            if event.get("type") == "result":
                final_result = event
                break

        if final_result:
            # Extract status from result
            # Claude Code result event has: subtype, cost_usd, duration_ms, etc.
            subtype = final_result.get("subtype", "")
            if subtype == "success":
                result["status"] = "completed"
                result["progress"] = 100
                result["next_action"] = "complete"
            elif subtype == "error":
                result["status"] = "failed"
                result["next_action"] = "retry"
            elif subtype == "cancelled":
                result["status"] = "error"
                result["next_action"] = "retry"
            else:
                result["status"] = "completed" if returncode == 0 else "failed"

            # Extract cost info
            cost_usd = final_result.get("cost_usd", 0)
            duration_ms = final_result.get("duration_ms", 0)
            session_id = final_result.get("session_id", "")

            result["details"] = (
                f"Cost: ${cost_usd:.4f} | Duration: {duration_ms / 1000:.1f}s"
                f"{' | Session: ' + session_id if session_id else ''}"
            )
        else:
            # No result event - infer from returncode
            if returncode == 0:
                result["status"] = "completed"
                result["progress"] = 100
                result["next_action"] = "complete"
            elif returncode == 5:
                # Claude Code exit code 5 = timeout
                result["status"] = "timeout"
                result["next_action"] = "retry"
            else:
                result["status"] = "failed"
                result["next_action"] = "retry"

        # Extract summary from assistant messages
        assistant_messages = []
        for event in events:
            if event.get("type") == "assistant":
                msg = event.get("message", {})
                content = msg.get("content", [])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            assistant_messages.append(text)

        if assistant_messages and not result["summary"]:
            # Use the last assistant message as summary (most relevant)
            last_msg = assistant_messages[-1]
            result["summary"] = last_msg[:500]  # Truncate long summaries

        # Estimate progress from tool usage
        if result["progress"] == 0:
            result["progress"] = self._estimate_progress(events)

        return result

    def _estimate_progress(self, events: list[dict]) -> int:
        """Estimate progress 0-100 from tool usage events.

        Uses a heuristic based on the number of tool calls relative
        to maxTurns parameter.
        """
        tool_use_count = sum(1 for e in events if e.get("type") == "tool_use")

        max_turns = self.config.parameters.get("maxTurns", 100)

        if max_turns > 0 and tool_use_count > 0:
            # Each turn roughly maps to one or more tool uses
            estimated = min(int((tool_use_count / max_turns) * 100), 95)
            return max(estimated, 10)

        return 50  # Default: unknown progress
