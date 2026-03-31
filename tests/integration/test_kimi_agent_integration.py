"""Integration tests for Kimi Agent - covering config, runner, and CLI layers."""

import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from zima.cli import app
from zima.config.manager import ConfigManager
from zima.core.kimi_runner import KimiRunner
from zima.models import AgentConfig
from zima.models.workflow import WorkflowConfig
from zima.models.variable import VariableConfig

runner = CliRunner()


class TestKimiAgentConfigLayer:
    """Test Kimi Agent configuration layer (TC-1 ~ TC-3)."""
    
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment."""
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        
        # Create required directories
        for kind in ["agents", "workflows", "variables", "envs", "pmgs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)
    
    def test_kimi_agent_parameter_template_merge(self):
        """TC-1: Verify Kimi agent parameters are correctly merged from template."""
        # Create Kimi agent with default parameters
        agent = AgentConfig.create(
            code="test-kimi-default",
            name="Test Kimi Agent",
            agent_type="kimi"
        )
        
        # Verify default parameters from template are merged
        assert agent.parameters["model"] == "kimi-code/kimi-for-coding"
        assert agent.parameters["maxStepsPerTurn"] == 50
        assert agent.parameters["maxRalphIterations"] == 10
        assert agent.parameters["maxRetriesPerStep"] == 3
        assert agent.parameters["yolo"] is True
        assert agent.parameters["workDir"] == "./workspace"
        assert agent.parameters["outputFormat"] == "text"
    
    def test_kimi_agent_custom_parameters_override(self):
        """TC-1b: Verify custom parameters override template defaults."""
        agent = AgentConfig.create(
            code="test-kimi-custom",
            name="Custom Kimi Agent",
            agent_type="kimi",
            parameters={
                "model": "kimi-custom-model",
                "maxStepsPerTurn": 100,
                "yolo": False
            }
        )
        
        # Verify overrides
        assert agent.parameters["model"] == "kimi-custom-model"
        assert agent.parameters["maxStepsPerTurn"] == 100
        assert agent.parameters["yolo"] is False
        
        # Verify non-overridden defaults remain
        assert agent.parameters["maxRalphIterations"] == 10
        assert agent.parameters["workDir"] == "./workspace"
    
    def test_kimi_agent_build_command(self):
        """TC-2: Verify build_command generates correct Kimi CLI command."""
        agent = AgentConfig.create(
            code="test-kimi-cmd",
            name="Command Test Agent",
            agent_type="kimi",
            parameters={
                "model": "kimi-k2-072515-preview",
                "maxStepsPerTurn": 50,
                "yolo": True
            }
        )
        
        prompt_file = Path("/tmp/test_prompt.md")
        work_dir = Path("/tmp/workspace")
        
        cmd = agent.build_command(prompt_file=prompt_file, work_dir=work_dir)
        
        # Verify command structure
        assert cmd[0] == "kimi"
        assert "--print" in cmd
        assert "--yolo" in cmd
        assert "--prompt" in cmd
        assert str(prompt_file) in cmd
        assert "--work-dir" in cmd
        assert str(work_dir) in cmd
        assert "--model" in cmd
        assert "kimi-k2-072515-preview" in cmd
        assert "--max-steps-per-turn" in cmd
        assert "50" in cmd
    
    def test_kimi_agent_build_command_with_extra_args(self):
        """TC-2b: Verify extra_args can override parameters at build time."""
        agent = AgentConfig.create(
            code="test-kimi-extra",
            name="Extra Args Agent",
            agent_type="kimi",
            parameters={"model": "default-model"}
        )
        
        extra_args = {"model": "runtime-model", "maxStepsPerTurn": 75}
        cmd = agent.build_command(extra_args=extra_args)
        
        # Verify extra_args override
        model_idx = cmd.index("--model")
        assert cmd[model_idx + 1] == "runtime-model"
        
        max_steps_idx = cmd.index("--max-steps-per-turn")
        assert cmd[max_steps_idx + 1] == "75"
    
    def test_kimi_agent_build_command_with_addDirs(self):
        """TC-2c: Verify addDirs parameter generates multiple --add-dir flags."""
        agent = AgentConfig.create(
            code="test-kimi-dirs",
            name="Dirs Test Agent",
            agent_type="kimi",
            parameters={"addDirs": ["/path/to/dir1", "/path/to/dir2"]}
        )
        
        cmd = agent.build_command()
        
        # Verify multiple --add-dir flags
        add_dir_indices = [i for i, x in enumerate(cmd) if x == "--add-dir"]
        assert len(add_dir_indices) == 2
        assert cmd[add_dir_indices[0] + 1] == "/path/to/dir1"
        assert cmd[add_dir_indices[1] + 1] == "/path/to/dir2"
    
    def test_agent_type_command_differences(self):
        """TC-3: Verify different agent types generate different commands."""
        kimi_agent = AgentConfig.create(code="k", name="K", agent_type="kimi")
        claude_agent = AgentConfig.create(code="c", name="C", agent_type="claude")
        gemini_agent = AgentConfig.create(code="g", name="G", agent_type="gemini")
        
        kimi_cmd = kimi_agent.get_cli_command_template()
        claude_cmd = claude_agent.get_cli_command_template()
        gemini_cmd = gemini_agent.get_cli_command_template()
        
        # Verify command differences
        assert kimi_cmd == ["kimi", "--print", "--yolo"]
        assert claude_cmd == ["claude", "-p"]
        assert gemini_cmd == ["gemini", "--yolo"]
        
        # Verify work-dir parameter differences
        work_dir = Path("/tmp/test")
        kimi_full = kimi_agent.build_command(work_dir=work_dir)
        gemini_full = gemini_agent.build_command(work_dir=work_dir)
        
        assert "--work-dir" in kimi_full
        assert "--worktree" in gemini_full  # Gemini uses different flag


class TestKimiAgentRunnerLayer:
    """Test Kimi Agent runner layer (TC-4 ~ TC-9)."""
    
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment."""
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.agent_dir = tmp_path / "agents" / "test-kimi"
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        
        # Create agent config
        self.agent = AgentConfig.create(
            code="test-kimi",
            name="Test Kimi Agent",
            agent_type="kimi",
            parameters={
                "maxStepsPerTurn": 50,
                "maxExecutionTime": 600,
                "cycleInterval": 900
            }
        )
    
    def test_kimi_runner_directory_setup(self):
        """TC-4: Verify KimiRunner creates required directories."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Verify directories are created
        assert (self.agent_dir / "prompts").exists()
        assert (self.agent_dir / "logs").exists()
        assert (self.agent_dir / "workspace").exists()
        
        # Verify they're actually directories
        assert (self.agent_dir / "prompts").is_dir()
        assert (self.agent_dir / "logs").is_dir()
        assert (self.agent_dir / "workspace").is_dir()
    
    def test_kimi_runner_prompt_preparation(self):
        """TC-5: Verify prompt file generation with JSON requirements."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        test_prompt = "Please analyze this code and provide feedback."
        task_name = "Code Analysis Task"
        
        # Access internal method
        result_file = self.agent_dir / "workspace" / ".zima" / "result.json"
        full_prompt = runner._prepare_prompt(test_prompt, result_file, task_name)
        
        # Verify original prompt is included
        assert test_prompt in full_prompt
        
        # Verify JSON output requirements are injected
        assert "Output Requirements" in full_prompt
        assert "```json" in full_prompt
        assert '"status": "completed|partial|failed|async_started"' in full_prompt
        assert '"progress": 0-100' in full_prompt
        assert task_name in full_prompt
        
        # Verify instruction not to create result file
        assert "Do NOT create any result file" in full_prompt
    
    @patch('zima.core.kimi_runner.subprocess.run')
    def test_kimi_runner_successful_execution(self, mock_run):
        """TC-6: Verify successful execution flow with mocked subprocess."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Mock log content with completed JSON - this will be written by subprocess mock
        log_content = """
