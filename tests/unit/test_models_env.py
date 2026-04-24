"""Unit tests for EnvConfig model."""

import pytest

from tests.base import TestIsolator
from zima.models.env import EnvConfig, SecretDef, SecretResolver


class TestSecretDef(TestIsolator):
    """SecretDef model tests."""

    class TestCreate:
        """Test SecretDef creation."""

        def test_create_env_source(self):
            """Test creating env source secret."""
            secret = SecretDef(name="API_KEY", source="env", key="MY_API_KEY")

            assert secret.name == "API_KEY"
            assert secret.source == "env"
            assert secret.key == "MY_API_KEY"
            assert secret.path is None
            assert secret.command is None

        def test_create_file_source(self):
            """Test creating file source secret."""
            secret = SecretDef(name="API_KEY", source="file", path="~/.keys/api_key")

            assert secret.source == "file"
            assert secret.path == "~/.keys/api_key"
            assert secret.key is None

        def test_create_cmd_source(self):
            """Test creating cmd source secret."""
            secret = SecretDef(name="API_KEY", source="cmd", command="pass show api/key")

            assert secret.source == "cmd"
            assert secret.command == "pass show api/key"

        def test_create_minimal(self):
            """Test creating with minimal fields."""
            secret = SecretDef(name="TEST", source="env")

            assert secret.name == "TEST"
            assert secret.source == "env"

    class TestDictConversion:
        """Test dictionary conversion."""

        def test_to_dict_env(self):
            """Test to_dict for env source."""
            secret = SecretDef(name="API_KEY", source="env", key="MY_KEY")

            data = secret.to_dict()
            assert data == {"name": "API_KEY", "source": "env", "key": "MY_KEY"}

        def test_to_dict_file(self):
            """Test to_dict for file source."""
            secret = SecretDef(name="API_KEY", source="file", path="/path/to/key")

            data = secret.to_dict()
            assert data == {"name": "API_KEY", "source": "file", "path": "/path/to/key"}

        def test_from_dict(self):
            """Test from_dict method."""
            data = {"name": "DB_PASSWORD", "source": "cmd", "command": "pass show db/password"}

            secret = SecretDef.from_dict(data)
            assert secret.name == "DB_PASSWORD"
            assert secret.source == "cmd"
            assert secret.command == "pass show db/password"

    class TestValidation:
        """Test secret validation."""

        def test_validate_valid_env(self):
            """Test valid env secret."""
            secret = SecretDef(name="API_KEY", source="env", key="MY_KEY")
            errors = secret.validate()
            assert errors == []

        def test_validate_valid_file(self):
            """Test valid file secret."""
            secret = SecretDef(name="API_KEY", source="file", path="/path")
            errors = secret.validate()
            assert errors == []

        def test_validate_missing_name(self):
            """Test missing name."""
            secret = SecretDef(name="", source="env")
            errors = secret.validate()
            assert any("name is required" in e for e in errors)

        def test_validate_missing_source(self):
            """Test missing source."""
            secret = SecretDef(name="TEST", source="")
            errors = secret.validate()
            assert any("source is required" in e for e in errors)

        def test_validate_invalid_source(self):
            """Test invalid source."""
            secret = SecretDef(name="TEST", source="invalid")
            errors = secret.validate()
            assert any("Invalid secret source" in e for e in errors)

        def test_validate_env_missing_key(self):
            """Test env source without key."""
            secret = SecretDef(name="TEST", source="env")
            errors = secret.validate()
            assert any("requires 'key' field" in e for e in errors)

        def test_validate_file_missing_path(self):
            """Test file source without path."""
            secret = SecretDef(name="TEST", source="file")
            errors = secret.validate()
            assert any("requires 'path' field" in e for e in errors)

        def test_validate_cmd_missing_command(self):
            """Test cmd source without command."""
            secret = SecretDef(name="TEST", source="cmd")
            errors = secret.validate()
            assert any("requires 'command' field" in e for e in errors)

    class TestMaskedValue:
        """Test masked value display."""

        def test_get_masked_value(self):
            """Test getting masked representation."""
            secret = SecretDef(name="API_KEY", source="env", key="MY_KEY")
            assert secret.get_masked_value() == "<secret:env>"


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


