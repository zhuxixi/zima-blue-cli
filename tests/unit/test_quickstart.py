"""Unit tests for quickstart helper functions."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from tests.base import TestIsolator


class TestDetectGitRepo(TestIsolator):
    """Test git repo detection."""

    def test_detect_git_repo_in_git_directory(self):
        """Test detection when in a git repo."""
        from zima.commands.quickstart import _detect_git_repo

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="/home/user/myproject\n", stderr=""
            )
            result = _detect_git_repo()
            assert result == "/home/user/myproject"

    def test_detect_git_repo_not_in_git_directory(self):
        """Test detection when not in a git repo."""
        from zima.commands.quickstart import _detect_git_repo

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("not a git repo")
            result = _detect_git_repo()
            assert result is None


class TestDetectRepoSlug(TestIsolator):
    """Test git remote repo slug detection."""

    def test_detect_repo_slug_https(self):
        """Test detection from HTTPS URL."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/zhuxixi/zima-blue-cli.git\n", stderr=""
            )
            result = _detect_repo_slug()
            assert result == "zhuxixi/zima-blue-cli"

    def test_detect_repo_slug_ssh(self):
        """Test detection from SSH URL."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="git@github.com:zhuxixi/zima-blue-cli.git\n", stderr=""
            )
            result = _detect_repo_slug()
            assert result == "zhuxixi/zima-blue-cli"

    def test_detect_repo_slug_no_git(self):
        """Test returns empty string when git command fails."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("no git")
            result = _detect_repo_slug()
            assert result == ""

    def test_detect_repo_slug_https_no_git_suffix(self):
        """Test detection from HTTPS URL without .git suffix."""
        from zima.commands.quickstart import _detect_repo_slug

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="https://github.com/owner/repo\n", stderr=""
            )
            result = _detect_repo_slug()
            assert result == "owner/repo"


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


class TestScanWithCommand(TestIsolator):
    """Test generic command scanning."""

    def test_scan_with_command_success(self):
        """Test successful scan with command."""
        from zima.commands.quickstart import _scan_with_command

        mock_json = '[{"number": 42, "title": "feat: add auth", "url": "https://github.com/owner/repo/pull/42"}]'
        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_json, stderr="")
            result = _scan_with_command(["gh", "pr", "list", "--json", "number,title,url"])
            assert len(result) == 1
            assert result[0]["number"] == 42

    def test_scan_with_command_failure(self):
        """Test scan when command fails."""
        from zima.commands.quickstart import _scan_with_command

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
            result = _scan_with_command(["gh", "pr", "list", "--json", "number,title,url"])
            assert result == []

    def test_scan_with_command_exception(self):
        """Test scan when subprocess raises exception."""
        from zima.commands.quickstart import _scan_with_command

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("gh not found")
            result = _scan_with_command(["gh", "pr", "list", "--json", "number,title,url"])
            assert result == []


