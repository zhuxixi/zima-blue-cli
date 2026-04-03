# PMG (Parameters Group) 设计文档
> ⚠️ 本文档写于实现前，部分内容可能已与代码不一致。最新状态请参考代码和 `docs/API-INTERFACE.md`。

> PMG 定义命令行参数组，用于为 Agent 启动时拼接命令行参数。

---

## 📋 目录

1. [概述](#1-概述)
2. [核心概念](#2-核心概念)
3. [Schema 定义](#3-schema-定义)
4. [参数类型详解](#4-参数类型详解)
5. [继承与条件](#5-继承与条件)
6. [CLI 命令设计](#6-cli-命令设计)
7. [使用示例](#7-使用示例)
8. [测试方案](#8-测试方案)
9. [实现阶段](#9-实现阶段)

---

## 1. 概述

### 1.1 什么是 PMG

PMG 是 **Parameters Group（参数组）**，定义了启动 Agent 时需要拼接的命令行参数。它：

- 支持 **多种参数类型**：长格式、短格式、标志、位置参数、可重复参数、JSON 参数
- 支持 **参数继承**：可以继承其他 PMG 并覆盖/扩展参数
- 支持 **条件参数**：根据环境条件（OS、环境变量）动态添加参数
- 与 **Agent 类型** 关联：每个 PMG 适用于特定的 Agent 类型

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **类型丰富** | 支持各种 CLI 工具的参数形式 |
| **可组合性** | 通过继承机制复用和扩展参数组 |
| **环境感知** | 根据运行环境动态调整参数 |
| **类型安全** | 每种参数类型有明确的格式规则 |

### 1.3 文件位置

```
~/.zima/configs/pmgs/{code}.yaml
```

---

## 2. 核心概念

### 2.1 PMG 使用流程

```
创建 PMG 配置
    ├─ 定义基础参数（模型、目录等）
    ├─ 定义标志参数（yolo、verbose 等）
    └─ 可选：继承其他 PMG
            ↓
关联到 Agent
    └─ agent.defaults.pmg = pmg-code
            ↓
启动 Agent 时
    ├─ 加载 PMG 配置
    ├─ 解析继承链，合并参数
    ├─ 评估条件参数
    ├─ 按类型构建命令行参数
    └─ 拼接到 Agent 启动命令
```

### 2.2 参数类型概览

```
┌─────────────┬─────────────────────┬─────────────────────────────┐
│ 类型        │ 示例                │ 说明                        │
├─────────────┼─────────────────────┼─────────────────────────────┤
│ long        │ --model gpt-4       │ 长格式参数                  │
│ short       │ -y                  │ 短格式参数                  │
│ flag        │ --verbose           │ 开关标志（无值）            │
│ positional  │ ./workspace         │ 位置参数                    │
│ repeatable  │ --add-dir src       │ 可重复使用的参数            │
│ json        │ --config '{...}'    │ JSON 值参数                 │
│ key-value   │ --labels a=1,b=2    │ 逗号分隔的键值对            │
└─────────────┴─────────────────────┴─────────────────────────────┘
```

---

## 3. Schema 定义

### 3.1 完整结构

```yaml
apiVersion: zima.io/v1
kind: PMG
metadata:
  code: kimi-default-pmg           # 唯一编码
  name: Kimi 默认参数组             # 显示名称
  description: Kimi CLI 的默认启动参数
createdAt: "2026-03-25T10:00:00Z"
updatedAt: "2026-03-25T10:00:00Z"
spec:
  # 适用的 Agent 类型（可多个）
  forTypes:
    - kimi
  
  # 参数列表
  parameters:
    # 长格式参数
    - name: model
      type: long
      value: "kimi-k2-072515-preview"
    
    - name: max-steps-per-turn
      type: long
      value: "50"
    
    - name: max-ralph-iterations
      type: long
      value: "10"
    
    # 短格式参数
    - name: y
      type: short
      value: true           # boolean 类型只渲染标志
    
    # 标志参数（无值）
    - name: verbose
      type: flag
      enabled: true
    
    - name: quiet
      type: flag
      enabled: false        # 禁用，不会渲染
    
    # 位置参数
    - name: work-dir
      type: positional
      value: "./workspace"
    
    # 可重复参数
    - name: add-dir
      type: repeatable
      values:
        - "./src"
        - "./tests"
        - "./docs"
    
    # JSON 参数
    - name: mcp-servers
      type: json
      value: |
        {
          "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
          }
        }
    
    # 键值对参数
    - name: labels
      type: key-value
      value:
        env: production
        team: platform
  
  # 原始参数字符串（直接追加）
  raw: "--experimental-features --no-color"
  
  # 继承其他 PMG
  extends:
    - code: base-pmg
      override: false        # true 表示覆盖同名参数
  
  # 条件参数
  conditions:
    - when: "os == 'linux'"
      parameters:
        - name: shell
          type: long
          value: "/bin/bash"
    
    - when: "env.DEBUG == 'true'"
      parameters:
        - name: debug
          type: flag
          enabled: true
        - name: log-level
          type: long
          value: "debug"
```

### 3.2 字段详解

#### metadata

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | 唯一标识符，小写字母/数字/连字符 |
| `name` | string | ✅ | 人类可读名称 |
| `description` | string | ❌ | 描述说明 |

#### spec.forTypes

指定该参数组适用于哪些 Agent 类型。

| 值 | 说明 |
|----|------|
| `kimi` | Kimi Code CLI |
| `claude` | Claude Code CLI |
| `gemini` | Gemini CLI |

#### spec.parameters

参数列表，每个参数包含：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 参数名（不含 -- 或 - 前缀） |
| `type` | string | ✅ | 参数类型 |
| `value` | any | 视类型而定 | 参数值 |
| `values` | list | 视类型而定 | 多值（repeatable 类型） |
| `enabled` | boolean | 视类型而定 | 是否启用（flag 类型） |

#### spec.raw

原始参数字符串，直接追加到命令行末尾。用于一些特殊的、不便于结构化定义的场景。

#### spec.extends

继承其他 PMG 的配置：

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 要继承的 PMG code |
| `override` | boolean | 是否覆盖同名参数 |

#### spec.conditions

条件参数，根据环境动态添加：

| 字段 | 类型 | 说明 |
|------|------|------|
| `when` | string | 条件表达式 |
| `parameters` | list | 条件满足时添加的参数 |

支持的条件变量：
- `os`: 操作系统 (windows, linux, darwin)
- `arch`: 架构 (amd64, arm64)
- `env.XXX`: 环境变量值

---

## 4. 参数类型详解

### 4.1 long（长格式参数）

```yaml
- name: model                    # 渲染为: --model
  type: long
  value: "kimi-k2-072515-preview" # 渲染为: kimi-k2-072515-preview
```

输出：`--model kimi-k2-072515-preview`

### 4.2 short（短格式参数）

```yaml
- name: y                        # 渲染为: -y
  type: short
  value: true                    # boolean: 只渲染标志
```

输出：`-y`

```yaml
- name: p                        # 渲染为: -p
  type: short
  value: "/path/to/file"         # string: 渲染标志和值
```

输出：`-p /path/to/file`

### 4.3 flag（开关标志）

```yaml
- name: verbose                  # 渲染为: --verbose
  type: flag
  enabled: true                  # true: 渲染，false: 不渲染
```

输出：`--verbose`

### 4.4 positional（位置参数）

```yaml
- name: work-dir                 # name 仅用于标识，不渲染
  type: positional
  value: "./workspace"           # 直接渲染值
```

输出：`./workspace`

### 4.5 repeatable（可重复参数）

```yaml
- name: add-dir                  # 渲染为: --add-dir（每个值）
  type: repeatable
  values:
    - "./src"
    - "./tests"
```

输出：`--add-dir ./src --add-dir ./tests`

### 4.6 json（JSON 值参数）

```yaml
- name: config                   # 渲染为: --config
  type: json
  value:                         # dict 或 JSON 字符串
    key: value
    nested:
      item: 1
```

输出：`--config '{"key": "value", "nested": {"item": 1}}'`

### 4.7 key-value（键值对参数）

```yaml
- name: labels                   # 渲染为: --labels
  type: key-value
  value:
    env: production
    team: platform
```

输出：`--labels env=production,team=platform`

---

## 5. 继承与条件

### 5.1 参数继承机制

```
Base PMG:
  - model: gpt-4
  - verbose: true

Extended PMG:
  extends:
    - code: base
      override: true
  parameters:
    - name: model              # 覆盖 base 中的 model
      type: long
      value: claude-sonnet
    - name: y                  # 新增参数
      type: short
      value: true

结果:
  - model: claude-sonnet       # 来自 extended，覆盖 base
  - verbose: true              # 来自 base
  - y: true                    # 来自 extended
```

### 5.2 条件表达式

条件表达式支持简单的比较操作：

```yaml
conditions:
  # 操作系统判断
  - when: "os == 'linux'"
    parameters:
      - name: shell
        type: long
        value: "/bin/bash"
  
  - when: "os == 'darwin'"
    parameters:
      - name: shell
        type: long
        value: "/bin/zsh"
  
  # 环境变量判断
  - when: "env.CI == 'true'"
    parameters:
      - name: non-interactive
        type: flag
        enabled: true
  
  # 多条件（AND）
  - when: "os == 'linux' && env.DEBUG == 'true'"
    parameters:
      - name: debug
        type: flag
        enabled: true
```

### 5.3 参数渲染优先级

```
1. 继承的基础参数（最低优先级）
2. 当前 PMG 定义的参数
3. 条件参数（满足条件时）
4. raw 字符串（追加到最后）
```

---

## 6. CLI 命令设计

### 6.1 命令概览

```bash
zima pmg create        # 创建 PMG
zima pmg list          # 列出 PMG
zima pmg show          # 查看详情
zima pmg update        # 更新配置
zima pmg delete        # 删除配置
zima pmg validate      # 验证配置
zima pmg add-param     # 添加参数
zima pmg remove-param  # 移除参数
zima pmg build         # 构建命令行参数（预览）
```

### 6.2 命令详情

#### create

```bash
zima pmg create \
  --code kimi-default \
  --name "Kimi 默认参数" \
  --for-types kimi \
  --description "Kimi CLI 的默认参数" \
  [--from existing-pmg]  # 从现有配置复制
```

#### list

```bash
zima pmg list [options]

Options:
  --format yaml|json|table   # 输出格式（默认 table）
  --for-type <type>          # 按类型过滤
```

**示例输出**：
```
CODE              NAME              TYPES       PARAMS
kimi-default      Kimi 默认参数      kimi        5
claude-verbose    Claude 详细模式    claude      3
base              基础参数组         kimi,claude 2
```

#### show

```bash
zima pmg show <code> [options]

Options:
  --format yaml|json   # 输出格式（默认 yaml）
```

#### update

```bash
zima pmg update <code> [options]

Options:
  --name <name>              # 更新名称
  --description <desc>       # 更新描述
  --add-type <type>          # 添加适用类型
  --remove-type <type>       # 移除适用类型
  --raw <string>             # 更新 raw 字符串
```

#### add-param

```bash
zima pmg add-param <code> [options]

Options:
  --name <name>              # 参数名（必填）
  --type <type>              # 参数类型（必填）
  --value <value>            # 参数值
  --values <values>          # 多值（逗号分隔，repeatable 类型）
  --enabled <bool>           # 是否启用（flag 类型）
```

**示例**：
```bash
# 添加长格式参数
zima pmg add-param kimi-default \
  --name model \
  --type long \
  --value "kimi-k2-072515-preview"

# 添加标志参数
zima pmg add-param kimi-default \
  --name verbose \
  --type flag \
  --enabled true

# 添加可重复参数
zima pmg add-param kimi-default \
  --name add-dir \
  --type repeatable \
  --values "./src,./tests"
```

#### remove-param

```bash
zima pmg remove-param <code> --name <param-name>
```

#### build

```bash
zima pmg build <code> [options]

Options:
  --format shell|list    # 输出格式（默认 list）
  --eval-conditions      # 评估条件参数
```

**示例输出**（list 格式）：
```
["--model", "kimi-k2-072515-preview", "--verbose", "-y", "./workspace"]
```

**示例输出**（shell 格式）：
```
--model kimi-k2-072515-preview --verbose -y ./workspace
```

---

## 7. 使用示例

### 7.1 Kimi 默认参数组

```bash
# 创建基础 PMG
zima pmg create \
  --code kimi-default \
  --name "Kimi 默认参数" \
  --for-types kimi

# 添加参数
zima pmg add-param kimi-default --name model --type long --value "kimi-k2-072515-preview"
zima pmg add-param kimi-default --name max-steps-per-turn --type long --value "50"
zima pmg add-param kimi-default --name yolo --type short --value "true"
zima pmg add-param kimi-default --name work-dir --type positional --value "./workspace"
zima pmg add-param kimi-default --name add-dir --type repeatable --values "./src,./tests"

# 预览构建的命令
zima pmg build kimi-default
```

### 7.2 继承并扩展

```bash
# 创建基础 PMG
zima pmg create \
  --code base-pmg \
  --name "基础参数" \
  --for-types kimi,claude

zima pmg add-param base-pmg --name verbose --type flag --enabled true
zima pmg add-param base-pmg --name work-dir --type positional --value "./workspace"

# 创建继承的 PMG
zima pmg create \
  --code kimi-extended \
  --name "Kimi 扩展参数" \
  --for-types kimi \
  --from base-pmg

# 添加/覆盖参数
zima pmg add-param kimi-extended --name model --type long --value "kimi-k2-072515-preview"
zima pmg add-param kimi-extended --name max-ralph-iterations --type long --value "15"
```

### 7.3 在 Agent 中使用

```bash
# 创建 Agent 时指定 PMG
zima agent create \
  --code my-agent \
  --name "My Agent" \
  --type kimi \
  --pmg kimi-default

# 查看 Agent 详情会显示关联的 PMG
zima agent show my-agent
```

### 7.4 条件参数示例

```yaml
# 手动编辑 YAML 添加条件参数
spec:
  conditions:
    - when: "os == 'linux'"
      parameters:
        - name: shell
          type: long
          value: "/bin/bash"
    
    - when: "env.CI == 'true'"
      parameters:
        - name: non-interactive
          type: flag
          enabled: true
```

---

## 8. 测试方案

### 8.1 单元测试

#### PMGConfig 模型测试 (`tests/unit/test_models_pmg.py`)

```python
class TestPMGConfig:
    """PMGConfig 模型单元测试"""
    
    class TestCreate:
        """测试创建"""
        
        test_create_basic()              # 基础创建
        test_create_with_parameters()    # 带参数创建
        test_create_with_extends()       # 带继承创建
        test_create_invalid_type()       # 无效类型抛出异常
    
    class TestValidation:
        """测试验证"""
        
        test_validate_valid()            # 有效配置
        test_validate_missing_code()     # 缺少 code
        test_validate_invalid_code()     # 无效 code 格式
        test_validate_invalid_param_type()  # 无效参数类型
        test_validate_duplicate_param_names()  # 重复参数名
        test_validate_extends_not_found()   # 继承的 PMG 不存在
    
    class TestParameterRendering:
        """测试参数渲染"""
        
        test_render_long_param()         # 长格式参数
        test_render_short_param_bool()   # 短格式布尔参数
        test_render_short_param_string() # 短格式字符串参数
        test_render_flag_enabled()       # 启用的标志
        test_render_flag_disabled()      # 禁用的标志
        test_render_positional()         # 位置参数
        test_render_repeatable()         # 可重复参数
        test_render_json()               # JSON 参数
        test_render_key_value()          # 键值对参数
    
    class TestInheritance:
        """测试继承"""
        
        test_inherit_single()            # 单继承
        test_inherit_multiple()          # 多继承
        test_inherit_override()          # 覆盖参数
        test_inherit_no_override()       # 不覆盖参数
        test_inherit_circular_detect()   # 循环继承检测
    
    class TestConditions:
        """测试条件参数"""
        
        test_condition_os_match()        # OS 条件匹配
        test_condition_os_no_match()     # OS 条件不匹配
        test_condition_env_match()       # 环境变量条件匹配
        test_condition_complex()         # 复杂条件表达式
        test_condition_invalid_syntax()  # 无效条件语法
    
    class TestBuildCommand:
        """测试构建命令"""
        
        test_build_basic()               # 基础构建
        test_build_with_extends()        # 带继承构建
        test_build_with_conditions()     # 带条件构建
        test_build_with_raw()            # 带 raw 字符串
```

### 8.2 集成测试

#### PMG CLI 测试 (`tests/integration/test_pmg_commands.py`)

```python
class TestPMGCreate:
    """测试 pmg create 命令"""
    
    test_create_basic()                # 基础创建
    test_create_with_types()           # 指定类型
    test_create_duplicate_code_fails() # 重复 code 失败
    test_create_invalid_type_fails()   # 无效类型失败
    test_create_from_existing()        # 从现有复制


class TestPMGAddParam:
    """测试 pmg add-param 命令"""
    
    test_add_long_param()              # 添加长格式参数
    test_add_short_param()             # 添加短格式参数
    test_add_flag_param()              # 添加标志参数
    test_add_repeatable_param()        # 添加可重复参数
    test_add_json_param()              # 添加 JSON 参数
    test_add_duplicate_name_fails()    # 重复参数名失败


class TestPMGRemoveParam:
    """测试 pmg remove-param 命令"""
    
    test_remove_existing()             # 移除存在的参数
    test_remove_nonexistent()          # 移除不存在的参数


class TestPMGBuild:
    """测试 pmg build 命令"""
    
    test_build_list_format()           # list 格式输出
    test_build_shell_format()          # shell 格式输出
    test_build_with_conditions()       # 带条件构建
    test_build_eval_conditions()       # 评估条件


class TestPMGLifecycle:
    """测试完整生命周期"""
    
    test_full_lifecycle():
        # 创建 → 添加参数 → 验证 → 构建 → 更新 → 删除
```

### 8.3 测试 Fixtures

```python
@pytest.fixture
def sample_pmg_config():
    """提供示例 PMG 配置"""
    return {
        "apiVersion": "zima.io/v1",
        "kind": "PMG",
        "metadata": {
            "code": "test-pmg",
            "name": "Test PMG"
        },
        "spec": {
            "forTypes": ["kimi"],
            "parameters": [
                {"name": "model", "type": "long", "value": "gpt-4"},
                {"name": "verbose", "type": "flag", "enabled": True},
                {"name": "work-dir", "type": "positional", "value": "./workspace"}
            ]
        }
    }


@pytest.fixture
def mock_os_info(monkeypatch):
    """模拟操作系统信息"""
    def mock_get_os():
        return "linux"
    
    def mock_get_arch():
        return "amd64"
    
    return {"os": mock_get_os, "arch": mock_get_arch}
```

### 8.4 测试覆盖率目标

| 模块 | 目标覆盖率 | 关键路径 |
|------|-----------|----------|
| PMGConfig 模型 | 95% | 创建、验证、参数渲染、继承、条件 |
| 参数渲染器 | 100% | 所有参数类型 |
| 条件评估器 | 100% | 所有条件表达式类型 |
| CLI 命令 | 90% | 所有子命令的正常和异常路径 |

---

## 9. 实现阶段

### Phase 1: 模型层

- [ ] `PMGConfig` 数据模型
- [ ] `ParameterDef` 参数定义
- [ ] `ParameterRenderer` 参数渲染器
- [ ] `ConditionEvaluator` 条件评估器
- [ ] 继承解析逻辑
- [ ] 单元测试（50+ 测试）

### Phase 2: CLI 命令

- [ ] `zima pmg create`
- [ ] `zima pmg list`
- [ ] `zima pmg show`
- [ ] `zima pmg update`
- [ ] `zima pmg delete`
- [ ] `zima pmg validate`
- [ ] `zima pmg add-param`
- [ ] `zima pmg remove-param`
- [ ] `zima pmg build`
- [ ] 集成测试（40+ 测试）

### Phase 3: 高级特性

- [ ] 循环继承检测
- [ ] 复杂条件表达式支持
- [ ] 参数类型自动推断
- [ ] 参数验证增强

---

> "参数是命令的灵魂，组合是智慧的体现。" —— Zima Blue
