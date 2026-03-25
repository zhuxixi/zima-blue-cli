# KimiWorld - Agent 编排管理平台设计方案

> 统一管理多个 Kimi Agents 的元数据、知识库和生命周期
> 
> 版本: v0.1.0
> 日期: 2026-03-25
> 状态: 设计阶段

---

## 1. 愿景

**KimiWorld** 是一个 Agent 编排平台，解决以下问题：

- 管理数十个甚至上百个 Kimi Agents 的元数据
- 组织 Agents 的层级关系（个人 → 团队 → 公司）
- 统一配置 Agents 的知识库访问权限
- 调度 Agents 的执行周期
- 集中查看所有 Agents 的执行日志和状态

---

## 2. 核心概念

### 2.1 层级架构

```
KimiWorld
│
├── Organization（组织）
│   ├── 公司级知识库（全局可读）
│   └── 公司级策略/规范
│
├── Team（团队）
│   ├── 团队级知识库（团队成员可读）
│   └── 团队共享的 Skills
│
└── Agent（智能体）
    ├── 个人知识库（私有）
    ├── 执行日志
    └── 工作目录
```

### 2.2 实体关系

```yaml
World
  └── Organizations[]
        └── Teams[]
              └── Agents[]
                    ├── Personal KB (agent-{id})
                    ├── Logs
                    └── Workspace
```

---

## 3. 目录结构

```
~/.kimiworld/                           # KimiWorld 主目录
│
├── config.yaml                         # 全局配置
│
├── organizations/                      # 组织目录
│   └── boboyun/                        # Boboyun 公司
│       ├── org.yaml                    # 组织元数据
│       ├── knowledge-base/             # 公司知识库
│       │   └── .zettelkasten-boboyun/  # zk 知识库
│       │
│       └── teams/                      # 团队目录
│           └── platform/               # 平台团队
│               ├── team.yaml           # 团队元数据
│               ├── knowledge-base/     # 团队知识库
│               │
│               └── agents/             # Agent 目录
│                   ├── boktionary-dev-001/
│                   │   ├── agent.yaml      # Agent 元数据 ⭐
│                   │   ├── knowledge-base/ # 个人知识库
│                   │   │   └── .zettelkasten-agent-boktionary-dev-001/
│                   │   ├── logs/           # 执行日志
│                   │   └── workspace/      # 代码工作区
│                   │
│                   └── boktionary-dev-002/
│                       └── ...
│
└── scheduler/                          # 调度系统
    └── ...
```

---

## 4. 元数据配置（YAML）

### 4.1 组织级配置

```yaml
# ~/.kimiworld/organizations/boboyun/org.yaml

apiVersion: kimiworld.io/v1
kind: Organization
metadata:
  name: boboyun
  displayName: "博博云科技"
  description: "AI 驱动的语言学习平台"
  createdAt: "2026-01-15T00:00:00Z"
  
spec:
  # 公司级知识库（所有 Agent 可读）
  knowledgeBase:
    type: zettelkasten
    path: "~/.kimiworld/organizations/boboyun/knowledge-base/.zettelkasten-boboyun"
    
  # 全局策略
  policies:
    defaultCycleInterval: 900        # 默认 15 分钟周期
    maxExecutionTime: 840            # 最大执行 14 分钟
    autoApprove: false               # 默认不自动批准
    
  # 共享 Skills
  sharedSkills:
    - name: git-workflow
      path: "./skills/git-workflow"
    - name: code-review
      path: "./skills/code-review"
```

### 4.2 团队级配置

```yaml
# ~/.kimiworld/organizations/boboyun/teams/platform/team.yaml

apiVersion: kimiworld.io/v1
kind: Team
metadata:
  name: platform
  displayName: "平台研发团队"
  description: "负责 Boktionary 核心平台开发"
  organization: boboyun
  
spec:
  # 团队知识库（团队成员可读）
  knowledgeBase:
    type: zettelkasten
    path: "./knowledge-base/.zettelkasten-platform"
    
  # 技术栈（影响 Skill 推荐）
  techStack:
    languages: [java, python]
    frameworks: [spring-boot, fastapi]
    databases: [postgresql]
    
  # 团队共享配置
  defaults:
    cycleInterval: 900
    maxExecutionTime: 840
```

