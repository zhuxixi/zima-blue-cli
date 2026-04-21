## 背景与动机

当前 Zima CLI 的核心是**单次执行模型**：用户手动触发 `zima pjob run`，Agent 执行一次任务后退出。这种模式适合研发阶段的主动探索，但无法支撑未来的自动化运维和 CI/CD 集成。

参考 Kimi CLI 生态中 Devin Review、Codex Review 等 GitHub App 的实现模式（详见笔记 [202604191043230289]），Zima CLI 的下一个进化方向是成为一台**事件驱动的自主调度引擎**：

> 当 GitHub Webhook 推送过来后，Zima CLI 负责分发和处理这些事件，融入到 32 周期中，实现自动化和部署。

## 核心架构愿景

```
┌─────────────────────────────────────────────────────────────┐
│              GitHub Webhook 事件流                          │
│  (PR opened / issue labeled / push / release / ...)         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Zima CLI 事件分发层 (Event Dispatcher)          │
│  • 接收并验证 GitHub Webhook 签名                            │
│  • 解析事件类型和 Payload                                    │
│  • 查询事件 → PJob 映射规则（PMG/Workflow 配置）              │
│  • 将任务加入**周期调度队列**，而非立即执行                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              32周期调度引擎 (Cycle Scheduler)                │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐      ┌─────────┐   │
│  │ Cycle 1 │→│ Cycle 2 │→│ Cycle 3 │→...→│ Cycle 32│   │
│  └────┬────┘  └────┬────┘  └────┬────┘      └────┬────┘   │
│       │            │            │                 │        │
│       ▼            ▼            ▼                 ▼        │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          资源感知调度器 (Resource-Aware Scheduler)   │  │
│  │  • 当前 CPU / Memory / GPU 利用率                   │  │
│  │  • 正在运行的 PJob 数量和优先级                     │  │
│  │  • Agent 类型负载均衡（Kimi/Claude/Gemini）          │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              PJob 执行池 (Managed PJob Pool)                 │
│                                                              │
│  事件类型          →  PJob 模板                               │
│  ─────────────────────────────────────────────               │
│  PR opened         →  code-review-pjob                       │
│  issue labeled     →  issue-analysis-pjob                    │
│  push to main      →  test-and-deploy-pjob                   │
│  release created   →  changelog-generate-pjob                │
│  issue assigned    →  task-decompose-pjob                    │
│                                                              │
│  每个 PJob 由 Agent + Workflow + Variable + Env 组合而成     │
└─────────────────────────────────────────────────────────────┘
```

## 关键设计原则

### 1. 非实时响应，周期内调度

与 GitHub Actions 的实时触发不同，Zima CLI 采用**准实时调度**：

- Webhook 事件进入队列后，不立即拉起 Agent
- 调度器根据当前机器资源状态，在下一个合适的**32周期窗口**中分配执行
- 避免资源争抢，尤其当多个仓库同时推送事件时

```python
# 伪代码：调度决策
async def schedule_event(event: GitHubEvent, pjob: PJobConfig):
    cycle = await scheduler.find_optimal_cycle(
        resource_usage=monitor.current(),
        pjob_priority=pjob.priority,
        estimated_duration=pjob.spec.max_execution_time,
        agent_type=pjob.spec.agent.type
    )
    await queue.enqueue(event, pjob, target_cycle=cycle)
```

### 2. 事件 → PJob 映射规则

通过 PMG（Parameter Group）配置实现灵活的事件路由：

```yaml
# event-mapping.yaml
apiVersion: zima.io/v1
kind: EventMapping
metadata:
  name: github-events
spec:
  rules:
    - event: pull_request
      actions: [opened, synchronize]
      match:
        - label: "needs-review"
      targetPJob: pr-code-review
      priority: high
      
    - event: issues
      actions: [labeled]
      match:
        - label: "needs-analysis"
      targetPJob: issue-analysis
      priority: medium
      
    - event: push
      match:
        - branch: "main"
      targetPJob: ci-test-suite
      priority: critical
```

### 3. 资源感知调度

```yaml
# scheduler-policy.yaml
spec:
  cycles:
    total: 32
    duration_seconds: 900  # 每个周期 15 分钟
  resources:
    max_concurrent_agents: 3
    max_cpu_percent: 80
    max_memory_percent: 75
  strategies:
    - name: "burst-mode"
      condition: "events.queued > 10"
      action: "reduce_cycle_duration_to_300s"
    - name: "night-mode"
      condition: "time.hour in [0,1,2,3,4,5,6]"
      action: "increase_max_concurrent_to_5"
```

### 4. 与现有 CLI 的兼容

新的调度层**不破坏现有单次执行模型**：

```bash
# 模式 1：单次执行（现有，保留）
zima pjob run daily-review

# 模式 2：事件监听（新增）
zima daemon start --event-mode=github-webhook

# 模式 3：混合模式（推荐）
zima daemon start --event-mode=github-webhook --scheduled-pjobs=daily-review,weekly-report
```

## 技术实现路径

### Phase 1: Webhook 接收与验证
- FastAPI 服务端接收 GitHub Webhook
- 签名验证（`X-Hub-Signature-256`）
- 事件解析与标准化

### Phase 2: 事件 → PJob 映射
- 扩展 PMG/Workflow 模型支持事件匹配规则
- 实现 EventDispatcher，查询映射规则
- PJob 模板参数化注入（如 `{{ event.pr_number }}`）

### Phase 3: 周期调度引擎
- 重构现有 CycleScheduler，支持事件队列
- 资源监控（psutil / Windows Performance Counter）
- 调度策略引擎（优先级、资源限制、时间窗口）

### Phase 4: 执行与反馈闭环
- PJob 执行后更新 GitHub（PR review comments / issue comments）
- 执行历史与事件溯源
- 失败重试与死信队列

## 参考资源

- **笔记**: [202604191043230289] Session: subagent work_dir 继承与 GitHub CR Bot 生态分析
  - Devin Review / Codex Review / Kimi CLI Review 三种 bot 的触发机制对比
  - GitHub App 注册、JWT 认证、Installation Token 换取流程
  - Webhook 接收、diff 拉取、Reviews API 提交完整示例代码
- **ADR**: [docs/decisions/004-single-execution.md] — 单次执行模型的设计决策
- **现有代码**: 
  - `zima/core/scheduler.py` — CycleScheduler 基础实现
  - `zima/models/pjob.py` — PJobConfig 模型
  - `zima/commands/pjob.py` — PJob CLI 命令

## 下一步行动

1. [ ] 编写 ADR：Event-Driven Scheduling Architecture
2. [ ] 设计 EventMapping 配置模型（扩展 PMG）
3. [ ] 实现最小可行 Webhook 接收端（FastAPI + smee.io 本地开发）
4. [ ] 扩展 CycleScheduler 支持事件队列和资源感知
5. [ ] 用 zima-blue-cli 自身作为第一个试验场：PR 自动 code review

---

> 💡 **核心洞察**：这不是一个 CI/CD 系统，而是一个**智能任务调度器**。GitHub 事件只是任务来源之一，未来还可以接入 Slack、邮件、定时任务等多种触发源。32周期的设计让 Agent 有"呼吸空间"，避免实时响应带来的资源风暴。
