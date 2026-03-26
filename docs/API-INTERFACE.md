# Zima CLI 接口设计文档

> 本文档列出 zima CLI 的所有接口，从接口层开始设计。

---

## 📁 目录

1. [CLI 命令接口](#1-cli-命令接口)
2. [数据模型接口](#2-数据模型接口)
3. [核心运行接口](#3-核心运行接口)
4. [守护进程接口](#4-守护进程接口)
5. [工具函数接口](#5-工具函数接口)
6. [配置文件规范](#6-配置文件规范)

---

## 1. CLI 命令接口

**模块**: `zima.cli`

### 1.1 命令概览

| 命令 | 功能 | 状态 |
|------|------|------|
| `zima create` | 创建新 Agent | ✅ 已实现 |
| `zima run` | 单次执行 Agent | ✅ 已实现 |
| `zima list` | 列出所有 Agent | ✅ 已实现 |
| `zima show` | 查看 Agent 配置 | ✅ 已实现 |
| `zima logs` | 查看 Agent 日志 | ✅ 已实现 |

### 1.2 详细接口

#### `zima create <name>`

创建一个新的 Agent。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Agent 名称 |
| `--workspace`, `-w` | Path | ❌ | 自定义工作目录 |
| `--prompt`, `-p` | Path | ❌ | 自定义 Prompt 文件 |

**示例**:
```bash
zima create my-agent
zima create my-agent --workspace ./custom-workspace
zima create my-agent --prompt ./custom-prompt.md
```

**输出**:
```
✓ Created agent 'my-agent'
  Directory: ~/.zima/agents/my-agent
  Workspace: ~/.zima/agents/my-agent/workspace

Edit ~/.zima/agents/my-agent/agent.yaml to configure
```

---

#### `zima run <name>`

单次执行 Agent。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Agent 名称 |
| `--timeout`, `-t` | int | ❌ | 最大执行时间(秒)，覆盖配置 |

**示例**:
```bash
zima run my-agent
zima run my-agent --timeout 600
```

**输出**:
```
🚀 Starting agent: my-agent
   Workspace: /home/user/.zima/agents/my-agent/workspace
   Log: /home/user/.zima/agents/my-agent/logs/run_20260325_143022.log

Result:
  Status: completed
  Time: 45.3s
  Summary: Agent finished with status: completed
```

---

#### `zima list`

列出所有 Agent。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--verbose`, `-v` | bool | ❌ | 显示详细信息 |

**示例**:
```bash
zima list
zima list -v
```

**输出**:
```
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name        ┃ Description                          ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ my-agent    │ Auto-generated agent                 │
│ test-agent  │ Test coverage agent                  │
└─────────────┴──────────────────────────────────────┘
```

---

#### `zima show <name>`

查看 Agent 详细配置。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Agent 名称 |

**示例**:
```bash
zima show my-agent
```

**输出**:
```
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Property        ┃ Value                               ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Name            │ my-agent                            │
│ Description     │ Auto-generated agent                │
│ Workspace       │ ~/.zima/agents/my-agent/workspace   │
│ Prompt File     │ prompt.md                           │
│ Max Time        │ 900s                                │
│ Max Steps/Turn  │ 50                                  │
│ Max Ralph Iter  │ 10                                  │
└─────────────────┴─────────────────────────────────────┘
```

---

#### `zima logs <name>`

查看 Agent 日志。

**参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | ✅ | - | Agent 名称 |
| `--lines`, `-n` | int | ❌ | 20 | 显示行数 |

**示例**:
```bash
zima logs my-agent
zima logs my-agent -n 50
```

---

## 2. 数据模型接口

**模块**: `zima.models`

### 2.1 AgentConfig

Agent 配置模型。

```python
@dataclass
class AgentConfig:
    """Agent configuration - manages Kimi CLI launch parameters"""
    
    # Metadata (核心元数据)
    name: str                           # Agent 名称
    description: str = ""               # Agent 描述
    
    # Workspace (工作目录)
    workspace: Path                     # 工作目录路径
    
    # Prompt Configuration (提示词配置)
    prompt_file: str = "prompt.md"      # 主提示词文件
    prompt_vars: dict                   # 提示词变量
    
    # Kimi CLI Parameters (Kimi 启动参数)
    max_execution_time: int = 900       # 最大执行时间(秒)
    max_steps_per_turn: int = 50        # 每轮最大步数
    max_ralph_iterations: int = 10      # Ralph迭代次数
```

**方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `from_yaml` | `classmethod from_yaml(path: Path) -> AgentConfig` | 从 YAML 文件加载配置 |
| `get_kimi_cmd` | `get_kimi_cmd(agent_dir: Path) -> list[str]` | 生成 kimi CLI 命令 |

---

### 2.2 AgentState

Agent 状态模型。

```python
@dataclass
class AgentState:
    """Minimal agent state"""
    
    agent_id: str                       # Agent ID
    status: str = "idle"                # 状态: idle, running, completed, failed
    created_at: Optional[str] = None    # 创建时间
    updated_at: Optional[str] = None    # 更新时间
    last_run: Optional[dict] = None     # 上次运行记录
```

**方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `to_dict` | `to_dict() -> dict` | 转换为字典 |
| `from_dict` | `classmethod from_dict(data: dict) -> AgentState` | 从字典创建 |

---

### 2.3 RunResult

单次运行结果模型。

```python
@dataclass
class RunResult:
    """Result of a single run"""
    
    status: str                         # 状态: completed, failed, timeout
    summary: str = ""                   # 执行摘要
    output: str = ""                    # stdout内容
    elapsed_time: float = 0.0           # 执行耗时
    return_code: int = 0                # 返回码
    timestamp: str                      # 时间戳
```

**方法**:

| 方法 | 签名 | 说明 |
|------|------|------|
| `to_dict` | `to_dict() -> dict` | 转换为字典 |

---

### 2.4 CycleResult (历史遗留)

周期执行结果模型（用于 daemon 模式）。

```python
@dataclass
class CycleResult:
    """Result of a single execution cycle"""
    
    cycle_num: int                      # 周期编号
    status: str                         # 状态
    progress: int                       # 进度 0-100
    summary: str                        # 摘要
    details: str                        # 详情
    next_action: str                    # 下一步动作
    log_file: Path                      # 日志文件路径
    prompt_file: Path                   # Prompt 文件路径
    result_file: Optional[Path]         # 结果文件路径
    elapsed_time: float                 # 耗时
    return_code: int                    # 返回码
```

---

## 3. 核心运行接口

### 3.1 AgentRunner

**模块**: `zima.core.runner`

单次执行 Agent 的运行器。

```python
class AgentRunner:
    """Runs agent once via kimi-cli"""
    
    def __init__(self, config: AgentConfig, agent_dir: Path)
    def run(self) -> RunResult
```

**使用示例**:
```python
from zima.models import AgentConfig
from zima.core import AgentRunner

config = AgentConfig.from_yaml(Path("./agent.yaml"))
runner = AgentRunner(config, Path("./my-agent"))
result = runner.run()

print(f"Status: {result.status}")
print(f"Time: {result.elapsed_time}s")
```

---

### 3.2 KimiRunner

**模块**: `zima.core.kimi_runner`

Kimi CLI 调用封装（用于 daemon 模式）。

```python
class KimiRunner:
    """Runs kimi-cli via subprocess"""
    
    def __init__(self, config: AgentConfig, agent_dir: Path)
    
    def run_cycle(
        self, 
        prompt: str, 
        cycle_num: int,
        task_name: str = ""
    ) -> CycleResult
```

---

### 3.3 StateManager

**模块**: `zima.core.state_manager`

Agent 状态持久化管理。

```python
class StateManager:
    """Manages agent state persistence"""
    
    def __init__(self, agent_dir: Path)
    
    # 状态管理
    def load_state(self) -> AgentState
    def save_state(self, state: AgentState) -> None
    
    # Session 管理
    def create_session(
        self,
        cycle_num: int,
        agent_name: str,
        task: str,
        execution: str,
        result: str,
        learnings: str = "",
        next_steps: str = ""
    ) -> Path
    
    def get_recent_sessions(self, count: int = 3) -> list[str]
    
    # Checkpoint 管理
    def create_checkpoint(
        self, 
        state: AgentState, 
        progress: int, 
        log_file: Path
    ) -> Path
    
    def get_latest_checkpoint(self) -> Optional[dict]
```

---

### 3.4 CycleScheduler

**模块**: `zima.core.scheduler`

周期调度器（用于 daemon 模式）。

```python
class CycleScheduler:
    """15-minute cycle scheduler for agent execution"""
    
    def __init__(
        self,
        config: AgentConfig,
        runner: KimiRunner,
        state_manager: StateManager
    )
    
    def run(self) -> None          # 启动调度循环
    def stop(self) -> None         # 停止调度器
```

---

## 4. 守护进程接口

### 4.1 Daemon 管理函数

**模块**: `zima.core.daemon`

```python
def start_daemon(agent_dir: Path) -> int:
    """Start an agent as a background process"""
    
def stop_daemon(agent_dir: Path) -> bool:
    """Stop a running daemon"""
    
def is_daemon_running(agent_dir: Path) -> bool:
    """Check if daemon is running"""
```

### 4.2 Daemon Runner

**模块**: `zima.daemon_runner`

守护进程入口模块。

```bash
# 启动守护进程
python -m zima.daemon_runner <agent_dir>
```

---

## 5. 工具函数接口

**模块**: `zima.utils`

```python
def safe_print(text: str) -> None:
    """Print text safely handling encoding issues on Windows"""

def icon(name: str) -> str:
    """Get an icon (or empty string on Windows to avoid encoding issues)
    
    Available icons:
    - "rocket": 🚀
    - "stop": ⏹️
    - "cycle": 🌅
    - "task": 🎯
    - "result": 📊
    - "sleep": 💤
    - "complete": 🎉
    - "warning": ⚠️
    - "check": ✓
    - "cross": ✗
    """
```

---

## 6. 配置文件规范

### 6.1 Agent 配置 (agent.yaml)

```yaml
metadata:
  name: <agent-name>
  description: <description>

spec:
  workspace: ./workspace           # 工作目录(相对 agent 目录)
  prompt:
    file: prompt.md                # Prompt 文件
    vars: {}                       # Prompt 变量
  execution:
    maxTime: 900                   # 最大执行时间(秒)
    maxStepsPerTurn: 50            # 每轮最大步数
    maxRalphIterations: 10         # Ralph 迭代次数
```

### 6.2 Agent 目录结构

```
~/.zima/agents/<agent-name>/
├── agent.yaml          # 配置文件
├── prompt.md           # Prompt 模板
├── workspace/          # 工作目录
│   └── .zima/          # 运行时数据
├── logs/               # 日志目录
│   └── run_*.log
├── prompts/            # 运行时 Prompt 文件(daemon 模式)
├── sessions/           # Session 记录
├── checkpoints/        # 检查点文件
└── state.json          # 状态文件
```

### 6.3 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ZIMA_HOME` | Zima 主目录 | `~/.zima` |

---

## 7. 接口调用流程

### 7.1 单次执行流程

```
CLI (zima run)
    ↓
AgentConfig.from_yaml()  # 加载配置
    ↓
AgentRunner.run()        # 执行
    ↓
    ├── 生成 kimi 命令
    ├── subprocess.run() # 调用 kimi-cli
    ├── 捕获输出到日志
    └── 解析结果
    ↓
RunResult                # 返回结果
```

### 7.2 Daemon 执行流程

```
CLI (zima daemon start)
    ↓
start_daemon()           # 启动守护进程
    ↓
python -m zima.daemon_runner
    ↓
CycleScheduler.run()     # 调度循环
    ↓
    ├── KimiRunner.run_cycle()  # 执行周期
    │       └── subprocess.run(kimi)
    ├── StateManager.save_state()
    └── sleep(cycle_interval)
```

---

## 8. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.0 | 2026-03-26 | 简化架构，移除 daemon 模式，改为单次执行 |
| v1.0 | 2026-03-26 | 初始版本，支持 daemon 模式和周期调度 |

---

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》
