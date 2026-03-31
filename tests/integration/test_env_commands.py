"""Integration tests for Env CLI commands."""

from typer.testing import CliRunner

from tests.base import TestIsolator
from tests.conftest import strip_ansi
from zima.cli import app

runner = CliRunner()


class TestEnvCreate(TestIsolator):
    """Test env create command."""

    def test_create_basic(self):
        """Test creating basic env config."""
        result = runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "test-env",
                "--name",
                "Test Environment",
                "--for-type",
                "kimi",
            ],
        )

        assert result.exit_code == 0
        assert "created successfully" in result.output
        assert "test-env" in result.output
        assert "kimi" in result.output

    def test_create_with_description(self):
        """Test creating with description."""
        result = runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "desc-env",
                "--name",
                "Desc Environment",
                "--for-type",
                "claude",
                "--description",
                "A test environment",
            ],
        )

        assert result.exit_code == 0
        assert "created successfully" in result.output

    def test_create_duplicate_code_fails(self):
        """Test creating with duplicate code fails."""
        runner.invoke(
            app,
            ["env", "create", "--code", "duplicate-env", "--name", "First", "--for-type", "kimi"],
        )

        result = runner.invoke(
            app,
            ["env", "create", "--code", "duplicate-env", "--name", "Second", "--for-type", "kimi"],
        )

        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_create_invalid_code_fails(self):
        """Test creating with invalid code fails."""
        result = runner.invoke(
            app, ["env", "create", "--code", "Invalid_Code", "--name", "Test", "--for-type", "kimi"]
        )

        assert result.exit_code != 0
        assert "Invalid code" in result.output

    def test_create_invalid_type_fails(self):
        """Test creating with invalid type fails."""
        result = runner.invoke(
            app, ["env", "create", "--code", "test", "--name", "Test", "--for-type", "invalid"]
        )

        assert result.exit_code != 0
        assert "Invalid type" in result.output

    def test_create_from_existing(self):
        """Test creating from existing env config."""
        runner.invoke(
            app, ["env", "create", "--code", "source-env", "--name", "Source", "--for-type", "kimi"]
        )

        result = runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "copied-env",
                "--name",
                "Copied",
                "--for-type",
                "kimi",
                "--from",
                "source-env",
            ],
        )

        assert result.exit_code == 0
        assert "created from" in result.output

    def test_create_from_nonexistent_fails(self):
        """Test creating from nonexistent env fails."""
        result = runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "new-env",
                "--name",
                "New",
                "--for-type",
                "kimi",
                "--from",
                "nonexistent",
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output


class TestEnvList(TestIsolator):
    """Test env list command."""

    def test_list_empty(self):
        """Test listing when no env configs exist."""
        result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        assert "No env configs found" in result.output

    def test_list_with_envs(self):
        """Test listing env configs."""
        for i in range(3):
            runner.invoke(
                app,
                [
                    "env",
                    "create",
                    "--code",
                    f"env-{i}",
                    "--name",
                    f"Environment {i}",
                    "--for-type",
                    "kimi",
                ],
            )

        result = runner.invoke(app, ["env", "list"])

        assert result.exit_code == 0
        for i in range(3):
            assert f"env-{i}" in result.output
            assert f"Environment {i}" in result.output

    def test_list_filter_by_type(self):
        """Test listing with type filter."""
        runner.invoke(
            app, ["env", "create", "--code", "kimi-env", "--name", "Kimi Env", "--for-type", "kimi"]
        )

        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "claude-env",
                "--name",
                "Claude Env",
                "--for-type",
                "claude",
            ],
        )

        result = runner.invoke(app, ["env", "list", "--for-type", "kimi"])

        assert result.exit_code == 0
        assert "kimi-env" in result.output
        assert "claude-env" not in result.output


class TestEnvShow(TestIsolator):
    """Test env show command."""

    def test_show_existing(self):
        """Test showing existing env config."""
        runner.invoke(
            app,
            ["env", "create", "--code", "show-test", "--name", "Show Test", "--for-type", "kimi"],
        )

        result = runner.invoke(app, ["env", "show", "show-test"])

        assert result.exit_code == 0
        assert "show-test" in result.output
        assert "Show Test" in result.output

    def test_show_nonexistent(self):
        """Test showing nonexistent env config."""
        result = runner.invoke(app, ["env", "show", "nonexistent"])

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_show_json_format(self):
        """Test showing in JSON format."""
        runner.invoke(
            app,
            ["env", "create", "--code", "json-env", "--name", "JSON Test", "--for-type", "kimi"],
        )

        result = runner.invoke(app, ["env", "show", "json-env", "--format", "json"])

        assert result.exit_code == 0
        assert '"code": "json-env"' in result.output or '"json-env"' in result.output


