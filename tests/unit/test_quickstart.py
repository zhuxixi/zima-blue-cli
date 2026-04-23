"""Unit tests for quickstart helper functions."""

from unittest.mock import MagicMock, patch

from tests.base import TestIsolator


class TestDetectGitRepo(TestIsolator):
    """Test git repo detection."""

    def test_detect_git_repo_in_git_directory(self):
        """Test detection when in a git repo."""
        from zima.commands.quickstart import _detect_git_repo

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=".git\n", stderr="")
            result = _detect_git_repo()
            assert result is not None

    def test_detect_git_repo_not_in_git_directory(self):
        """Test detection when not in a git repo."""
        from zima.commands.quickstart import _detect_git_repo

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("not a git repo")
            result = _detect_git_repo()
            assert result is None


class TestGenerateUniqueCode(TestIsolator):
    """Test unique code generation."""

    def test_generate_code_no_collision(self):
        """Test code generation when no collision."""
        from zima.commands.quickstart import _generate_unique_code
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result = _generate_unique_code("hello-agent", manager, "agent")
        assert result == "hello-agent"

    def test_generate_code_with_collision(self):
        """Test code generation appends suffix on collision."""
        from zima.commands.quickstart import _generate_unique_code
        from zima.config.manager import ConfigManager
        from zima.models.agent import AgentConfig

        manager = ConfigManager()
        # Pre-create an agent to cause collision
        agent = AgentConfig.create(code="hello-agent", name="Hello Agent", agent_type="kimi")
        manager.save_config("agent", "hello-agent", agent.to_dict())

        result = _generate_unique_code("hello-agent", manager, "agent")
        assert result == "hello-agent-2"

    def test_generate_code_multiple_collisions(self):
        """Test code generation with multiple collisions."""
        from zima.commands.quickstart import _generate_unique_code
        from zima.config.manager import ConfigManager
        from zima.models.agent import AgentConfig

        manager = ConfigManager()
        for i in range(1, 4):
            code = "hello-agent" if i == 1 else f"hello-agent-{i}"
            agent = AgentConfig.create(code=code, name="Hello Agent", agent_type="kimi")
            manager.save_config("agent", code, agent.to_dict())

        result = _generate_unique_code("hello-agent", manager, "agent")
        assert result == "hello-agent-4"


class TestScanGithubPRs(TestIsolator):
    """Test GitHub PR scanning."""

    def test_scan_prs_success(self):
        """Test successful PR scan."""
        from zima.commands.quickstart import _scan_github_prs

        mock_json = '[{"number": 42, "title": "feat: add auth", "url": "https://github.com/owner/repo/pull/42"}]'
        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_json, stderr="")
            result = _scan_github_prs("need-review")
            assert len(result) == 1
            assert result[0]["number"] == 42

    def test_scan_prs_failure(self):
        """Test PR scan when gh command fails."""
        from zima.commands.quickstart import _scan_github_prs

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            result = _scan_github_prs("need-review")
            assert result == []

    def test_scan_prs_exception(self):
        """Test PR scan when subprocess raises exception."""
        from zima.commands.quickstart import _scan_github_prs

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("gh not found")
            result = _scan_github_prs("need-review")
            assert result == []
