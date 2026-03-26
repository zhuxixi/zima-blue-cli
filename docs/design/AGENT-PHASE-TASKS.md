# Agent 阶段详细任务清单

> Agent 管理功能的逐步实现指南

---

## 📋 当前状态

现有代码：
- `zima/cli.py` - 旧版命令（create/run/list/show/logs）
- `zima/models/agent.py` - 旧版模型（仅支持 Kimi）
- 配置文件存储在 `~/.zima/agents/{name}/`

目标架构：
- 新命令：`zima agent [create|update|delete|list|show|edit|validate|test]`
- 新模型：支持多类型（kimi/claude/gemini/openai/custom）
- 配置文件存储在 `~/.zima/configs/agents/{code}.yaml`

---

## 任务 1：基础设施搭建

### 1.1 创建目录结构

```bash
# 创建新的代码目录
mkdir -p zima/commands
mkdir -p zima/config
mkdir -p tests/commands
```

### 1.2 实现工具函数（zima/utils.py 补充）

```python
def get_zima_home() -> Path:
    """获取 Zima 主目录"""
    
def get_config_dir() -> Path:
    """获取配置目录"""
    
def get_agents_config_dir() -> Path:
    """获取 Agents 配置目录"""
    
def validate_code(code: str) -> bool:
    """验证 code 格式（小写字母、数字、连字符）"""
    # 正则: ^[a-z][a-z0-9-]*$
    
def generate_timestamp() -> str:
    """生成 ISO8601 时间戳"""
    
def ensure_dir(path: Path) -> Path:
    """确保目录存在，不存在则创建"""
```

**验收**：所有工具函数有单元测试

---

## 任务 2：配置管理器（zima/config/manager.py）

### 2.1 实现 ConfigManager 类

```python
class ConfigManager:
    """统一配置管理"""
    
    KINDS = ["agent", "workflow", "variable", "env", "pmg"]
    
    def __init__(self, config_dir: Path = None):
        self.config_dir = config_dir or get_config_dir()
        
    def _get_kind_dir(self, kind: str) -> Path:
        """获取某类配置的目录"""
        return self.config_dir / f"{kind}s"
        
    def get_config_path(self, kind: str, code: str) -> Path:
        """获取配置文件路径"""
        return self._get_kind_dir(kind) / f"{code}.yaml"
        
    def list_configs(self, kind: str) -> list[dict]:
        """
        列出所有配置
        返回: [{"code": "xxx", "name": "xxx", "metadata": {...}}, ...]
        """
        
    def load_config(self, kind: str, code: str) -> dict:
        """加载配置为字典"""
        
    def save_config(self, kind: str, code: str, data: dict) -> None:
        """保存配置"""
        # 自动更新 updated_at
        
    def delete_config(self, kind: str, code: str) -> bool:
        """删除配置，成功返回 True"""
        
    def config_exists(self, kind: str, code: str) -> bool:
        """检查配置是否存在"""
        
    def copy_config(self, kind: str, from_code: str, to_code: str, 
                    new_name: str = None) -> bool:
        """复制配置"""
```

**验收**：
- [ ] 配置目录自动创建
- [ ] YAML 读写正常
- [ ] updated_at 自动更新
- [ ] 100% 单元测试覆盖

---

## 任务 3：基础模型（zima/models/base.py）

### 3.1 实现 Metadata 类

```python
@dataclass
class Metadata:
    code: str = ""
    name: str = ""  
    description: str = ""
```

### 3.2 实现 BaseConfig 抽象类

```python
@dataclass
class BaseConfig:
    api_version: str = "zima.io/v1"
    kind: str = ""
    metadata: Metadata = field(default_factory=Metadata)
    created_at: str = ""
    updated_at: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> "BaseConfig":
        """从字典创建"""
        
    def to_dict(self) -> dict:
        """转为字典"""
        
    def to_yaml(self) -> str:
        """转为 YAML 字符串"""
        
    @classmethod
    def from_yaml_file(cls, path: Path) -> "BaseConfig":
        """从 YAML 文件加载"""
        
    def save_to_file(self, path: Path) -> None:
        """保存到文件"""
```

**验收**：
- [ ] 序列化/反序列化正确
- [ ] 支持嵌套对象（Metadata）
- [ ] YAML 格式规范

---

## 任务 4：Agent 模型（zima/models/agent.py 重构）

### 4.1 实现新的 AgentConfig