class TestEnvUpdate(TestIsolator):
    """Test env update command."""

    def test_update_name(self):
        """Test updating name."""
        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "update-test",
                "--name",
                "Original Name",
                "--for-type",
                "kimi",
            ],
        )

        result = runner.invoke(app, ["env", "update", "update-test", "--name", "Updated Name"])

        assert result.exit_code == 0
        assert "updated" in result.output

        result = runner.invoke(app, ["env", "show", "update-test"])
        assert "Updated Name" in result.output

    def test_update_override_existing(self):
        """Test updating override_existing."""
        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "override-test",
                "--name",
                "Override Test",
                "--for-type",
                "kimi",
            ],
        )

        result = runner.invoke(app, ["env", "update", "override-test", "--override-existing"])

        assert result.exit_code == 0
        assert "updated" in result.output

    def test_update_no_changes(self):
        """Test update with no changes."""
        runner.invoke(
            app,
            ["env", "create", "--code", "no-change", "--name", "No Change", "--for-type", "kimi"],
        )

        result = runner.invoke(app, ["env", "update", "no-change"])

        assert result.exit_code == 0
        assert "No changes" in result.output


class TestEnvDelete(TestIsolator):
    """Test env delete command."""

    def test_delete_existing(self):
        """Test deleting existing env config."""
        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "delete-test",
                "--name",
                "Delete Test",
                "--for-type",
                "kimi",
            ],
        )

        result = runner.invoke(app, ["env", "delete", "delete-test", "--force"])

        assert result.exit_code == 0
        assert "deleted" in result.output.lower()

        result = runner.invoke(app, ["env", "show", "delete-test"])
        assert result.exit_code != 0

    def test_delete_nonexistent(self):
        """Test deleting nonexistent env config."""
        result = runner.invoke(app, ["env", "delete", "nonexistent", "--force"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestEnvValidate(TestIsolator):
    """Test env validate command."""

    def test_validate_valid(self):
        """Test validating valid env config."""
        runner.invoke(
            app,
            ["env", "create", "--code", "valid-env", "--name", "Valid Env", "--for-type", "kimi"],
        )

        result = runner.invoke(app, ["env", "validate", "valid-env"])

        assert result.exit_code == 0
        assert "is valid" in result.output

    def test_validate_nonexistent(self):
        """Test validating nonexistent env config."""
        result = runner.invoke(app, ["env", "validate", "nonexistent"])

        assert result.exit_code != 0
        assert "not found" in result.output


class TestEnvSet(TestIsolator):
    """Test env set command."""

    def test_set_variable(self):
        """Test setting plain variable."""
        runner.invoke(
            app, ["env", "create", "--code", "set-test", "--name", "Set Test", "--for-type", "kimi"]
        )

        result = runner.invoke(
            app, ["env", "set", "set-test", "--key", "MY_VAR", "--value", "my_value"]
        )

        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "Variable 'MY_VAR' set" in clean
        assert "my_value" in clean

    def test_set_secret_env_source(self, monkeypatch):
        """Test setting secret with env source."""
        monkeypatch.setenv("SOURCE_KEY", "secret_value")

        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "secret-env-test",
                "--name",
                "Secret Env Test",
                "--for-type",
                "kimi",
            ],
        )

        result = runner.invoke(
            app,
            [
                "env",
                "set",
                "secret-env-test",
                "--key",
                "API_KEY",
                "--secret",
                "--source",
                "env",
                "--source-key",
                "SOURCE_KEY",
            ],
        )

        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "Secret 'API_KEY' set" in clean

    def test_set_secret_file_source(self, tmp_path):
        """Test setting secret with file source."""
        key_file = tmp_path / "key.txt"
        key_file.write_text("file_secret")

        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "secret-file-test",
                "--name",
                "Secret File Test",
                "--for-type",
                "kimi",
            ],
        )

        result = runner.invoke(
            app,
            [
                "env",
                "set",
                "secret-file-test",
                "--key",
                "API_KEY",
                "--secret",
                "--source",
                "file",
                "--source-path",
                str(key_file),
            ],
        )

        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "Secret 'API_KEY' set" in clean

    def test_set_secret_missing_source_field(self):
        """Test setting secret without required source field."""
        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "secret-missing",
                "--name",
                "Secret Missing",
                "--for-type",
                "kimi",
            ],
        )

        result = runner.invoke(
            app,
            [
                "env",
                "set",
                "secret-missing",
                "--key",
                "API_KEY",
                "--secret",
                "--source",
                "env",
                # Missing --source-key and --value
            ],
        )

        assert result.exit_code != 0
        # Should fail due to missing source-key or value
        assert result.exit_code == 1