### 4.3 Agent 级配置 ⭐核心

```yaml
# ~/.kimiworld/organizations/boboyun/teams/platform/agents/boktionary-dev-001/agent.yaml

apiVersion: kimiworld.io/v1
kind: Agent
metadata:
  name: boktionary-dev-001
  displayName: "Boktionary 开发 Agent #1"
  description: "负责 ETL 数据处理模块的开发"
  
  # 归属信息
  organization: boboyun
  team: platform
  
  # 创建信息
  createdAt: "2026-03-25T00:00:00Z"
  createdBy: admin
  
  # 标签（用于筛选和分组）
  labels:
    role: backend
    specialty: etl
    priority: high
    
spec:
  # ========== 知识库配置 ==========
  knowledgeBases:
    # 个人知识库（私有，只此 Agent 读写）
    personal:
      type: zettelkasten
      path: "./knowledge-base/.zettelkasten-agent-boktionary-dev-001"
      
    # 团队知识库（只读）
    team:
      type: zettelkasten
      path: "../../knowledge-base/.zettelkasten-platform"
      access: read-only
      
    # 公司知识库（只读）
    organization:
      type: zettelkasten
      path: "../../../../boboyun/knowledge-base/.zettelkasten-boboyun"
      access: read-only
      
  # ========== 运行时配置 ==========
  runtime:
    # 执行周期（秒）
    cycleInterval: 900           # 15 分钟
    
    # 单次最大执行时间（秒）
    maxExecutionTime: 840        # 14 分钟
    
    # 自动批准工具调用
    yolo: true
    
    # 最大每轮步数
    maxStepsPerTurn: 50
    
    # 工作目录
    workspace: "./workspace"
    
    # 日志目录（保留所有历史日志）
    logs: "./logs"
    
    # ⭐ Skills 目录（非交互模式下加载）
    skillsDir: "./skills"
    
  # ========== 能力配置 ==========
  capabilities:
    # 专属 Skills（会合并团队/公司的 Skills）
    skills:
      - name: ralph-executor
        path: "./skills/ralph-executor"
        
    # 允许使用的工具
    tools:
      - file/read
      - file/write
      - file/replace
      - shell/bash
      - shell/powershell
      - web/search
      
    # 禁止使用的工具（黑名单优先）
    disabledTools:
      - shell/bash:rm -rf /
      
  # ========== 任务配置 ==========
  tasks:
    # 任务来源
    sources:
      - type: github
        repo: "boboyun/boktionary"
        labels: ["confirmed", "in-progress"]
        assignee: boktionary-dev-001
        
    # 任务筛选规则
    filters:
      # 优先处理带有高优先级标签的 Issue
      priorityLabels: ["P0", "critical"]
      
      # 忽略的标签
      ignoreLabels: ["wontfix", "duplicate"]
      
  # ========== 身份配置 ==========
  identity:
    # Agent 角色设定（用于 Prompt 生成）
    role: "后端开发工程师"
    
    # 专长领域
    specialties:
      - "ETL 数据处理"
      - "Spring Batch"
      - "PostgreSQL"
      
    # 经验等级
    level: "intermediate"
    
    # 个性化 Prompt 前缀
    systemPrompt: |
      你是 Boktionary 平台团队的开发工程师，专注于 ETL 数据处理。
      你擅长使用 Spring Batch 和 PostgreSQL 解决数据管道问题。
      你的工作风格是：先分析、再设计、最后实现，确保代码质量和测试覆盖。
      
  # ========== 通知配置 ==========
  notifications:
    # 阻塞时通知
    onBlocked:
      enabled: true
      channels:
        - type: github-comment
          repo: "boboyun/boktionary"
          
    # 每日汇总
    dailyDigest:
      enabled: true
      time: "09:00"
      timezone: "Asia/Shanghai"
```

---

## 5. 核心组件设计

