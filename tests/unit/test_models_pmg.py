"""Unit tests for PMGConfig model."""

from tests.base import TestIsolator
from zima.models.pmg import ConditionEvaluator, ParameterDef, PMGConfig


class TestParameterDef(TestIsolator):
    """ParameterDef model tests."""

    class TestCreate:
        """Test ParameterDef creation."""

        def test_create_long(self):
            """Test creating long parameter."""
            param = ParameterDef(name="model", type="long", value="gpt-4")
            assert param.name == "model"
            assert param.type == "long"
            assert param.value == "gpt-4"

        def test_create_short_bool(self):
            """Test creating short boolean parameter."""
            param = ParameterDef(name="y", type="short", value=True)
            assert param.type == "short"
            assert param.value is True

        def test_create_flag(self):
            """Test creating flag parameter."""
            param = ParameterDef(name="verbose", type="flag", enabled=True)
            assert param.type == "flag"
            assert param.enabled is True

        def test_create_repeatable(self):
            """Test creating repeatable parameter."""
            param = ParameterDef(name="add-dir", type="repeatable", values=["./src", "./tests"])
            assert param.type == "repeatable"
            assert param.values == ["./src", "./tests"]

        def test_create_positional(self):
            """Test creating positional parameter."""
            param = ParameterDef(name="work-dir", type="positional", value="./workspace")
            assert param.type == "positional"
            assert param.value == "./workspace"

    class TestValidation:
        """Test parameter validation."""

        def test_validate_valid_long(self):
            """Test valid long parameter."""
            param = ParameterDef(name="model", type="long", value="gpt-4")
            errors = param.validate()
            assert errors == []

        def test_validate_missing_name(self):
            """Test missing name."""
            param = ParameterDef(name="", type="long", value="test")
            errors = param.validate()
            assert any("name is required" in e.lower() for e in errors)

        def test_validate_missing_type(self):
            """Test missing type."""
            param = ParameterDef(name="test", type="", value="test")
            errors = param.validate()
            assert any("type is required" in e.lower() for e in errors)

        def test_validate_invalid_type(self):
            """Test invalid type."""
            param = ParameterDef(name="test", type="invalid", value="test")
            errors = param.validate()
            assert any("Invalid parameter type" in e for e in errors)

        def test_validate_repeatable_missing_values(self):
            """Test repeatable without values."""
            param = ParameterDef(name="test", type="repeatable")
            errors = param.validate()
            assert any("requires 'values'" in e for e in errors)

        def test_validate_non_flag_missing_value(self):
            """Test non-flag type without value."""
            param = ParameterDef(name="test", type="long")
            errors = param.validate()
            assert any("requires 'value'" in e for e in errors)

    class TestRender:
        """Test parameter rendering."""

        def test_render_long(self):
            """Test rendering long parameter."""
            param = ParameterDef(name="model", type="long", value="gpt-4")
            assert param.render() == ["--model", "gpt-4"]

        def test_render_short_bool_true(self):
            """Test rendering short boolean (true)."""
            param = ParameterDef(name="y", type="short", value=True)
            assert param.render() == ["-y"]

        def test_render_short_bool_false(self):
            """Test rendering short boolean (false)."""
            param = ParameterDef(name="y", type="short", value=False)
            assert param.render() == []

        def test_render_short_string(self):
            """Test rendering short string."""
            param = ParameterDef(name="p", type="short", value="/path")
            assert param.render() == ["-p", "/path"]

        def test_render_flag_enabled(self):
            """Test rendering enabled flag."""
            param = ParameterDef(name="verbose", type="flag", enabled=True)
            assert param.render() == ["--verbose"]

        def test_render_flag_disabled(self):
            """Test rendering disabled flag."""
            param = ParameterDef(name="verbose", type="flag", enabled=False)
            assert param.render() == []

        def test_render_positional(self):
            """Test rendering positional."""
            param = ParameterDef(name="work-dir", type="positional", value="./workspace")
            assert param.render() == ["./workspace"]

        def test_render_repeatable(self):
            """Test rendering repeatable."""
            param = ParameterDef(name="add-dir", type="repeatable", values=["./src", "./tests"])
            assert param.render() == ["--add-dir", "./src", "--add-dir", "./tests"]

        def test_render_json_dict(self):
            """Test rendering JSON from dict."""
            import json

            param = ParameterDef(name="config", type="json", value={"key": "value"})
            result = param.render()
            assert result[0] == "--config"
            assert json.loads(result[1]) == {"key": "value"}

        def test_render_key_value(self):
            """Test rendering key-value."""
            param = ParameterDef(
                name="labels", type="key-value", value={"env": "prod", "team": "platform"}
            )
            result = param.render()
            assert result[0] == "--labels"
            assert "env=prod" in result[1]
            assert "team=platform" in result[1]