class TestCreateAllConfigs(TestIsolator):
    """Test creating all 5 configs."""

    def test_create_all_configs_code_review(self):
        """Test creating full config set for code-review scene."""
        from zima.commands.quickstart import _create_all_configs
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        codes = _create_all_configs(
            base_name="test",
            scene_key="code-review",
            agent_type="kimi",
            work_dir="/tmp/workspace",
            env_code="test-env",
            manager=manager,
            detected_repo="zhuxixi/zima-blue-cli",
        )

        assert "agent" in codes
        assert "workflow" in codes
        assert "variable" in codes
        assert "pjob" in codes
        assert codes["env"] == "test-env"

        # Verify configs were saved
        assert manager.config_exists("agent", codes["agent"])
        assert manager.config_exists("workflow", codes["workflow"])
        assert manager.config_exists("variable", codes["variable"])
        assert manager.config_exists("pjob", codes["pjob"])

        # Verify agent has workDir
        agent_data = manager.load_config("agent", codes["agent"])
        assert agent_data["spec"]["parameters"]["workDir"] == "/tmp/workspace"

        # Verify workflow has variables including repo and pr_number
        wf_data = manager.load_config("workflow", codes["workflow"])
        var_names = {v["name"] for v in wf_data["spec"]["variables"]}
        assert "pr_url" in var_names
        assert "repo" in var_names
        assert "pr_number" in var_names

        # Verify variable has forWorkflow and repo populated
        var_data = manager.load_config("variable", codes["variable"])
        assert var_data["spec"]["forWorkflow"] == codes["workflow"]
        assert var_data["spec"]["values"]["repo"] == "zhuxixi/zima-blue-cli"

        # Verify pjob refs are correct
        job_data = manager.load_config("pjob", codes["pjob"])
        assert job_data["spec"]["agent"] == codes["agent"]
        assert job_data["spec"]["workflow"] == codes["workflow"]
        assert job_data["spec"]["variable"] == codes["variable"]
        assert job_data["spec"]["env"] == "test-env"

    def test_create_all_configs_code_review_has_actions(self):
        """Test code-review PJob gets preExec and postExec actions from scene defaults."""
        from zima.commands.quickstart import _create_all_configs
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        codes = _create_all_configs(
            base_name="test",
            scene_key="code-review",
            agent_type="kimi",
            work_dir="/tmp/workspace",
            env_code=None,
            manager=manager,
        )

        job_data = manager.load_config("pjob", codes["pjob"])
        actions = job_data["spec"].get("actions", {})

        # preExec: scan_pr
        pre_exec = actions.get("preExec", [])
        assert len(pre_exec) == 1
        assert pre_exec[0]["type"] == "scan_pr"
        assert pre_exec[0]["label"] == "zima:needs-review"
        assert pre_exec[0]["repo"] == "{{repo}}"

        # postExec: success and failure
        post_exec = actions.get("postExec", [])
        assert len(post_exec) == 2
        assert post_exec[0]["condition"] == "success"
        assert post_exec[0]["removeLabels"] == ["zima:needs-review"]
        assert post_exec[1]["condition"] == "failure"
        assert post_exec[1]["addLabels"] == ["zima:needs-fix"]

    def test_create_all_configs_custom_has_no_actions(self):
        """Test custom PJob gets no postExec actions."""
        from zima.commands.quickstart import _create_all_configs
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        codes = _create_all_configs(
            base_name="test",
            scene_key="custom",
            agent_type="kimi",
            work_dir="/tmp/workspace",
            env_code=None,
            manager=manager,
        )

        job_data = manager.load_config("pjob", codes["pjob"])
        # actions should be absent or empty (ActionsConfig().to_dict() returns {})
        assert job_data["spec"].get("actions") in (None, {}, {"postExec": [], "preExec": []})

    def test_create_all_configs_without_env(self):
        """Test creating configs when no env is selected."""
        from zima.commands.quickstart import _create_all_configs
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        codes = _create_all_configs(
            base_name="test",
            scene_key="code-review",
            agent_type="kimi",
            work_dir="/tmp/workspace",
            env_code=None,
            manager=manager,
        )

        assert codes["env"] == ""
        job_data = manager.load_config("pjob", codes["pjob"])
        assert job_data["spec"].get("env", "") == ""


class TestSelectAgentType(TestIsolator):
    """Test agent type selection."""

    def test_select_agent_type_invalid_choice(self):
        """Test invalid agent choice exits with code 1."""
        from zima.commands.quickstart import _select_agent_type

        with patch("zima.commands.quickstart.typer.prompt", return_value="99"):
            with pytest.raises(typer.Exit) as exc_info:
                _select_agent_type()
            assert exc_info.value.exit_code == 1

    def test_select_agent_type_non_numeric(self):
        """Test non-numeric agent choice exits with code 1."""
        from zima.commands.quickstart import _select_agent_type

        with patch("zima.commands.quickstart.typer.prompt", return_value="abc"):
            with pytest.raises(typer.Exit) as exc_info:
                _select_agent_type()
            assert exc_info.value.exit_code == 1


class TestResolveWorkDir(TestIsolator):
    """Test working directory resolution."""

    def test_resolve_work_dir_user_declines_git(self):
        """Test when user declines current git directory."""
        from zima.commands.quickstart import _resolve_work_dir

        with patch("zima.commands.quickstart._detect_git_repo", return_value="/tmp/repo"):
            with patch("zima.commands.quickstart.subprocess.run") as mock_remote:
                mock_remote.return_value = MagicMock(
                    returncode=0, stdout="https://github.com/user/repo.git"
                )
                with patch("zima.commands.quickstart.typer.confirm", return_value=False):
                    with patch(
                        "zima.commands.quickstart.typer.prompt", return_value="/custom/path"
                    ):
                        result = _resolve_work_dir()
        assert result == "/custom/path"

    def test_resolve_work_dir_no_git_repo(self):
        """Test fallback prompt when not in a git repo."""
        from zima.commands.quickstart import _resolve_work_dir

        with patch("zima.commands.quickstart._detect_git_repo", return_value=None):
            with patch("zima.commands.quickstart.typer.prompt", return_value="/some/path"):
                result = _resolve_work_dir()
        assert result == "/some/path"


