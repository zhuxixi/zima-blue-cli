# Workflow 配置设计文档

> Workflow 是 Zima Blue 的核心组件，定义 Agent 执行的任务流程（Prompt 模板）。

---

## 📋 目录

1. [概述](#1-概述)
2. [核心概念](#2-核心概念)
3. [Schema 定义](#3-schema-定义)
4. [变量系统](#4-变量系统)
5. [模板引擎](#5-模板引擎)
6. [CLI 命令设计](#6-cli-命令设计)
7. [使用示例](#7-使用示例)
8. [实现阶段](#8-实现阶段)

---

## 1. 概述

### 1.1 什么是 Workflow

Workflow 是 **Prompt 模板**，定义了 Agent 执行任务的指令内容。它：

- 使用 **Jinja2** 语法支持变量插值和逻辑控制
- 通过 `variables` 声明需要的变量及其类型
- 与 `variable` 配置配合，实现模板与数据的分离

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **模板与数据分离** | Workflow 只定义模板结构，具体值由 Variable 提供 |
| **类型安全** | 变量声明包含类型、必填性、默认值 |
| **可复用性** | 一个 Workflow 可被多个 PJob 使用 |
| **版本化** | 支持 `version` 字段管理模板演进 |

### 1.3 文件位置

```
~/.zima/configs/workflows/{code}.yaml
```

---

## 2. 核心概念

### 2.1 Workflow 执行流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Workflow   │  +  │  Variable   │  →  │  Rendered   │
│  (Template) │     │  (Values)   │     │  Prompt     │
└─────────────┘     └─────────────┘     └─────────────┘
      ↑                                    ↓
   定义结构                          生成最终 Prompt
                                     传递给 Agent
```

### 2.2 与 Variable 的关系

```
Workflow "code-review"
  ├─ template: "审查 {{ project.name }}"
  └─ variables: [project.name, project.path]
         ↓
Variable "my-project-vars"
  ├─ forWorkflow: code-review
  └─ values:
       project:
         name: "Zima Blue"
         path: "./zima-blue-cli"
         ↓
    Rendered: "审查 Zima Blue"
```

---

## 3. Schema 定义

### 3.1 完整结构

```yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: default-workflow          # 唯一编码
  name: 默认工作流                  # 显示名称
  description: 通用的代码审查工作流   # 描述
createdAt: "2026-03-25T10:00:00Z"
updatedAt: "2026-03-25T10:00:00Z"
spec:
  # 模板格式
  format: jinja2
  
  # 模板内容
  template: |
    # {{ task.name }}
    
    你是一个 {{ agent.role }}。
    
    ## 任务目标
    {{ task.objective }}
    
    ## 输出要求
    {{ output.requirements }}
  
  # 变量声明
  variables:
    - name: task.name
      type: string
      required: true
      description: 任务名称
  
  # 元数据
  tags:
    - code-review
    - python
  author: zima-team
  version: "1.0.0"
```

### 3.2 字段详解

#### metadata

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | 唯一标识符，小写字母/数字/连字符 |
| `name` | string | ✅ | 人类可读名称 |
| `description` | string | ❌ | 描述说明 |

#### spec.format

| 值 | 说明 |
|----|------|
| `jinja2` | Jinja2 模板语法（推荐，默认） |
| `mustache` | Mustache/Handlebars 语法 |
| `plain` | 纯文本，无变量替换 |

#### spec.template

模板内容字符串，使用 Jinja2 语法。支持：

- **变量插值**: `{{ variable.name }}`
- **条件判断**: `{% if condition %}...{% endif %}`
- **循环**: `{% for item in list %}...{% endfor %}`
- **过滤器**: `{{ value | filter }}`

#### spec.variables

变量声明列表，用于文档说明和验证：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 变量名，支持点号嵌套（如 `task.name`） |
| `type` | string | ✅ | string/number/boolean/array/object |
| `required` | boolean | ✅ | 是否必填 |
| `default` | any | ❌ | 默认值 |
| `description` | string | ❌ | 变量说明 |

### 3.3 支持的变量类型

```yaml
variables:
  # 字符串
  - name: task.name
    type: string
    required: true
  
  # 数字
  - name: config.timeout
    type: number
    default: 30
  
  # 布尔值
  - name: config.verbose
    type: boolean
    default: false
  
  # 数组
  - name: task.steps
    type: array
    required: true
  
  # 对象
  - name: project.metadata
    type: object
    required: false
```

---

## 4. 变量系统

### 4.1 变量命名规范

变量名支持点号表示嵌套结构：

```yaml
# 简单变量
name: "任务名称"

# 嵌套变量
task.name: "任务名称"
task.objective: "任务目标"
task.steps: ["步骤1", "步骤2"]

# 深层嵌套
project.config.language: "Python"
project.config.version: "3.11"
```

### 4.2 变量解析规则

```yaml
# Variable 配置
spec:
  values:
    task:
      name: "代码审查"
      steps:
        - "拉取代码"
        - "运行测试"

# 解析结果
task.name → "代码审查"
task.steps → ["拉取代码", "运行测试"]
task → {name: "代码审查", steps: [...]}
```

### 4.3 变量验证

Workflow 加载时会验证：

1. **必填检查**: 所有 `required: true` 的变量必须有值
2. **类型检查**: 值类型与声明一致
3. **结构检查**: 嵌套变量路径存在

---

## 5. 模板引擎

### 5.1 Jinja2 语法支持

#### 变量插值

```jinja2
{{ variable }}
{{ variable | default("fallback") }}
{{ variable | upper }}
{{ list | join(", ") }}
```

#### 条件判断

```jinja2
{% if task.priority == "high" %}
⚠️ 这是高优先级任务，请优先处理。
{% endif %}

{% if config.debug %}
调试模式已启用。
{% else %}
生产模式。
{% endif %}
```

#### 循环

```jinja2
## 工作步骤
{% for step in task.steps %}
{{ loop.index }}. {{ step }}
{% endfor %}

## 参考文档
{% for ref in references %}
- {{ ref.name }}: {{ ref.url }}
{% else %}
无参考文档。
{% endfor %}
```

#### 过滤器

| 过滤器 | 说明 | 示例 |
|--------|------|------|
| `default` | 默认值 | `{{ name \| default("匿名") }}` |
| `upper` | 转大写 | `{{ status \| upper }}` |
| `lower` | 转小写 | `{{ name \| lower }}` |
| `trim` | 去空白 | `{{ text \| trim }}` |
| `join` | 连接数组 | `{{ items \| join(", ") }}` |

### 5.2 内置变量

模板中可访问以下内置变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `now` | 当前时间 | `{{ now }}` |
| `env.XXX` | 环境变量 | `{{ env.HOME }}` |

---

## 6. CLI 命令设计

### 6.1 命令概览

```bash
zima workflow create      # 创建 Workflow
zima workflow list        # 列出 Workflow
zima workflow show        # 查看详情
zima workflow update      # 更新配置
zima workflow delete      # 删除配置
zima workflow validate    # 验证配置
zima workflow render      # 渲染模板（预览）
```

### 6.2 命令详情

#### create

```bash
zima workflow create \
  --code code-review \
  --name "代码审查工作流" \
  --description "用于代码审查的标准工作流" \
  [--from existing-workflow]  # 从现有配置复制
```

**功能**：
- 创建新的 Workflow 配置
- 可选 `--from` 复制现有配置
- 验证 code 格式（小写字母/数字/连字符）
- 检查 code 唯一性

#### list

```bash
zima workflow list [options]

Options:
  --format yaml|json|table   # 输出格式（默认 table）
  --tag <tag>                # 按标签过滤
```

**示例输出**：
```
CODE              NAME              TAGS              VERSION   UPDATED
code-review       代码审查          code-review,py    1.0.0     2h ago
bug-fix           Bug修复           debug             1.1.0     1d ago
refactor          重构任务          refactor          2.0.0     3d ago
```

#### show

```bash
zima workflow show <code> [options]

Options:
  --format yaml|json   # 输出格式（默认 yaml）
```

**示例**：
```bash
$ zima workflow show code-review --format yaml

apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: code-review
  name: 代码审查工作流
  description: 用于代码审查的标准工作流
spec:
  format: jinja2
  template: |
    # {{ task.name }}
    ...
  variables:
    - name: task.name
      type: string
      required: true
```

#### update

```bash
zima workflow update <code> [options]

Options:
  --name <name>              # 更新名称
  --description <desc>       # 更新描述
  --template <template>      # 更新模板内容（文件路径或字符串）
  --format <format>          # 更新模板格式
  --add-tag <tag>            # 添加标签
  --remove-tag <tag>         # 移除标签
  --version <version>        # 更新版本号
```

**示例**：
```bash
zima workflow update code-review \
  --name "Python代码审查" \
  --add-tag python \
  --version "1.1.0"
```

#### delete

```bash
zima workflow delete <code> [--force]
```

**功能**：
- 删除 Workflow 配置
- `--force` 跳过确认提示
- 检查是否有 PJob 正在使用该 Workflow

#### validate

```bash
zima workflow validate <code>
```

**验证内容**：
- YAML 格式正确性
- 必需字段完整性
- 变量声明语法
- 模板语法（Jinja2）

**输出**：
```
✓ YAML 格式正确
✓ 必需字段完整
✓ 变量声明语法正确
✓ 模板语法正确

Workflow 'code-review' 验证通过！
```

#### render

```bash
zima workflow render <code> [options]

Options:
  --variable <code>          # 指定 Variable 配置
  --var key=value            # 直接传入变量值（可多次）
  --output <file>            # 输出到文件
```

**功能**：渲染模板并输出结果，用于预览。

**示例**：
```bash
# 使用 Variable 配置渲染
zima workflow render code-review --variable my-project-vars

# 直接传入变量
zima workflow render greeting --var name="World" --var mood="happy"
```

---

## 7. 使用示例

### 7.1 简单问候工作流

```yaml
# ~/.zima/configs/workflows/greeting.yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: greeting
  name: 问候工作流
  description: 简单的问候示例
spec:
  format: jinja2
  template: |
    你好，{{ name }}！
    
    {% if mood == "happy" %}
    希望你今天过得愉快！😊
    {% else %}
    希望你心情能好起来。
    {% endif %}
  
  variables:
    - name: name
      type: string
      required: true
      description: 要问候的名字
    
    - name: mood
      type: string
      required: false
      default: "happy"
      description: 心情状态
```

### 7.2 代码审查工作流

```yaml
# ~/.zima/configs/workflows/code-review.yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: code-review
  name: 代码审查工作流
  description: 系统化的代码审查流程
  tags:
    - code-review
    - quality
spec:
  format: jinja2
  template: |
    # {{ task.name }}
    
    你是一个 {{ agent.role }}，擅长 {{ agent.specialty }}。
    
    ## 审查目标
    {{ task.objective }}
    
    ## 审查范围
    {% if scope.files %}
    文件列表：
    {% for file in scope.files %}
    - {{ file }}
    {% endfor %}
    {% endif %}
    
    ## 审查步骤
    {% for step in task.steps %}
    {{ loop.index }}. {{ step }}
    {% endfor %}
    
    ## 检查清单
    {% for item in checklist %}
    - [ ] {{ item }}
    {% endfor %}
    
    ## 输出格式
    {{ output.format }}
  
  variables:
    - name: task.name
      type: string
      required: true
    
    - name: task.objective
      type: string
      required: true
    
    - name: task.steps
      type: array
      required: true
    
    - name: agent.role
      type: string
      default: "高级代码审查员"
    
    - name: agent.specialty
      type: string
      default: "Python、TypeScript"
    
    - name: scope.files
      type: array
      required: false
    
    - name: checklist
      type: array
      required: true
    
    - name: output.format
      type: string
      required: true
  
  version: "1.0.0"
```

### 7.3 对应的 Variable 配置

```yaml
# ~/.zima/configs/variables/python-review-vars.yaml
apiVersion: zima.io/v1
kind: Variable
metadata:
  code: python-review-vars
  name: Python代码审查变量
spec:
  forWorkflow: code-review
  values:
    task:
      name: "Python项目代码审查"
      objective: "审查昨日提交的所有Python代码变更"
      steps:
        - "检查代码风格是否符合PEP8"
        - "检查类型注解是否完整"
        - "检查是否有潜在的性能问题"
        - "检查测试覆盖率"
    
    agent:
      role: "Python专家"
      specialty: "Python代码质量、性能优化"
    
    scope:
      files:
        - "src/**/*.py"
        - "tests/**/*.py"
    
    checklist:
      - "函数命名符合规范"
      - "没有未使用的导入"
      - "异常处理完善"
      - "文档字符串完整"
    
    output:
      format: |
        请以 JSON 格式输出审查结果：
        ```json
        {
          "summary": "审查摘要",
          "issues": [...],
          "score": 85
        }
        ```
```

### 7.4 渲染命令示例

```bash
# 渲染代码审查工作流
$ zima workflow render code-review --variable python-review-vars

输出：
# Python项目代码审查

你是一个 Python专家，擅长 Python代码质量、性能优化。

## 审查目标
审查昨日提交的所有Python代码变更

## 审查范围
文件列表：
- src/**/*.py
- tests/**/*.py

## 审查步骤
1. 检查代码风格是否符合PEP8
2. 检查类型注解是否完整
3. 检查是否有潜在的性能问题
4. 检查测试覆盖率

...
```

---

## 8. 实现阶段

### Phase 1: 模型层

- [ ] WorkflowConfig 数据模型
- [ ] Variable 模型
- [ ] 模板渲染引擎（Jinja2）
- [ ] 变量验证器

### Phase 2: CLI 命令

- [ ] `zima workflow create`
- [ ] `zima workflow list`
- [ ] `zima workflow show`
- [ ] `zima workflow update`
- [ ] `zima workflow delete`
- [ ] `zima workflow validate`
- [ ] `zima workflow render`

### Phase 3: Variable CLI

- [ ] `zima variable create`
- [ ] `zima variable list`
- [ ] `zima variable show`
- [ ] `zima variable update`
- [ ] `zima variable delete`

---

> "模板是骨架，变量是血肉，渲染是灵魂。" —— Zima Blue