class TestEnvUnset(TestIsolator):
    """Test env unset command."""

    def test_unset_variable(self):
        """Test unsetting variable."""
        runner.invoke(
            app,
            ["env", "create", "--code", "unset-test", "--name", "Unset Test", "--for-type", "kimi"],
        )
        runner.invoke(app, ["env", "set", "unset-test", "--key", "TO_REMOVE", "--value", "value"])

        result = runner.invoke(app, ["env", "unset", "unset-test", "--key", "TO_REMOVE"])

        assert result.exit_code == 0
        assert "removed" in result.output

    def test_unset_nonexistent(self):
        """Test unsetting nonexistent variable."""
        runner.invoke(
            app,
            ["env", "create", "--code", "unset-none", "--name", "Unset None", "--for-type", "kimi"],
        )

        result = runner.invoke(app, ["env", "unset", "unset-none", "--key", "NONEXISTENT"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestEnvGet(TestIsolator):
    """Test env get command."""

    def test_get_variable(self):
        """Test getting plain variable."""
        runner.invoke(
            app, ["env", "create", "--code", "get-test", "--name", "Get Test", "--for-type", "kimi"]
        )
        runner.invoke(app, ["env", "set", "get-test", "--key", "MY_VAR", "--value", "my_value"])

        result = runner.invoke(app, ["env", "get", "get-test", "--key", "MY_VAR"])

        assert result.exit_code == 0
        assert "my_value" in result.output

    def test_get_secret_masked(self):
        """Test getting secret shows masked value."""
        runner.invoke(
            app,
            ["env", "create", "--code", "get-secret", "--name", "Get Secret", "--for-type", "kimi"],
        )
        runner.invoke(
            app,
            [
                "env",
                "set",
                "get-secret",
                "--key",
                "API_KEY",
                "--secret",
                "--source",
                "env",
                "--value",
                "SRC",  # Use --value as source-key for env
            ],
        )

        result = runner.invoke(app, ["env", "get", "get-secret", "--key", "API_KEY"])

        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "<secret:env>" in clean

    def test_get_secret_resolved(self, monkeypatch):
        """Test getting secret with --resolve."""
        monkeypatch.setenv("RESOLVE_SRC", "resolved_value")

        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "get-resolved",
                "--name",
                "Get Resolved",
                "--for-type",
                "kimi",
            ],
        )
        runner.invoke(
            app,
            [
                "env",
                "set",
                "get-resolved",
                "--key",
                "API_KEY",
                "--secret",
                "--source",
                "env",
                "--value",
                "RESOLVE_SRC",  # Use --value as source-key
            ],
        )

        result = runner.invoke(app, ["env", "get", "get-resolved", "--key", "API_KEY", "--resolve"])

        assert result.exit_code == 0
        assert "resolved_value" in result.output