### 5.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        KimiWorld CLI                            │
├─────────────────────────────────────────────────────────────────┤
│  Commands:                                                      │
│    - world init          # 初始化 KimiWorld                     │
│    - org create          # 创建组织                             │
│    - team create         # 创建团队                             │
│    - agent create        # 创建 Agent                           │
│    - agent start         # 启动 Agent                           │
│    - agent logs          # 查看日志                             │
│    - agent status        # 查看状态                             │
│    - dashboard           # 启动 Web 仪表盘                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      KimiWorld Core                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Config     │  │   Registry   │  │     Scheduler        │  │
│  │   Manager    │  │   (Agents)   │  │     (定时调度)        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│         │                 │                    │               │
│         └─────────────────┼────────────────────┘               │
│                           ▼                                    │
│              ┌────────────────────────┐                       │
│              │    Agent Controller    │                       │
│              │    (Agent 生命周期)     │                       │
│              └────────────────────────┘                       │
│                           │                                    │
│                           ▼                                    │
│              ┌────────────────────────┐                       │
│              │   Kimi CLI Runner      │                       │
│              │   (执行 Kimi Code)     │                       │
│              └────────────────────────┘                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 核心类设计

```python
# kimiworld/models.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class KnowledgeBaseRef:
    """知识库引用"""
    type: str                      # zettelkasten, notion, etc.
    path: Path
    access: str = "read-write"     # read-only, read-write

@dataclass
class AgentSpec:
    """Agent 规格定义（对应 agent.yaml）"""
    # Metadata
    name: str
    display_name: str
    description: str
    organization: str
    team: str
    labels: Dict[str, str] = field(default_factory=dict)
    
    # Knowledge Bases
    personal_kb: KnowledgeBaseRef
    team_kb: Optional[KnowledgeBaseRef] = None
    org_kb: Optional[KnowledgeBaseRef] = None
    
    # Runtime
    cycle_interval: int = 900          # 15 minutes
    max_execution_time: int = 840      # 14 minutes
    yolo: bool = True
    max_steps_per_turn: int = 50
    workspace: Path = field(default_factory=lambda: Path("./workspace"))
    logs: Path = field(default_factory=lambda: Path("./logs"))
    skills_dir: Path = field(default_factory=lambda: Path("./skills"))  # ⭐ Skills 目录
    
    # Capabilities
    skills: List[Dict] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    disabled_tools: List[str] = field(default_factory=list)
    
    # Identity
    role: str = "Developer"
    specialties: List[str] = field(default_factory=list)
    level: str = "intermediate"
    system_prompt: str = ""
    
    # Tasks
    task_sources: List[Dict] = field(default_factory=list)
    
    @property
    def full_id(self) -> str:
        """完整标识符: org-team-name"""
        return f"{self.organization}-{self.team}-{self.name}"

@dataclass
class AgentStatus:
    """Agent 运行状态"""
    agent_id: str
    state: str                      # idle, running, blocked, error
    current_cycle: int
    last_run_at: Optional[datetime]
    last_task: Optional[str]
    success_rate: float             # 过去 100 个周期的成功率
    
@dataclass
class AgentInstance:
    """Agent 运行时实例"""
    spec: AgentSpec
    status: AgentStatus
    process: Optional[Any] = None   # 当前运行的进程
```

---

## 6. CLI 命令设计

### 6.1 初始化命令

```bash
# 初始化 KimiWorld
kimiworld init

# 创建组织
kimiworld org create boboyun \
  --display-name "博博云科技" \
  --description "AI 驱动的语言学习平台"

# 创建团队
kimiworld team create boboyun/platform \
  --display-name "平台研发团队" \
  --tech-stack "java,python,spring-boot"

# 创建 Agent
kimiworld agent create boboyun/platform/boktionary-dev-001 \
  --display-name "Boktionary 开发 Agent #1" \
  --role "后端开发工程师" \
  --specialty "ETL 数据处理" \
  --from-template backend-developer
```

### 6.2 管理命令

