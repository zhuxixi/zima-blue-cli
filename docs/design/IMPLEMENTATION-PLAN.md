# Zima CLI 开发实现方案

> **本文档记录历史实现计划，复选框状态可能未更新。** 最新状态请参考代码和 `docs/API-INTERFACE.md`。

> 基于设计文档的分阶段实现计划

---

## 📋 目录

1. [总体策略](#1-总体策略)
2. [阶段一：基础设施](#阶段一基础设施)
3. [阶段二：Agent 管理](#阶段二agent-管理)
4. [阶段三：其他配置](#阶段三其他配置)
5. [阶段四：PJob 实现](#阶段四pjob-实现)
6. [技术细节](#技术细节)

---

## 1. 总体策略

### 1.1 核心原则

- **渐进式重构**: 保留现有功能，逐步迁移到新架构
- **向后兼容**: 旧版 agent 配置可以继续使用
- **测试驱动**: 每个功能点都有对应的单元测试
- **先数据后界面**: 先实现模型和配置管理，再实现 CLI

### 1.2 代码组织

```
zima/
├── cli.py                    # 主入口，只做命令分发
├── commands/                 # 子命令包
│   ├── __init__.py
│   ├── agent.py             # zima agent *
│   ├── workflow.py          # zima workflow *
│   ├── variable.py          # zima variable *
│   ├── env.py               # zima env *
│   ├── pmg.py               # zima pmg *
│   └── pjob.py              # zima pjob *
├── config/                   # 配置管理
│   ├── __init__.py
│   ├── manager.py           # 配置 CRUD 管理
│   ├── loader.py            # 配置文件加载
│   └── validator.py         # 配置验证
├── models/                   # 数据模型
│   ├── __init__.py
│   ├── agent.py             # AgentConfig
│   ├── workflow.py          # WorkflowConfig
│   ├── variable.py          # VariableConfig
│   ├── env.py               # EnvConfig
│   ├── pmg.py               # PMGConfig
│   └── pjob.py              # PJob 运行时模型
├── core/                     # 核心逻辑
│   ├── __init__.py
│   ├── runner.py            # Agent 执行器
│   ├── builder.py           # 命令构建器
│   └── renderer.py          # 模板渲染
└── utils.py                  # 工具函数
```

---

## 阶段一：基础设施

### 1.1 配置管理基础

**目标**: 建立统一的配置存储和加载机制

**文件**: `zima/config/manager.py`, `zima/config/loader.py`

**实现要点**:

```python
# 配置目录结构
ZIMA_HOME = Path(os.environ.get("ZIMA_HOME", Path.home() / ".zima"))
CONFIG_DIR = ZIMA_HOME / "configs"

# 统一的配置管理类
class ConfigManager:
    """管理所有配置的 CRUD"""
    
    def get_config_path(self, kind: str, code: str) -> Path:
        """获取配置文件路径"""
        return CONFIG_DIR / f"{kind}s" / f"{code}.yaml"
    
    def list_configs(self, kind: str) -> list[dict]:
        """列出所有配置"""
        
    def load_config(self, kind: str, code: str) -> dict:
        """加载配置"""
        
    def save_config(self, kind: str, code: str, data: dict) -> None:
        """保存配置"""
        
    def delete_config(self, kind: str, code: str) -> bool:
        """删除配置"""
        
    def config_exists(self, kind: str, code: str) -> bool:
        """检查配置是否存在"""
```

**验收标准**:
- [ ] 配置目录自动创建
- [ ] 支持增删改查操作
- [ ] 配置变化自动记录 updatedAt
- [ ] 非法 code 格式校验

### 1.2 基础模型定义

**目标**: 定义所有配置的数据类

**文件**: `zima/models/agent.py`, `zima/models/base.py`

**实现要点**:

```python
# 基础配置类
@dataclass
class BaseConfig:
    """所有配置的基类"""
    api_version: str = "zima.io/v1"
    kind: str = ""
    metadata: Metadata = field(default_factory=lambda: Metadata())
    created_at: str = ""
    updated_at: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> "BaseConfig":
        pass
    
    def to_dict(self) -> dict:
        pass

@dataclass  
class Metadata:
    code: str = ""
    name: str = ""
    description: str = ""
```

**验收标准**:
- [ ] 所有模型支持 from_dict/to_dict
- [ ] 支持 YAML 序列化/反序列化
- [ ] 字段类型验证

### 1.3 工具函数

**文件**: `zima/utils.py`

**添加功能**:
- `get_zima_home()` - 获取 Zima 主目录
- `get_config_dir()` - 获取配置目录
- `validate_code(code)` - 验证 code 格式（小写字母、数字、连字符）
- `generate_timestamp()` - 生成 ISO8601 时间戳

---

## 阶段二：Agent 管理

### 2.1 Agent 模型升级

**目标**: 实现新设计的 AgentConfig

**文件**: `zima/models/agent.py`

**实现要点**:

```python
@dataclass
class AgentConfig(BaseConfig):
    """Agent 配置 - 支持多类型"""
    kind: str = "Agent"
    
    # Spec
    type: str = "kimi"  # kimi | claude | gemini
    parameters: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    
    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        agent_type: str,
        description: str = "",
        parameters: dict = None,
        defaults: dict = None
    ) -> "AgentConfig":
        """创建新 Agent 配置"""
        now = generate_timestamp()
        return cls(
            metadata=Metadata(
                code=code,
                name=name,
                description=description
            ),
            type=agent_type,
            parameters=parameters or {},
            defaults=defaults or {},
            created_at=now,
            updated_at=now
        )
    
    def to_yaml(self) -> str:
        """转换为 YAML 字符串"""
        
    @classmethod
    def from_yaml(cls, path: Path) -> "AgentConfig":
        """从 YAML 文件加载"""
        
    def get_cli_command(self) -> list[str]:
        """生成 CLI 启动命令"""
        # 根据 type 返回对应的 CLI 命令模板
```

**验收标准**:
- [ ] 支持所有 Agent 类型
- [ ] 参数校验（必填字段、类型检查）
- [ ] 生成正确的 CLI 命令预览

### 2.2 Agent CLI 命令

**目标**: 实现 `zima agent` 子命令

**文件**: `zima/commands/agent.py`

**命令列表**:

#### `zima agent create`

```python
@app.command()
def create(
    name: str = typer.Option(..., "--name", "-n", help="显示名称"),
    code: str = typer.Option(..., "--code", "-c", help="唯一编码"),
    type: str = typer.Option("kimi", "--type", "-t", help="类型"),
    description: str = typer.Option("", "--description", "-d"),
    from_code: Optional[str] = typer.Option(None, "--from", help="复制现有配置"),
    interactive: bool = typer.Option(False, "--interactive", "-i"),
):
    """创建新 Agent"""
    # 1. 验证 code 格式
    # 2. 检查 code 是否已存在
    # 3. 如果 --from，复制现有配置
    # 4. 创建配置对象
    # 5. 保存到文件
    # 6. 输出成功信息
```

#### `zima agent update`

```python
@app.command()
def update(
    code: str = typer.Argument(..., help="Agent code"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    set_param: Optional[list[str]] = typer.Option(None, "--set-param", "-p"),
    remove_param: Optional[list[str]] = typer.Option(None, "--remove-param", "-r"),
):
    """更新 Agent 配置"""
    # 1. 加载现有配置
    # 2. 应用修改
    # 3. 保存回文件
```

#### `zima agent delete`

```python
@app.command()
def delete(
    code: str = typer.Argument(..., help="Agent code"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """删除 Agent"""
    # 1. 确认配置存在
    # 2. 检查是否有 pjob 引用（可选）
    # 3. 删除文件
```

#### `zima agent list`

```python
@app.command()
def list(
    type: Optional[str] = typer.Option(None, "--type", "-t"),
    format: str = typer.Option("table", "--format"),
):
    """列出所有 Agent"""
    # 1. 加载所有 Agent 配置
    # 2. 按类型过滤
    # 3. 格式化输出
```

#### `zima agent show`

```python
@app.command()
def show(
    code: str = typer.Argument(..., help="Agent code"),
    format: str = typer.Option("yaml", "--format"),
):
    """查看 Agent 详情"""
    # 1. 加载配置
    # 2. 格式化输出
```

#### `zima agent edit`

```python
@app.command()
def edit(
    code: str = typer.Argument(..., help="Agent code"),
):
    """使用系统编辑器编辑"""
    # 1. 获取配置文件路径
    # 2. 调用系统编辑器
    # 3. 验证修改后的配置
```

#### `zima agent validate`

```python
@app.command()
def validate(
    code: str = typer.Argument(..., help="Agent code"),
):
    """验证配置有效性"""
    # 1. 加载配置
    # 2. 检查必填字段
    # 3. 检查参数合法性
    # 4. 输出验证结果
```

#### `zima agent test`

```python
@app.command()
def test(
    code: str = typer.Argument(..., help="Agent code"),
    workflow: Optional[str] = typer.Option(None, "--workflow", "-w"),
    variable: Optional[str] = typer.Option(None, "--variable", "-v"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    pmg: Optional[str] = typer.Option(None, "--pmg", "-p"),
):
    """测试 Agent 启动命令（不实际执行）"""
    # 1. 加载 Agent 配置
    # 2. 加载关联配置
    # 3. 构建完整命令
    # 4. 输出预览
```

### 2.3 测试覆盖

**文件**: `tests/test_agent_commands.py`, `tests/test_agent_model.py`

**测试用例**:
- [ ] `test_agent_create_success` - 正常创建
- [ ] `test_agent_create_duplicate_code` - 重复 code 报错
- [ ] `test_agent_create_invalid_code` - 非法 code 格式
- [ ] `test_agent_update_params` - 更新参数
- [ ] `test_agent_delete` - 删除
- [ ] `test_agent_list_filter` - 列表过滤
- [ ] `test_agent_validate` - 验证配置
- [ ] `test_agent_test_command` - 测试命令生成

---

## 阶段三：其他配置

### 3.1 Workflow 管理

**目标**: 实现 `zima workflow` 命令

**依赖**: 模板渲染引擎 (Jinja2)

**实现顺序**:
1. WorkflowConfig 模型
2. 模板渲染器
3. CLI 命令

### 3.2 Variable 管理

**目标**: 实现 `zima variable` 命令

### 3.3 Env 管理

**目标**: 实现 `zima env` 命令

**特殊功能**: Secrets 管理

### 3.4 PMG 管理

**目标**: 实现 `zima pmg` 命令

**特殊功能**: 参数继承、条件渲染

---

## 阶段四：PJob 实现

### 4.1 PJob 运行时

**目标**: 实现配置组合和命令执行

**核心功能**:
- 配置组合（Agent + Workflow + Variable + Env + PMG）
- 模板渲染（Workflow + Variable → Prompt）
- 命令构建（Agent + PMG → CLI Command）
- 执行环境设置（Env）

### 4.2 PJob CLI

**命令**: `zima pjob create/run/list/show/logs`

---

## 技术细节

### 错误处理

统一错误类型:

```python
class ZimaError(Exception):
    """Base error"""
    pass

class ConfigNotFoundError(ZimaError):
    """配置不存在"""
    pass

class ConfigValidationError(ZimaError):
    """配置验证失败"""
    pass

class DuplicateCodeError(ZimaError):
    """code 已存在"""
    pass
```

### 输出样式

使用 Rich 库美化输出:

```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

# 成功信息
console.print("[green]✓[/green] Agent created successfully")

# 错误信息
console.print("[red]✗[/red] Config not found: xxx")

# 表格
console.print(Table(...))

# YAML 高亮
console.print(Syntax(yaml_content, "yaml"))
```

### 配置验证

使用 Pydantic 进行验证:

```python
from pydantic import BaseModel, validator, Field

class AgentSpec(BaseModel):
    type: str = Field(..., regex="^(kimi|claude|gemini)$")
    parameters: dict = Field(default_factory=dict)
    
    @validator('type')
    def validate_type(cls, v):
        if v not in AGENT_TYPES:
            raise ValueError(f"Unknown type: {v}")
        return v
```

---

## 附录：实现检查清单

### 第一阶段
- [ ] ConfigManager 实现
- [ ] BaseConfig 和 Metadata 模型
- [ ] 工具函数
- [ ] 单元测试

### 第二阶段（Agent）
- [ ] AgentConfig 模型
- [ ] agent create
- [ ] agent update
- [ ] agent delete
- [ ] agent list
- [ ] agent show
- [ ] agent edit
- [ ] agent validate
- [ ] agent test
- [ ] 单元测试

### 第三阶段
- [ ] Workflow 完整实现
- [ ] Variable 完整实现
- [ ] Env 完整实现
- [ ] PMG 完整实现

### 第四阶段
- [ ] PJob 运行时
- [ ] PJob CLI
- [ ] 集成测试

---

> "从简单开始，逐步完善。" —— Zima Blue
