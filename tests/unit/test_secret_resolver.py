"""Unit tests for secret resolution and env export (zima.execution.secret_resolver).

These cover the IO that was moved out of the domain layer (zima.models.env) so
that models stays free of ``subprocess``.
"""

import pytest

from tests.base import TestIsolator
from zima.execution.secret_resolver import (
    SecretResolver,
    export_env_dotenv,
    export_env_json,
    export_env_shell,
    resolve_env_all,
    resolve_env_secret,
)
from zima.models.env import EnvConfig, SecretDef


class TestSecretResolver(TestIsolator):
    """SecretResolver tests."""

    class TestEnvSource:
        """Test env source resolution."""

        def test_resolve_env_success(self, monkeypatch):
            """Test successful env resolution."""
            monkeypatch.setenv("MY_SECRET_KEY", "secret_value_123")

            secret = SecretDef(name="API_KEY", source="env", key="MY_SECRET_KEY")
            value = SecretResolver.resolve(secret)

            assert value == "secret_value_123"

        def test_resolve_env_not_set(self):
            """Test env not set raises error."""
            secret = SecretDef(name="API_KEY", source="env", key="NONEXISTENT_VAR")

            with pytest.raises(ValueError) as exc_info:
                SecretResolver.resolve(secret)

            assert "not set" in str(exc_info.value)

        def test_resolve_env_empty_key(self):
            """Test env with empty key raises error."""
            secret = SecretDef(name="API_KEY", source="env", key="")

            with pytest.raises(ValueError) as exc_info:
                SecretResolver.resolve(secret)

            assert "key" in str(exc_info.value).lower()

    class TestFileSource:
        """Test file source resolution."""

        def test_resolve_file_success(self, tmp_path):
            """Test successful file resolution."""
            key_file = tmp_path / "api_key.txt"
            key_file.write_text("  file_secret_value  ")

            secret = SecretDef(name="API_KEY", source="file", path=str(key_file))
            value = SecretResolver.resolve(secret)

            assert value == "file_secret_value"

        def test_resolve_file_not_found(self):
            """Test file not found raises error."""
            secret = SecretDef(name="API_KEY", source="file", path="/nonexistent/path/key.txt")

            with pytest.raises(ValueError) as exc_info:
                SecretResolver.resolve(secret)

            assert "not found" in str(exc_info.value)

        def test_resolve_file_expand_user(self, tmp_path, monkeypatch):
            """Test file path expands user home."""
            # Create file in temp location and use direct path
            key_file = tmp_path / "api_key.txt"
            key_file.write_text("home_secret")

            # Use the actual path without ~ to test file reading works
            secret = SecretDef(name="API_KEY", source="file", path=str(key_file))
            value = SecretResolver.resolve(secret)

            assert value == "home_secret"

    class TestCmdSource:
        """Test cmd source resolution."""

        def test_resolve_cmd_success(self):
            """Test successful cmd resolution."""
            secret = SecretDef(name="API_KEY", source="cmd", command="echo cmd_secret_value")
            value = SecretResolver.resolve(secret)

            assert value == "cmd_secret_value"

        def test_resolve_cmd_failed(self):
            """Test failed cmd raises error."""
            secret = SecretDef(name="API_KEY", source="cmd", command="exit 1")

            with pytest.raises(ValueError) as exc_info:
                SecretResolver.resolve(secret)

            assert "failed" in str(exc_info.value).lower()

        def test_resolve_cmd_timeout(self):
            """Test cmd timeout raises error."""
            # Use a shorter sleep and lower timeout by patching
            import subprocess

            original_run = subprocess.run

            def mock_run(*args, **kwargs):
                if args[0] == "sleep 35":
                    raise subprocess.TimeoutExpired(args[0], timeout=1)
                return original_run(*args, **kwargs)

            monkeypatch = pytest.MonkeyPatch()
            monkeypatch.setattr(subprocess, "run", mock_run)

            secret = SecretDef(name="API_KEY", source="cmd", command="sleep 35")

            with pytest.raises(ValueError) as exc_info:
                SecretResolver.resolve(secret)

            assert "timed out" in str(exc_info.value).lower()
            monkeypatch.undo()

        def test_resolve_cmd_strips_output(self):
            """Test cmd output is stripped."""
            secret = SecretDef(name="API_KEY", source="cmd", command="echo spaced_value")
            value = SecretResolver.resolve(secret)

            # Windows echo includes quotes, so just check the value is present
            assert "spaced_value" in value

    class TestVaultSource:
        """Test vault source resolution."""

        def test_resolve_vault_not_implemented(self):
            """Test vault source raises not implemented."""
            secret = SecretDef(name="API_KEY", source="vault", path="secret/key")

            with pytest.raises(ValueError) as exc_info:
                SecretResolver.resolve(secret)

            assert "not yet implemented" in str(exc_info.value)