```bash
# 查看所有 Agent
kimiworld agent list

# 查看 Agent 详情
kimiworld agent get boboyun/platform/boktionary-dev-001

# 编辑 Agent 配置
kimiworld agent edit boboyun/platform/boktionary-dev-001

# 启动 Agent
kimiworld agent start boboyun/platform/boktionary-dev-001

# 停止 Agent
kimiworld agent stop boboyun/platform/boktionary-dev-001

# 重启 Agent
kimiworld agent restart boboyun/platform/boktionary-dev-001

# 查看 Agent 状态
kimiworld agent status boboyun/platform/boktionary-dev-001
```

### 6.3 日志命令

```bash
# 查看最新日志
kimiworld agent logs boboyun/platform/boktionary-dev-001

# 查看指定周期的日志
kimiworld agent logs boboyun/platform/boktionary-dev-001 --cycle 20260325_001500

# 实时跟踪日志
kimiworld agent logs boboyun/platform/boktionary-dev-001 -f

# 查看错误日志
kimiworld agent logs boboyun/platform/boktionary-dev-001 --stderr
```

### 6.4 仪表盘

```bash
# 启动 Web 仪表盘
kimiworld dashboard

# 指定端口
kimiworld dashboard --port 8080
```

---

## 7. Prompt 生成策略

KimiWorld 会根据 Agent 配置自动生成完整的 Prompt：

```python
def generate_agent_prompt(agent_spec: AgentSpec, task: Optional[Task]) -> str:
    """生成 Agent 执行 Prompt"""
    
    prompt_parts = []
    
    # 1. 系统身份
    prompt_parts.append(f"""
# 系统身份

你是 **{agent_spec.display_name}**（{agent_spec.name}）
角色：{agent_spec.role}
经验等级：{agent_spec.level}

{agent_spec.system_prompt}
""")

    # 2. 知识库路径（告诉 Agent 去哪里读取记忆）
    prompt_parts.append(f"""
# 知识库路径

## 个人知识库（读写）
```
{agent_spec.personal_kb.path}
```

## 团队知识库（只读）
```
{agent_spec.team_kb.path if agent_spec.team_kb else 'N/A'}
```

## 公司知识库（只读）
```
{agent_spec.org_kb.path if agent_spec.org_kb else 'N/A'}
```
""")

    # 3. 执行约束
    prompt_parts.append(f"""
# 执行约束

- 执行周期：{agent_spec.cycle_interval} 秒
- 最大执行时间：{agent_spec.max_execution_time} 秒
- 最大步数：{agent_spec.max_steps_per_turn}
- 工作目录：{agent_spec.workspace}
- 日志目录：{agent_spec.logs}
""")

    # 4. 当前任务
    if task:
        prompt_parts.append(f"""
# 当前任务

**任务 ID**: {task.id}
**任务标题**: {task.title}
**任务描述**:
{task.description}

**当前进度**: {task.progress}%
""")

    # 5. 执行指南
    prompt_parts.append("""
# 执行指南

1. **苏醒阶段**（前 3 分钟）
   - 读取个人知识库了解之前做了什么
   - 读取团队/公司知识库了解项目背景
   
2. **执行阶段**（中间 9 分钟）
   - 分析任务、设计方案
   - 编码实现
   - 运行测试
   
3. **结束阶段**（最后 3 分钟）
   - 保存 Session 到个人知识库
   - 更新任务状态
   - 记录执行日志

请在 {max_execution_time} 秒内完成，超时会被强制终止。
""")

    return "\n\n---\n\n".join(prompt_parts)
```

---

## 8. 状态存储

### 8.1 不使用 Session，改用文件系统

由于 Kimi CLI 的输出已经保存到日志文件，KimiWorld 不需要额外的 Session 管理：

```
~/.kimiworld/
└── state/
    └── agents/
        └── boktionary-dev-001/
            ├── status.json           # 当前状态
            ├── cycles.json           # 周期历史
            └── current-task.json     # 当前任务
```

### 8.2 日志保留策略

**保留所有历史日志**，不自动清理：

