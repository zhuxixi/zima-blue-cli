# Issue #14: camelCase/snake_case 统一映射 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有 dataclass 的 YAML 键名映射从分散硬编码改为集中声明 + 自动处理，消灭死代码。

**Architecture:** 新建 `YamlSerializable` mixin + `serialize()`/`deserialize()`/`serialize_spec()`/`deserialize_spec()` 工具函数。`BaseConfig` 子类声明 `SPEC_FIELD_ALIASES` 即可，无需手写 to_dict/from_dict。嵌套类继承 `YamlSerializable` 声明 `FIELD_ALIASES`。

**Tech Stack:** Python 3.10+, dataclasses, pytest

---

## File Structure

| 文件 | 职责 |
|------|------|
| `zima/models/serialization.py` (new) | `YamlSerializable`, `serialize()`, `deserialize()`, `serialize_spec()`, `deserialize_spec()`, `omit_empty()`, `convert_to_camel_case()`, `convert_to_snake_case()` |
| `zima/models/base.py` (modify) | `BaseConfig`/`Metadata` 继承 `YamlSerializable`，删除死代码 |
| `zima/models/env.py` (modify) | `EnvConfig` 声明 `SPEC_FIELD_ALIASES` |
| `zima/models/variable.py` (modify) | `VariableConfig` 声明 `SPEC_FIELD_ALIASES` |
| `zima/models/pmg.py` (modify) | `PMGConfig` 声明 `SPEC_FIELD_ALIASES` |
| `zima/models/workflow.py` (modify) | `WorkflowConfig` 声明 `SPEC_FIELD_ALIASES` |
| `zima/models/agent.py` (modify) | `AgentConfig` 声明 `SPEC_FIELD_ALIASES` |
| `zima/models/pjob.py` (modify) | 嵌套类继承 `YamlSerializable` + 声明别名；`PJobConfig` 声明 `SPEC_FIELD_ALIASES`；`PJobSpec` 覆盖 `to_dict` 用 `omit_empty` |
| `zima/models/actions.py` (modify) | `PostExecAction`/`ActionsConfig` 继承 `YamlSerializable` + 声明别名；`ActionsConfig` 覆盖 `to_dict` 用 `omit_empty` |
| `zima/models/schedule.py` (modify) | `ScheduleConfig`/`ScheduleStage`/`ScheduleCycleType` 继承/声明别名 |
| `tests/unit/test_serialization.py` (new) | 通用序列化测试 + 所有模型 round-trip 测试 |
| `tests/unit/test_models_base.py` (modify) | 删除 `test_convert_to_*` 测试 |

---

## Task 1: serialization.py 核心模块

**Files:**
- Create: `zima/models/serialization.py`
- Test: `tests/unit/test_serialization.py`

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_serialization.py`:

```python
"""Tests for generic YAML serialization utilities."""

import pytest
from dataclasses import dataclass, field

from zima.models.serialization import (
    YamlSerializable,
    serialize,
    deserialize,
    omit_empty,
    convert_to_camel_case,
    convert_to_snake_case,
)


class TestConvertFunctions:
    def test_camel_case(self):
        assert convert_to_camel_case("snake_case") == "snakeCase"
        assert convert_to_camel_case("my_var_name") == "myVarName"
        assert convert_to_camel_case("simple") == "simple"

    def test_snake_case(self):
        assert convert_to_snake_case("camelCase") == "camel_case"
        assert convert_to_snake_case("myVarName") == "my_var_name"
        assert convert_to_snake_case("simple") == "simple"


class TestSerialize:
    def test_basic(self):
        @dataclass
        class Demo(YamlSerializable):
            FIELD_ALIASES = {"my_field": "myField"}
            my_field: str = ""
            other_field: int = 0

        obj = Demo(my_field="hello", other_field=42)
        assert obj.to_dict() == {"myField": "hello", "otherField": 42}

    def test_nested_dataclass(self):
        @dataclass
        class Inner(YamlSerializable):
            value: str = ""

        @dataclass
        class Outer(YamlSerializable):
            inner: Inner = field(default_factory=Inner)

        obj = Outer(inner=Inner(value="x"))
        assert obj.to_dict() == {"inner": {"value": "x"}}

    def test_list_of_dataclasses(self):
        @dataclass
        class Item(YamlSerializable):
            name: str = ""

        @dataclass
        class Container(YamlSerializable):
            items: list = field(default_factory=list)

        obj = Container(items=[Item(name="a"), Item(name="b")])
        assert obj.to_dict() == {"items": [{"name": "a"}, {"name": "b"}]}


