"""Tests for Claude Code agent type and runner."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from zima.models.agent import AgentConfig, CycleResult
from zima.core.claude_runner import ClaudeRunner


class TestClaudeAgentConfig:
    """Test Claude agent configuration."""

    def test_claude_parameter_template(self):
        """Test Claude default parameters are correct."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")

        assert config.parameters["model"] == "claude-sonnet-4-6"
        assert config.parameters["maxTurns"] == 100
        assert config.parameters["permissionMode"] == "plan"
        assert config.parameters["outputFormat"] == "stream-json"
        assert config.parameters["allowedTools"] == []
        assert config.parameters["disallowedTools"] == []

    def test_claude_cli_template(self):
        """Test Claude CLI template uses -p, not --print."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")
        template = config.get_cli_command_template()

        assert template == ["claude", "-p"]

    def test_claude_needs_stdin_pipe(self):
        """Test Claude agent type requires stdin pipe for prompt."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")
        assert config.needs_stdin_pipe is True

    def test_kimi_does_not_need_stdin_pipe(self):
        """Test Kimi agent type does NOT need stdin pipe."""
        config = AgentConfig.create("test-kimi", "Test Kimi", "kimi")
        assert config.needs_stdin_pipe is False

    def test_claude_build_command_basic(self):
        """Test basic Claude command building."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")

        cmd = config.build_command(
            prompt_file=Path("/tmp/prompt.md"),
            work_dir=Path("/tmp/workspace"),
        )

        assert "claude" in cmd
        assert "-p" in cmd
        assert "--model" in cmd
        assert "claude-sonnet-4-6" in cmd
        assert "--max-turns" in cmd
        assert "100" in cmd
        assert "--permission-mode" in cmd
        assert "plan" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd

    def test_claude_build_command_no_prompt_flag(self):
        """Test Claude command does NOT include --prompt flag."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")

        cmd = config.build_command(prompt_file=Path("/tmp/prompt.md"))

        # Claude receives prompt via stdin pipe, not CLI argument
        assert "--prompt" not in cmd
        assert "/tmp/prompt.md" not in cmd

    def test_claude_build_command_custom_params(self):
        """Test Claude command with custom parameters."""
        config = AgentConfig.create(
            "test-claude",
            "Test Claude",
            "claude",
            parameters={
                "maxTurns": 30,
                "model": "claude-opus-4-6",
                "allowedTools": ["Bash", "Read", "Edit"],
                "disallowedTools": ["Write"],
                "appendSystemPrompt": "Always use TypeScript",
            },
        )

        cmd = config.build_command(
            prompt_file=Path("/tmp/prompt.md"),
            work_dir=Path("/tmp/workspace"),
        )

        assert "--max-turns" in cmd
        assert "30" in cmd
        assert "--model" in cmd
        assert "claude-opus-4-6" in cmd
        assert "--allowedTools" in cmd
        assert "Bash,Read,Edit" in cmd
        assert "--disallowedTools" in cmd
        assert "Write" in cmd
        assert "--append-system-prompt" in cmd
        assert "Always use TypeScript" in cmd

    def test_claude_build_command_add_dirs(self):
        """Test Claude command with additional directories."""
        config = AgentConfig.create(
            "test-claude",
            "Test Claude",
            "claude",
            parameters={"addDirs": ["./src", "./tests"]},
        )

        cmd = config.build_command()

        assert "--add-dir" in cmd
        assert "./src" in cmd
        assert "./tests" in cmd

    def test_claude_build_command_empty_tools_lists(self):
        """Test that empty allowed/disallowed tools lists are not added."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")

        cmd = config.build_command()

        assert "--allowedTools" not in cmd
        assert "--disallowedTools" not in cmd

    def test_claude_build_command_verbose(self):
        """Test Claude command with verbose flag."""
        config = AgentConfig.create(
            "test-claude",
            "Test Claude",
            "claude",
            parameters={"verbose": True},
        )

        cmd = config.build_command()

        assert "--verbose" in cmd

    def test_claude_build_command_without_prompt_file(self):
        """Test Claude command without prompt file."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")

        cmd = config.build_command()

        assert "claude" in cmd
        assert "-p" in cmd
        assert "--model" in cmd