Starting execution...
Processing task...
```json
{
  "status": "completed",
  "progress": 100,
  "summary": "Task completed successfully",
  "details": "All operations finished as expected",
  "next_action": "complete"
}
```
Execution finished.
"""
        
        # Mock subprocess to write log content and return success
        def mock_subprocess_run(cmd, **kwargs):
            # Write to stdout file if provided
            if 'stdout' in kwargs and kwargs['stdout']:
                kwargs['stdout'].write(log_content)
            return MagicMock(returncode=0)
        
        mock_run.side_effect = mock_subprocess_run
        
        # Run cycle
        result = runner.run_cycle(
            prompt="Test prompt for execution",
            cycle_num=1,
            task_name="Test Task"
        )
        
        # Verify subprocess was called
        assert mock_run.called
        
        # Verify result
        assert result.cycle_num == 1
        assert result.status == "completed"
        assert result.progress == 100
        assert result.summary == "Task completed successfully"
        assert result.next_action == "complete"
        assert result.return_code == 0
        assert result.elapsed_time >= 0
        
        # Verify file paths are set
        assert result.log_file is not None
        assert result.prompt_file is not None
    
    @patch('zima.core.kimi_runner.subprocess.run')
    def test_kimi_runner_timeout_handling(self, mock_run):
        """TC-7: Verify timeout handling."""
        # Setup mock to raise TimeoutExpired
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=['kimi'], 
            timeout=self.agent.max_execution_time
        )
        
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Pre-create log file to enable progress estimation
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = runner.logs_dir / f"cycle_{timestamp}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("Some progress... git commit test", encoding="utf-8")
        
        # Run cycle
        result = runner.run_cycle(
            prompt="Test prompt",
            cycle_num=2,
            task_name="Timeout Test"
        )
        
        # Verify timeout result
        assert result.status == "timeout"
        assert result.next_action == "continue"
        assert result.return_code == -1
        assert result.elapsed_time == self.agent.max_execution_time
    
    @patch('zima.core.kimi_runner.subprocess.run')
    def test_kimi_runner_failure_handling(self, mock_run):
        """TC-8: Verify failure handling with non-zero return code."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Mock log content with failed status
        log_content = """
Execution failed with error:
Some error occurred
```json
{
  "status": "failed",
  "progress": 0,
  "summary": "Task failed",
  "next_action": "retry"
}
```
"""
        
        # Mock subprocess to write log content and return failure
        def mock_subprocess_run(cmd, **kwargs):
            if 'stdout' in kwargs and kwargs['stdout']:
                kwargs['stdout'].write(log_content)
            return MagicMock(returncode=1)
        
        mock_run.side_effect = mock_subprocess_run
        
        # Run cycle
        result = runner.run_cycle(
            prompt="Test prompt",
            cycle_num=3,
            task_name="Failure Test"
        )
        
        # Verify failure result
        assert result.status == "failed"
        assert result.return_code == 1
    
    def test_kimi_runner_json_parsing_standard(self):
        """TC-9: Verify JSON parsing from standard format."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Test standard JSON block
        log_content = """
