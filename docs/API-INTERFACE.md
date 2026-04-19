# Zima CLI 接口设计文档 (v2.1)

> 本文档列出 ZimaBlue CLI 的所有接口，基于当前已实现功能。
> 
> 最后更新: 2026-03-28

---

## 📁 目录

1. [CLI 命令接口](#1-cli-命令接口)
   - [1.1 Daemon 管理](#11-daemon-管理)
   - [1.2 Agent 管理](#12-agent-管理)
   - [1.3 Workflow 管理](#13-workflow-管理)
   - [1.4 Variable 管理](#14-variable-管理)
   - [1.5 Env 管理](#15-env-管理)
   - [1.6 PMG 管理](#16-pmg-管理)
   - [1.7 PJob 管理](#17-pjob-管理)
2. [数据模型接口](#2-数据模型接口)
3. [核心运行接口](#3-核心运行接口)
4. [配置文件规范](#4-配置文件规范)
5. [执行流程](#5-执行流程)

---

## 1. CLI 命令接口

### 1.1 Daemon 管理

**命令**: `zima daemon <subcommand>`

守护进程管理，用于启动/停止/查看调度器守护进程。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `start` | 启动守护进程 | `zima daemon start --schedule my-schedule` |
| `stop` | 停止守护进程 | `zima daemon stop` |
| `status` | 查看守护进程状态 | `zima daemon status` |
| `logs` | 查看守护进程日志 | `zima daemon logs --tail 50` |

---

### 1.2 Agent 管理

**命令**: `zima agent <subcommand>`

Agent 配置管理，支持多种类型 (kimi/claude/gemini)。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `create` | 创建新 Agent | `zima agent create --name "My Agent" --code my-agent` |
| `list` | 列出所有 Agent | `zima agent list --type kimi` |
| `show` | 显示 Agent 详情 | `zima agent show my-agent` |
| `update` | 更新 Agent 配置 | `zima agent update my-agent --name "New Name"` |
| `delete` | 删除 Agent | `zima agent delete my-agent --force` |
| `validate` | 验证配置 | `zima agent validate my-agent` |
| `test` | 测试预览命令 | `zima agent test my-agent` |

#### Agent Create 详细参数

```bash
zima agent create [OPTIONS]

Options:
  --name TEXT          Agent 显示名称 (必填)
  --code TEXT          Agent 唯一标识 (必填)
  --type TEXT          Agent 类型: kimi/claude/gemini (默认: kimi)
  --description TEXT   Agent 描述
  --model TEXT         使用的模型
  --from TEXT          从现有 Agent 复制
  --yolo BOOLEAN       是否启用 yolo 模式
```

**示例**:
```bash
# 创建 Kimi Agent
zima agent create --name "Code Reviewer" --code code-reviewer --type kimi

# 创建 Claude Agent 并指定模型
zima agent create --name "Doc Writer" --code doc-writer --type claude --model claude-sonnet-4-6

# 从现有 Agent 复制
zima agent create --name "Test Agent" --code test-agent --from code-reviewer
```

---

### 1.3 Workflow 管理

**命令**: `zima workflow <subcommand>`

Prompt 模板管理，支持 Jinja2 变量替换。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `create` | 创建 Workflow | `zima workflow create --name "Review" --code review` |
| `list` | 列出 Workflows | `zima workflow list` |
| `show` | 显示详情 | `zima workflow show review` |
| `update` | 更新配置 | `zima workflow update review --template "..."` |
| `delete` | 删除 | `zima workflow delete review` |
| `validate` | 验证 | `zima workflow validate review` |
| `render` | 渲染模板 | `zima workflow render review --var review-task` |
| `add-var` | 添加变量定义 | `zima workflow add-var review --name task_type` |

#### Workflow 模板示例

```bash
# 创建带模板的 Workflow
zima workflow create \
  --name "Code Review" \
  --code code-review \
  --template "# Review Task: {{ task_name }}

Please review the following code for {{ review_focus }}.

## Context
{{ context }}

## Requirements
- Check for: {{ check_items | join(', ') }}"
```

---

### 1.4 Variable 管理

**命令**: `zima variable <subcommand>`

变量配置管理，用于 Workflow 模板渲染。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `create` | 创建 Variable | `zima variable create --name "Review Var" --code review-var` |
| `list` | 列出 | `zima variable list` |
| `show` | 显示 | `zima variable show review-var` |
| `update` | 更新 | `zima variable update review-var --name "New Name"` |
| `delete` | 删除 | `zima variable delete review-var` |
| `set` | 设置值 | `zima variable set review-var task_name "Bug Fix"` |
| `get` | 获取值 | `zima variable get review-var task_name` |
| `validate` | 验证 | `zima variable validate review-var` |
| `merge` | 合并值 | `zima variable merge review-var --file values.json` |

#### Variable 使用示例

```bash
# 创建变量配置
zima variable create --name "Task Variables" --code task-vars

# 设置变量值
zima variable set task-vars project_name "Zima Blue"
zima variable set task-vars version "2.1.0"
zima variable set task-vars features '["cli", "runner", "scheduler"]'

# 验证变量
zima variable validate task-vars
```

---

### 1.5 Env 管理

**命令**: `zima env <subcommand>`

环境变量配置，支持多种密钥来源 (env/file/vault)。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `create` | 创建 Env | `zima env create --name "Prod Env" --code prod-env` |
| `list` | 列出 | `zima env list` |
| `show` | 显示 | `zima env show prod-env` |
| `update` | 更新 | `zima env update prod-env --name "Production"` |
| `delete` | 删除 | `zima env delete prod-env` |
| `set` | 设置变量 | `zima env set prod-env API_KEY --value secret123` |
| `set-secret` | 设置密钥 | `zima env set-secret prod-env DB_PASS --source env` |
| `unset` | 移除变量 | `zima env unset prod-env API_KEY` |
| `validate` | 验证 | `zima env validate prod-env` |

#### Env 密钥来源

| 来源 | 说明 | 示例 |
|------|------|------|
| `env` | 从环境变量读取 | `--source env` |
| `file` | 从文件读取 | `--source file --source-path /path/to/secret` |
| `vault` | 从密钥库读取 | `--source vault --source-path vault://secret/path` |

---

### 1.6 PMG 管理

**命令**: `zima pmg <subcommand>`

PMG (Parameters Group) 参数组管理，用于动态参数注入。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `create` | 创建 PMG | `zima pmg create --name "Build Params" --code build-params` |
| `list` | 列出 | `zima pmg list` |
| `show` | 显示 | `zima pmg show build-params` |
| `update` | 更新 | `zima pmg update build-params` |
| `delete` | 删除 | `zima pmg delete build-params` |
| `add-param` | 添加参数 | `zima pmg add-param build-params --name timeout` |
| `remove-param` | 移除参数 | `zima pmg remove-param build-params timeout` |
| `validate` | 验证 | `zima pmg validate build-params` |

#### PMG 参数类型

- `string` - 字符串
- `integer` - 整数
- `boolean` - 布尔值
- `array` - 数组
- `object` - 对象

---

### 1.7 PJob 管理

**命令**: `zima pjob <subcommand>`

PJob (Parameterized Job) 是执行层，组合 Agent + Workflow + Variable + Env + PMG 来执行具体任务。

| 子命令 | 功能 | 示例 |
|--------|------|------|
| `create` | 创建 PJob | `zima pjob create --name "Daily Task" --code daily` |
| `list` | 列出 | `zima pjob list --label automated` |
| `show` | 显示详情 | `zima pjob show daily` |
| `update` | 更新 | `zima pjob update daily --timeout 1200` |
| `delete` | 删除 | `zima pjob delete daily --force` |
| `copy` | 复制 | `zima pjob copy daily daily-v2` |
| `run` | 执行 | `zima pjob run daily` |
| `render` | 渲染预览 | `zima pjob render daily --show-command` |
| `validate` | 验证 | `zima pjob validate daily --strict` |
| `history` | 历史记录 | `zima pjob history daily` |

#### PJob Create 详细参数

```bash
zima pjob create [OPTIONS]

Options:
  --name TEXT              PJob 显示名称 (必填)
  --code TEXT              PJob 唯一标识 (必填)
  --agent TEXT             使用的 Agent code (必填)
  --workflow TEXT          使用的 Workflow code (必填)
  --variable TEXT          使用的 Variable code
  --env TEXT               使用的 Env code
  --pmg TEXT               使用的 PMG code
  --label TEXT             标签 (可多次使用)
  --timeout INTEGER        执行超时(秒)
  --from-code TEXT         从现有 PJob 复制
```

#### PJob 执行示例

```bash
# 创建完整配置的 PJob
zima pjob create \
  --name "Code Review Task" \
  --code review-task \
  --agent code-reviewer \
  --workflow code-review \
  --variable review-vars \
  --env prod-env \
  --label automated \
  --label daily

# 渲染预览 (不执行)
zima pjob render review-task --show-command

# 执行 PJob
zima pjob run review-task

# 后台执行（立即返回）
zima pjob run review-task --background
zima pjob run review-task -b

# 后台执行并实时跟踪日志
zima pjob run review-task --background --follow
zima pjob run review-task -b -f

# 执行并覆盖参数
zima pjob run review-task \
  --set-param model=kimi-k2-072515-preview \
  --set-env DEBUG=true

# 查看执行历史
zima pjob history review-task
```

---

## 2. 数据模型接口

### 2.1 AgentConfig

Agent 配置模型，支持多种类型 (kimi/claude/gemini)。

```python
@dataclass
class AgentConfig(BaseConfig):
    kind: str = "Agent"
    type: str = "kimi"                      # kimi / claude / gemini
    parameters: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    
    # 运行时属性
    @property
    def max_execution_time(self) -> int: ...
    @property
    def cycle_interval(self) -> int: ...
    @property
    def max_steps_per_turn(self) -> int: ...
    
    # 方法
    def build_command(prompt_file, work_dir, extra_args) -> list[str]: ...
    def get_cli_command_template(self) -> list[str]: ...
    def validate(self) -> list[str]: ...
```

**Agent 类型参数模板**:

| 类型 | 默认参数 |
|------|----------|
| `kimi` | model, maxStepsPerTurn, maxRalphIterations, maxRetriesPerStep, yolo |
| `claude` | model, maxTurns, plan, acceptEdits |
| `gemini` | model, approvalMode, checkpointing |

### 2.2 WorkflowConfig

Workflow 模板配置。

```python
@dataclass
class WorkflowConfig(BaseConfig):
    kind: str = "Workflow"
    template: str = ""                      # Jinja2 模板
    variables: list[VariableDef] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
```

### 2.3 VariableConfig

变量配置，用于模板渲染。

```python
@dataclass
class VariableConfig(BaseConfig):
    kind: str = "Variable"
    values: dict = field(default_factory=dict)
    schema: dict = field(default_factory=dict)
```

### 2.4 EnvConfig

环境变量配置。

```python
@dataclass
class EnvConfig(BaseConfig):
    kind: str = "Env"
    for_type: str = ""                      # 适用的 Agent 类型
    variables: dict = field(default_factory=dict)
    secrets: list[SecretDef] = field(default_factory=list)
```

### 2.5 PMGConfig

参数组配置。

```python
@dataclass
class PMGConfig(BaseConfig):
    kind: str = "PMG"
    for_types: list[str] = field(default_factory=list)
    parameters: list[ParameterDef] = field(default_factory=list)
    conditions: list[ConditionDef] = field(default_factory=list)
```

### 2.6 PJobConfig

PJob 执行配置。

```python
@dataclass
class PJobConfig(BaseConfig):
    kind: str = "PJob"
    spec: PJobSpec                          # Agent/Workflow/Variable/Env/PMG 引用
    metadata: PJobMetadata                  # 包含 labels 和 annotations
    
@dataclass
class PJobSpec:
    agent: str                              # Agent code (必填)
    workflow: str                           # Workflow code (必填)
    variable: str = ""                      # Variable code
    env: str = ""                           # Env code
    pmg: str = ""                           # PMG code
    overrides: Overrides                    # 运行时覆盖
    execution: ExecutionOptions             # 执行选项
    output: OutputOptions                   # 输出选项
```

### 2.7 结果模型

```python
@dataclass
class RunResult:
    """单次运行结果"""
    status: str                             # completed / failed / timeout
    summary: str = ""
    output: str = ""
    elapsed_time: float = 0.0
    return_code: int = 0

@dataclass
class CycleResult:
    """周期执行结果"""
    cycle_num: int
    status: str
    progress: int                           # 0-100
    summary: str
    details: str
    next_action: str                        # continue / wait / complete / fix
    log_file: Path
    prompt_file: Path
    result_file: Path
    elapsed_time: float
    return_code: int
```

---

## 3. 核心运行接口

### 3.1 AgentRunner (单次执行)

**模块**: `zima.core.runner`

```python
class AgentRunner:
    """单次执行 Agent"""
    
    def __init__(self, config: AgentConfig, agent_dir: Path)
    def run(self) -> RunResult
```

### 3.2 KimiRunner (周期执行)

**模块**: `zima.core.kimi_runner`

```python
class KimiRunner:
    """Kimi CLI 调用封装"""
    
    def __init__(self, config: AgentConfig, agent_dir: Path)
    
    def run_cycle(
        self, 
        prompt: str, 
        cycle_num: int,
        task_name: str = ""
    ) -> CycleResult
    
    def _parse_from_log(self, log_file: Path) -> dict
    def _estimate_progress_from_log(self, log_file: Path) -> int
```

### 3.3 ConfigManager

**模块**: `zima.config.manager`

统一配置管理，支持所有配置类型 (agent/workflow/variable/env/pmg/pjob)。

```python
class ConfigManager:
    KINDS = {"agent", "workflow", "variable", "env", "pmg", "pjob"}
    
    def __init__(self, config_dir: Optional[Path] = None)
    
    # CRUD 操作
    def save_config(self, kind: str, code: str, data: dict) -> Path
    def load_config(self, kind: str, code: str) -> dict
    def delete_config(self, kind: str, code: str) -> bool
    def config_exists(self, kind: str, code: str) -> bool
    
    # 列表操作
    def list_configs(self, kind: str) -> list[dict]
    def list_config_codes(self, kind: str) -> list[str]
    
    # 复制
    def copy_config(self, kind: str, from_code: str, to_code: str, new_name: str = None) -> bool
    
    # 工具
    def get_config_path(self, kind: str, code: str) -> Path
    def get_config_summary(self, kind: str, code: str) -> Optional[dict]
```

---

## 4. 配置文件规范

### 4.1 配置存储结构

```
~/.zima/                                  # ZIMA_HOME
├── config.yaml                           # 全局配置
├── configs/
│   ├── agents/
│   │   ├── code-reviewer.yaml
│   │   └── doc-writer.yaml
│   ├── workflows/
│   │   ├── code-review.yaml
│   │   └── documentation.yaml
│   ├── variables/
│   │   ├── review-vars.yaml
│   │   └── doc-vars.yaml
│   ├── envs/
│   │   ├── dev-env.yaml
│   │   └── prod-env.yaml
│   ├── pmgs/
│   │   └── build-params.yaml
│   └── pjobs/
│       ├── daily-review.yaml
│       └── weekly-report.yaml
└── agents/                               # Agent 运行时目录
    └── <agent-code>/
        ├── logs/
        ├── prompts/
        └── workspace/
```

### 4.2 Agent 配置示例

```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: code-reviewer
  name: Code Reviewer
  description: Review code for quality and bugs
  createdAt: "2026-03-28T10:00:00Z"
  updatedAt: "2026-03-28T10:00:00Z"
spec:
  type: kimi
  parameters:
    model: kimi-k2-072515-preview
    maxStepsPerTurn: 50
    maxRalphIterations: 10
    maxRetriesPerStep: 3
    yolo: true
    workDir: "./workspace"
    outputFormat: text
  defaults:
    workflow: code-review
    variable: review-vars
    env: dev-env
```

### 4.3 Workflow 配置示例

```yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: code-review
  name: Code Review Workflow
  description: Standard code review process
spec:
  template: |
    # Code Review: {{ task_name }}
    
    ## Context
    {{ context }}
    
    ## Files to Review
    {% for file in files %}
    - {{ file }}
    {% endfor %}
    
    ## Checklist
    {% for item in check_items %}
    - [ ] {{ item }}
    {% endfor %}
  variables:
    - name: task_name
      type: string
      required: true
    - name: files
      type: array
      required: true
  tags: ["review", "code-quality"]
```

### 4.4 PJob 配置示例

```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: daily-review
  name: Daily Code Review
  description: Automated daily code review
  labels:
    - automated
    - daily
  annotations:
    priority: high
spec:
  agent: code-reviewer
  workflow: code-review
  variable: review-vars
  env: prod-env
  execution:
    workDir: "./workspace"
    timeout: 900
    retries: 1
  output:
    saveTo: "./output/review-{{ date }}.md"
    format: markdown
```

### 4.5 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ZIMA_HOME` | Zima 主目录 | `~/.zima` |
| `ZIMA_CONFIG_DIR` | 配置目录 | `$ZIMA_HOME/configs` |

---

## 5. 执行流程

### 5.1 PJob 执行完整流程

```
User: zima pjob run <pjob-code>
    ↓
CLI: 加载 PJob 配置
    ↓
PJobConfig: 解析 spec.agent/workflow/variable/env/pmg
    ↓
ConfigManager: 加载引用的所有配置
    ↓
Workflow: 渲染模板 (注入 Variable 值)
    ↓
AgentConfig: 构建 CLI 命令
    ↓
KimiRunner: 执行 subprocess.run(kimi ...)
    ↓
    ├── 启动 MCP 服务
    ├── 读取 prompt 文件
    ├── LLM 推理
    ├── 工具调用 (可选)
    └── 输出结果
    ↓
KimiRunner: 解析日志，提取 JSON 结果
    ↓
CycleResult: 返回执行结果
    ↓
CLI: 显示结果，保存历史
```

### 5.2 单次执行 (简化)

```
zima run <agent-code>
    ↓
AgentRunner.run()
    ↓
subprocess.run(kimi ...)
    ↓
RunResult
```

---

## 6. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.3 | 2026-04-19 | CLI 命令层级重组：移除顶层命令，新增 daemon 子命令组 |
| v2.2 | 2026-03-29 | 新增 PJob 后台执行 (`--background`, `--follow`) 和输出目录自动处理 |
| v2.1 | 2026-03-28 | 新增完整 CLI 命令文档 (agent/workflow/variable/env/pmg/pjob) |
| v2.0 | 2026-03-26 | 简化架构，新增配置实体系统，PJob 执行层 |
| v1.0 | 2026-03-25 | 初始版本，基础 Agent 管理 |

---

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》
