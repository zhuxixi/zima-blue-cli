"""Cycle scheduler for agent execution"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from zima.models import AgentConfig, AgentState, AgentStatus, CycleResult
from zima.core.kimi_runner import KimiRunner
from zima.core.state_manager import StateManager
from zima.utils import safe_print, icon


class CycleScheduler:
    """15-minute cycle scheduler for agent execution"""
    
    def __init__(
        self,
        config: AgentConfig,
        runner: KimiRunner,
        state_manager: StateManager
    ):
        self.config = config
        self.runner = runner
        self.state = state_manager
        self.running = False
    
    def run(self) -> None:
        """Main scheduling loop"""
        self.running = True
        
        safe_print(f"\n{'='*60}")
        safe_print(f"{icon('rocket')} Starting Agent: {self.config.name}")
        safe_print(f"   Cycle interval: {self.config.cycle_interval}s")
        safe_print(f"   Max execution: {self.config.max_execution_time}s")
        safe_print(f"{'='*60}\n")
        
        while self.running:
            cycle_start = datetime.now()
            
            # Load current state
            agent_state = self.state.load_state()
            cycle_num = agent_state.current_cycle + 1
            
            # Check if we should stop
            if self._should_stop(agent_state):
                safe_print(f"\n{icon('stop')} Stopping agent: reached limit")
                break
            
            safe_print(f"\n{'='*60}")
            safe_print(f"{icon('cycle')} Cycle {cycle_num} started - {cycle_start.strftime('%H:%M:%S')}")
            safe_print(f"{'='*60}")
            
            # Determine current task
            task = self._determine_task(agent_state)
            safe_print(f"{icon('task')} Task: {task['name']} - {task['description']}")
            
            # Build prompt
            prompt = self._build_prompt(task, agent_state)
            
            # Execute
            agent_state.status = AgentStatus.RUNNING.value
            agent_state.current_cycle = cycle_num
            self.state.save_state(agent_state)
            
            result = self.runner.run_cycle(prompt, cycle_num, task['name'])
            
            # Handle result
            self._handle_result(result, agent_state, task)
            
            # Check if completed
            if result.next_action == "complete" or result.status == "completed":
                if self._is_pipeline_complete(agent_state):
                    print(f"\n🎉 All tasks completed!")
                    agent_state.status = AgentStatus.COMPLETED.value
                    self.state.save_state(agent_state)
                    break
            
            # Calculate sleep time
            elapsed = (datetime.now() - cycle_start).total_seconds()
            sleep_time = max(0, self.config.cycle_interval - elapsed)
            
            if sleep_time > 0 and self.running:
                next_wake = datetime.now() + timedelta(seconds=sleep_time)
                safe_print(f"\n{icon('sleep')} Sleeping for {sleep_time:.0f}s, next wake: {next_wake.strftime('%H:%M:%S')}")
                
                # Sleep with interrupt check
                self._sleep_with_interrupt(sleep_time)
        
        safe_print(f"\n{icon('complete')} Agent stopped")
    
    def stop(self) -> None:
        """Stop the scheduler"""
        self.running = False
        print("\n🛑 Stopping scheduler...")
    
    def _determine_task(self, agent_state: AgentState) -> dict:
        """Determine the current task based on state
        
        Supports two modes:
        1. Pipeline mode: sequential stages
        2. Autonomous mode: same task each cycle (kimi controls execution)
        """
        pipeline = self.config.pipeline
        
        # Autonomous mode: no pipeline, use initial task every time
        if not pipeline:
            initial = self.config.initial_task
            return {
                "name": initial.get("type", "autonomous"),
                "description": initial.get("description", "Autonomous execution"),
                "prompt_file": initial.get("prompt"),
            }
        
        # Pipeline mode: sequential stages
        current_stage = agent_state.current_stage
        
        if not current_stage:
            # Start with first pipeline stage
            return {
                "name": pipeline[0]["name"],
                "description": pipeline[0].get("description", "Execute task"),
                "prompt_file": pipeline[0].get("prompt"),
            }
        
        # Find current stage in pipeline
        for stage in pipeline:
            if stage["name"] == current_stage:
                return {
                    "name": stage["name"],
                    "description": stage.get("description", "Execute task"),
                    "prompt_file": stage.get("prompt"),
                }
        
        # Fallback to initial task
        return {
            "name": self.config.initial_task.get("type", "task"),
            "description": self.config.initial_task.get("description", "Execute task"),
            "prompt_file": None,
        }
    
    def _build_prompt(self, task: dict, agent_state: AgentState) -> str:
        """Build the execution prompt"""
        # Get recent sessions for context
        recent_sessions = self.state.get_recent_sessions(3)
        
        sessions_context = ""
        if recent_sessions:
            sessions_context = "\n\n## Recent Sessions\n\n"
            for i, session in enumerate(recent_sessions, 1):
                sessions_context += f"### Session -{i}\n{session[:500]}...\n\n"
        
        # Load task prompt file if specified
        task_prompt_content = ""
        if task.get("prompt_file"):
            prompt_file = self.config.workspace / task["prompt_file"]
            if prompt_file.exists():
                try:
                    task_prompt_content = prompt_file.read_text(encoding="utf-8")
                except Exception:
                    task_prompt_content = ""
        
        # Load project context from agent_state.json if exists
        project_context = ""
        agent_state_file = self.config.workspace.parent / "agent_state.json"
        if agent_state_file.exists():
            try:
                import json
                with open(agent_state_file, 'r', encoding='utf-8') as f:
                    agent_data = json.load(f)
                    project = agent_data.get('project', {})
                    if project.get('path'):
                        project_context = f"\n## Project Context\n- **Project Path**: {project['path']}\n"
                        if project.get('test_dir'):
                            project_context += f"- **Test Directory**: {project['test_dir']}\n"
                    # Add progress info
                    progress = agent_data.get('progress', {})
                    if progress.get('pending_files'):
                        project_context += f"- **Pending Test Files**: {len(progress['pending_files'])}\n"
                    if progress.get('completed_files'):
                        project_context += f"- **Completed Files**: {len(progress['completed_files'])}\n"
            except Exception:
                pass
        
        return f"""# Agent Task Execution

