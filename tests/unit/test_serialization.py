"""Unit tests for serialization utilities."""

from dataclasses import dataclass, field

from zima.models.serialization import (
    YamlSerializable,
    convert_to_camel_case,
    convert_to_snake_case,
    deserialize_spec,
    omit_empty,
    serialize_spec,
)


class TestConvertFunctions:
    """Test case conversion helpers."""

    def test_camel_case(self):
        """Test convert_to_camel_case."""
        assert convert_to_camel_case("snake_case") == "snakeCase"
        assert convert_to_camel_case("api_version") == "apiVersion"
        assert convert_to_camel_case("simple") == "simple"
        assert convert_to_camel_case("a_b_c") == "aBC"
        assert convert_to_camel_case("created_at") == "createdAt"
        assert convert_to_camel_case("") == ""

    def test_snake_case(self):
        """Test convert_to_snake_case."""
        assert convert_to_snake_case("camelCase") == "camel_case"
        assert convert_to_snake_case("apiVersion") == "api_version"
        assert convert_to_snake_case("simple") == "simple"
        assert convert_to_snake_case("ABC") == "abc"
        assert convert_to_snake_case("createdAt") == "created_at"
        assert convert_to_snake_case("") == ""


@dataclass
class InnerItem(YamlSerializable):
    """Simple inner dataclass for testing."""

    item_name: str = ""
    item_value: int = 0


@dataclass
class OuterItem(YamlSerializable):
    """Outer dataclass with nested and list fields."""

    my_name: str = ""
    inner_obj: InnerItem = field(default_factory=InnerItem)
    inner_list: list[InnerItem] = field(default_factory=list)


@dataclass
class AliasItem(YamlSerializable):
    """Dataclass with explicit field aliases."""

    FIELD_ALIASES = {"special_field": "customKey"}

    normal_field: str = ""
    special_field: str = ""


class TestSerialize:
    """Test serialize function."""

    def test_basic(self):
        """Test basic serialization with alias override."""
        item = AliasItem(normal_field="hello", special_field="world")
        result = item.to_dict()

        assert result["normalField"] == "hello"
        assert result["customKey"] == "world"

    def test_nested_dataclass(self):
        """Test nested object recursive serialization."""
        outer = OuterItem(
            my_name="outer",
            inner_obj=InnerItem(item_name="inner", item_value=42),
        )
        result = outer.to_dict()

        assert result["myName"] == "outer"
        assert result["innerObj"] == {"itemName": "inner", "itemValue": 42}

    def test_list_of_dataclasses(self):
        """Test list of objects recursive serialization."""
        outer = OuterItem(
            my_name="outer",
            inner_list=[
                InnerItem(item_name="a", item_value=1),
                InnerItem(item_name="b", item_value=2),
            ],
        )
        result = outer.to_dict()

        assert result["myName"] == "outer"
        assert result["innerList"] == [
            {"itemName": "a", "itemValue": 1},
            {"itemName": "b", "itemValue": 2},
        ]


class TestDeserialize:
    """Test deserialize function."""

    def test_basic(self):
        """Test basic deserialization with alias override."""
        data = {"normalField": "hello", "customKey": "world"}
        item = AliasItem.from_dict(data)

        assert item.normal_field == "hello"
        assert item.special_field == "world"

    def test_nested(self):
        """Test nested object recursive deserialization."""
        data = {
            "myName": "outer",
            "innerObj": {"itemName": "inner", "itemValue": 42},
            "innerList": [],
        }
        outer = OuterItem.from_dict(data)

        assert outer.my_name == "outer"
        assert outer.inner_obj.item_name == "inner"
        assert outer.inner_obj.item_value == 42

    def test_defaults_on_missing(self):
        """Test missing fields use defaults."""
        data = {"myName": "partial"}
        outer = OuterItem.from_dict(data)

        assert outer.my_name == "partial"
        assert outer.inner_obj == InnerItem()
        assert outer.inner_list == []

    def test_list_of_dataclasses(self):
        """Test list of objects recursive deserialization."""
        data = {
            "myName": "outer",
            "innerObj": {"itemName": "", "itemValue": 0},
            "innerList": [
                {"itemName": "a", "itemValue": 1},
                {"itemName": "b", "itemValue": 2},
            ],
        }
        outer = OuterItem.from_dict(data)

        assert len(outer.inner_list) == 2
        assert outer.inner_list[0].item_name == "a"
        assert outer.inner_list[1].item_value == 2


class TestOmitEmpty:
    """Test omit_empty function."""

    def test_filters_none_empty(self):
        """Test filtering None, '', [], {}."""
        data = {
            "a": None,
            "b": "",
            "c": [],
            "d": {},
            "e": "keep",
        }
        result = omit_empty(data)
        assert result == {"e": "keep"}

    def test_keeps_false_and_zero(self):
        """Test keeping False and 0."""
        data = {
            "a": False,
            "b": 0,
            "c": None,
            "d": "",
        }
        result = omit_empty(data)
        assert result == {"a": False, "b": 0}


