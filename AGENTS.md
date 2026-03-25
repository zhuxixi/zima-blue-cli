# Zima Blue CLI - Agent 工厂车间

> "我选择了蓝色。那是那么强烈的蓝色。" —— 《齐马蓝》

**Zima Blue** 是一个个人 Agent 编排平台,让你能够在自己的电脑上运行一个 7x24 小时自主工作的 AI Agent 工厂。你只需与 Agent 对话,第二天早上醒来,Agent 已经帮你实现了多个版本。

> 📚 **文档导航**
> - [愿景和故事](../docs/vision/) — 项目愿景和齐马蓝故事
> - [架构设计](../docs/architecture/) ⭐ **最新设计，以此为准**
> - [历史文档](../docs/history/) — 设计演进过程（仅供参考）
> - [架构决策](../docs/decisions/) — ADR 决策记录

---

## 1. 项目愿景

### 1.1 核心理念

未来的工作方式:
- **你**: "帮我实现这个功能..."
- **Agent 工厂**: 自动分析、设计、编码、测试
- **第二天早上**: 多个版本等待你审查

人的职责:说话、决策、审查。
Agent 的职责:执行、迭代、交付。

### 1.2 命名来源

**Zima Blue** 源自 Alastair Reynolds 的科幻短篇《齐马蓝》。故事讲述了一个艺术家机器人不断回归最初的蓝色——一种纯粹、原始、本质的颜色。

这个名字象征着:
- **回归本质**:剥离复杂的管理系统,让 Agent 工作回归纯粹的"说话→执行"循环
- **无尽循环**:如同故事中的泳池清洁机器人,Agent 持续循环工作
- **自我进化**:从简单开始,逐渐成长为能够处理复杂任务的存在

---

## 2. 系统架构

### 2.1 核心循环: Ralph Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                    Ralph Loop - 15分钟周期                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   🌅 苏醒阶段 (3分钟)                                            │
│   ├── 加载个人记忆 (Session 历史)                                 │
│   ├── 读取项目知识库                                             │
│   └── 读取 GitHub Issue 状态                                     │
│                                                                 │
│   ⚡ 执行阶段 (9分钟)                                            │
│   ├── 分析任务需求                                               │
│   ├── 规划设计方案                                               │
│   ├── 编码实现                                                   │
│   └── 本地测试验证                                               │
│                                                                 │
│   📝 结束阶段 (3分钟)                                            │
│   ├── 保存 Session 记忆                                          │
│   ├── 更新 GitHub Issue                                          │
│   └── 本地 commit (等待人工 push)                                │
│                                                                 │
│   💤 休眠 → 等待下一个 15 分钟                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 三层记忆架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent 个人知识库                          │
│              (agent: zima-blue-dev-001)                     │
├─────────────────────────────────────────────────────────────┤
│ 🧠 Session 记忆（短期）                                      │
│    - 上一轮做了什么                                          │
│    - 学到了什么经验                                          │
│    - 犯的错误                                                │
│                                                              │
│ 📚 累积经验（中期）                                          │
│    - 多次 session 的模式总结                                 │
│    - 对特定技术的熟练度                                      │
│    - 个人的代码风格偏好                                      │
│                                                              │
│ 🎯 元认知（长期）                                            │
│    - 自己在项目中的角色定位                                  │
│    - 与人类的协作模式                                        │
│    - 自我改进的目标                                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 每次苏醒时读取 / 结束时写入
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    项目知识库（共享，只读）                   │
│                    (kb: zima-blue)                          │
├─────────────────────────────────────────────────────────────┤
│ 📋 项目长期记忆                                              │
│    - 架构决策 (ADR)                                          │
│    - 里程碑                                                  │
│    - 技术方案                                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 读取
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Issue（执行状态）                  │
├─────────────────────────────────────────────────────────────┤
│ 📝 当前任务状态                                              │
│    - 本次要执行的具体任务                                    │
│    - 代码进度检查点                                          │
│    - 读写在每个周期                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 安全边界 (信任等级)