## Your Identity
You are {self.config.name}.
{self.config.description}

## Current Task
**Name**: {task['name']}
**Description**: {task['description']}
**Cycle**: {agent_state.current_cycle}
{project_context}

## Task Instructions
{task_prompt_content}

## Context
You are operating in a 15-minute cycle system.
- You have about 9 minutes of execution time
- Focus on making concrete progress
- If you can't finish, save progress and report partial completion
- Write a result file when done

## Workspace
{self.config.workspace}

## Guidelines
1. Read any existing context from the workspace
2. Execute the task step by step
3. Make small, frequent git commits with "wip:" prefix
4. If starting a long async task (like tests), report async_started
5. If you finish early, report completed with progress 100
{sessions_context}

Now execute the task: {task['name']}
"""
    
    def _handle_result(
        self,
        result: CycleResult,
        agent_state: AgentState,
        task: dict
    ) -> None:
        """Handle execution result"""
        safe_print(f"\n{icon('result')} Result: {result.status}")
        safe_print(f"   Progress: {result.progress}%")
        safe_print(f"   Time: {result.elapsed_time:.1f}s")
        safe_print(f"   Summary: {result.summary}")
        
        # Create session record
        execution_desc = f"Executed {task['name']}"
        if result.log_file:
            execution_desc += f"\nLog: {result.log_file.name}"
        
        self.state.create_session(
            cycle_num=result.cycle_num,
            agent_name=self.config.name,
            task=task['description'],
            execution=execution_desc,
            result=f"{result.status} - {result.summary}",
            learnings="",
            next_steps=result.next_action
        )
        
        # Update state based on result
        if result.status == "completed":
            agent_state.status = AgentStatus.IDLE.value
            # Advance to next pipeline stage
            self._advance_stage(agent_state)
            
        elif result.status == "partial":
            agent_state.status = AgentStatus.IDLE.value
            # Stay on current stage
            
        elif result.status == "async_started":
            agent_state.status = AgentStatus.WAITING_ASYNC.value
            # Record async task
            agent_state.async_tasks[task['name']] = {
                "status": "running",
                "started_at": datetime.now().isoformat(),
            }
            
        elif result.status == "timeout":
            agent_state.status = AgentStatus.TIMEOUT.value
            # Create checkpoint
            self.state.create_checkpoint(agent_state, result.progress, result.log_file)
            
        elif result.status in ("error", "failed"):
            # Check retry count
            retry_key = task['name']
            current_retries = agent_state.retry_count.get(retry_key, 0)
            
            if current_retries < self.config.max_retries:
                agent_state.retry_count[retry_key] = current_retries + 1
                agent_state.status = AgentStatus.IDLE.value
                safe_print(f"   Will retry ({current_retries + 1}/{self.config.max_retries})")
            else:
                agent_state.status = AgentStatus.FAILED.value
                safe_print(f"   Max retries reached, marking as failed")
        
        self.state.save_state(agent_state)
    
    def _advance_stage(self, agent_state: AgentState) -> None:
        """Advance to next pipeline stage"""
        pipeline = self.config.pipeline
        current = agent_state.current_stage
        
        if not pipeline:
            return
        
        # Find current stage index
        current_idx = -1
        for i, stage in enumerate(pipeline):
            if stage["name"] == current:
                current_idx = i
                break
        
        # Advance to next
        if current_idx >= 0 and current_idx + 1 < len(pipeline):
            agent_state.current_stage = pipeline[current_idx + 1]["name"]
        elif current_idx == -1:
            # Start with first
            agent_state.current_stage = pipeline[0]["name"]
        else:
            # Completed all stages
            agent_state.current_stage = "completed"
    
    def _is_pipeline_complete(self, agent_state: AgentState) -> bool:
        """Check if all pipeline stages are complete"""
        return agent_state.current_stage == "completed"
    
    def _should_stop(self, agent_state: AgentState) -> bool:
        """Check if agent should stop due to limits"""
        # Check max cycles
        if agent_state.current_cycle >= self.config.max_cycles:
            safe_print(f"{icon('warning')} Reached max cycles: {self.config.max_cycles}")
            return True
        
        # Check max duration
        if agent_state.started_at:
            started = datetime.fromisoformat(agent_state.started_at)
            max_duration = self._parse_duration(self.config.max_duration)
            if datetime.now() - started > max_duration:
                safe_print(f"{icon('warning')} Reached max duration: {self.config.max_duration}")
                return True
        
        return False
    
    def _parse_duration(self, duration_str: str) -> timedelta:
        """Parse duration string like '24h', '30m'"""
        if duration_str.endswith('h'):
            return timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('m'):
            return timedelta(minutes=int(duration_str[:-1]))
        elif duration_str.endswith('s'):
            return timedelta(seconds=int(duration_str[:-1]))
        else:
            return timedelta(hours=24)  # Default
    
    def _sleep_with_interrupt(self, seconds: float) -> None:
        """Sleep with interrupt checking"""
        # Sleep in small increments to allow interrupt
        slept = 0.0
        interval = 1.0  # Check every second
        
        while slept < seconds and self.running:
            time.sleep(min(interval, seconds - slept))
            slept += interval