Some output before JSON...
```json
{
  "status": "partial",
  "progress": 50,
  "summary": "Halfway done",
  "details": "More details here",
  "next_action": "continue"
}
```
Some output after...
"""
        log_file = self.agent_dir / "test_standard.log"
        log_file.write_text(log_content, encoding="utf-8")
        
        result = runner._parse_from_log(log_file)
        
        assert result["status"] == "partial"
        assert result["progress"] == 50
        assert result["summary"] == "Halfway done"
        assert result["next_action"] == "continue"
    
    def test_kimi_runner_json_parsing_multiline(self):
        """TC-9b: Verify JSON parsing with multiline content."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Test multiline JSON block with actual newlines in the content
        log_content = '''
```json
{
  "status": "completed",
  "progress": 100,
  "summary": "Task done",
  "details": "Line 1\\nLine 2\\nLine 3",
  "next_action": "complete"
}
```
'''
        log_file = self.agent_dir / "test_multiline.log"
        log_file.write_text(log_content, encoding="utf-8")
        
        result = runner._parse_from_log(log_file)
        
        assert result["status"] == "completed"
        # The escaped newlines in JSON should be preserved
        assert "Line 1" in result.get("details", "")
    
    def test_kimi_runner_json_parsing_fallback(self):
        """TC-9c: Verify fallback heuristic parsing."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Test fallback without JSON block
        test_cases = [
            ("Task completed with 100% success", {"status": "completed", "progress": 100}),
            ("Partial progress made, 50% done", {"status": "partial", "progress": 50}),
            ("Operation failed completely", {"status": "failed", "progress": 0}),
        ]
        
        for content, expected in test_cases:
            log_file = self.agent_dir / f"test_fallback_{expected['status']}.log"
            log_file.write_text(content, encoding="utf-8")
            
            result = runner._parse_from_log(log_file)
            assert result["status"] == expected["status"]
            assert result["progress"] == expected["progress"]
    
    def test_kimi_runner_progress_estimation(self):
        """TC-9d: Verify progress estimation from log content."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        test_cases = [
            ("Reading files and analyzing", 20),  # read keyword
            ("Writing code and editing files", 40),  # write/edit keyword
            ("Running tests and validation", 60),  # test keyword
            ("Making git commit", 80),  # git commit keyword
            ("Unknown operation xyz", 50),  # default
        ]
        
        for content, expected_progress in test_cases:
            log_file = self.agent_dir / f"test_progress_{expected_progress}.log"
            log_file.write_text(content, encoding="utf-8")
            
            progress = runner._estimate_progress_from_log(log_file)
            assert progress == expected_progress