class TestSelectEnv(TestIsolator):
    """Test env config selection."""

    def test_select_env_with_matching_configs(self):
        """Test selecting a matching env config."""
        from zima.commands.quickstart import _select_env
        from zima.config.manager import ConfigManager
        from zima.models.env import EnvConfig

        manager = ConfigManager()
        env = EnvConfig.create(
            code="kimi-key",
            name="Kimi Key",
            for_type="kimi",
            secrets=[{"type": "env", "key": "KIMI_API_KEY"}],
        )
        manager.save_config("env", "kimi-key", env.to_dict())

        with patch("zima.commands.quickstart.typer.prompt", return_value="1"):
            result = _select_env("kimi", manager)
        assert result == "kimi-key"

    def test_select_env_skip(self):
        """Test skipping env selection."""
        from zima.commands.quickstart import _select_env
        from zima.config.manager import ConfigManager
        from zima.models.env import EnvConfig

        manager = ConfigManager()
        env = EnvConfig.create(
            code="kimi-key",
            name="Kimi Key",
            for_type="kimi",
            secrets=[{"type": "env", "key": "KIMI_API_KEY"}],
        )
        manager.save_config("env", "kimi-key", env.to_dict())

        # "2" = skip (1 config + 1 skip option)
        with patch("zima.commands.quickstart.typer.prompt", return_value="2"):
            result = _select_env("kimi", manager)
        assert result is None

    def test_select_env_no_matching_configs(self):
        """Test when no env configs match agent type."""
        from zima.commands.quickstart import _select_env
        from zima.config.manager import ConfigManager

        manager = ConfigManager()
        result = _select_env("kimi", manager)
        assert result is None

    def test_select_env_invalid_choice(self):
        """Test invalid env choice exits with code 1."""
        from zima.commands.quickstart import _select_env
        from zima.config.manager import ConfigManager
        from zima.models.env import EnvConfig

        manager = ConfigManager()
        env = EnvConfig.create(
            code="kimi-key",
            name="Kimi Key",
            for_type="kimi",
            secrets=[{"type": "env", "key": "KIMI_API_KEY"}],
        )
        manager.save_config("env", "kimi-key", env.to_dict())

        with patch("zima.commands.quickstart.typer.prompt", return_value="abc"):
            with pytest.raises(typer.Exit) as exc_info:
                _select_env("kimi", manager)
            assert exc_info.value.exit_code == 1