```
~/.kimiworld/organizations/boboyun/teams/platform/agents/boktionary-dev-001/logs/
├── cycle_20260325_001500.log      # 2026-03-25 00:15:00 的执行日志
├── cycle_20260325_003000.log      # 2026-03-25 00:30:00 的执行日志
├── cycle_20260325_004500.log      # 2026-03-25 00:45:00 的执行日志
├── ...
└── cycle_20260325_234500.log      # 当天的最后一个周期
```

**日志格式**：
- stdout 和 stderr 合并存储（方案 A）
- 每个周期一个独立文件
- 文件名包含时间戳，便于排序和查找
- 编码：UTF-8

**日志查看**：
```bash
# 查看最新日志
kimiworld agent logs boktionary-dev-001

# 查看指定日期的日志
kimiworld agent logs boktionary-dev-001 --date 2026-03-25

# 查看所有历史日志列表
kimiworld agent logs boktionary-dev-001 --list
```

### 8.2 status.json 示例

```json
{
  "agent_id": "boktionary-dev-001",
  "organization": "boboyun",
  "team": "platform",
  "state": "running",
  "current_cycle": 156,
  "last_run_at": "2026-03-25T00:15:00Z",
  "last_task": {
    "id": "88",
    "title": "实现超时机制",
    "status": "in_progress",
    "progress": 60
  },
  "stats": {
    "total_cycles": 156,
    "successful_cycles": 142,
    "failed_cycles": 8,
    "timeout_cycles": 6,
    "success_rate": 0.91
  },
  "current_process": {
    "pid": 12345,
    "started_at": "2026-03-25T00:15:00Z"
  }
}
```

---

## 9. 路线图

### Phase 1: 基础功能（MVP）
- [ ] CLI 初始化命令（world init, org create, team create, agent create）
- [ ] Agent 配置解析（YAML → AgentSpec）
- [ ] 简单的调度器（单进程轮询）
- [ ] 日志收集和查看

### Phase 2: 调度增强
- [ ] 多 Agent 并发调度
- [ ] 周期配置（支持不同 Agent 不同周期）
- [ ] 健康检查和自动重启
- [ ] Web 仪表盘（只读）

### Phase 3: 高级功能
- [ ] 任务队列管理（集成 GitHub Issues）
- [ ] Agent 间通信机制
- [ ] 动态扩缩容（根据任务量自动启停 Agent）
- [ ] 完整的 Web 管理界面

### Phase 4: 企业级
- [ ] 多租户支持
- [ ] RBAC 权限控制
- [ ] 审计日志
- [ ] 集成 SSO

---

## 10. 与现有方案的关系

| 现有方案 | KimiWorld 角色 |
|---------|---------------|
| `RALPH-LOOP-DESIGN.md` | Agent 执行策略（KimiWorld 实现的一部分） |
| `AGENT-CYCLE-TIMELINE.md` | Agent 生命周期管理（KimiWorld 调度器参考） |
| `boktionary` 知识库 | 公司级知识库（KimiWorld 管理的资源） |
| `kimi-cli` | 底层执行引擎（KimiWorld 调用） |

---

## 附录：完整示例

### 创建一个完整的 Agent

```bash
# 1. 初始化 KimiWorld
kimiworld init

# 2. 创建 Boboyun 组织
kimiworld org create boboyun \
  --display-name "博博云科技"

# 3. 创建平台团队
kimiworld team create boboyun/platform

# 4. 创建 Agent
kimiworld agent create boboyun/platform/boktionary-dev-001 \
  --display-name "Boktionary 开发 Agent #1" \
  --role "后端开发工程师" \
  --specialty "ETL 数据处理"

# 5. 生成的目录结构
# ~/.kimiworld/organizations/boboyun/teams/platform/agents/boktionary-dev-001/
# ├── agent.yaml
# ├── knowledge-base/
# ├── logs/
# └── workspace/

# 6. 启动 Agent
kimiworld agent start boboyun/platform/boktionary-dev-001

# 7. 查看状态
kimiworld agent status boboyun/platform/boktionary-dev-001

# 8. 查看日志
kimiworld agent logs boboyun/platform/boktionary-dev-001 -f
```

---

> **下一步**：是否需要我实现 KimiWorld 的 MVP 版本（核心 CLI 命令和调度器）？