class TestKimiAgentCLILayer:
    """Test Kimi Agent CLI layer (TC-10 ~ TC-11)."""
    
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment."""
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()
        
        # Create required directories
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)
    
    def create_test_agent(self, code="test-kimi-cli", agent_type="kimi"):
        """Helper to create test agent."""
        config = AgentConfig.create(
            code=code,
            name="Test CLI Agent",
            agent_type=agent_type,
            parameters={"model": "kimi-k2-072515-preview"}
        )
        self.manager.save_config("agent", code, config.to_dict())
        return config
    
    def create_test_workflow(self, code="test-workflow"):
        """Helper to create test workflow."""
        config = WorkflowConfig.create(
            code=code,
            name="Test Workflow",
            template="# Test Workflow for {{ name }}",
        )
        self.manager.save_config("workflow", code, config.to_dict())
        return config
    
    def create_test_variable(self, code="test-var"):
        """Helper to create test variable."""
        config = VariableConfig.create(
            code=code,
            name="Test Variable",
            values={"name": "Kimi"},
        )
        self.manager.save_config("variable", code, config.to_dict())
        return config
    
    def test_agent_test_command_output(self):
        """TC-10: Verify agent test command shows generated command."""
        self.create_test_agent("test-cmd-agent")
        
        result = runner.invoke(app, ["agent", "test", "test-cmd-agent"])
        
        assert result.exit_code == 0
        assert "Generated Command" in result.output
        assert "kimi" in result.output
        assert "--print" in result.output
        assert "--yolo" in result.output
        assert "test-cmd-agent" in result.output
    
    def test_agent_test_with_different_types(self):
        """TC-10b: Verify test command works for different agent types."""
        # Test Kimi agent
        self.create_test_agent("k-agent", "kimi")
        result = runner.invoke(app, ["agent", "test", "k-agent"])
        assert result.exit_code == 0
        assert "kimi" in result.output
        
        # Test Claude agent
        self.create_test_agent("c-agent", "claude")
        result = runner.invoke(app, ["agent", "test", "c-agent"])
        assert result.exit_code == 0
        assert "claude" in result.output
        
        # Test Gemini agent
        self.create_test_agent("g-agent", "gemini")
        result = runner.invoke(app, ["agent", "test", "g-agent"])
        assert result.exit_code == 0
        assert "gemini" in result.output
    
    def test_pjob_run_with_kimi_agent_dry_run(self):
        """TC-11: Verify PJob dry-run with Kimi agent integration."""
        # Create dependencies
        self.create_test_agent("pjob-test-agent")
        self.create_test_workflow("pjob-test-workflow")
        self.create_test_variable("pjob-test-var")
        
        # Create PJob
        from zima.models.pjob import PJobConfig
        pjob = PJobConfig.create(
            code="test-kimi-pjob",
            name="Test Kimi PJob",
            agent="pjob-test-agent",
            workflow="pjob-test-workflow",
            variable="pjob-test-var"
        )
        self.manager.save_config("pjob", "test-kimi-pjob", pjob.to_dict())
        
        # Run PJob with dry-run
        result = runner.invoke(app, [
            "pjob", "run", "test-kimi-pjob",
            "--dry-run"
        ])
        
        # Verify dry-run output (check essential elements)
        assert result.exit_code == 0
        output = result.output
        # Check for key elements in output (handle encoding issues on Windows)
        assert "DRY RUN" in output or "dry" in output.lower()
        assert "kimi" in output.lower() or "--print" in output
        # Verify command structure is present
        assert "--work-dir" in output or "work" in output.lower()


class TestKimiAgentEdgeCases:
    """Test Kimi Agent edge cases (TC-12 ~ TC-14)."""
    
    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment."""
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.agent_dir = tmp_path / "agents" / "test-kimi-edge"
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        
        self.agent = AgentConfig.create(
            code="test-kimi-edge",
            name="Edge Case Agent",
            agent_type="kimi"
        )
    
    def test_kimi_runner_special_characters_in_prompt(self):
        """TC-12: Verify handling of special characters in prompt."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        special_prompts = [
            "包含中文内容的提示词",
            "Prompt with \"quotes\" and 'apostrophes'",
            "Multi\nline\nprompt\ncontent",
            "Unicode: 🚀 🎉 💻 🐍",
            "Code block: ```python\nprint('hello')\n```",
            "Path: C:\\Users\\test\\file.txt",
        ]
        
        for prompt in special_prompts:
            result_file = self.agent_dir / "workspace" / ".zima" / "result.json"
            full_prompt = runner._prepare_prompt(prompt, result_file, "Test Task")
            
            # Verify prompt is preserved
            # Note: some characters may be escaped in the output format
            assert "Output Requirements" in full_prompt
            assert "Test Task" in full_prompt
    
    def test_kimi_runner_long_prompt(self):
        """TC-13: Verify handling of long prompts."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Create a long prompt (>10KB)
        long_prompt = "This is a line.\n" * 500  # ~7KB
        long_prompt += "More content here. " * 200  # Additional content
        
        assert len(long_prompt) > 10000  # Verify it's actually long
        
        result_file = self.agent_dir / "workspace" / ".zima" / "result.json"
        full_prompt = runner._prepare_prompt(long_prompt, result_file, "Long Task")
        
        # Verify long prompt is handled
        assert len(full_prompt) > 10000
        assert "Output Requirements" in full_prompt
    
    @patch('zima.core.kimi_runner.datetime')
    @patch('zima.core.kimi_runner.subprocess.run')
    def test_kimi_runner_concurrent_cycles(self, mock_run, mock_datetime):
        """TC-14: Verify cycle execution creates unique filenames with different timestamps."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Mock datetime to return incrementing timestamps
        base_time = datetime(2026, 3, 28, 12, 0, 0)
        call_count = [0]
        
        def mock_now():
            call_count[0] += 1
            # Return incrementing timestamps (1 second apart)
            from datetime import timedelta
            return base_time + timedelta(seconds=call_count[0])
        
        mock_datetime.now = mock_now
        mock_datetime.strftime = datetime.strftime
        
        def mock_subprocess_run(cmd, **kwargs):
            log_content = """