```python
@dataclass
class AgentConfig(BaseConfig):
    """Agent 配置"""
    kind: str = "Agent"
    
    # Spec 字段
    type: str = "kimi"  # kimi | claude | gemini | openai | custom
    parameters: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    
    # 类型特定参数的默认值模板
    PARAMETER_TEMPLATES = {
        "kimi": {
            "model": "kimi-k2-072515-preview",
            "maxStepsPerTurn": 50,
            "maxRalphIterations": 10,
            "yolo": True,
        },
        "claude": {
            "model": "claude-sonnet-4-6",
            "maxTurns": 100,
        },
        "gemini": {
            "model": "gemini-2.5-flash",
            "approvalMode": "default",
        },
        "openai": {
            "model": "gpt-4o",
        },
        "custom": {}
    }
    
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
        """工厂方法：创建新 Agent"""
        now = generate_timestamp()
        # 合并默认参数
        merged_params = cls.PARAMETER_TEMPLATES.get(agent_type, {}).copy()
        if parameters:
            merged_params.update(parameters)
            
        return cls(
            metadata=Metadata(
                code=code,
                name=name,
                description=description
            ),
            type=agent_type,
            parameters=merged_params,
            defaults=defaults or {},
            created_at=now,
            updated_at=now
        )
    
    def validate(self) -> list[str]:
        """验证配置，返回错误列表（空列表表示验证通过）"""
        errors = []
        if not self.metadata.code:
            errors.append("metadata.code is required")
        if self.type not in self.PARAMETER_TEMPLATES:
            errors.append(f"unknown type: {self.type}")
        return errors
    
    def get_cli_template(self) -> list[str]:
        """
        返回 CLI 命令模板
        例如 kimi: ["kimi", "--print", "--prompt", "{prompt_file}"]
        """
        templates = {
            "kimi": ["kimi", "--print", "--yolo"],
            "claude": ["claude", "--print"],
            "gemini": ["gemini", "-y"],
            "openai": ["openai"],
            "custom": []
        }
        return templates.get(self.type, [])
    
    def build_command(
        self,
        prompt_file: Path = None,
        work_dir: Path = None,
        extra_params: dict = None
    ) -> list[str]:
        """构建完整命令"""
        # 基础命令
        cmd = self.get_cli_template()
        
        # 添加参数
        params = self.parameters.copy()
        if extra_params:
            params.update(extra_params)
        
        # 根据类型生成对应的参数
        if self.type == "kimi":
            if params.get("model"):
                cmd.extend(["--model", params["model"]])
            if params.get("maxStepsPerTurn"):
                cmd.extend(["--max-steps-per-turn", str(params["maxStepsPerTurn"])])
            # ... 其他参数
        
        # 添加通用参数
        if prompt_file:
            cmd.extend(["--prompt", str(prompt_file)])
        if work_dir:
            cmd.extend(["--work-dir", str(work_dir)])
            
        return cmd
```

### 4.2 兼容旧版配置

```python
def migrate_old_config(old_config_path: Path) -> AgentConfig:
    """将旧版配置迁移到新版"""
    # 读取旧版 agent.yaml
    # 转换为新版 AgentConfig
    # 保存到新的位置（configs/agents/）
```

**验收**：
- [ ] 支持所有 Agent 类型
- [ ] 参数模板正确
- [ ] 命令构建正确
- [ ] 旧版配置可迁移

---

## 任务 5：Agent CLI 命令（zima/commands/agent.py）

### 5.1 创建命令入口

```python
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

app = typer.Typer(name="agent", help="Agent management")
console = Console()

# 后续在这里添加各个命令
```

### 5.2 实现 create 命令

