# Issue #14: 配置字段 camelCase/snake_case 统一映射 — 设计方案

## 背景

当前代码中，YAML 配置使用 camelCase（如 `apiVersion`、`workDir`、`saveTo`），Python dataclass 模型使用 snake_case（如 `api_version`、`work_dir`、`save_to`）。每个模型在 `to_dict()`/`from_dict()` 中手动维护键名映射，共涉及约 25 处分散在 8 个文件中的硬编码。

`base.py` 中已实现的 `convert_to_camel_case()` / `convert_to_snake_case()` 从未被调用，属于死代码。

## 目标

1. 将所有 dataclass（顶层模型 + 嵌套类）的键名映射从分散硬编码改为**集中声明 + 自动处理**
2. 激活 `convert_to_camel_case()` / `convert_to_snake_case()`，消灭死代码
3. 保证 round-trip 一致性：`from_dict(to_dict(obj)) == obj`
4. 不破坏现有 YAML 输出格式（键名、结构不变）

## 架构

### 新建模块：`zima/models/serialization.py`

提供通用序列化/反序列化 API，所有 dataclass 复用。

```python
# 核心 API
serialize(obj, aliases=None) -> dict
deserialize(cls, data, aliases=None) -> T
omit_empty(data: dict) -> dict
```

### `YamlSerializable` mixin

所有需要 YAML 序列化的 dataclass（包括不继承 `BaseConfig` 的嵌套类）统一使用此 mixin：

```python
class YamlSerializable:
    FIELD_ALIASES: dict[str, str] = {}

    def to_dict(self) -> dict:
        return serialize(self, self.FIELD_ALIASES)

    @classmethod
    def from_dict(cls, data: dict):
        return deserialize(cls, data, cls.FIELD_ALIASES)
```

### `BaseConfig` 增强

```python
class BaseConfig(YamlSerializable):
    FIELD_ALIASES = {
        "api_version": "apiVersion",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
    }
```

`Metadata` 也继承 `YamlSerializable`（字段名一致，`FIELD_ALIASES` 为空）：

```python
@dataclass
class Metadata(YamlSerializable):
    code: str = ""
    name: str = ""
    description: str = ""
```

### 嵌套对象自动递归

`serialize()` 自动检测字段类型：
- 字段值是 dataclass → 递归调用 `value.to_dict()`
- 字段值是 `list[dataclass]` → 递归序列化每个元素
- 普通字段 → 直接取值

`deserialize()` 自动检测字段类型注解：
- 字段类型是 dataclass → 递归调用 `cls.from_dict(value)`
- 字段类型是 `list[T]` 且 T 是 dataclass → 递归反序列化
- 普通字段 → 直接取值

### 条件输出处理

默认序列化输出所有字段。需要条件输出（空值 omit）的类覆盖 `to_dict()`：

```python
def to_dict(self) -> dict:
    return omit_empty(serialize(self, self.FIELD_ALIASES))
```

需要覆盖的类共 3 个：
- `PJobSpec` — `overrides`/`execution`/`hooks`/`output`/`actions` 空时 omit
- `PostExecAction` — `body`/`repo`/`issue`/`addLabels`/`removeLabels` 空时 omit
- `ActionsConfig` — `postExec` 空时 omit

其余所有类使用默认 `BaseConfig.to_dict()`。

## 各模型 FIELD_ALIASES 映射表

### 继承 BaseConfig 的顶层模型

| 类 | 额外映射 |
|----|----------|
| `EnvConfig` | `for_type` → `forType`, `override_existing` → `overrideExisting` |
| `PMGConfig` | `for_types` → `forTypes` |
| `VariableConfig` | `for_workflow` → `forWorkflow` |
| `WorkflowConfig` | 无（字段名一致） |
| `ScheduleConfig` | `cycle_minutes` → `cycleMinutes`, `daily_cycles` → `dailyCycles`, `cycle_types` → `cycleTypes`, `cycle_mapping` → `cycleMapping` |
| `PJobConfig` | 无（映射在嵌套类中） |
| `AgentConfig` | 无（字段名一致） |

### 不继承 BaseConfig 的嵌套模型（均继承 YamlSerializable）

| 类 | 映射 |
|----|------|
| `ExecutionOptions` | `work_dir` → `workDir`, `keep_temp` → `keepTemp`, `async_` → `async` |
| `OutputOptions` | `save_to` → `saveTo` |
| `Overrides` | `agent_params` → `agentParams`, `variable_values` → `variableValues`, `env_vars` → `envVars`, `pmg_params` → `pmgParams` |
| `PostExecAction` | `add_labels` → `addLabels`, `remove_labels` → `removeLabels` |
| `ActionsConfig` | `post_exec` → `postExec` |
| `ScheduleStage` | `offset_minutes` → `offsetMinutes`, `duration_minutes` → `durationMinutes` |
| `ScheduleCycleType` | `type_id` → `typeId` |
| `PJobMetadata` | 无（继承 Metadata，labels/annotations 无映射） |
| `PJobSpec` | 无（字段名一致） |
| `Metadata` | 无（字段名一致） |