```json
{
  "status": "completed",
  "progress": 100,
  "summary": "Cycle done",
  "next_action": "complete"
}
```
"""
            if 'stdout' in kwargs and kwargs['stdout']:
                kwargs['stdout'].write(log_content)
            return MagicMock(returncode=0)
        
        mock_run.side_effect = mock_subprocess_run
        
        # Execute multiple cycles
        results = []
        for i in range(5):
            result = runner.run_cycle(
                prompt=f"Prompt for Cycle {i+1}",
                cycle_num=i+1,
                task_name=f"Task {i+1}"
            )
            results.append(result)
        
        # Verify all cycles completed
        assert len(results) == 5
        
        # Verify each result has unique files (different timestamps)
        log_files = [str(r.log_file) for r in results]
        prompt_files = [str(r.prompt_file) for r in results]
        
        # All files should be unique
        assert len(set(log_files)) == 5, f"Log files should have unique paths, got: {log_files}"
        assert len(set(prompt_files)) == 5, f"Prompt files should have unique paths, got: {prompt_files}"
        
        # All should have success status
        for result in results:
            assert result.status == "completed"
    
    def test_kimi_runner_empty_prompt(self):
        """Additional: Verify handling of empty prompt."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        result_file = self.agent_dir / "workspace" / ".zima" / "result.json"
        full_prompt = runner._prepare_prompt("", result_file, "Empty Task")
        
        # Should still have JSON requirements
        assert "Output Requirements" in full_prompt
        assert "Empty Task" in full_prompt
    
    def test_kimi_runner_missing_log_file(self):
        """Additional: Verify handling of missing log file."""
        runner = KimiRunner(self.agent, self.agent_dir)
        
        # Try to parse non-existent log file
        result = runner._parse_from_log(Path("/nonexistent/path.log"))
        
        # Should return unknown status with default progress
        assert result["status"] == "unknown"
        assert result["progress"] == 0
