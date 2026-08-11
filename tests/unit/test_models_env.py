"""Unit tests for EnvConfig model (pure data layer).

Resolution/export IO moved to zima.execution.secret_resolver (see
test_secret_resolver.py); this module covers the data model only.
"""

import pytest

from tests.base import TestIsolator
from zima.models.env import EnvConfig, SecretDef


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

        def test_create_pi_for_type(self):
            """Test env config accepts pi as for_type."""
            env = EnvConfig.create(code="test-env-pi", name="Test Pi Env", for_type="pi")
            assert env.for_type == "pi"

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