### 映射统计

- **显式声明**（`FIELD_ALIASES`）：23 个映射
- **特殊映射**（非简单 snake→camel）：1 个（`async_` → `async`）
- **自动推断**（`snake_to_camel` 自动处理）：约 30+ 个字段无需声明

## 删除的代码

### 死代码删除

- `base.py` 中的 `convert_to_camel_case()` / `convert_to_snake_case()` 函数 → 迁移到 `serialization.py`
- 各模型文件中约 500 行手动 `to_dict()`/`from_dict()` 映射代码 → 替换为 `FIELD_ALIASES` 声明 + 调用 `serialize()`/`deserialize()`

### 测试迁移

- `tests/unit/test_models_base.py` 中的 `test_convert_to_camel_case` / `test_convert_to_snake_case` → 迁移到 `tests/unit/test_serialization.py`
- 删除模型文件中的孤立测试（如果有）

## 测试策略

### 新测试文件：`tests/unit/test_serialization.py`

| 测试 | 内容 |
|------|------|
| `test_serialize_basic` | 基本序列化：键名自动转换 + 别名覆盖 |
| `test_deserialize_basic` | 基本反序列化：键名反向映射 + 默认值填充 |
| `test_serialize_nested` | 嵌套对象递归序列化 |
| `test_deserialize_nested` | 嵌套对象递归反序列化 |
| `test_omit_empty` | 空值过滤功能 |
| `test_round_trip_all_models` | 所有模型类的 `from_dict(to_dict(obj)) == obj` |
| `test_special_alias_async` | `async_` → `async` 特殊映射 |

### round-trip 覆盖的模型

- `BaseConfig`
- `Metadata` / `PJobMetadata`
- `AgentConfig`
- `EnvConfig`
- `VariableConfig`
- `PMGConfig`
- `WorkflowConfig`
- `PJobConfig`（含所有嵌套对象）
- `ActionsConfig` / `PostExecAction`
- `ScheduleConfig`（含 `ScheduleStage`、`ScheduleCycleType`）

## 向后兼容

当前 Zima 仅作者个人使用且尚未正式启用，不强制要求 YAML 输出格式完全一致。设计保证：

- **键名完全一致**：所有 YAML 键名与当前手动映射相同
- **条件输出差异**：此前部分字段（如 `labels`、`annotations`、`description`）在空值时被 omit，现在会显式写出空值。这不影响反序列化（`from_dict` 会正确处理默认值）
- **现有 YAML 可读**：`~/.zima/configs/` 下的现有文件正常读取

若未来需要恢复严格的条件输出，可扩展 `omit_empty` 的字段白名单机制。

## 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 自动序列化引入嵌套递归 bug | 所有模型类均有 round-trip 测试覆盖 |
| 条件输出覆盖遗漏导致 YAML 膨胀 | 仅 3 个类使用 `omit_empty`，范围可控 |
| `convert_to_camel_case` 边缘 case（如连续大写） | 保留现有实现，行为不变；补充单元测试 |
| `__post_init__` 与自动反序列化冲突 | `deserialize()` 通过 `cls(**kwargs)` 构造，触发 `__post_init__`；验证 timestamp 行为正确 |

## 文件变更清单

### 新增
- `zima/models/serialization.py` — 通用序列化模块
- `tests/unit/test_serialization.py` — 序列化单元测试

### 修改
- `zima/models/base.py` — `BaseConfig` 增强，删除死代码
- `zima/models/env.py` — `EnvConfig` 添加 `FIELD_ALIASES`
- `zima/models/pmg.py` — `PMGConfig` 添加 `FIELD_ALIASES`
- `zima/models/variable.py` — `VariableConfig` 添加 `FIELD_ALIASES`
- `zima/models/workflow.py` — `WorkflowConfig` 使用默认序列化
- `zima/models/pjob.py` — `ExecutionOptions`/`OutputOptions`/`Overrides`/`PJobSpec` 添加映射
- `zima/models/actions.py` — `PostExecAction`/`ActionsConfig` 添加映射
- `zima/models/schedule.py` — `ScheduleConfig`/`ScheduleStage`/`ScheduleCycleType` 添加映射
- `tests/unit/test_models_base.py` — 迁移 `convert_to_*` 测试
