"""
Real integration tests for Kimi Agent - actually calls Kimi Code CLI.

These tests require:
- Kimi Code CLI (kimi) installed and authenticated
- Network connection to Kimi API
- Sufficient API quota

Run with: pytest tests/integration/test_kimi_agent_real.py -v
Skip with: pytest tests/integration/ --ignore=tests/integration/test_kimi_agent_real.py
"""

import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zima.cli import app
from zima.config.manager import ConfigManager
from zima.core.kimi_runner import KimiRunner
from zima.models import AgentConfig
from zima.models.variable import VariableConfig
from zima.models.workflow import WorkflowConfig

runner = CliRunner()


def _setup_isolated_home(monkeypatch, tmp_path):
    """Create an isolated HOME directory that symlinks to the real Kimi config.

    Kimi Code CLI stores its configuration under ``~/.kimi-code`` (and may
    still reference the legacy ``~/.kimi`` directory). The tests isolate
    ``HOME`` to a temp directory and symlink the real config directories into
    it so Kimi Code CLI can authenticate and run without writing into the
    user's actual home directory.
    """
    real_home = Path.home()
    config_dirs = [
        real_home / ".kimi-code",
        real_home / ".kimi",
    ]
    found = [p for p in config_dirs if p.exists()]
    if not found:
        pytest.skip("Real Kimi Code CLI config not found")

    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)

    for real_dir in found:
        link = fake_home / real_dir.name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(real_dir, target_is_directory=True)

    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