class TestConditionEvaluator(TestIsolator):
    """ConditionEvaluator tests."""

    def test_evaluate_empty(self):
        """Test empty expression returns True."""
        assert ConditionEvaluator.evaluate("") is True

    def test_evaluate_os_match(self, monkeypatch):
        """Test OS condition matching."""
        import platform

        current_os = platform.system().lower()
        if current_os == "windows":
            expr = "os == 'windows'"
        elif current_os == "linux":
            expr = "os == 'linux'"
        else:
            expr = "os == 'darwin'"

        assert ConditionEvaluator.evaluate(expr) is True

    def test_evaluate_os_no_match(self, monkeypatch):
        """Test OS condition not matching."""
        import platform

        current_os = platform.system().lower()
        if current_os == "windows":
            expr = "os == 'linux'"
        else:
            expr = "os == 'windows'"

        assert ConditionEvaluator.evaluate(expr) is False

    def test_evaluate_env_match(self, monkeypatch):
        """Test env variable condition matching."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        assert ConditionEvaluator.evaluate("env.TEST_VAR == 'test_value'") is True

    def test_evaluate_and(self, monkeypatch):
        """Test AND condition."""
        monkeypatch.setenv("CI", "true")
        result = ConditionEvaluator.evaluate("env.CI == 'true' && os != 'invalid'")
        assert result is True

    def test_evaluate_or(self, monkeypatch):
        """Test OR condition."""
        result = ConditionEvaluator.evaluate(
            "os == 'invalid1' || os == 'invalid2' || os != 'never'"
        )
        assert result is True

    def test_evaluate_invalid_syntax(self):
        """Test invalid syntax returns False."""
        assert ConditionEvaluator.evaluate("invalid!!!") is False


class TestPMGConfig(TestIsolator):
    """PMGConfig model tests."""

    class TestCreate:
        """Test PMGConfig creation."""

        def test_create_basic(self):
            """Test creating basic PMG."""
            pmg = PMGConfig.create(code="test-pmg", name="Test PMG", for_types=["kimi"])

            assert pmg.metadata.code == "test-pmg"
            assert pmg.metadata.name == "Test PMG"
            assert pmg.for_types == ["kimi"]
            assert pmg.kind == "PMG"

        def test_create_with_all_fields(self):
            """Test creating with all fields."""
            pmg = PMGConfig.create(
                code="full-pmg",
                name="Full PMG",
                for_types=["kimi", "claude"],
                description="A test PMG",
                parameters=[{"name": "model", "type": "long", "value": "gpt-4"}],
                raw="--experimental",
                extends=[{"code": "base", "override": True}],
                conditions=[{"when": "os == 'linux'", "parameters": []}],
            )

            assert pmg.metadata.description == "A test PMG"
            assert len(pmg.parameters) == 1
            assert pmg.raw == "--experimental"
            assert len(pmg.extends) == 1
            assert len(pmg.conditions) == 1

        def test_create_with_string_extends(self):
            """Test creating with string extends."""
            pmg = PMGConfig.create(
                code="test", name="Test", for_types=["kimi"], extends=["base-pmg"]
            )

            assert len(pmg.extends) == 1
            assert pmg.extends[0].code == "base-pmg"
            assert pmg.extends[0].override is False

    class TestValidation:
        """Test PMG validation."""

        def test_validate_valid(self):
            """Test valid PMG."""
            pmg = PMGConfig.create(code="valid-pmg", name="Valid PMG", for_types=["kimi"])
            errors = pmg.validate()
            assert errors == []

        def test_validate_missing_code(self):
            """Test missing code."""
            pmg = PMGConfig()
            pmg.metadata.code = ""
            pmg.metadata.name = "Test"
            pmg.for_types = ["kimi"]
            errors = pmg.validate()
            assert any("code is required" in e for e in errors)

        def test_validate_invalid_code_format(self):
            """Test invalid code format."""
            pmg = PMGConfig.create(code="Invalid_Code", name="Test", for_types=["kimi"])
            errors = pmg.validate()
            assert any("has invalid format" in e for e in errors)

        def test_validate_missing_name(self):
            """Test missing name."""
            pmg = PMGConfig.create(code="test", name="", for_types=["kimi"])
            pmg.metadata.name = ""
            errors = pmg.validate()
            assert any("name is required" in e for e in errors)

        def test_validate_missing_for_types(self):
            """Test missing for_types."""
            pmg = PMGConfig.create(code="test", name="Test", for_types=["kimi"])
            pmg.for_types = []
            errors = pmg.validate()
            assert any("forTypes is required" in e for e in errors)

        def test_validate_invalid_for_type(self):
            """Test invalid for_type."""
            pmg = PMGConfig.create(code="test", name="Test", for_types=["invalid"])
            errors = pmg.validate()
            assert any("Invalid forType" in e for e in errors)

        def test_validate_duplicate_param_names(self):
            """Test duplicate parameter names."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                parameters=[
                    {"name": "model", "type": "long", "value": "gpt-4"},
                    {"name": "model", "type": "long", "value": "claude"},
                ],
            )
            errors = pmg.validate()
            assert any("Duplicate parameter name" in e for e in errors)

    class TestDictConversion:
        """Test dictionary conversion."""

        def test_to_dict(self):
            """Test to_dict method."""
            pmg = PMGConfig.create(
                code="dict-test",
                name="Dict Test",
                for_types=["kimi"],
                parameters=[{"name": "verbose", "type": "flag", "enabled": True}],
            )

            data = pmg.to_dict()
            assert data["apiVersion"] == "zima.io/v1"
            assert data["kind"] == "PMG"
            assert data["metadata"]["code"] == "dict-test"
            assert data["spec"]["forTypes"] == ["kimi"]
            assert len(data["spec"]["parameters"]) == 1

        def test_from_dict(self):
            """Test from_dict method."""
            data = {
                "apiVersion": "zima.io/v1",
                "kind": "PMG",
                "metadata": {"code": "from-dict", "name": "From Dict"},
                "spec": {
                    "forTypes": ["claude"],
                    "parameters": [{"name": "model", "type": "long", "value": "claude-3"}],
                    "raw": "--test",
                    "extends": [{"code": "base"}],
                },
            }

            pmg = PMGConfig.from_dict(data)
            assert pmg.metadata.code == "from-dict"
            assert pmg.for_types == ["claude"]
            assert len(pmg.parameters) == 1
            assert pmg.raw == "--test"
            assert len(pmg.extends) == 1

    class TestParameterManagement:
        """Test parameter management."""

        def test_add_parameter(self):
            """Test adding parameter."""
            pmg = PMGConfig.create(code="test", name="Test", for_types=["kimi"])

            param = ParameterDef(name="model", type="long", value="gpt-4")
            pmg.add_parameter(param)

            assert len(pmg.parameters) == 1
            assert pmg.parameters[0].name == "model"

        def test_add_parameter_replaces_existing(self):
            """Test adding parameter replaces existing with same name."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                parameters=[{"name": "model", "type": "long", "value": "old"}],
            )

            new_param = ParameterDef(name="model", type="long", value="new")
            pmg.add_parameter(new_param)

            assert len(pmg.parameters) == 1
            assert pmg.parameters[0].value == "new"

        def test_remove_parameter(self):
            """Test removing parameter."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                parameters=[{"name": "model", "type": "long", "value": "gpt-4"}],
            )

            removed = pmg.remove_parameter("model")

            assert removed is True
            assert len(pmg.parameters) == 0

        def test_remove_parameter_not_found(self):
            """Test removing nonexistent parameter."""
            pmg = PMGConfig.create(code="test", name="Test", for_types=["kimi"])

            removed = pmg.remove_parameter("nonexistent")

            assert removed is False

        def test_get_parameter(self):
            """Test getting parameter."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                parameters=[{"name": "model", "type": "long", "value": "gpt-4"}],
            )

            param = pmg.get_parameter("model")
            assert param is not None
            assert param.value == "gpt-4"

            assert pmg.get_parameter("nonexistent") is None

        def test_list_parameters(self):
            """Test listing parameters."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                parameters=[
                    {"name": "p1", "type": "flag", "enabled": True},
                    {"name": "p2", "type": "flag", "enabled": True},
                ],
            )

            names = pmg.list_parameters()
            assert names == ["p1", "p2"]

    class TestBuildCommand:
        """Test build command."""

        def test_build_basic(self):
            """Test basic build."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                parameters=[
                    {"name": "model", "type": "long", "value": "gpt-4"},
                    {"name": "verbose", "type": "flag", "enabled": True},
                ],
            )

            args = pmg.build_command()

            assert "--model" in args
            assert "gpt-4" in args
            assert "--verbose" in args

        def test_build_with_raw(self):
            """Test build with raw string."""
            pmg = PMGConfig.create(
                code="test", name="Test", for_types=["kimi"], raw="--experimental --no-color"
            )

            args = pmg.build_command()

            assert "--experimental" in args
            assert "--no-color" in args

        def test_build_with_conditions(self, monkeypatch):
            """Test build with conditions."""
            import platform

            current_os = platform.system().lower()

            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                conditions=[
                    {
                        "when": f"os == '{current_os}'",
                        "parameters": [{"name": "os-specific", "type": "flag", "enabled": True}],
                    }
                ],
            )

            args = pmg.build_command(eval_conditions=True)

            assert "--os-specific" in args

        def test_build_without_conditions(self, monkeypatch):
            """Test build without evaluating conditions."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                conditions=[
                    {
                        "when": "os == 'linux'",
                        "parameters": [{"name": "linux-only", "type": "flag", "enabled": True}],
                    }
                ],
            )

            args = pmg.build_command(eval_conditions=False)

            # Condition parameters should not be included
            assert "--linux-only" not in args

        def test_build_command_string(self):
            """Test build command string."""
            pmg = PMGConfig.create(
                code="test",
                name="Test",
                for_types=["kimi"],
                parameters=[{"name": "model", "type": "long", "value": "gpt-4"}],
            )

            cmd = pmg.build_command_string()

            assert "--model" in cmd
            assert "gpt-4" in cmd