| 等级 | 操作类型 | 夜间自动 | 说明 |
|------|---------|---------|------|
| 🟢 L1 | 只读/分析 | ✅ 自动 | 读取知识库、分析代码、生成方案 |
| 🟡 L2 | 本地修改 | ✅ 自动 | 编写代码、本地测试、生成文档 |
| 🟠 L3 | 本地提交 | ✅ 自动 | `git commit` 到 feature 分支 |
| 🔴 L4 | 远程操作 | ❌ 禁止 | `git push`、合并 PR、部署生产 |

**原则**: Agent 只能执行 L1-L3, L4 必须人工审查后执行。

---

## 3. 项目结构

```
zima-blue-cli/
│
├── AGENTS.md                   # 本文件: Agent 开发指南
├── README.md                   # 项目介绍(面向人类)
│
├── src/                        # CLI 源码
│   ├── __init__.py
│   ├── cli.py                  # 主 CLI 入口 (Typer)
│   ├── commands/               # CLI 子命令
│   │   ├── __init__.py
│   │   ├── init.py             # `zima init`
│   │   ├── agent.py            # `zima agent *`
│   │   ├── org.py              # `zima org *`
│   │   ├── team.py             # `zima team *`
│   │   ├── kb.py               # `zima kb *` (知识库管理)
│   │   └── dashboard.py        # `zima dashboard`
│   │
│   ├── core/                   # 核心逻辑
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理
│   │   ├── scheduler.py        # Agent 调度器
│   │   ├── prompt_builder.py   # Prompt 生成器
│   │   ├── kimi_runner.py      # Kimi CLI 调用
│   │   └── state_manager.py    # 状态管理
│   │
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   ├── agent.py            # Agent 配置模型
│   │   ├── organization.py     # 组织模型
│   │   ├── team.py             # 团队模型
│   │   └── task.py             # 任务模型
│   │
│   └── templates/              # Prompt 模板
│       └── agent_prompt.j2     # Agent 执行模板
│
├── tests/                      # 测试
│   ├── __init__.py
│   ├── test_scheduler.py
│   ├── test_prompt_builder.py
│   └── fixtures/               # 测试数据
│
├── skills/                     # 内置 Skills
│   ├── ralph-executor/         # Ralph Loop 执行 Skill
│   │   └── SKILL.md
│   └── knowledge-base/         # 知识库管理 Skill
│       └── SKILL.md
│
├── pyproject.toml              # Python 项目配置
├── requirements.txt            # 依赖
└── .zima/                      # Zima Blue 运行时数据
    ├── config.yaml             # 全局配置
    ├── state.json              # 运行状态
    └── cache/                  # 缓存目录
```

---

## 4. Agent 身份与命名

### 4.1 命名规范

每个 Agent 拥有全局唯一身份标识:

```
格式: {project}-{role}-{instance}

示例:
- zima-blue-dev-001      (Zima Blue 项目开发 Agent #1)
- zima-blue-test-001     (Zima Blue 项目测试 Agent #1)
- boktionary-dev-001     (Boktionary 项目开发 Agent #1)
```

### 4.2 知识库存储

```
~/.zettelkasten-agent-{agent_name}/
├── notes/
│   ├── session/           # 每轮周期的 Session 记忆
│   │   ├── 20260325-0015.md
│   │   └── ...
│   │
│   ├── experience/        # 累积经验
│   │   ├── patterns.md
│   │   ├── mistakes.md
│   │   └── skills.md
│   │
│   └── meta/              # 元认知
│       ├── identity.md
│       └── goals.md
│
└── .zk/                   # 向量索引
```

---

## 5. 开发规范

### 5.1 Python 代码风格

- **格式化**: Black (line-length: 100)
- **类型检查**: mypy (strict mode)
- **代码质量**: ruff
- **文档**: Google docstring style

### 5.2 提交规范

```
类型(模块): 简短描述

详细描述(可选)

类型:
- feat: 新功能
- fix: Bug 修复
- docs: 文档更新
- test: 测试相关
- refactor: 重构
- chore: 构建/工具
```