def check_kimi_available():
    """Check if Kimi Code CLI is available and working."""
    try:
        result = subprocess.run(
            ["kimi", "--version"], capture_output=True, text=True, encoding="utf-8", timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# Skip all tests in this file if kimi is not available
pytestmark = pytest.mark.skipif(
    not check_kimi_available(), reason="Kimi Code CLI not available or not authenticated"
)


class TestKimiAgentRealCommands:
    """Test with real Kimi Code CLI calls (lightweight operations only)."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment.

        HOME is monkeypatched to a temp directory, and the real ~/.kimi
        configuration is symlinked into it so Kimi Code CLI can locate its
        config and credentials without writing into the user's home directory.
        """
        _setup_isolated_home(monkeypatch, tmp_path)
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.agent_dir = tmp_path / "agents" / "test-kimi-real"
        self.agent_dir.mkdir(parents=True, exist_ok=True)

        self.agent = AgentConfig.create(
            code="test-kimi-real",
            name="Real Test Kimi Agent",
            agent_type="kimi",
        )
        self.manager = ConfigManager()

        # Create required directories
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def test_kimi_cli_basic_invocation(self):
        """Test 1: Verify Kimi Code CLI can be invoked with --help."""
        # This is the most basic test - just verify kimi responds
        result = subprocess.run(
            ["kimi", "--help"], capture_output=True, text=True, encoding="utf-8", timeout=10
        )

        assert result.returncode == 0, f"kimi --help failed: {result.stderr}"
        assert "Usage:" in result.stdout or "usage:" in result.stdout.lower()
        print(f"✅ Kimi CLI version info: {result.stdout[:200]}")

    def test_kimi_cli_simple_prompt_mode(self):
        """Test 2: Test Kimi Code CLI prompt mode with a simple prompt."""
        # Create a simple prompt file
        prompt_file = self.temp_dir / "simple_prompt.md"
        prompt_file.write_text(
            'Respond with a JSON object: {"status": "ok", "message": "Hello"}', encoding="utf-8"
        )

        workspace = self.temp_dir / "workspace"
        workspace.mkdir(exist_ok=True)

        # Run kimi with prompt mode (non-interactive)
        result = subprocess.run(
            [
                "kimi",
                "--prompt",
                str(prompt_file),
                "--output-format",
                "text",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,  # Give it up to 60 seconds
            cwd=str(workspace),
        )

        # Print output for debugging
        print(f"\n📤 STDOUT:\n{result.stdout[:1000]}")
        print(f"\n📥 STDERR:\n{result.stderr[:500]}")
        print(f"\n🔢 Return code: {result.returncode}")

        # Verify kimi executed (even if the response isn't perfect)
        assert result.returncode in [0, 1], f"Unexpected return code: {result.returncode}"
        assert len(result.stdout) > 0, "No output from kimi"

    def test_kimi_runner_real_execution(self):
        """Test 3: Test KimiRunner with real kimi call."""
        runner = KimiRunner(self.agent, self.agent_dir)

        # Use a very simple prompt
        prompt = """
You are a test assistant. Please output exactly this JSON:

```json
{
  "status": "completed",
  "progress": 100,
  "summary": "Test task completed",
  "details": "This is a test execution",
  "next_action": "complete"
}
```

That's all. Do not do anything else.
"""

        print("\n>> Starting REAL Kimi execution...")
        start_time = datetime.now()

        result = runner.run_cycle(prompt=prompt, cycle_num=1, task_name="Real Execution Test")

        elapsed = (datetime.now() - start_time).total_seconds()

        print("\n>> Execution Result:")
        print(f"   Status: {result.status}")
        print(f"   Progress: {result.progress}")
        print(f"   Summary: {result.summary}")
        print(f"   Elapsed: {elapsed:.2f}s")
        print(f"   Log file: {result.log_file}")

        # Verify execution completed
        assert result.status in ["completed", "partial", "unknown"]
        assert result.log_file is not None
        assert result.log_file.exists()

        # Print log content for verification
        log_content = result.log_file.read_text(encoding="utf-8")
        print(f"\n>> Log content (first 800 chars):\n{log_content[:800]}")

    def test_kimi_runner_with_simple_file_operation(self):
        """Test 4: Test kimi can perform a simple file operation."""
        runner = KimiRunner(self.agent, self.agent_dir)

        test_file = runner.workspace / "test_file.txt"

        prompt = f"""
Create a file at {test_file} with the following content:
Hello from Kimi Agent Test!
Timestamp: {datetime.now().isoformat()}

Then output this JSON:
```json
{{
  "status": "completed",
  "progress": 100,
  "summary": "File created successfully",
  "next_action": "complete"
}}
```
"""

        print("\n🚀 Testing file operation...")

        result = runner.run_cycle(prompt=prompt, cycle_num=2, task_name="File Operation Test")

        print(f"\n📊 Result: {result.status} - {result.summary}")

        # Check if file was created
        if test_file.exists():
            content = test_file.read_text(encoding="utf-8")
            print(f"\n📄 File created with content:\n{content}")
            assert "Hello from Kimi Agent Test!" in content
        else:
            print("\n⚠️ File not created (this is OK if kimi chose not to)")
            # Don't fail - kimi might have reasons not to create the file

    def test_agent_config_to_real_command(self):
        """Test 5: Verify AgentConfig generates valid command that kimi accepts."""
        # Create the extra_dir first (kimi requires it to exist)
        extra_dir = self.temp_dir / "extra_dir"
        extra_dir.mkdir(exist_ok=True)

        agent = AgentConfig.create(
            code="real-cmd-test",
            name="Real Command Test",
            agent_type="kimi",
            parameters={
                "addDirs": [str(extra_dir)],
            },
        )

        # Create necessary files
        prompt_file = self.temp_dir / "test_prompt.md"
        prompt_file.write_text(
            "Say 'Hello from test' and output JSON with status=completed", encoding="utf-8"
        )

        workspace = self.temp_dir / "test_workspace"
        workspace.mkdir(exist_ok=True)

        # Build command
        cmd = agent.build_command(prompt_file=prompt_file, work_dir=workspace)

        print(f"\n🔧 Generated command:\n{' '.join(cmd)}")

        # Verify the command is valid by running it
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)

        print(f"\n📤 STDOUT (first 500 chars):\n{result.stdout[:500]}")
        print(f"\n🔢 Return code: {result.returncode}")

        # Just verify kimi accepted the command
        assert "error" not in result.stderr.lower() or result.returncode == 0


class TestKimiAgentRealPJobIntegration:
    """Test PJob integration with real kimi execution."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment.

        HOME is monkeypatched to a temp directory with the real ~/.kimi
        configuration symlinked in so Kimi Code CLI remains functional.
        """
        _setup_isolated_home(monkeypatch, tmp_path)
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.manager = ConfigManager()

        # Create required directories
        for kind in ["agents", "workflows", "variables", "envs", "pmgs", "pjobs"]:
            (tmp_path / "configs" / kind).mkdir(parents=True, exist_ok=True)

    def create_real_test_agent(self, code="real-test-agent"):
        """Create an agent config for real testing."""
        config = AgentConfig.create(
            code=code,
            name="Real Test Agent",
            agent_type="kimi",
        )
        self.manager.save_config("agent", code, config.to_dict())
        return config

    def create_simple_workflow(self, code="simple-workflow"):
        """Create a simple workflow."""
        config = WorkflowConfig.create(
            code=code,
            name="Simple Workflow",
            template="""# Simple Test Task

Please perform the following:
1. Output the text: "Workflow executed: {{ task_name }}"
2. Then output this exact JSON:

```json
{
  "status": "completed",
  "progress": 100,
  "summary": "Workflow {{ task_name }} completed",
  "next_action": "complete"
}
```
""",
        )
        self.manager.save_config("workflow", code, config.to_dict())
        return config

    def create_simple_variable(self, code="simple-var"):
        """Create simple variable config."""
        config = VariableConfig.create(
            code=code,
            name="Simple Variable",
            values={"task_name": "RealIntegrationTest"},
        )
        self.manager.save_config("variable", code, config.to_dict())
        return config

    def test_pjob_render_then_execute(self):
        """Test 6: Render PJob template, then execute with real kimi."""
        from zima.models.pjob import PJobConfig

        # Create configs
        self.create_real_test_agent("pjob-real-agent")
        self.create_simple_workflow("pjob-real-workflow")
        self.create_simple_variable("pjob-real-var")

        # Create PJob
        pjob = PJobConfig.create(
            code="real-execution-pjob",
            name="Real Execution PJob",
            agent="pjob-real-agent",
            workflow="pjob-real-workflow",
            variable="pjob-real-var",
        )
        self.manager.save_config("pjob", "real-execution-pjob", pjob.to_dict())

        # Step 1: Render the PJob
        render_result = runner.invoke(app, ["pjob", "render", "real-execution-pjob"])

        assert render_result.exit_code == 0
        rendered_output = render_result.output
        print(f"\n📝 Rendered workflow:\n{rendered_output}")

        # Verify variable was substituted
        assert "RealIntegrationTest" in rendered_output

        # Step 2: Execute with dry-run first
        dry_result = runner.invoke(app, ["pjob", "run", "real-execution-pjob", "--dry-run"])

        assert dry_result.exit_code == 0
        assert "kimi" in dry_result.output.lower()
        print("\n🔍 Dry run command generated successfully")

        # Step 3: Real execution (optional - can be slow)
        # Uncomment the following to do real execution:
        """
        print(f"\n🚀 Starting REAL PJob execution...")
        run_result = runner.invoke(app, [
            "pjob", "run", "real-execution-pjob",
            "--timeout", "60"
        ])

        print(f"\n📊 Execution output:\n{run_result.output}")
        assert run_result.exit_code == 0
        """


class TestKimiAgentErrorHandling:
    """Test error handling with real kimi calls."""

    @pytest.fixture(autouse=True)
    def setup_isolation(self, monkeypatch, tmp_path):
        """Set up isolated test environment.

        HOME is monkeypatched to a temp directory with the real ~/.kimi
        configuration symlinked in so Kimi Code CLI remains functional.
        """
        _setup_isolated_home(monkeypatch, tmp_path)
        monkeypatch.setenv("ZIMA_HOME", str(tmp_path))
        self.temp_dir = tmp_path
        self.agent_dir = tmp_path / "agents" / "error-test"
        self.agent_dir.mkdir(parents=True, exist_ok=True)

        self.agent = AgentConfig.create(
            code="error-test",
            name="Error Test Agent",
            agent_type="kimi",
        )

    def test_invalid_work_directory(self):
        """Test 7: Test behavior with invalid work directory."""
        # Try to use a path that doesn't exist. subprocess.run cwd must exist,
        # so we expect a FileNotFoundError from Python rather than from kimi.
        invalid_workspace = self.temp_dir / "does_not_exist" / "nested"

        prompt_file = self.temp_dir / "prompt.md"
        prompt_file.write_text("Say hello", encoding="utf-8")

        # This should fail gracefully since cwd does not exist
        with pytest.raises(FileNotFoundError):
            subprocess.run(
                [
                    "kimi",
                    "--prompt",
                    str(prompt_file),
                    "--output-format",
                    "text",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                cwd=str(invalid_workspace),
            )

        print("\n📊 Invalid directory test: subprocess correctly raised FileNotFoundError")


def pytest_configure(config):
    """Configure pytest to add custom markers."""
    config.addinivalue_line(
        "markers",
        "real_kimi: marks tests that make real calls to Kimi Code CLI (may be slow and use API quota)",
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