```python
@app.command()
def create(
    name: str = typer.Option(..., "--name", "-n", help="显示名称"),
    code: str = typer.Option(..., "--code", "-c", help="唯一编码（小写字母、数字、连字符）"),
    type: str = typer.Option("kimi", "--type", "-t", help="类型: kimi/claude/gemini/openai/custom"),
    description: str = typer.Option("", "--description", "-d"),
    from_code: Optional[str] = typer.Option(None, "--from", help="复制现有配置"),
    # 常用参数快速设置
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    work_dir: Optional[str] = typer.Option(None, "--work-dir", "-w"),
):
    """创建新 Agent"""
    # 1. 验证 code 格式
    if not validate_code(code):
        console.print(f"[red]✗[/red] Invalid code format: '{code}'")
        console.print("   Code must start with lowercase letter, contain only lowercase letters, numbers, and hyphens")
        raise typer.Exit(1)
    
    # 2. 检查是否已存在
    manager = ConfigManager()
    if manager.config_exists("agent", code):
        console.print(f"[red]✗[/red] Agent with code '{code}' already exists")
        raise typer.Exit(1)
    
    # 3. 处理 --from
    if from_code:
        if not manager.config_exists("agent", from_code):
            console.print(f"[red]✗[/red] Source agent '{from_code}' not found")
            raise typer.Exit(1)
        # 复制配置
        source = manager.load_config("agent", from_code)
        source["metadata"]["code"] = code
        source["metadata"]["name"] = name
        if description:
            source["metadata"]["description"] = description
        manager.save_config("agent", code, source)
        console.print(f"[green]✓[/green] Agent '{code}' created from '{from_code}'")
        return
    
    # 4. 创建新配置
    params = {}
    if model:
        params["model"] = model
    if work_dir:
        params["workDir"] = work_dir
        
    config = AgentConfig.create(
        code=code,
        name=name,
        agent_type=type,
        description=description,
        parameters=params
    )
    
    # 5. 保存
    manager.save_config("agent", code, config.to_dict())
    
    # 6. 输出
    console.print(f"[green]✓[/green] Agent '{code}' created successfully")
    console.print(f"   Name: {name}")
    console.print(f"   Type: {type}")
    console.print(f"   File: {manager.get_config_path('agent', code)}")
```

### 5.3 实现其他命令

每个命令的实现模式类似：

```python
@app.command()
def list(
    type: Optional[str] = typer.Option(None, "--type", "-t"),
    format: str = typer.Option("table", "--format", help="table/json"),
):
    """列出所有 Agent"""
    
@app.command()
def show(
    code: str = typer.Argument(..., help="Agent code"),
    format: str = typer.Option("yaml", "--format", help="yaml/json"),
):
    """查看 Agent 详情"""
    
@app.command()
def update(
    code: str = typer.Argument(..., help="Agent code"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    set_param: Optional[list[str]] = typer.Option(None, "--set-param", "-p"),
):
    """更新 Agent 配置"""
    
@app.command()
def delete(
    code: str = typer.Argument(..., help="Agent code"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """删除 Agent"""
    
@app.command()
def edit(
    code: str = typer.Argument(..., help="Agent code"),
):
    """使用系统编辑器编辑配置"""
    
@app.command()
def validate(
    code: str = typer.Argument(..., help="Agent code"),
):
    """验证配置有效性"""
    
@app.command()
def test(
    code: str = typer.Argument(..., help="Agent code"),
    workflow: Optional[str] = typer.Option(None, "--workflow", "-w"),
    variable: Optional[str] = typer.Option(None, "--variable", "-v"),
    env: Optional[str] = typer.Option(None, "--env", "-e"),
    pmg: Optional[str] = typer.Option(None, "--pmg", "-p"),
):
    """测试 Agent 启动命令（预览，不执行）"""
```

---

## 任务 6：注册新命令（zima/cli.py 修改）

### 6.1 添加子命令注册

```python
from zima.commands import agent as agent_cmd

# 在 app 创建后添加
app.add_typer(agent_cmd.app, name="agent")

# 保留旧命令作为兼容层（可选）
# @app.command()
# def create(...):  # 旧版命令，可以添加弃用警告
```

---

## 任务 7：测试

### 7.1 单元测试

```python
# tests/test_config_manager.py
# tests/test_models_agent.py
# tests/test_commands_agent.py

# 使用 pytest + pytest-mock
```

### 7.2 集成测试

```bash
# 手动测试脚本
zima agent create -n "测试" -c test-agent -t kimi
zima agent list
zima agent show test-agent
zima agent test test-agent
zima agent delete test-agent -f
```

---

## 附录：快速开始命令

### 创建 Kimi Agent
```bash
zima agent create -n "Kimi 代码审查" -c kimi-review -t kimi --model kimi-k2-072515-preview
```

### 创建 Claude Agent（使用第三方代理）
```bash
zima agent create -n "Claude GLM代理" -c claude-glm -t claude --model claude-sonnet-4-6
```

### 从现有配置复制
```bash
zima agent create -n "生产环境" -c prod-agent --from dev-agent
```

### 预览启动命令
```bash
zima agent test kimi-review -w code-review-workflow -v my-vars
```

---

> "每一步都要走得扎实。" —— Zima Blue
