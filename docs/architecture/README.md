# ZimaBlue CLI 架构设计文档 (v2)

> 简化版 Agent Runner - 单次执行，明确工作流

---

## 1. 核心概念

### 1.1 什么是 Zima？

**Zima = Agent 启动器**

管理 Agent 配置和 Kimi CLI 启动参数：

```
┌─────────────────────────────────────────────────────────────┐
│                     Zima Agent Runner                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   1. 读取 agent.yaml（元数据 + Prompt + 执行参数）           │
│                                                             │
│   2. 生成 kimi CLI 命令                                     │
│      kimi --print --prompt <file> --work-dir <dir> ...      │
│                                                             │
│   3. 执行并捕获输出                                         │
│                                                             │
│   4. 返回结果                                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 什么是 Agent？

**Agent = Prompt 模板 + 工作空间**

```
agents/my-agent/
│
├── agent.yaml          # 配置：元数据、Prompt文件、Kimi参数
├── prompt.md           # Prompt模板（定义工作流）
├── workspace/          # 工作目录（代码、文件）
└── logs/              # 执行日志
```

### 1.3 执行流程

```
用户: zima run my-agent
         │
         ▼
    ┌─────────────┐
    │ 读取配置     │
    │ agent.yaml  │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ 生成命令     │
    │ kimi --print │
    │   --prompt   │
    │   --work-dir │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ 执行        │
    │ subprocess  │
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │ 返回结果    │
    │ RunResult   │
    └─────────────┘
```

---

## 2. 文件结构

> ⚠️ **Outdated (Issue #43)**: This section describes a legacy per-agent directory layout (`~/.zima/agents/{agent-name}/`) that was never implemented. The actual system stores configs centrally in `~/.zima/configs/` and uses the system temp directory for execution artifacts. See [AGENTS.md](../../../AGENTS.md) for the accurate data layout.

```
~/.zima/agents/{agent-name}/        # LEGACY — not implemented
│
├── agent.yaml              # Agent 配置 (stored in ~/.zima/configs/agents/)
│   ├── metadata: name, description
│   ├── spec.workspace: ./workspace
│   ├── spec.prompt: file + vars
│   └── spec.execution: maxTime, maxStepsPerTurn, maxRalphIterations
│
├── prompt.md               # Prompt 模板（运行时渲染到 temp dir）
│   └── 包含：任务描述、步骤、输出格式
│
├── workspace/              # 工作目录 (运行时 temp dir)
│   └── (Agent 操作的项目文件)
│
└── logs/                   # 执行日志 (stored in ~/.zima/history/pjobs.json)
    └── run_20260326_120000.log
```

---

## 3. 配置详解

### 3.1 agent.yaml

```yaml
metadata:
  name: coverage-improver
  description: 提升项目测试覆盖率

spec:
  # 工作目录
  workspace: ./workspace
  
  # Prompt 配置
  prompt:
    file: prompt.md
    vars:
      project_path: "./my-project"
      target_coverage: 80
  
  # Kimi 执行参数
  execution:
    maxTime: 900              # 最大执行时间（秒）
    maxStepsPerTurn: 50       # 每轮最大步数
    maxRalphIterations: 10    # Ralph 迭代次数
```

### 3.2 Prompt 模板

```markdown
# {{ name }}

## 任务
{{ description }}

## 输入参数
- project: {{ vars.project_path }}
- target: {{ vars.target_coverage }}%

## 工作流
1. 分析当前覆盖率
2. 找出未覆盖代码
3. 编写测试
4. 验证覆盖率达标

## 输出
执行完成后输出 JSON 结果：
```json
{
  "status": "completed|partial",
  "coverage_before": "xx%",
  "coverage_after": "xx%",
  "summary": "..."
}
```
```

---

## 4. 与 v1 循环架构的区别

| 特性 | v1 (循环) | v2 (单次) |
|------|-----------|-----------|
| **唤起方式** | 定时 15 分钟 | 手动/脚本 |
| **后台进程** | 守护进程 | 无 |
| **状态管理** | state.json 循环更新 | 每次执行独立 |
| **控制权** | Zima 调度 + Kimi 自主 | Prompt 定义明确 |
| **适用场景** | 开放式研发 | SOP 明确任务 |

详见 [ADR 004: 从循环到单次执行](../decisions/004-single-execution.md)

---

## 5. CLI 使用

```bash
# 创建 Agent
zima create my-agent

# 运行 Agent（单次执行）
zima run my-agent

# 查看配置
zima show my-agent

# 查看日志
zima logs my-agent
```

---

## 6. 适用场景

### 6.1 SOP 任务（推荐）

- 运维脚本执行
- 数据处理和报告生成
- 代码规范检查
- 测试覆盖率提升

### 6.2 CI/CD 集成

```yaml
# .github/workflows/ci.yml
- name: Run Coverage Agent
  run: zima run coverage-agent --input target=80
```

---

## 附录：历史架构

- [v1 循环架构](../history/ralph-loop-design.md) - 已废弃的 15 分钟循环设计