class TestDeserialize:
    def test_basic(self):
        @dataclass
        class Demo(YamlSerializable):
            FIELD_ALIASES = {"my_field": "myField"}
            my_field: str = ""
            other_field: int = 0

        obj = Demo.from_dict({"myField": "hello", "otherField": 42})
        assert obj.my_field == "hello"
        assert obj.other_field == 42

    def test_nested(self):
        @dataclass
        class Inner(YamlSerializable):
            value: str = ""

        @dataclass
        class Outer(YamlSerializable):
            inner: Inner = field(default_factory=Inner)

        obj = Outer.from_dict({"inner": {"value": "x"}})
        assert obj.inner.value == "x"

    def test_defaults_on_missing(self):
        @dataclass
        class Demo(YamlSerializable):
            name: str = ""
            count: int = 5

        obj = Demo.from_dict({})
        assert obj.name == ""
        assert obj.count == 5


class TestOmitEmpty:
    def test_filters_none_empty(self):
        data = {"a": "hello", "b": None, "c": "", "d": [], "e": {}}
        assert omit_empty(data) == {"a": "hello"}

    def test_keeps_false_and_zero(self):
        assert omit_empty({"flag": False, "count": 0}) == {"flag": False, "count": 0}
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/unit/test_serialization.py -v
```

Expected: `ModuleNotFoundError: No module named 'zima.models.serialization'`

- [ ] **Step 3: Write serialization.py**

Create `zima/models/serialization.py`:

```python
"""Generic YAML serialization utilities for dataclasses."""

from __future__ import annotations

import re
from dataclasses import MISSING, fields, is_dataclass
from typing import Union, get_args, get_origin


def convert_to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split("_")
    return components[0] + "".join(x.capitalize() for x in components[1:])


