# Data & Runtime Reference（内部参考）

> Migrated from docs/API-INTERFACE.md §2/§3/§5 (2026-09-05); CLI command tables were superseded by the generated docs/cli-reference.md.

本文保留原 API-INTERFACE 的数据模型、核心运行接口与执行流程章节，供内部开发参考。已按当前代码修正明显漂移处（以 `[2026-09 漂移修正]` 标注）。

---

## 2. 数据模型接口

### 2.1 AgentConfig

Agent 配置模型，支持多种类型 (kimi/claude/pi)。`[2026-09 漂移修正: gemini 类型已被 pi 取代，见 zima/models/agent.py VALID_AGENT_TYPES]`

```python
@dataclass
class AgentConfig(BaseConfig):
    kind: str = "Agent"
    type: str = "kimi"                      # kimi / claude / pi
    parameters: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)

    # 方法
    def build_command(prompt_file, work_dir, extra_args) -> list[str]: ...
    def get_cli_command_template(self) -> list[str]: ...
    def validate(self) -> list[str]: ...
```

**Agent 类型参数模板**（默认参数见 `zima/models/agent.py::AGENT_PARAMETER_TEMPLATES`）:

| 类型 | 默认参数 |
|------|----------|
| `kimi` | addDirs, outputFormat |
| `claude` | maxTurns, permissionMode, outputFormat, allowedTools, workDir, addDirs |
| `pi` | provider, model, thinking, noSession, outputFormat, tools |

`[2026-09 漂移修正: 原表中的 kimi maxStepsPerTurn/maxRalphIterations/maxRetriesPerStep/yolo 与 gemini approvalMode/checkpointing 行已与当前模板不符，按代码更新；v1 运行时属性（max_execution_time/cycle_interval/max_steps_per_turn）仍作为 AgentConfig 的 property 保留（zima/models/agent.py，供 legacy kimi_runner 周期路径使用），故未列入 v2 参数模板表——v2 参数模板面才是当前默认路径。]`

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
    actions: ActionsConfig                  # preExec / postExec 动作配置
```

`[2026-09 漂移修正: PJobSpec 补充 actions: ActionsConfig 字段（zima/models/pjob.py），覆盖 scan_pr 等 preExec 动作与 add_label/add_comment 等 postExec 动作]`

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

`[2026-09 漂移修正: zima/core/runner 模块与 AgentRunner 类在当前代码中不存在——v1 的 AgentRunner 已随 v2 单次执行模型（ADR 004）移除，单次执行由 PJobExecutor（zima/execution/executor.py）承担。以下保留原文仅作历史参考。]`

**模块**: `zima.core.runner`（已移除）

```python
class AgentRunner:
    """单次执行 Agent（v1，已移除）"""

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

统一配置管理，支持所有配置类型 (agent/workflow/variable/env/pmg/pjob/schedule)。`[2026-09 漂移修正: KINDS 补充 schedule]`

```python
class ConfigManager:
    KINDS = {"agent", "workflow", "variable", "env", "pmg", "pjob", "schedule"}

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

## 5. 执行流程

### 5.1 PJob 执行完整流程

`[2026-09 漂移修正: 原流程早于 preExec/postExec actions 与后台执行机制（background_runner），已补充对应步骤；v2 中由 PJobExecutor 组装执行（zima/execution/executor.py），后台运行经 zima/execution/background_runner 派生 detached 子进程]`

```
User: zima pjob run <pjob-code>
    ↓
CLI: 加载 PJob 配置
    ↓
PJobConfig: 解析 spec.agent/workflow/variable/env/pmg
    ↓
ConfigManager: 加载引用的所有配置 (ConfigBundle)
    ↓
ActionsRunner: 执行 preExec actions (如 scan_pr)
    ├── 发现无可执行目标 → SkipAction → 状态 SKIPPED，流程结束
    ↓
Workflow: 渲染模板 (注入 Variable 值)
    ↓
AgentConfig: 构建 CLI 命令
    ↓
后台执行: spawn zima.execution.background_runner (detached，记录 PID/状态)
    ↓
PJobExecutor: 执行 subprocess (kimi / claude / pi ...)
    ├── 启动 Agent CLI
    ├── 读取 prompt 文件
    ├── LLM 推理
    ├── 工具调用 (可选)
    └── 输出结果
    ↓
ReviewParser: 解析 <zima-review> XML（reviewer 类 PJob，映射有效返回码）
    ↓
ActionsRunner: finally 块中执行 postExec actions (如 add_label / add_comment)
    ↓
ExecutionHistory: 记录执行历史 (history/pjobs/<code>/<id>.json)
    ↓
CLI: 显示结果，保存历史
```

### 5.2 单次执行 (简化)

```
zima run <agent-code>                    [2026-09 漂移修正: v1 入口，v2 已由 zima pjob run 取代]
    ↓
AgentRunner.run()                         (v1，已移除)
    ↓
subprocess.run(kimi ...)
    ↓
RunResult
```
