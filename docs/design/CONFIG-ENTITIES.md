# Zima CLI 配置实体设计文档
> ⚠️ 本文档写于实现前，部分内容可能已与代码不一致。最新状态请参考代码和 `docs/API-INTERFACE.md`。

> 本文档定义 zima CLI 的五组配置实体：agent、workflow、variable、env、pmg

---

## 📋 目录

1. [设计原则](#1-设计原则)
2. [通用字段规范](#2-通用字段规范)
3. [Agent 配置](#3-agent-配置)
4. [Workflow 配置](#4-workflow-配置)
5. [Variable 配置](#5-variable-配置)
6. [Env 配置](#6-env-配置)
7. [PMG (Parameters Group) 配置](#7-pmg-parameters-group-配置)
8. [配置存储结构](#8-配置存储结构)
9. [配置继承与覆盖规则](#9-配置继承与覆盖规则)

---

## 1. 设计原则

1. **统一元数据**: 所有配置都包含 `metadata` 和 `spec` 两部分
2. **全局唯一编码**: `code` 字段全局唯一，作为标识符
3. **类型安全**: 每个配置有明确的 schema 定义
4. **可组合性**: 通过引用关系组合配置（如 pjob 引用 agent、workflow 等）
5. **扩展性**: 支持不同类型的 Agent 实例（Kimi、Claude、Gemini 等）

---

## 2. 通用字段规范

所有配置实体的通用结构：

```yaml
apiVersion: zima.io/v1
kind: <ConfigType>          # Agent/Workflow/Variable/Env/PMG
metadata:
  code: <unique-code>       # 全局唯一编码，用于 CLI 引用
  name: <display-name>      # 人类可读的名称（中文/英文）
  description: <desc>       # 描述说明
createdAt: <timestamp>
updatedAt: <timestamp>
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `apiVersion` | string | ✅ | API 版本，当前为 `zima.io/v1` |
| `kind` | string | ✅ | 配置类型 |
| `metadata.code` | string | ✅ | 全局唯一编码，只允许小写字母、数字、连字符 |
| `metadata.name` | string | ✅ | 显示名称，支持中英文 |
| `metadata.description` | string | ❌ | 描述说明 |
| `createdAt` | string | ✅ | 创建时间 (ISO8601) |
| `updatedAt` | string | ✅ | 更新时间 (ISO8601) |

---

## 3. Agent 配置

**文件**: `~/.zima/configs/agents/{code}.yaml`

**用途**: 定义 Agent 的规格参数，包括名称、描述、实例类型等。

### Schema

```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: test-agent
  name: 测试用 Agent
  description: 用于测试的 Agent 实例
spec:
  # 实例类型: kimi | claude | gemini
  type: kimi
  
  # 实例特定的参数（根据 type 变化）
  parameters:
    # Kimi 特有参数
    model: "kimi-k2-072515-preview"    # 模型选择
    thinking: false                     # 是否启用思考模式
    
    # 通用参数（各类型都支持）
    workDir: "./workspace"             # 工作目录
    addDirs: []                        # 额外目录
    yolo: true                         # 自动批准模式
    
  # 默认关联配置（可选，可被 pjob 覆盖）
  defaults:
    workflow: default-workflow        # 默认 workflow code
    variable: default-vars            # 默认 variable code
    env: default-env                  # 默认 env code
    pmg: kimi-default-pmg             # 默认 pmg code
```

### 字段详解

#### spec.type

| 值 | 说明 | 对应 CLI 工具 |
|----|------|--------------|
| `kimi` | Kimi Code CLI | `kimi` |
| `claude` | Claude Code CLI | `claude` |
| `gemini` | Gemini CLI | `gemini` |


#### spec.parameters（按类型）

**Kimi 特有参数** (`type: kimi`):

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | - | 模型名称 |
| `thinking` | boolean | false | 思考模式 |
| `maxStepsPerTurn` | integer | 50 | 每轮最大步数 |
| `maxRalphIterations` | integer | 10 | Ralph 迭代次数 |
| `maxRetriesPerStep` | integer | 3 | 每步重试次数 |
| `session` | string | - | 会话 ID |
| `continue_` | boolean | false | 继续上次会话 |

**Claude 特有参数** (`type: claude`):

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | - | 模型名称 (claude-sonnet-4-6, claude-opus-4-6) |
| `plan` | boolean | false | 计划模式 |
| `acceptEdits` | boolean | false | 自动接受编辑 |
| `maxTurns` | integer | - | 最大轮数 |
| `teammateMode` | string | auto | 队友模式 (auto, in-process, tmux) |
| `tools` | string | default | 限制工具使用 |
| `disableSlashCommands` | boolean | false | 禁用斜杠命令 |

**Gemini 特有参数** (`type: gemini`):

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | auto | 模型名称 |
| `approvalMode` | string | default | 批准模式 (default, auto_edit, ...) |
| `checkpointing` | boolean | false | 启用检查点 |
| `extensions` | array | - | 扩展列表 |

**通用参数** (所有类型):

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `workDir` | string | ./workspace | 工作目录 |
| `addDirs` | array | [] | 额外包含的目录 |
| `yolo` | boolean | false | YOLO 模式（自动批准） |
| `verbose` | boolean | false | 详细输出 |
| `debug` | boolean | false | 调试模式 |
| `outputFormat` | string | text | 输出格式 (text, json, stream-json) |

#### spec.defaults

定义 Agent 的默认关联配置，在创建 pjob 时可被覆盖。

---

## 4. Workflow 配置

**文件**: `~/.zima/configs/workflows/{code}.yaml`

**用途**: 定义 Agent 执行的工作流程（Prompt 模板），包含变量占位符。

### Schema

```yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: default-workflow
  name: 默认工作流
  description: 通用的代码审查工作流
createdAt: "2026-03-25T10:00:00Z"
updatedAt: "2026-03-25T10:00:00Z"
spec:
  # 模板格式: jinja2 | mustache | plain
  format: jinja2
  
  # 模板内容（Jinja2 格式）
  template: |
    # {{ task.name }}
    
    你是一个 {{ agent.role }}，擅长 {{ agent.specialty }}。
    
    ## 任务目标
    {{ task.objective }}
    
    ## 工作步骤
    {% for step in task.steps %}
    {{ loop.index }}. {{ step }}
    {% endfor %}
    
    ## 参考文档
    {% if references %}
    {% for ref in references %}
    - {{ ref.name }}: {{ ref.path }}
    {% endfor %}
    {% endif %}
    
    ## 技能调用指南
    {% for skill in skills %}
    ### {{ skill.name }}
    {{ skill.description }}
    使用场景: {{ skill.when_to_use }}
    {% endfor %}
    
    ## 输出要求
    {{ output.requirements }}
  
  # 定义的变量列表（文档说明用途）
  variables:
    - name: task.name
      type: string
      required: true
      description: 任务名称
    - name: task.objective
      type: string
      required: true
      description: 任务目标
    - name: task.steps
      type: array
      required: true
      description: 工作步骤列表
    - name: agent.role
      type: string
      required: false
      default: "软件工程师"
      description: Agent 角色
    - name: agent.specialty
      type: string
      required: false
      default: "Python 开发"
      description: Agent 专长
    - name: references
      type: array
      required: false
      description: 参考文档列表
    - name: skills
      type: array
      required: false
      description: 要使用的技能列表
    - name: output.requirements
      type: string
      required: true
      description: 输出要求
  
  # 元数据
  tags:
    - code-review
    - python
  author: zima-team
  version: "1.0.0"
```

### 字段详解

#### spec.format

| 值 | 说明 |
|----|------|
| `jinja2` | Jinja2 模板语法（推荐） |
| `mustache` | Mustache/Handlebars 语法 |
| `plain` | 纯文本，无变量替换 |

#### spec.variables

定义模板中使用的变量，用于文档说明和验证。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 变量名，支持点号表示嵌套 |
| `type` | string | ✅ | 变量类型: string, number, boolean, array, object |
| `required` | boolean | ✅ | 是否必填 |
| `default` | any | ❌ | 默认值 |
| `description` | string | ❌ | 变量说明 |

---

## 5. Variable 配置

**文件**: `~/.zima/configs/variables/{code}.yaml`

**用途**: 为 Workflow 模板提供变量值，实现模板和数据的分离。

### Schema

```yaml
apiVersion: zima.io/v1
kind: Variable
metadata:
  code: v1g
  name: 代码审查变量组
  description: 用于代码审查任务的变量
createdAt: "2026-03-25T10:00:00Z"
updatedAt: "2026-03-25T10:00:00Z"
spec:
  # 适用的 workflow（可选，用于验证和提示）
  forWorkflow: default-workflow
  
  # 变量值（KV 结构）
  values:
    task:
      name: "每日代码审查"
      objective: "审查昨日提交的代码，找出潜在问题"
      steps:
        - "拉取最新代码"
        - "运行静态分析"
        - "检查代码风格"
        - "生成审查报告"
    
    agent:
      role: "高级代码审查员"
      specialty: "Python、TypeScript 代码审查"
    
    references:
      - name: "代码规范"
        path: "./docs/coding-standards.md"
      - name: "架构文档"
        path: "./docs/architecture.md"
    
    skills:
      - name: "CodeReview"
        description: "系统化代码审查技能"
        when_to_use: "需要审查代码变更时"
      - name: "StaticAnalysis"
        description: "静态代码分析"
        when_to_use: "检查代码质量问题时"
    
    output:
      requirements: |
        请输出 JSON 格式的审查报告：
        ```json
        {
          "summary": "审查摘要",
          "issues": [
            {"file": "路径", "line": 行号, "severity": "error|warning|info", "message": "问题描述"}
          ],
          "score": 85
        }
        ```
```

### 字段详解

#### spec.forWorkflow

指定这组变量适用于哪个 workflow，用于 CLI 提示和验证变量是否匹配。

#### spec.values

变量值对象，结构与 workflow 中定义的 variables 对应。支持任意嵌套结构。

---

## 6. Env 配置

**文件**: `~/.zima/configs/envs/{code}.yaml`

**用途**: 定义环境变量，用于启动 Agent 时注入。

### Schema

```yaml
apiVersion: zima.io/v1
kind: Env
metadata:
  code: env3
  name: Claude 第三方环境
  description: 使用第三方 API 的 Claude 环境配置
createdAt: "2026-03-25T10:00:00Z"
updatedAt: "2026-03-25T10:00:00Z"
spec:
  # 该环境变量组适用的 Agent 类型
  forType: claude
  
  # 环境变量
  variables:
    ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
    ANTHROPIC_BASE_URL: "https://api.anthropic.com"
    # 或使用第三方代理
    # ANTHROPIC_BASE_URL: "https://api.glm.cn/claude"
    CLAUDE_CODE_MODEL: "claude-sonnet-4-6"
    TZ: "Asia/Shanghai"
    LANG: "zh_CN.UTF-8"
    DEBUG: "false"
  
  # 密钥引用（敏感信息从环境或密钥管理器读取）
  secrets:
    - name: ANTHROPIC_API_KEY
      source: env                    # 从当前环境变量读取
      key: MY_ANTHROPIC_KEY
    - name: KIMI_API_KEY
      source: file                   # 从文件读取
      path: "~/.keys/kimi.key"
    - name: GOOGLE_API_KEY
      source: cmd                    # 从命令输出读取
      command: "pass show google/api-key"
  
  # 是否覆盖已存在的环境变量
  overrideExisting: false
```

### 字段详解

#### spec.forType

指定该环境变量组适用于哪种 Agent 类型（kimi/claude/gemini）。一个 Env 配置只对应一种类型。

#### spec.variables

环境变量定义，KV 结构。

#### spec.secrets

敏感信息管理，支持多种来源：

| source | 说明 | 附加字段 |
|--------|------|----------|
| `env` | 从环境变量读取 | `key`: 源环境变量名 |
| `file` | 从文件读取 | `path`: 文件路径 |
| `cmd` | 从命令输出读取 | `command`: 命令字符串 |
| `vault` | 从密钥管理器读取 | `path`: 密钥路径 |

#### spec.overrideExisting

是否覆盖系统中已存在的环境变量。默认 false，即保留已有值。

---

## 7. PMG (Parameters Group) 配置

**文件**: `~/.zima/configs/pmgs/{code}.yaml`

**用途**: 定义命令行参数组，用于启动 Agent 时拼接参数。

### Schema

```yaml
apiVersion: zima.io/v1
kind: PMG
metadata:
  code: kimi-default-pmg
  name: Kimi 默认参数组
  description: Kimi CLI 的默认启动参数
createdAt: "2026-03-25T10:00:00Z"
updatedAt: "2026-03-25T10:00:00Z"
spec:
  # 适用的 Agent 类型
  forTypes:
    - kimi
  
  # 参数列表
  parameters:
    # 长格式参数
    - name: max-steps-per-turn
      type: long
      value: "50"
    
    - name: max-ralph-iterations
      type: long
      value: "10"
    
    # 短格式参数
    - name: y
      type: short
      value: true           # boolean 类型只渲染标志，不渲染值
    
    # 位置参数
    - name: work-dir
      type: positional
      value: "./workspace"
    
    # 重复参数
    - name: add-dir
      type: repeatable
      values:
        - "./src"
        - "./tests"
    
    # 标志参数
    - name: print
      type: flag
      enabled: true
    
    # 复合参数（用于特殊场景）
    - name: mcp-servers
      type: json
      value: |
        {
          "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]
          }
        }
  
  # 原始参数字符串（直接追加到命令行）
  raw: "--quiet --no-color"
  
  # 继承其他 PMG
  extends:
    - code: base-pmg
      override: false        # true 表示覆盖同名参数
  
  # 条件参数（根据环境决定是否添加）
  conditions:
    - when: "os == 'linux'"
      parameters:
        - name: shell
          type: long
          value: "/bin/bash"
    - when: "env.DEBUG == 'true'"
      parameters:
        - name: verbose
          type: flag
          enabled: true
```

### 字段详解

#### spec.forTypes

指定这组参数适用于哪些 Agent 类型。

#### spec.parameters

参数列表，支持多种类型：

| type | 格式示例 | 说明 |
|------|----------|------|
| `long` | `--name value` | 长格式参数 |
| `short` | `-n value` | 短格式参数 |
| `flag` | `--name` | 开关参数（无值） |
| `positional` | `value` | 位置参数 |
| `repeatable` | `--name v1 --name v2` | 可重复参数 |
| `json` | `--name '{...}'` | JSON 值参数 |
| `key-value` | `--name k1=v1,k2=v2` | 键值对参数 |

参数结构：

```yaml
- name: param-name        # 参数名（不含 -- 或 - 前缀）
  type: long              # 参数类型
  value: "value"          # 参数值（type=flag 时不需要）
  values: []              # 多值（type=repeatable 时使用）
  condition: "..."        # 条件表达式（可选）
```

#### spec.raw

原始参数字符串，直接追加到命令行末尾。用于一些特殊的、不便于结构化定义的场景。

#### spec.extends

继承其他 PMG 的配置，实现参数复用。

#### spec.conditions

条件参数，根据环境动态添加。支持的条件变量：

- `os`: 操作系统 (windows, linux, darwin)
- `arch`: 架构 (amd64, arm64)
- `env.XXX`: 环境变量值

---

## 8. 配置存储结构

```
~/.zima/
├── configs/
│   ├── agents/
│   │   ├── test-agent.yaml
│   │   ├── claude-code-agent.yaml
│   │   └── gemini-agent.yaml
│   ├── workflows/
│   │   ├── default-workflow.yaml
│   │   ├── code-review.yaml
│   │   └── bug-fix.yaml
│   ├── variables/
│   │   ├── v1g.yaml
│   │   ├── python-project-vars.yaml
│   │   └── frontend-vars.yaml
│   ├── envs/
│   │   ├── env3.yaml
│   │   ├── kimi-prod.yaml
│   │   ├── claude-glm-proxy.yaml
│   │   └── claude-minimax-proxy.yaml
│   └── pmgs/
│       ├── kimi-default-pmg.yaml
│       ├── claude-default-pmg.yaml
│       ├── verbose-pmg.yaml
│       └── mcp-enabled-pmg.yaml
├── cache/
│   └── ...
└── state.json
```

---

## 9. 配置继承与覆盖规则

### PJob 配置组合优先级（从高到低）

```
1. PJob 中显式指定的配置
2. Agent defaults 中的配置
3. 系统默认值
```

### 示例

假设有以下配置：

**Agent** (`test-agent`):
```yaml
spec:
  defaults:
    workflow: default-workflow
    env: default-env
```

**PJob**:
```bash
zima pjob create \
  --agent test-agent \
  --workflow code-review-workflow \
  --env prod-env
```

最终使用的配置：
- workflow: `code-review-workflow` (PJob 覆盖)
- env: `prod-env` (PJob 覆盖)

---

## 附录 A：各 CLI 工具参数对照表

| 功能 | Kimi | Claude | Gemini |
|------|------|--------|--------|
| 工作目录 | `--work-dir` | `--work-dir` | `--worktree` |
| 额外目录 | `--add-dir` | `--add-dir` | `--include-directories` |
| 非交互模式 | `--print` | `--print` | `-p` |
| 自动批准 | `--yolo` | (默认) | `-y` |
| 提示词 | `--prompt` | `-p` | `-p` |
| 模型选择 | `--model` | `--model` | `-m` |
| 调试模式 | `--verbose` | `--debug` | `-d` |
| 输出格式 | `--output-format` | `--output-format` | `--output-format` |
| 继续会话 | `--continue` | `--resume` | `--resume` |
| 最大步数 | `--max-steps-per-turn` | `--max-turns` | - |

---

> "配置即代码，简洁即美。" —— Zima Blue