class TestEnvExport(TestIsolator):
    """Test env export command."""

    def test_export_dotenv(self):
        """Test exporting as dotenv."""
        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "export-test",
                "--name",
                "Export Test",
                "--for-type",
                "kimi",
            ],
        )
        runner.invoke(app, ["env", "set", "export-test", "--key", "KEY1", "--value", "value1"])

        result = runner.invoke(app, ["env", "export", "export-test", "--format", "dotenv"])

        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "KEY1=value1" in clean

    def test_export_shell(self):
        """Test exporting as shell script."""
        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "export-shell",
                "--name",
                "Export Shell",
                "--for-type",
                "kimi",
            ],
        )
        runner.invoke(app, ["env", "set", "export-shell", "--key", "KEY1", "--value", "value1"])

        result = runner.invoke(app, ["env", "export", "export-shell", "--format", "shell"])

        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "#!/bin/bash" in clean
        assert "export KEY1=" in clean

    def test_export_json(self):
        """Test exporting as JSON."""
        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "export-json",
                "--name",
                "Export JSON",
                "--for-type",
                "kimi",
            ],
        )
        runner.invoke(app, ["env", "set", "export-json", "--key", "KEY1", "--value", "value1"])

        result = runner.invoke(app, ["env", "export", "export-json", "--format", "json"])

        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert '"KEY1": "value1"' in clean

    def test_export_to_file(self, tmp_path):
        """Test exporting to file."""
        output_file = tmp_path / "output.env"

        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "export-file",
                "--name",
                "Export File",
                "--for-type",
                "kimi",
            ],
        )
        runner.invoke(app, ["env", "set", "export-file", "--key", "KEY1", "--value", "value1"])

        result = runner.invoke(
            app,
            ["env", "export", "export-file", "--format", "dotenv", "--output", str(output_file)],
        )

        assert result.exit_code == 0
        assert "Exported to" in result.output
        assert output_file.exists()
        assert "KEY1=value1" in output_file.read_text()

    def test_export_resolve_secrets(self, monkeypatch):
        """Test exporting with resolved secrets."""
        monkeypatch.setenv("SECRET_SRC", "my_secret_value")

        runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "export-secret",
                "--name",
                "Export Secret",
                "--for-type",
                "kimi",
            ],
        )
        runner.invoke(
            app,
            [
                "env",
                "set",
                "export-secret",
                "--key",
                "SECRET_KEY",
                "--secret",
                "--source",
                "env",
                "--value",
                "SECRET_SRC",  # Use --value as source-key
            ],
        )

        result = runner.invoke(
            app, ["env", "export", "export-secret", "--format", "dotenv", "--resolve-secrets"]
        )

        assert result.exit_code == 0
        assert "my_secret_value" in result.output


class TestEnvLifecycle(TestIsolator):
    """Test complete env lifecycle."""

    def test_full_lifecycle(self, monkeypatch):
        """Test complete env config lifecycle."""
        monkeypatch.setenv("API_KEY_SRC", "sk-test-key")

        # Create
        result = runner.invoke(
            app,
            [
                "env",
                "create",
                "--code",
                "lifecycle-env",
                "--name",
                "Lifecycle Environment",
                "--for-type",
                "kimi",
                "--description",
                "For lifecycle testing",
            ],
        )
        assert result.exit_code == 0

        # Set variables
        result = runner.invoke(
            app, ["env", "set", "lifecycle-env", "--key", "TIMEOUT", "--value", "30"]
        )
        assert result.exit_code == 0

        # Set secret - use --value as source-key for env source
        result = runner.invoke(
            app,
            [
                "env",
                "set",
                "lifecycle-env",
                "--key",
                "API_KEY",
                "--secret",
                "--source",
                "env",
                "--value",
                "API_KEY_SRC",
            ],
        )
        assert result.exit_code == 0

        # List
        result = runner.invoke(app, ["env", "list"])
        assert result.exit_code == 0
        assert "lifecycle-env" in result.output

        # Show
        result = runner.invoke(app, ["env", "show", "lifecycle-env"])
        assert result.exit_code == 0
        assert "Lifecycle Environment" in result.output

        # Validate
        result = runner.invoke(app, ["env", "validate", "lifecycle-env"])
        assert result.exit_code == 0

        # Get (masked)
        result = runner.invoke(app, ["env", "get", "lifecycle-env", "--key", "API_KEY"])
        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "<secret:" in clean

        # Get (resolved)
        result = runner.invoke(
            app, ["env", "get", "lifecycle-env", "--key", "API_KEY", "--resolve"]
        )
        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "sk-test-key" in clean

        # Export
        result = runner.invoke(app, ["env", "export", "lifecycle-env", "--format", "dotenv"])
        assert result.exit_code == 0
        clean = strip_ansi(result.output)
        assert "TIMEOUT=30" in clean

        # Update
        result = runner.invoke(
            app, ["env", "update", "lifecycle-env", "--name", "Updated Lifecycle"]
        )
        assert result.exit_code == 0

        # Delete
        result = runner.invoke(app, ["env", "delete", "lifecycle-env", "--force"])
        assert result.exit_code == 0

        # Verify deletion
        result = runner.invoke(app, ["env", "show", "lifecycle-env"])
        assert result.exit_code != 0