def convert_to_snake_case(camel_str: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", camel_str)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _unwrap_optional(t):
    """Unwrap Optional[T] or T | None."""
    origin = get_origin(t)
    if origin is not None:
        args = get_args(t)
        if origin is Union and len(args) == 2 and type(None) in args:
            return args[0] if args[1] is type(None) else args[1]
    return t


def _is_list_of_dataclasses(t):
    """Check if type is list[T] where T is a dataclass."""
    origin = get_origin(t)
    if origin is list:
        args = get_args(t)
        return bool(args and is_dataclass(args[0]))
    return False


def _get_item_type_from_list(t):
    """Get T from list[T]."""
    args = get_args(t)
    return args[0] if args else None


BASE_CONFIG_FIELDS = {"api_version", "kind", "metadata", "created_at", "updated_at"}


class YamlSerializable:
    """Mixin for dataclasses that support YAML serialization."""

    FIELD_ALIASES: dict[str, str] = {}

    def to_dict(self) -> dict:
        return serialize(self, self.FIELD_ALIASES)

    @classmethod
    def from_dict(cls, data: dict):
        return deserialize(cls, data, cls.FIELD_ALIASES)


def serialize(obj, aliases: dict[str, str] | None = None) -> dict:
    """Serialize a dataclass instance to a dictionary."""
    if not is_dataclass(obj):
        raise TypeError(f"Expected dataclass instance, got {type(obj)}")

    result = {}
    aliases = aliases or {}

    for f in fields(obj):
        value = getattr(obj, f.name)
        yaml_key = aliases.get(f.name, convert_to_camel_case(f.name))
        if is_dataclass(value):
            result[yaml_key] = value.to_dict()
        elif isinstance(value, list):
            result[yaml_key] = [
                item.to_dict() if is_dataclass(item) else item for item in value
            ]
        else:
            result[yaml_key] = value

    return result


def deserialize(cls, data: dict, aliases: dict[str, str] | None = None):
    """Deserialize a dictionary into a dataclass instance."""
    if not is_dataclass(cls):
        raise TypeError(f"Expected dataclass type, got {type(cls)}")

    aliases = aliases or {}
    kwargs = {}
    for f in fields(cls):
        yaml_key = aliases.get(f.name, convert_to_camel_case(f.name))
        value = data.get(yaml_key)

        if value is None:
            if f.default is not MISSING:
                kwargs[f.name] = f.default
            elif f.default_factory is not MISSING:
                kwargs[f.name] = f.default_factory()
            else:
                kwargs[f.name] = None
            continue

        field_type = _unwrap_optional(f.type)
        if is_dataclass(field_type):
            kwargs[f.name] = field_type.from_dict(value)
        elif _is_list_of_dataclasses(field_type):
            item_cls = _get_item_type_from_list(field_type)
            kwargs[f.name] = [item_cls.from_dict(item) for item in value]
        else:
            kwargs[f.name] = value

    return cls(**kwargs)


def serialize_spec(obj, aliases: dict[str, str] | None = None) -> dict:
    """Serialize non-base fields into a spec dict (for BaseConfig subclasses)."""
    if not is_dataclass(obj):
        raise TypeError(f"Expected dataclass instance, got {type(obj)}")

    result = {}
    aliases = aliases or {}
    for f in fields(obj):
        if f.name in BASE_CONFIG_FIELDS:
            continue
        value = getattr(obj, f.name)
        yaml_key = aliases.get(f.name, convert_to_camel_case(f.name))
        if is_dataclass(value):
            result[yaml_key] = value.to_dict()
        elif isinstance(value, list):
            result[yaml_key] = [
                item.to_dict() if is_dataclass(item) else item for item in value
            ]
        else:
            result[yaml_key] = value

    return result


def deserialize_spec(cls, spec_data: dict, aliases: dict[str, str] | None = None) -> dict:
    """Deserialize spec fields from a dict into kwargs (for BaseConfig subclasses)."""
    if not is_dataclass(cls):
        raise TypeError(f"Expected dataclass type, got {type(cls)}")

    aliases = aliases or {}
    kwargs = {}
    for f in fields(cls):
        if f.name in BASE_CONFIG_FIELDS:
            continue
        yaml_key = aliases.get(f.name, convert_to_camel_case(f.name))
        value = spec_data.get(yaml_key)

        if value is None:
            if f.default is not MISSING:
                kwargs[f.name] = f.default
            elif f.default_factory is not MISSING:
                kwargs[f.name] = f.default_factory()
            else:
                kwargs[f.name] = None
            continue

        field_type = _unwrap_optional(f.type)
        if is_dataclass(field_type):
            kwargs[f.name] = field_type.from_dict(value)
        elif _is_list_of_dataclasses(field_type):
            item_cls = _get_item_type_from_list(field_type)
            kwargs[f.name] = [item_cls.from_dict(item) for item in value]
        else:
            kwargs[f.name] = value

    return kwargs


def omit_empty(data: dict) -> dict:
    """Remove entries whose value is None, empty string, empty list, or empty dict."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
pytest tests/unit/test_serialization.py -v
```

- [ ] **Step 5: Commit**

```bash
git add zima/models/serialization.py tests/unit/test_serialization.py
git commit -m "feat: add YamlSerializable mixin and generic serialize/deserialize utilities (#14)"
```

---

## Task 2: base.py 重构

**Files:**
- Modify: `zima/models/base.py`
- Modify: `tests/unit/test_models_base.py`

- [ ] **Step 1: Update base.py**

Replace imports at top:
```python
from zima.models.serialization import YamlSerializable
```

Replace `Metadata`:
```python
@dataclass
class Metadata(YamlSerializable):
    code: str = ""
    name: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "description": self.description}

    @classmethod
    def from_dict(cls, data: dict) -> Metadata:
        return cls(
            code=data.get("code", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
        )
```

Replace `BaseConfig`:
```python
@dataclass
class BaseConfig(YamlSerializable):
    FIELD_ALIASES = {
        "api_version": "apiVersion",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
    }

    api_version: str = "zima.io/v1"
    kind: str = ""
    metadata: Metadata = field(default_factory=Metadata)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = generate_timestamp()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        from zima.models.serialization import serialize_spec
        result = super().to_dict()
        result["spec"] = serialize_spec(self, getattr(self, "SPEC_FIELD_ALIASES", None))
        return result

    @classmethod
    def from_dict(cls, data: dict):
        from zima.models.serialization import deserialize_spec
        spec_data = data.get("spec", {})
        kwargs = {
            "api_version": data.get("apiVersion", "zima.io/v1"),
            "kind": data.get("kind", ""),
            "metadata": Metadata.from_dict(data.get("metadata", {})),
            "created_at": data.get("createdAt", ""),
            "updated_at": data.get("updatedAt", ""),
        }
        kwargs.update(deserialize_spec(cls, spec_data, getattr(cls, "SPEC_FIELD_ALIASES", None)))
        return cls(**kwargs)
```

Delete `convert_to_camel_case()` and `convert_to_snake_case()` at bottom of file.

- [ ] **Step 2: Remove old tests**

In `tests/unit/test_models_base.py`, delete `test_convert_to_camel_case` and `test_convert_to_snake_case`.

- [ ] **Step 3: Run tests**

```bash
pytest tests/unit/test_models_base.py -v
```

- [ ] **Step 4: Commit**

```bash
git add zima/models/base.py tests/unit/test_models_base.py
git commit -m "refactor: BaseConfig and Metadata use YamlSerializable with auto spec mapping (#14)"
```

---

## Task 3: 简单模型迁移

**Files:** Modify `env.py`, `variable.py`, `pmg.py`, `workflow.py`, `agent.py`

对每个文件，做以下操作：

1. 在类定义中添加 `SPEC_FIELD_ALIASES`
2. 删除手动 `to_dict()` 和 `from_dict()` 方法（保留 `from_yaml_file`）
3. 保留 `create()` 工厂方法不变
4. 保留所有业务方法不变

- [ ] **Step 1: env.py — EnvConfig**

```python
class EnvConfig(BaseConfig):
    SPEC_FIELD_ALIASES = {
        "for_type": "forType",
        "override_existing": "overrideExisting",
    }
    # ... existing fields ...
```

Delete `to_dict()` and `from_dict()` methods.

- [ ] **Step 2: variable.py — VariableConfig**

```python
class VariableConfig(BaseConfig):
    SPEC_FIELD_ALIASES = {
        "for_workflow": "forWorkflow",
    }
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 3: pmg.py — PMGConfig**

```python
class PMGConfig(BaseConfig):
    SPEC_FIELD_ALIASES = {
        "for_types": "forTypes",
    }
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 4: workflow.py — WorkflowConfig**

```python
class WorkflowConfig(BaseConfig):
    SPEC_FIELD_ALIASES = {}
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 5: agent.py — AgentConfig**

```python
class AgentConfig(BaseConfig):
    SPEC_FIELD_ALIASES = {}
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 6: Run all model tests**

```bash
pytest tests/unit/test_models_env.py tests/unit/test_models_variable.py tests/unit/test_models_pmg.py tests/unit/test_models_workflow.py tests/unit/test_models_agent.py -v
```

- [ ] **Step 7: Commit**

```bash
git add zima/models/env.py zima/models/variable.py zima/models/pmg.py zima/models/workflow.py zima/models/agent.py
git commit -m "refactor: migrate Env/Variable/PMG/Workflow/Agent configs to auto spec mapping (#14)"
```

---

## Task 4: PJob 嵌套类迁移

**Files:** Modify `zima/models/pjob.py`

- [ ] **Step 1: ExecutionOptions**

Add `YamlSerializable` import and inheritance:

```python
from zima.models.serialization import YamlSerializable, omit_empty

@dataclass
class ExecutionOptions(YamlSerializable):
    FIELD_ALIASES = {
        "work_dir": "workDir",
        "keep_temp": "keepTemp",
        "async_": "async",
    }
    # existing fields unchanged
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 2: OutputOptions**

```python
@dataclass
class OutputOptions(YamlSerializable):
    FIELD_ALIASES = {"save_to": "saveTo"}
    # existing fields unchanged
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 3: Overrides**

```python
@dataclass
class Overrides(YamlSerializable):
    FIELD_ALIASES = {
        "agent_params": "agentParams",
        "variable_values": "variableValues",
        "env_vars": "envVars",
        "pmg_params": "pmgParams",
    }
    # existing fields unchanged
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 4: PJobSpec — 条件输出**

```python
@dataclass
class PJobSpec(YamlSerializable):
    # no FIELD_ALIASES needed (field names match)
    # existing fields unchanged

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())
```

Delete old `to_dict()` and `from_dict()`.

- [ ] **Step 5: PJobMetadata**

```python
@dataclass
class PJobMetadata(Metadata):
    # inherits YamlSerializable from Metadata
    labels: list[str] = field(default_factory=list)
    annotations: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.labels:
            result["labels"] = self.labels
        if self.annotations:
            result["annotations"] = self.annotations
        return result

    @classmethod
    def from_dict(cls, data: dict) -> PJobMetadata:
        return cls(
            code=data.get("code", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            labels=data.get("labels", []),
            annotations=data.get("annotations", {}),
        )
```

- [ ] **Step 6: PJobConfig**

```python
class PJobConfig(BaseConfig):
    SPEC_FIELD_ALIASES = {}
    # existing fields unchanged
```

Delete `to_dict()` and `from_dict()` (the generic BaseConfig ones handle metadata + spec).

Wait — `PJobConfig` currently uses `PJobMetadata` not `Metadata`. The generic `BaseConfig.from_dict()` does `Metadata.from_dict(...)`. We need `PJobMetadata.from_dict(...)`.

Override in PJobConfig:

```python
    @classmethod
    def from_dict(cls, data: dict) -> PJobConfig:
        from zima.models.serialization import deserialize_spec
        spec_data = data.get("spec", {})
        kwargs = {
            "api_version": data.get("apiVersion", "zima.io/v1"),
            "kind": data.get("kind", "PJob"),
            "metadata": PJobMetadata.from_dict(data.get("metadata", {})),
            "created_at": data.get("createdAt", ""),
            "updated_at": data.get("updatedAt", ""),
        }
        kwargs.update(deserialize_spec(cls, spec_data, getattr(cls, "SPEC_FIELD_ALIASES", None)))
        return cls(**kwargs)
```

- [ ] **Step 7: Run pjob tests**

```bash
pytest tests/unit/test_models_pjob.py -v
```

- [ ] **Step 8: Commit**

```bash
git add zima/models/pjob.py
git commit -m "refactor: migrate PJob nested classes to YamlSerializable with auto mapping (#14)"
```

---

## Task 5: ActionsConfig + PostExecAction 迁移

**Files:** Modify `zima/models/actions.py`

- [ ] **Step 1: PostExecAction**

```python
from zima.models.serialization import YamlSerializable, omit_empty

@dataclass
class PostExecAction(YamlSerializable):
    FIELD_ALIASES = {
        "add_labels": "addLabels",
        "remove_labels": "removeLabels",
    }
    # existing fields unchanged

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())
```

Delete old `to_dict()` and `from_dict()`.

- [ ] **Step 2: ActionsConfig**

```python
@dataclass
class ActionsConfig(YamlSerializable):
    FIELD_ALIASES = {"post_exec": "postExec"}
    # existing fields unchanged

    def to_dict(self) -> dict:
        return omit_empty(super().to_dict())
```

Delete old `to_dict()` and `from_dict()`.

- [ ] **Step 3: Run actions tests**

```bash
pytest tests/unit/test_models_actions.py -v
```

- [ ] **Step 4: Commit**

```bash
git add zima/models/actions.py
git commit -m "refactor: migrate Actions models to YamlSerializable with auto mapping (#14)"
```

---

## Task 6: Schedule 模型迁移

**Files:** Modify `zima/models/schedule.py`

- [ ] **Step 1: ScheduleStage**

```python
from zima.models.serialization import YamlSerializable

@dataclass
class ScheduleStage(YamlSerializable):
    FIELD_ALIASES = {
        "offset_minutes": "offsetMinutes",
        "duration_minutes": "durationMinutes",
    }
    # existing fields unchanged
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 2: ScheduleCycleType**

```python
@dataclass
class ScheduleCycleType(YamlSerializable):
    FIELD_ALIASES = {"type_id": "typeId"}
    # existing fields unchanged
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 3: ScheduleConfig**

```python
class ScheduleConfig(BaseConfig):
    SPEC_FIELD_ALIASES = {
        "cycle_minutes": "cycleMinutes",
        "daily_cycles": "dailyCycles",
        "cycle_types": "cycleTypes",
        "cycle_mapping": "cycleMapping",
    }
    # existing fields unchanged
```

Delete `to_dict()` and `from_dict()`.

- [ ] **Step 4: Run schedule tests**

```bash
pytest tests/unit/test_models_schedule.py -v
```

- [ ] **Step 5: Commit**

```bash
git add zima/models/schedule.py
git commit -m "refactor: migrate Schedule models to YamlSerializable with auto mapping (#14)"
```

---

## Task 7: 全面 round-trip 测试

**Files:**
- Modify: `tests/unit/test_serialization.py`
- Test: all model test files

- [ ] **Step 1: Add round-trip tests**

Append to `tests/unit/test_serialization.py`:

```python
class TestRoundTrip:
    """Round-trip tests: from_dict(to_dict(obj)) == obj for all model classes."""

    def test_metadata(self):
        from zima.models.base import Metadata
        original = Metadata(code="test", name="Test", description="desc")
        restored = Metadata.from_dict(original.to_dict())
        assert restored == original

    def test_agent_config(self):
        from zima.models.agent import AgentConfig
        original = AgentConfig.create("test", "Test", agent_type="claude")
        restored = AgentConfig.from_dict(original.to_dict())
        assert restored == original

    def test_env_config(self):
        from zima.models.env import EnvConfig
        original = EnvConfig.create("test", "Test", for_type="kimi", override_existing=True)
        restored = EnvConfig.from_dict(original.to_dict())
        assert restored == original

    def test_variable_config(self):
        from zima.models.variable import VariableConfig
        original = VariableConfig.create("test", "Test", for_workflow="wf1", values={"k": "v"})
        restored = VariableConfig.from_dict(original.to_dict())
        assert restored == original

    def test_pmg_config(self):
        from zima.models.pmg import PMGConfig
        original = PMGConfig.create("test", "Test", for_types=["kimi"])
        restored = PMGConfig.from_dict(original.to_dict())
        assert restored == original

    def test_workflow_config(self):
        from zima.models.workflow import WorkflowConfig
        original = WorkflowConfig.create("test", "Test", template="Hello")
        restored = WorkflowConfig.from_dict(original.to_dict())
        assert restored == original

    def test_pjob_config(self):
        from zima.models.pjob import PJobConfig
        original = PJobConfig.create("test", "Test", agent="a1", workflow="w1")
        restored = PJobConfig.from_dict(original.to_dict())
        assert restored == original

    def test_pjob_with_overrides(self):
        from zima.models.pjob import PJobConfig, Overrides, ExecutionOptions
        original = PJobConfig.create(
            "test", "Test", agent="a1", workflow="w1",
            overrides={"agentParams": {"model": "sonnet"}},
            execution={"workDir": "/tmp", "timeout": 60},
        )
        restored = PJobConfig.from_dict(original.to_dict())
        assert restored == original

    def test_actions_config(self):
        from zima.models.actions import ActionsConfig, PostExecAction
        original = ActionsConfig(post_exec=[
            PostExecAction(condition="success", type="github_label", repo="o/r", add_labels=["done"])
        ])
        restored = ActionsConfig.from_dict(original.to_dict())
        assert restored == original

    def test_schedule_config(self):
        from zima.models.schedule import ScheduleConfig
        original = ScheduleConfig.create("test", "Test")
        restored = ScheduleConfig.from_dict(original.to_dict())
        assert restored == original

    def test_special_alias_async(self):
        from zima.models.pjob import ExecutionOptions
        original = ExecutionOptions(work_dir="/tmp", async_=True)
        data = original.to_dict()
        assert "async" in data
        assert "async_" not in data
        restored = ExecutionOptions.from_dict(data)
        assert restored.async_ is True
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: ALL PASS

- [ ] **Step 3: Run lint and format**

```bash
black zima/ tests/ --line-length 100
ruff check zima/ tests/
```

Fix any issues.

- [ ] **Step 4: Run full test suite**

```bash
pytest --cov=zima --cov-fail-under=60
```

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_serialization.py
git commit -m "test: add round-trip tests for all models with auto serialization (#14)"
```

---

## Self-Review Checklist

After completing all tasks, verify:

- [ ] `convert_to_camel_case` / `convert_to_snake_case` deleted from `base.py`
- [ ] All model `to_dict` / `from_dict` methods either deleted or use `YamlSerializable`
- [ ] No hardcoded camelCase strings remain in model files (except template/examples)
- [ ] All round-trip tests pass
- [ ] Coverage ≥ 60%
- [ ] No ruff errors
- [ ] Black formatting applied

## Spec Coverage Check

| Spec Section | Implementing Task |
|--------------|-------------------|
| YamlSerializable mixin | Task 1 |
| serialize() / deserialize() | Task 1 |
| serialize_spec() / deserialize_spec() | Task 1 |
| omit_empty() | Task 1 |
| BaseConfig + Metadata | Task 2 |
| EnvConfig / VariableConfig / PMGConfig | Task 3 |
| WorkflowConfig / AgentConfig | Task 3 |
| ExecutionOptions / OutputOptions / Overrides | Task 4 |
| PJobSpec (omit_empty) | Task 4 |
| PJobMetadata / PJobConfig | Task 4 |
| PostExecAction / ActionsConfig (omit_empty) | Task 5 |
| ScheduleStage / ScheduleCycleType / ScheduleConfig | Task 6 |
| Round-trip tests | Task 7 |
| Delete dead code | Tasks 1-2 |