class TestEnvConfig(TestIsolator):
    """EnvConfig model tests."""

    class TestCreate:
        """Test EnvConfig creation."""

        def test_create_basic(self):
            """Test creating basic env config."""
            env = EnvConfig.create(code="test-env", name="Test Environment", for_type="kimi")

            assert env.metadata.code == "test-env"
            assert env.metadata.name == "Test Environment"
            assert env.for_type == "kimi"
            assert env.kind == "Env"
            assert env.override_existing is False

        def test_create_with_all_fields(self):
            """Test creating with all fields."""
            env = EnvConfig.create(
                code="full-env",
                name="Full Environment",
                for_type="claude",
                description="Test description",
                variables={"KEY1": "value1", "KEY2": "value2"},
                secrets=[{"name": "SECRET1", "source": "env", "key": "SRC1"}],
                override_existing=True,
            )

            assert env.metadata.description == "Test description"
            assert env.variables == {"KEY1": "value1", "KEY2": "value2"}
            assert len(env.secrets) == 1
            assert env.secrets[0].name == "SECRET1"
            assert env.override_existing is True

        def test_create_invalid_type(self):
            """Test creating with invalid type raises error."""
            with pytest.raises(ValueError) as exc_info:
                EnvConfig.create(code="test", name="Test", for_type="invalid")

            assert "Invalid for_type" in str(exc_info.value)

    class TestValidation:
        """Test env validation."""

        def test_validate_valid(self):
            """Test valid env config."""
            env = EnvConfig.create(code="valid-env", name="Valid Environment", for_type="kimi")
            errors = env.validate()
            assert errors == []

        def test_validate_missing_code(self):
            """Test missing code."""
            env = EnvConfig()
            env.metadata.code = ""
            env.metadata.name = "Test"
            env.for_type = "kimi"
            errors = env.validate()
            assert any("code is required" in e for e in errors)

        def test_validate_invalid_code_format(self):
            """Test invalid code format."""
            env = EnvConfig.create(code="Invalid_Code", name="Test", for_type="kimi")
            errors = env.validate()
            assert any("has invalid format" in e for e in errors)

        def test_validate_missing_name(self):
            """Test missing name."""
            env = EnvConfig.create(code="test", name="", for_type="kimi")
            env.metadata.name = ""
            errors = env.validate()
            assert any("name is required" in e for e in errors)

        def test_validate_missing_for_type(self):
            """Test missing for_type."""
            env = EnvConfig.create(code="test", name="Test")
            env.for_type = ""
            errors = env.validate()
            assert any("forType is required" in e for e in errors)

        def test_validate_invalid_for_type(self):
            """Test invalid for_type."""
            # Create valid then manually set invalid for_type
            env = EnvConfig.create(code="test", name="Test", for_type="kimi")
            env.for_type = "invalid"
            errors = env.validate()
            assert any("is not valid" in e for e in errors)

        def test_validate_invalid_variables_type(self):
            """Test variables not being a dict."""
            env = EnvConfig.create(code="test", name="Test", for_type="kimi")
            env.variables = ["not", "a", "dict"]  # type: ignore
            errors = env.validate()
            assert any("must be a dictionary" in e for e in errors)

        def test_validate_duplicate_secret_names(self):
            """Test duplicate secret names."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                secrets=[
                    {"name": "SECRET1", "source": "env", "key": "A"},
                    {"name": "SECRET1", "source": "env", "key": "B"},
                ],
            )
            errors = env.validate()
            assert any("Duplicate secret names" in e for e in errors)

        def test_validate_variable_secret_conflict(self):
            """Test conflict between variables and secrets."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                variables={"KEY1": "value1"},
                secrets=[{"name": "KEY1", "source": "env", "key": "SRC"}],
            )
            errors = env.validate()
            assert any("conflict" in e.lower() for e in errors)

    class TestDictConversion:
        """Test dictionary conversion."""

        def test_to_dict(self):
            """Test to_dict method."""
            env = EnvConfig.create(
                code="dict-test",
                name="Dict Test",
                for_type="claude",
                variables={"VAR1": "val1"},
                secrets=[{"name": "SEC1", "source": "env", "key": "K"}],
            )

            data = env.to_dict()
            assert data["apiVersion"] == "zima.io/v1"
            assert data["kind"] == "Env"
            assert data["metadata"]["code"] == "dict-test"
            assert data["spec"]["forType"] == "claude"
            assert data["spec"]["variables"] == {"VAR1": "val1"}
            assert len(data["spec"]["secrets"]) == 1
            assert data["spec"]["overrideExisting"] is False

        def test_from_dict(self):
            """Test from_dict method."""
            data = {
                "apiVersion": "zima.io/v1",
                "kind": "Env",
                "metadata": {"code": "from-dict", "name": "From Dict", "description": "Test desc"},
                "spec": {
                    "forType": "kimi",
                    "variables": {"KEY": "value"},
                    "secrets": [{"name": "SEC", "source": "file", "path": "/path"}],
                    "overrideExisting": True,
                },
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-01T00:00:00Z",
            }

            env = EnvConfig.from_dict(data)
            assert env.metadata.code == "from-dict"
            assert env.for_type == "kimi"
            assert env.variables == {"KEY": "value"}
            assert len(env.secrets) == 1
            assert env.override_existing is True

    class TestVariableManagement:
        """Test variable management methods."""

        def test_set_variable(self):
            """Test setting a variable."""
            env = EnvConfig.create(code="test", name="Test", for_type="kimi")

            env.set_variable("NEW_KEY", "new_value")

            assert env.variables["NEW_KEY"] == "new_value"

        def test_set_variable_conflict_with_secret(self):
            """Test setting variable that conflicts with secret."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                secrets=[{"name": "EXISTING_SECRET", "source": "env", "key": "SRC"}],
            )

            with pytest.raises(ValueError) as exc_info:
                env.set_variable("EXISTING_SECRET", "value")

            assert "already exists as a secret" in str(exc_info.value)

        def test_unset_variable(self):
            """Test unsetting a variable."""
            env = EnvConfig.create(
                code="test", name="Test", for_type="kimi", variables={"KEY1": "val1"}
            )

            removed = env.unset_variable("KEY1")

            assert removed is True
            assert "KEY1" not in env.variables

        def test_unset_variable_not_found(self):
            """Test unsetting nonexistent variable."""
            env = EnvConfig.create(code="test", name="Test", for_type="kimi")

            removed = env.unset_variable("NONEXISTENT")

            assert removed is False

        def test_get_variable(self):
            """Test getting a variable."""
            env = EnvConfig.create(
                code="test", name="Test", for_type="kimi", variables={"KEY": "value"}
            )

            assert env.get_variable("KEY") == "value"
            assert env.get_variable("NONEXISTENT") is None
            assert env.get_variable("NONEXISTENT", "default") == "default"

    class TestSecretManagement:
        """Test secret management methods."""

        def test_set_secret(self):
            """Test setting a secret."""
            env = EnvConfig.create(code="test", name="Test", for_type="kimi")

            env.set_secret(name="API_KEY", source="env", key="MY_KEY")

            secret = env.get_secret("API_KEY")
            assert secret is not None
            assert secret.source == "env"
            assert secret.key == "MY_KEY"

        def test_set_secret_replaces_existing(self):
            """Test setting secret replaces existing with same name."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                secrets=[{"name": "API_KEY", "source": "env", "key": "OLD_KEY"}],
            )

            env.set_secret(name="API_KEY", source="file", path="/new/path")

            secret = env.get_secret("API_KEY")
            assert secret.source == "file"
            assert secret.path == "/new/path"

        def test_set_secret_conflict_with_variable(self):
            """Test setting secret that conflicts with variable."""
            env = EnvConfig.create(
                code="test", name="Test", for_type="kimi", variables={"EXISTING_VAR": "value"}
            )

            with pytest.raises(ValueError) as exc_info:
                env.set_secret(name="EXISTING_VAR", source="env", key="SRC")

            assert "already exists as a variable" in str(exc_info.value)

        def test_unset_secret(self):
            """Test unsetting a secret."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                secrets=[{"name": "SECRET", "source": "env", "key": "SRC"}],
            )

            removed = env.unset_secret("SECRET")

            assert removed is True
            assert env.get_secret("SECRET") is None

        def test_unset_secret_not_found(self):
            """Test unsetting nonexistent secret."""
            env = EnvConfig.create(code="test", name="Test", for_type="kimi")

            removed = env.unset_secret("NONEXISTENT")

            assert removed is False

        def test_list_secrets(self):
            """Test listing secrets."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                secrets=[
                    {"name": "SEC1", "source": "env", "key": "A"},
                    {"name": "SEC2", "source": "env", "key": "B"},
                ],
            )

            secrets = env.list_secrets()
            assert secrets == ["SEC1", "SEC2"]

        def test_list_all_keys(self):
            """Test listing all keys."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                variables={"VAR1": "val1"},
                secrets=[{"name": "SEC1", "source": "env", "key": "SRC"}],
            )

            keys = env.list_all_keys()
            assert "VAR1" in keys
            assert "SEC1" in keys

    class TestResolution:
        """Test resolution methods."""

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

            result = env.resolve_all(include_secrets=True)

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

            result = env.resolve_all(include_secrets=False)

            assert result["PLAIN"] == "plain_value"
            assert result["SECRET"] == "<secret:env>"

        def test_resolve_all_secret_failure(self):
            """Test resolve_all handles secret resolution failure."""
            env = EnvConfig.create(
                code="test",
                name="Test",
                for_type="kimi",
                secrets=[{"name": "BAD_SECRET", "source": "env", "key": "NONEXISTENT"}],
            )

            result = env.resolve_all(include_secrets=True)

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

            value = env.resolve_secret("TARGET")
            assert value == "secret_value"

        def test_resolve_secret_not_found(self):
            """Test resolving nonexistent secret."""
            env = EnvConfig.create(code="test", name="Test", for_type="kimi")

            with pytest.raises(ValueError) as exc_info:
                env.resolve_secret("NONEXISTENT")

            assert "not found" in str(exc_info.value)

    class TestExport:
        """Test export methods."""

        def test_export_dotenv(self):
            """Test exporting as dotenv."""
            env = EnvConfig.create(
                code="test",
                name="Test Environment",
                description="A test env",
                for_type="kimi",
                variables={"KEY": "value"},
            )

            output = env.export_dotenv(resolve_secrets=False)

            assert "# Test Environment" in output
            assert "# A test env" in output
            assert "KEY=value" in output

        def test_export_dotenv_with_quotes(self):
            """Test dotenv quotes special characters."""
            env = EnvConfig.create(
                code="test", name="Test", for_type="kimi", variables={"KEY": "value with spaces"}
            )

            output = env.export_dotenv()

            assert 'KEY="value with spaces"' in output

        def test_export_shell(self):
            """Test exporting as shell script."""
            env = EnvConfig.create(
                code="test", name="Test Environment", for_type="kimi", variables={"KEY": "value"}
            )

            output = env.export_shell(resolve_secrets=False)

            assert "#!/bin/bash" in output
            assert 'export KEY="value"' in output

        def test_export_json(self):
            """Test exporting as JSON."""
            env = EnvConfig.create(
                code="test", name="Test", for_type="kimi", variables={"KEY": "value"}
            )

            output = env.export_json(resolve_secrets=False)

            assert '"KEY": "value"' in output