class TestClaudeRunnerParsing:
    """Test ClaudeRunner NDJSON parsing logic."""

    @pytest.fixture
    def runner(self, tmp_path):
        """Create a ClaudeRunner with temp directory."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")
        agent_dir = tmp_path / "agents" / "test-claude"
        agent_dir.mkdir(parents=True)
        return ClaudeRunner(config, agent_dir)

    def test_parse_valid_ndjson(self, runner):
        """Test parsing valid NDJSON lines."""
        line = '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}'
        result = runner._parse_ndjson_line(line)
        assert result is not None
        assert result["type"] == "assistant"

    def test_parse_invalid_ndjson(self, runner):
        """Test parsing invalid JSON returns None."""
        result = runner._parse_ndjson_line("not json at all")
        assert result is None

    def test_parse_empty_line(self, runner):
        """Test parsing empty line returns None."""
        assert runner._parse_ndjson_line("") is None
        assert runner._parse_ndjson_line("   ") is None

    def test_extract_result_success(self, runner):
        """Test extracting success result from events."""
        events = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Working..."}]}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            {"type": "tool_result", "content": "file1.txt\nfile2.txt"},
            {"type": "result", "subtype": "success", "cost_usd": 0.05, "duration_ms": 5000, "session_id": "abc123"},
        ]

        result = runner._extract_result(events, returncode=0)

        assert result["status"] == "completed"
        assert result["progress"] == 100
        assert result["next_action"] == "complete"
        assert "Cost: $0.0500" in result["details"]
        assert "Session: abc123" in result["details"]

    def test_extract_result_error(self, runner):
        """Test extracting error result from events."""
        events = [
            {"type": "result", "subtype": "error", "cost_usd": 0.01, "duration_ms": 1000},
        ]

        result = runner._extract_result(events, returncode=1)

        assert result["status"] == "failed"
        assert result["next_action"] == "retry"

    def test_extract_result_no_result_event(self, runner):
        """Test extracting result when no result event is present."""
        events = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done"}]}},
        ]

        # Success returncode
        result = runner._extract_result(events, returncode=0)
        assert result["status"] == "completed"

        # Failed returncode
        result = runner._extract_result(events, returncode=1)
        assert result["status"] == "failed"

    def test_extract_result_timeout_exit_code(self, runner):
        """Test that exit code 5 is recognized as timeout."""
        events = []
        result = runner._extract_result(events, returncode=5)

        assert result["status"] == "timeout"
        assert result["next_action"] == "retry"

    def test_extract_summary_from_assistant(self, runner):
        """Test extracting summary from last assistant message."""
        events = [
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "First message"}]}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Task completed successfully"}]}},
            {"type": "result", "subtype": "success", "cost_usd": 0.05, "duration_ms": 5000},
        ]

        result = runner._extract_result(events, returncode=0)
        assert "Task completed successfully" in result["summary"]

    def test_estimate_progress(self, runner):
        """Test progress estimation from tool usage."""
        events = [
            {"type": "tool_use", "name": "Bash"},
            {"type": "tool_use", "name": "Read"},
            {"type": "tool_use", "name": "Edit"},
        ]

        progress = runner._estimate_progress(events)
        assert 0 < progress <= 95

    def test_estimate_progress_no_tools(self, runner):
        """Test progress estimation with no tools."""
        events = []
        progress = runner._estimate_progress(events)
        assert progress == 50  # Default

    def test_runner_creates_directories(self, tmp_path):
        """Test that runner creates required directories."""
        config = AgentConfig.create("test-claude", "Test Claude", "claude")
        agent_dir = tmp_path / "agents" / "test-claude"

        runner = ClaudeRunner(config, agent_dir)

        assert runner.prompts_dir.exists()
        assert runner.logs_dir.exists()
        assert runner.workspace.exists()