@dataclass
class SpecModel(YamlSerializable):
    """Model with BaseConfig-like fields for spec testing."""

    api_version: str = "zima.io/v1"
    kind: str = "Test"
    metadata: str = "meta"
    created_at: str = "now"
    updated_at: str = "then"
    spec_field_one: str = ""
    spec_field_two: int = 0


class TestSerializeSpec:
    """Test serialize_spec function."""

    def test_skips_base_fields(self):
        """Test that BASE_CONFIG_FIELDS are excluded from spec."""
        obj = SpecModel(spec_field_one="hello", spec_field_two=42)
        result = serialize_spec(obj)

        assert "apiVersion" not in result
        assert "kind" not in result
        assert "metadata" not in result
        assert "createdAt" not in result
        assert "updatedAt" not in result
        assert result["specFieldOne"] == "hello"
        assert result["specFieldTwo"] == 42


class TestDeserializeSpec:
    """Test deserialize_spec function."""

    def test_skips_base_fields(self):
        """Test that BASE_CONFIG_FIELDS are excluded from deserialization."""
        spec_data = {"specFieldOne": "hello", "specFieldTwo": 42}
        kwargs = deserialize_spec(SpecModel, spec_data)

        assert "api_version" not in kwargs
        assert "kind" not in kwargs
        assert kwargs["spec_field_one"] == "hello"
        assert kwargs["spec_field_two"] == 42

    def test_uses_defaults_for_missing(self):
        """Test missing spec fields use defaults."""
        spec_data = {"specFieldOne": "hello"}
        kwargs = deserialize_spec(SpecModel, spec_data)

        assert kwargs["spec_field_one"] == "hello"
        assert kwargs["spec_field_two"] == 0


class TestRoundTrip:
    """Round-trip tests for all model classes."""

    def test_metadata(self):
        from zima.models.base import Metadata

        original = Metadata(code="test", name="Test", description="desc")
        assert Metadata.from_dict(original.to_dict()) == original

    def test_agent_config(self):
        from zima.models.agent import AgentConfig

        original = AgentConfig.create("test", "Test", agent_type="claude")
        assert AgentConfig.from_dict(original.to_dict()) == original

    def test_env_config(self):
        from zima.models.env import EnvConfig

        original = EnvConfig.create("test", "Test", for_type="kimi", override_existing=True)
        assert EnvConfig.from_dict(original.to_dict()) == original

    def test_variable_config(self):
        from zima.models.variable import VariableConfig

        original = VariableConfig.create("test", "Test", for_workflow="wf1", values={"k": "v"})
        assert VariableConfig.from_dict(original.to_dict()) == original

    def test_pmg_config(self):
        from zima.models.pmg import PMGConfig

        original = PMGConfig.create("test", "Test", for_types=["kimi"])
        assert PMGConfig.from_dict(original.to_dict()) == original

    def test_workflow_config(self):
        from zima.models.workflow import WorkflowConfig

        original = WorkflowConfig.create("test", "Test", template="Hello")
        assert WorkflowConfig.from_dict(original.to_dict()) == original

    def test_pjob_config(self):
        from zima.models.pjob import PJobConfig

        original = PJobConfig.create("test", "Test", agent="a1", workflow="w1")
        assert PJobConfig.from_dict(original.to_dict()) == original

    def test_pjob_with_nested_objects(self):
        from zima.models.pjob import PJobConfig

        original = PJobConfig.create(
            "test",
            "Test",
            agent="a1",
            workflow="w1",
            overrides={"agentParams": {"model": "sonnet"}},
            execution={"workDir": "/tmp", "timeout": 60},
        )
        assert PJobConfig.from_dict(original.to_dict()) == original

    def test_actions_config(self):
        from zima.models.actions import ActionsConfig, PostExecAction

        original = ActionsConfig(
            post_exec=[
                PostExecAction(
                    condition="success", type="github_label", repo="o/r", add_labels=["done"]
                )
            ]
        )
        assert ActionsConfig.from_dict(original.to_dict()) == original

    def test_schedule_config(self):
        from zima.models.schedule import ScheduleConfig

        original = ScheduleConfig.create("test", "Test")
        assert ScheduleConfig.from_dict(original.to_dict()) == original

    def test_special_alias_async(self):
        from zima.models.pjob import ExecutionOptions

        original = ExecutionOptions(work_dir="/tmp", async_=True)
        data = original.to_dict()
        assert "async" in data
        assert "async_" not in data
        restored = ExecutionOptions.from_dict(data)
        assert restored.async_ is True