class TestScanWithCommandExtra(TestIsolator):
    """Additional command scanning tests."""

    def test_scan_with_command_invalid_json(self):
        """Test scan handles invalid JSON gracefully."""
        from zima.commands.quickstart import _scan_with_command

        with patch("zima.commands.quickstart.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
            result = _scan_with_command(["gh", "pr", "list", "--json", "number,title,url"])
            assert result == []


class TestSelectScene(TestIsolator):
    """Test scene selection."""

    def test_select_scene_invalid_choice(self):
        """Test invalid scene choice exits with code 1."""
        from zima.commands.quickstart import _select_scene

        with patch("zima.commands.quickstart.typer.prompt", return_value="99"):
            with pytest.raises(typer.Exit) as exc_info:
                _select_scene()
            assert exc_info.value.exit_code == 1

    def test_select_scene_non_numeric(self):
        """Test non-numeric scene choice exits with code 1."""
        from zima.commands.quickstart import _select_scene

        with patch("zima.commands.quickstart.typer.prompt", return_value="abc"):
            with pytest.raises(typer.Exit) as exc_info:
                _select_scene()
            assert exc_info.value.exit_code == 1


class TestSanitizeBaseName(TestIsolator):
    """Test base name sanitization."""

    def test_sanitize_lowercase(self):
        """Test lowercase input passes through."""
        from zima.commands.quickstart import _sanitize_base_name

        assert _sanitize_base_name("hello-world") == "hello-world"

    def test_sanitize_uppercase(self):
        """Test uppercase is converted to lowercase."""
        from zima.commands.quickstart import _sanitize_base_name

        assert _sanitize_base_name("HelloWorld") == "helloworld"

    def test_sanitize_spaces(self):
        """Test spaces replaced with hyphens."""
        from zima.commands.quickstart import _sanitize_base_name

        assert _sanitize_base_name("hello world") == "hello-world"

    def test_sanitize_underscores(self):
        """Test underscores replaced with hyphens."""
        from zima.commands.quickstart import _sanitize_base_name

        assert _sanitize_base_name("hello_world") == "hello-world"

    def test_sanitize_special_chars(self):
        """Test special characters removed."""
        from zima.commands.quickstart import _sanitize_base_name

        assert _sanitize_base_name("hello@world#123") == "helloworld123"

    def test_sanitize_leading_digit(self):
        """Test leading digit gets prefix."""
        from zima.commands.quickstart import _sanitize_base_name

        assert _sanitize_base_name("123-project") == "a--project"

    def test_sanitize_empty(self):
        """Test empty string defaults to zima."""
        from zima.commands.quickstart import _sanitize_base_name

        assert _sanitize_base_name("") == "zima"

    def test_sanitize_too_long(self):
        """Test long names are truncated."""
        from zima.commands.quickstart import _sanitize_base_name

        result = _sanitize_base_name("a" * 100)
        assert len(result) <= 64 - 13  # max_base limit


class TestSanitizeGitUrl(TestIsolator):
    """Test git URL sanitization."""

    def test_sanitize_url_no_creds(self):
        """Test URL without credentials passes through."""
        from zima.commands.quickstart import _sanitize_git_url

        url = "https://github.com/user/repo.git"
        assert _sanitize_git_url(url) == url

    def test_sanitize_url_with_token(self):
        """Test token is stripped from URL."""
        from zima.commands.quickstart import _sanitize_git_url

        result = _sanitize_git_url("https://token@github.com/user/repo.git")
        assert result == "https://github.com/user/repo.git"

    def test_sanitize_url_with_user_pass(self):
        """Test user:pass is stripped from URL."""
        from zima.commands.quickstart import _sanitize_git_url

        result = _sanitize_git_url("https://user:pass@github.com/user/repo.git")
        assert result == "https://github.com/user/repo.git"

    def test_sanitize_ssh_url(self):
        """Test SSH URL passes through unchanged."""
        from zima.commands.quickstart import _sanitize_git_url

        url = "git@github.com:user/repo.git"
        assert _sanitize_git_url(url) == url


class TestGenerateUniqueCodeLimits(TestIsolator):
    """Test unique code generation limits."""

    def test_generate_code_respects_max_length(self):
        """Test generated code does not exceed max length."""
        from zima.commands.quickstart import _generate_unique_code
        from zima.config.manager import ConfigManager
        from zima.models.agent import AgentConfig
        from zima.utils import CODE_MAX_LENGTH

        manager = ConfigManager()
        long_base = "a" * 60
        agent = AgentConfig.create(code=long_base, name="Test", agent_type="kimi")
        manager.save_config("agent", long_base, agent.to_dict())

        result = _generate_unique_code(long_base, manager, "agent")
        assert len(result) <= CODE_MAX_LENGTH

    def test_generate_code_max_attempts_exceeded(self):
        """Test RuntimeError when max attempts exceeded."""
        from zima.commands.quickstart import _generate_unique_code
        from zima.config.manager import ConfigManager
        from zima.models.agent import AgentConfig

        manager = ConfigManager()
        # Create base config + enough configs to exhaust attempts
        base_agent = AgentConfig.create(code="hello-agent", name="Test", agent_type="kimi")
        manager.save_config("agent", "hello-agent", base_agent.to_dict())
        for i in range(2, 1003):
            code = f"hello-agent-{i}"
            agent = AgentConfig.create(code=code, name="Test", agent_type="kimi")
            manager.save_config("agent", code, agent.to_dict())

        with pytest.raises(RuntimeError, match="Could not generate unique code"):
            _generate_unique_code("hello-agent", manager, "agent")
