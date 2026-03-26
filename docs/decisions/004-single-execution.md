# ADR 004: 从循环到单次执行

## 状态

✅ **已接受** (Session 2, 2026-03-26)

## 背景

### 原始设计的问题

在 Session 1 中，我们设计了 15 分钟循环架构：
- Zima 定时唤起 Kimi（每 15 分钟）
- Kimi 执行一轮任务后返回
- Zima 解析结果，决定是否进入下一轮

**问题**：
1. **调度逻辑分散**：Zima 和 Kimi 都有控制逻辑，职责不清
2. **过度复杂**：守护进程、状态同步、提前完成等机制过于复杂
3. **适用场景有限**：15 分钟循环更适合开放式研发任务，不适合明确的 SOP

### 讨论过程

Session 2 中重新思考了 Zima 的定位：

> "Zima 本质上是一个 Agent 调度器，调度的是 Kimi 的启动参数。"
> 
> "Prompt 模板决定了工作流，工作流要明确，验证目标也要明确。"

核心洞察：
- 对于 **SOP 明确** 的任务（运维、填表、规范流程），不需要循环
- 对于 **目标模糊** 的任务（如"提高测试覆盖率"），应该由 Prompt 定义工作流

## 决策

采用 **单次执行模式**：

```
用户/脚本 → zima run <agent> → 唤起 Kimi → 执行完成 → 返回结果
```

### 架构变化

| 组件 | 旧设计 | 新设计 |
|------|--------|--------|
| 唤起方式 | 定时 15 分钟循环 | 手动/脚本单次执行 |
| 控制权 | Zima 调度 + Kimi 自主 | Prompt 模板定义明确 |
| 后台进程 | 守护进程模式 | 无，前台执行 |
| 状态管理 | state.json 循环更新 | 每次执行独立 |
| CLI 命令 | create/start/stop/status | create/run/list/show/logs |

### Agent 配置简化

```yaml
# 新配置结构
metadata:
  name: agent-name
  description: 描述

spec:
  workspace: ./workspace        # 工作目录
  prompt:
    file: prompt.md             # 提示词模板
    vars: {}                    # 变量
  execution:                    # Kimi 参数
    maxTime: 900
    maxStepsPerTurn: 50
    maxRalphIterations: 10
```

## 好处

### 1. 职责清晰
- Zima：管理 Agent 配置和 Kimi 启动参数
- Kimi：执行 Prompt 定义的工作流
- 用户：决定何时运行、查看结果

### 2. 简化实现
- 删除：CycleScheduler、Daemon、状态同步
- 保留：AgentConfig、AgentRunner、CLI
- 代码量减少约 60%

### 3. 适用性更强
- **SOP 任务**：运维脚本、数据处理、报告生成
- **研发任务**：测试覆盖、代码重构（通过 Prompt 定义工作流）
- **CI/CD 集成**：作为构建步骤，返回结构化结果

### 4. 可预测性
- 每次执行是独立的
- 没有后台状态需要同步
- 结果通过 stdout 返回

## 权衡

### 放弃的功能
- ❌ 定时循环执行
- ❌ 后台守护进程
- ❌ 跨周期的状态自动恢复

### 替代方案
- ✅ 使用 cron/systemd 定时调用 `zima run`
- ✅ 使用脚本管理多次执行
- ✅ 使用 Prompt 变量传递上下文

## 相关文档

- [旧 ADR 002](./002-15min-cycle.md) - 已废弃的 15 分钟循环设计
- [旧 ADR 003](./003-early-completion.md) - 已废弃的提前完成机制
- [Session 历史](../../SESSION.md) - Session 2 详细记录