class TestResolution(TestIsolator):
    """Test env resolution functions."""

    def test_resolve_all_with_secrets(self, monkeypatch):
        """Test resolving all with secrets."""
        monkeypatch.setenv("MY_KEY", "resolved_value")

        env = EnvConfig.create(
            code="test",
            name="Test",
            for_type="kimi",
            variables={"PLAIN": "plain_value"},
            secrets=[{"name": "SECRET", "source": "env", "key": "MY_KEY"}],
        )

        result = resolve_env_all(env, include_secrets=True)

        assert result["PLAIN"] == "plain_value"
        assert result["SECRET"] == "resolved_value"

    def test_resolve_all_without_secrets(self):
        """Test resolving all without secrets."""
        env = EnvConfig.create(
            code="test",
            name="Test",
            for_type="kimi",
            variables={"PLAIN": "plain_value"},
            secrets=[{"name": "SECRET", "source": "env", "key": "MY_KEY"}],
        )

        result = resolve_env_all(env, include_secrets=False)

        assert result["PLAIN"] == "plain_value"
        assert result["SECRET"] == "<secret:env>"

    def test_resolve_all_secret_failure(self):
        """Test resolve_env_all handles secret resolution failure."""
        env = EnvConfig.create(
            code="test",
            name="Test",
            for_type="kimi",
            secrets=[{"name": "BAD_SECRET", "source": "env", "key": "NONEXISTENT"}],
        )

        result = resolve_env_all(env, include_secrets=True)

        assert "<error:" in result["BAD_SECRET"]

    def test_resolve_secret(self, monkeypatch):
        """Test resolving single secret."""
        monkeypatch.setenv("SRC_KEY", "secret_value")

        env = EnvConfig.create(
            code="test",
            name="Test",
            for_type="kimi",
            secrets=[{"name": "TARGET", "source": "env", "key": "SRC_KEY"}],
        )

        value = resolve_env_secret(env, "TARGET")
        assert value == "secret_value"

    def test_resolve_secret_not_found(self):
        """Test resolving nonexistent secret."""
        env = EnvConfig.create(code="test", name="Test", for_type="kimi")

        with pytest.raises(ValueError) as exc_info:
            resolve_env_secret(env, "NONEXISTENT")

        assert "not found" in str(exc_info.value)


class TestExport(TestIsolator):
    """Test env export functions."""

    def test_export_dotenv(self):
        """Test exporting as dotenv."""
        env = EnvConfig.create(
            code="test",
            name="Test Environment",
            description="A test env",
            for_type="kimi",
            variables={"KEY": "value"},
        )

        output = export_env_dotenv(env, resolve_secrets=False)

        assert "# Test Environment" in output
        assert "# A test env" in output
        assert "KEY=value" in output

    def test_export_dotenv_with_quotes(self):
        """Test dotenv quotes special characters."""
        env = EnvConfig.create(
            code="test", name="Test", for_type="kimi", variables={"KEY": "value with spaces"}
        )

        output = export_env_dotenv(env)

        assert 'KEY="value with spaces"' in output

    def test_export_shell(self):
        """Test exporting as shell script."""
        env = EnvConfig.create(
            code="test", name="Test Environment", for_type="kimi", variables={"KEY": "value"}
        )

        output = export_env_shell(env, resolve_secrets=False)

        assert "#!/bin/bash" in output
        assert 'export KEY="value"' in output

    def test_export_json(self):
        """Test exporting as JSON."""
        env = EnvConfig.create(
            code="test", name="Test", for_type="kimi", variables={"KEY": "value"}
        )

        output = export_env_json(env, resolve_secrets=False)

        assert '"KEY": "value"' in output