### 5.3 Agent 参与项目的准则

当 Agent 在这个项目上工作时:

1. **优先读取 AGENTS.md**: 每次开始工作前确认当前规范
2. **保持知识库同步**: 
   - 读取个人记忆了解之前的进展
   - 更新 skills.md 记录新掌握的技能
   - 更新 mistakes.md 记录犯的错误
3. **小步快跑**:
   - 每个周期完成一个可验证的小任务
   - 如果任务太大,主动提出拆分
4. **记录 Session**:
   - 每个周期结束时创建 session 笔记
   - 包含:做了什么、学到了什么、遇到了什么问题

---

## 6. 命令设计

### 6.1 核心命令

```bash
# 初始化 Zima Blue
zima init

# 组织管理
zima org create <name>              # 创建组织
zima org list                       # 列出组织
zima org delete <name>              # 删除组织

# 团队管理
zima team create <org>/<name>       # 创建团队
zima team list <org>                # 列出团队

# Agent 管理
zima agent create <org>/<team>/<name>   # 创建 Agent
zima agent start <name>                 # 启动 Agent
zima agent stop <name>                  # 停止 Agent
zima agent status <name>                # 查看状态
zima agent logs <name>                  # 查看日志
zima agent config <name>                # 编辑配置

# 知识库管理
zima kb init <name>                 # 初始化知识库
zima kb list                        # 列出知识库
zima kb sync                        # 同步索引

# 仪表盘
zima dashboard                      # 启动 Web 仪表盘
```

### 6.2 Agent 配置 (agent.yaml)

```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  name: zima-blue-dev-001
  displayName: "Zima Blue 开发 Agent"
  organization: personal
  team: default
  labels:
    role: backend
    specialty: cli

spec:
  # 知识库配置
  knowledgeBases:
    personal:
      type: zettelkasten
      path: "~/.zettelkasten-agent-zima-blue-dev-001"
    project:
      type: zettelkasten
      path: "./docs/knowledge-base"
      access: read-only

  # 运行时配置
  runtime:
    cycleInterval: 900           # 15 分钟
    maxExecutionTime: 840        # 14 分钟
    yolo: true
    workspace: "./workspace"
    logs: "./logs"

  # 能力配置
  capabilities:
    skills:
      - ralph-executor
    tools:
      - file/read
      - file/write
      - shell/bash

  # 身份配置
  identity:
    role: "Python CLI 开发工程师"
    specialties:
      - "Typer CLI 框架"
      - "Python 异步编程"
    level: "intermediate"

  # 任务配置
  tasks:
    sources:
      - type: github
        repo: "user/zima-blue-cli"
        labels: ["confirmed", "in-progress"]
```

---

## 7. 开发任务分解

### Phase 1: 基础 CLI (当前)

- [x] 项目初始化与架构设计
- [ ] CLI 框架搭建 (Typer)
- [ ] 配置管理模块
- [ ] Agent 元数据管理

### Phase 2: 核心调度

- [ ] Agent 调度器实现
- [ ] Prompt 生成器
- [ ] Kimi CLI 集成
- [ ] 状态管理

### Phase 3: 知识库集成

- [ ] zk 知识库管理
- [ ] Agent 个人知识库初始化
- [ ] Session 记忆读写

### Phase 4: Web 仪表盘

- [ ] Agent 状态可视化
- [ ] 日志查看器
- [ ] 任务队列管理

---

## 8. 参考资源

- [RALPH-LOOP-DESIGN.md](./RALPH-LOOP-DESIGN.md) - Ralph Loop 完整设计
- [KIMIWORLD-DESIGN.md](./KIMIWORLD-DESIGN.md) - KimiWorld 编排平台设计
- [AGENT-CYCLE-TIMELINE.md](./AGENT-CYCLE-TIMELINE.md) - 15分钟周期时间表

---

> "蓝色从来不是为了寻找答案,蓝色本身就是答案。"
