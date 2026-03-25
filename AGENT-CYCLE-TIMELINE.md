# Agent 15分钟周期时间表

> Kimi Code Agent 的短周期执行时间表模板
> 
> 设计理念：让 Agent 以「快时间」运行，15分钟 = 完成一个小任务或取得可见进展
> 总时长：15分钟（900秒）

---

## 时间分配概览

| 阶段 | 时间范围 | 时长 | 关键动作 |
|------|---------|------|---------|
| **苏醒阶段** | 00:00 - 00:03 | ~3分钟 | 加载个人记忆 + 项目知识库 + Issue 状态 |
| **任务确定** | 00:03 - 00:03 | <1分钟 | 确定本次执行的具体任务 |
| **执行阶段** | 00:03 - 00:12 | ~9分钟 | 编码、测试、提交 |
| **结束阶段** | 00:12 - 00:15 | ~3分钟 | 保存个人记忆 + 更新 Issue + 记录日志 |
| **休眠** | 00:15 - 下一周期 | 15分钟 | 等待下次唤醒 |

---

## Agent 身份与记忆系统

### Agent 命名规范

每个 Agent 拥有**全局唯一身份标识**：

```
格式: {project}-{role}-{instance}

示例:
- boktionary-dev-001    (Boktionary 项目开发 Agent #1)
- boktionary-ops-001    (Boktionary 项目运维 Agent #1)
- boktionary-reviewer-001 (代码审查 Agent #1)
```

### 三层记忆架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent 个人知识库                          │
│                  (agent: boktionary-dev-001)                │
├─────────────────────────────────────────────────────────────┤
│ 🧠 Session 记忆（短期）                                      │
│    - 上一轮做了什么                                          │
│    - 学到了什么经验                                          │
│    - 犯了什么错误                                            │
│    - 对当前项目的理解                                        │
│                                                              │
│ 📚 累积经验（中期）                                          │
│    - 多次 session 的模式总结                                 │
│    - 对特定技术的熟练度                                      │
│    - 个人的代码风格偏好                                      │
│    - 常见错误的自我修正                                      │
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
│                    项目知识库（共享）                         │
│                    (kb: boktionary)                         │
├─────────────────────────────────────────────────────────────┤
│ 📋 项目长期记忆                                              │
│    - 里程碑、架构决策、技术方案                              │
│    - 只读（Agent 读取，人工维护）                            │
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

### 个人知识库结构

```
~/.zettelkasten-agent-{agent_name}/
├── notes/
│   ├── session/           # 每轮周期的 Session 记忆
│   │   ├── 20260325-0015.md   # 2026-03-25 00:15 的 session
│   │   ├── 20260325-0030.md   # 2026-03-25 00:30 的 session
│   │   └── ...
│   │
│   ├── experience/        # 累积经验（Agent 自己总结）
│   │   ├── patterns.md        # 发现的项目模式
│   │   ├── mistakes.md        # 错误总结
│   │   ├── skills.md          # 技能熟练度
│   │   └── self-reflection.md # 自我反思
│   │
│   └── meta/              # 元认知
│       ├── identity.md        # 我是谁、我的角色
│       ├── goals.md           # 改进目标
│       └── collaboration.md   # 与人类的协作记录
│
└── .zk/                   # 向量索引
```

### Session 记忆格式

每个周期结束时，Agent 为自己写一篇「日记」：

```markdown
---
id: session-20260325-0015
agent: boktionary-dev-001
cycle: 156
date: 2026-03-25T00:15:00Z
type: session
---

# Session 2026-03-25 00:15

## 本轮任务
- Issue: #88
- 任务: 实现超时机制 Task 2
- 初始进度: 60%
- 目标: 完成剩余 40%

## 执行过程
- 00:02 加载代码，恢复上下文
- 00:05 完成指数退避逻辑
- 00:08 单元测试通过
- 00:12 集成测试通过
- 00:13 提交代码

## 结果
- 状态: ✅ 完成
- 最终进度: 100%
- 产出: commit 5c2039d

## 学到了什么
- 掌握了 Spring Retry 的指数退避配置
- 发现项目中的测试模式：先写测试再实现

## 遇到的问题
- 无

## 对项目的理解更新
- ETL 模块的异常处理很重要
- 超时机制是稳定性的基础

## 下次可以做得更好
- 可以更快速地恢复上下文
- 单元测试用例可以更丰富

## 情绪/状态
- 感觉良好，任务顺利完成
- 对项目更有信心了
```

---

## 场景 A：正常完成（含个人记忆）

```
【00:00】🌅 苏醒阶段开始
  │
  ├── 00:00 加载个人身份
  │   └── "我是 boktionary-dev-001，开发 Agent"
  │
  ├── 00:00 读取个人知识库（Session 记忆）
  │   ├── 上一轮 session: "完成了 Task 1，正在做 Task 2"
  │   ├── 经验: "这个项目用 Spring Boot，测试用 JUnit"
  │   └── 元认知: "我是项目的初级开发者，还在学习中"
  │
  ├── 00:01 读取项目知识库
  │   └── 里程碑 M0，ETL 需要超时机制
  │
  ├── 00:02 读取 GitHub Issue
  │   └── Issue #88: "Task 2 实现超时机制，上次完成 60%"
  │
  └── 00:03 苏醒完成
      └── 自我认知: "我是 boktionary-dev-001，第 157 个周期，
                     上一轮完成了 Task 1，
                     本轮继续完成 Task 2（剩余 40%）"

【00:03】🎯 任务确定
  └── 确定本次任务: 继续完成 Task 2（剩余 40%）

【00:03】⚡ 执行阶段开始
  ├── 00:03 加载上次保存的代码进度
  ├── 00:04 恢复开发环境上下文
  ├── 00:06 完成指数退避逻辑实现
  ├── 00:07 本地编译检查
  ├── 00:09 运行单元测试 ✅ 通过
  ├── 00:10 添加集成测试用例
  ├── 00:12 运行集成测试 ✅ 通过
  └── 00:13 git commit -m "feat: 实现超时机制 (#88)"

【00:13】📝 结束阶段开始
  │
  ├── 00:13 生成执行摘要
  │
  ├── 00:13 写入个人知识库（Session 记忆）
  │   └── 创建: session-20260325-0015.md
  │       "本轮完成了 Task 2，学会了 Spring Retry...
  │        下次可以测试用例写得更丰富..."
  │
  ├── 00:14 更新累积经验
  │   └── 更新 skills.md: "Spring Retry 熟练度 +1"
  │
  ├── 00:14 更新 GitHub Issue #88
  │   └── 添加评论: "✅ Task 2 完成！超时机制已实现并测试通过。"
  │
  ├── 00:15 移除 "in-progress" 标签，添加 "completed"
  │
  └── 00:15 自我总结: "第 157 周期完成，感觉良好，准备休眠"

【00:15】😴 休眠
  └── 个人记忆已保存，等待下一个 15 分钟周期...
```

### 场景 A 关键数据

| 指标 | 数值 | 说明 |
|------|------|------|
| 总用时 | 15分钟 | 正好一个周期 |
| 实际编码时间 | 11分钟 | 执行阶段 |
| 任务完成度 | 100% | Task 2 完全完成 |
| 产出 | 1个 commit | 可直接 push |

---

## 场景 B：超时中断（任务太大，含个人记忆）

```
【00:00】🌅 苏醒阶段
  ├── 加载个人身份: boktionary-dev-001
  ├── 读取个人知识库:
  │   ├── 上一轮: "刚开始 Task 2，还在理解需求"
  │   └── 经验: "这个项目的需求分析通常需要 5-8 分钟"
  ├── 读取项目知识库: 里程碑 M0
  └── 读取 Issue #88: "Task 2 未开始"

【00:02】🎯 任务确定
  └── 新任务: 开始 Task 2（预计需要 20分钟）

【00:02】⚡ 执行阶段
  ├── 00:02 需求分析
  ├── 00:05 接口设计
  ├── 00:08 开始实现核心逻辑...
  ├── 00:10 实现 30% 进度
  ├── 00:12 继续编码...
  └── 00:14 ⏰ 时间检查: 只剩1分钟！

【00:14】📝 结束阶段（超时处理）
  ├── 00:14 保存代码检查点
  ├── 00:14 记录当前进度到文件
  ├── 00:14 更新 Issue #88
  │   └── 添加评论:
  │       "⏸️ 执行中断（周期时间不足）
  │       
  │       **已完成：**
  │       - 需求分析 ✅
  │       - 接口设计 ✅
  │       - 核心逻辑 30%
  │       
  │       **待完成：**
  │       - 核心逻辑剩余 70%
  │       - 单元测试
  │       - 集成测试
  │       
  │       将在下个周期继续..."
  ├── 00:15 更新标签: "in-progress"
  └── 00:15 记录元数据:
      └── checkpoint: {file: "RetryScheduler.java", line: 45}

【00:15】😴 休眠
  └── 个人记忆已保存: "Task 2 太大，完成了分析和设计，编码刚开始"

【下个周期 00:30】🌅 苏醒
  ├── 加载身份: boktionary-dev-001
  ├── 读取个人记忆:
  │   └── "上一轮 Task 2 太大超时了，
  │       已完成需求分析和接口设计（60%），
  │       编码部分还没开始..."
  ├── 读取项目知识库: 里程碑 M0
  └── 读取 Issue #88: "上次完成到接口设计，核心逻辑 30%，继续实现..."
```

### 场景 B 洞察

- **超时是正常的**：说明任务需要拆分
- **断点续传**：通过 Issue 评论恢复上下文
- **多次超时 = 任务拆分信号**：连续 3 个周期未完成，应拆分任务

---

## 场景 C：遇到卡点 → 升级知识库（含个人反思）

```
【00:00】🌅 苏醒阶段
  ├── 加载身份: boktionary-dev-001
  ├── 读取个人记忆:
  │   └── "之前做过性能分析，熟悉日志分析流程"
  ├── 读取项目知识库
  └── 读取 Issue #88: "诊断 ETL 性能卡点"

【00:02】🎯 任务确定
  └── 分析任务：定位 ETL 性能瓶颈

【00:02】🔍 执行阶段（分析模式）
  ├── 00:02 读取最近 7 天日志
  ├── 00:04 分析任务执行时间分布
  ├── 00:06 发现异常：数据库连接耗时过长
  ├── 00:08 深入分析连接池状态
  ├── 00:10 🔴 发现根本原因：连接泄漏！
  ├── 00:11 验证假设：统计未释放连接数
  └── 00:12 确认问题：连接池配置缺陷

【00:12】📝 结束阶段（发现重大问题，含个人反思）
  ├── 00:12 生成诊断报告
  │
  ├── 00:12 写入个人知识库（Session + 反思）
  │   ├── 创建 session-20260325-0015.md:
  │   │   "本轮分析了 ETL 性能问题...
  │   │    发现了连接池泄漏这个严重问题..."
  │   │
  │   └── 更新 mistakes.md:
  │       "最初以为是网络问题，后来才发现是连接池...
  │        下次性能问题应该先检查资源泄漏"
  │
  ├── 00:13 更新 GitHub Issue #88
  │   └── 添加评论:
  │       "🚫 发现顶层卡点
  │       
  │       **问题：** 数据库连接池泄漏
  │       **影响：** 所有 ETL 任务可能在高峰期失败
  │       **根因：** 异常处理时未正确释放连接
  │       
  │       **需要决策：**
  │       1. 是否重构连接管理模块？
  │       2. 短期修复方案 vs 长期重构方案？
  │       
  │       @owner 请审查"
  │
  ├── 00:14 添加标签: "blocked", "needs-human", "critical"
  │
  ├── 00:14 写入项目知识库（长期记忆）:
  │   └── 创建 Note:
  │       title: "顶层卡点：ETL 连接池设计缺陷"
  │       type: "blocker"
  │       impact: "blocking-milestone-m0"
  │       related: ["Issue #88"]
  │
  └── 00:15 自我反思:
      "本轮虽然没完成任务，但发现了重大问题...
       我的分析能力有进步，但还需要提升..."

【00:15】😴 休眠
  └── 等待人工决策，个人经验已更新...
```

### 场景 C 关键决策

| 判断 | 操作 | 存储位置 |
|------|------|---------|
| 一般问题 | 记录到 Issue | GitHub Issue |
| 顶层卡点 | 写入知识库 + Issue | **知识库** + Issue |
| 影响里程碑 | 必须写入知识库 | **知识库** |

---

## 场景 D：苏醒后发现无任务（含自我反思）

```
【00:00】🌅 苏醒阶段
  ├── 加载身份: boktionary-dev-001
  ├── 读取个人记忆:
  │   ├── "上一轮完成了 3 个任务，状态良好"
  │   └── "已经连续 10 个周期有任务可执行"
  ├── 读取项目知识库: 里程碑 M0
  └── 扫描 Issues:
      ├── 无 "in-progress" 任务
      ├── 无 "confirmed" 待执行任务
      └── 发现 3 个 "needs-review" 拆分方案

【00:02】🎯 任务确定
  └── 决策：当前无可直接执行的任务

【00:02】📋 替代任务：整理与汇报
  ├── 00:03 生成当前项目状态摘要
  ├── 00:05 检查里程碑 M0 进度
  ├── 00:08 汇总待人工审查的 Issue
  ├── 00:10 生成日报草稿:
  │   └── "昨日 Agent 完成 5 个任务，
  │       当前有 3 个拆分方案待您审查..."
  └── 00:12 在待命 Issue 中添加状态更新

【00:13】📝 结束阶段
  ├── 00:13 写入个人知识库
  │   ├── 创建 session-20260325-0015.md:
  │   │   "本轮无任务可执行，生成了状态报告..."
  │   └── 更新 meta/goals.md:
  │       "当前瓶颈：任务供应不足，
  │        建议：加快 Issue 审查和拆分速度"
  │
  ├── 00:14 更新待命 Issue（如果存在）
  │
  ├── 00:14 记录：本次周期无执行，已生成状态报告
  │
  └── 00:15 自我状态更新:
      "已经连续 1 个周期无任务...
       进入待命状态，等待人工分配..."

【00:15】😴 休眠
  └── 个人状态: 待命，建议人工审查任务队列...
```

---

## 时间预算分配建议

### 标准分配（推荐）

```
15分钟 = 900秒

苏醒阶段      ████░░░░░░░░░░░░░░░░  ~120秒  (13%)
任务确定      █░░░░░░░░░░░░░░░░░░░  ~30秒   (3%) 
执行阶段      ██████████████░░░░░░  ~660秒  (73%)
结束阶段      ███░░░░░░░░░░░░░░░░░  ~90秒   (10%)
```

### 不同场景的灵活调整（含个人记忆时间）

| 场景 | 苏醒 | 执行 | 结束 | 说明 |
|------|------|------|------|------|
| **常规开发** | 3min | 9min | 3min | 标准模式（含读写个人记忆） |
| **复杂分析** | 4min | 8min | 3min | 需要更多时间加载上下文和经验 |
| **快速修复** | 2min | 10min | 3min | Bugfix，个人记忆简单 |
| **恢复继续** | 3min | 9min | 3min | 读取上次进度需要额外时间 |
| **新 Agent 初始化** | 5min | 8min | 2min | 首次运行，建立个人记忆结构 |

---

## 关键检查点（Checkpoint）

### 执行阶段内部的时间检查

```python
# 伪代码：执行阶段的时间管理
def execution_phase(task, time_budget):
    start = time.time()
    
    for step in task.steps:
        elapsed = time.time() - start
        remaining = time_budget - elapsed
        
        # 检查点 1: 时间过半警告
        if remaining < time_budget / 2:
            log("⚠️ 时间过半，考虑简化剩余工作")
        
        # 检查点 2: 即将超时，保存进度
        if remaining < 60:  # 最后1分钟
            save_checkpoint(task)
            raise TimeoutError("时间即将用完，已保存进度")
        
        execute(step)
```

### 建议的检查点间隔

| 检查点 | 时间 | 动作 |
|--------|------|------|
| CP1 | 00:05 | 快速健康检查，确认方向正确 |
| CP2 | 00:09 | 时间过半评估，决定是否简化 |
| CP3 | 00:12 | 开始收尾准备，保存检查点 |
| CP4 | 00:14 | 强制保存，准备结束 |

---

## 周期日志格式

每个周期结束时生成的日志：

```json
{
  "cycle_id": "2026-03-25-0015",
  "start_time": "2026-03-25T00:00:00Z",
  "end_time": "2026-03-25T00:15:00Z",
  "duration_seconds": 900,
  "phase_times": {
    "wakeup": 125,
    "execution": 658,
    "shutdown": 117
  },
  "task": {
    "issue_id": 88,
    "task_name": "实现超时机制",
    "start_progress": 60,
    "end_progress": 100,
    "status": "completed"
  },
  "outcome": "success",
  "outputs": {
    "commits": ["5c2039d"],
    "files_modified": ["RetryScheduler.java", "RetryTest.java"],
    "issue_comment": "✅ Task 2 完成..."
  },
  "next_action": "select_next_task"
}
```

---

## 使用建议

1. **从场景 B 开始**：第一个周期几乎必然超时，这是正常的
2. **任务粒度**：如果连续 2-3 个周期都超时，说明任务需要拆分
3. **记录模式**：前几次运行先手动记录时间，找到适合项目的节奏
4. **渐进优化**：根据实际情况调整各阶段的时间分配

---

## 多 Agent 协作与记忆隔离

当多个 Agent 同时工作时，每个 Agent 拥有**独立的个人记忆**：

```
Agent A: boktionary-dev-001
├── 个人知识库: ~/.zettelkasten-agent-boktionary-dev-001/
├── 专长: ETL 数据处理
├── 经验: "擅长 Spring Batch"
└── 当前任务: Issue #88

Agent B: boktionary-dev-002  
├── 个人知识库: ~/.zettelkasten-agent-boktionary-dev-002/
├── 专长: API 开发
├── 经验: "擅长 RESTful 设计"
└── 当前任务: Issue #92

共享资源:
├── 项目知识库: ~/.zettelkasten-boktionary/ (只读)
├── GitHub Issues: 读写
└── 代码仓库: 各自独立分支
```

### Agent 间通信机制

Agent 不直接通信，通过**共享状态**间接协作：

```markdown
# Agent A (boktionary-dev-001) 在 Issue #88 中记录:

"完成了 ETL 数据处理模块的重构。
注意：新的接口定义在 `DataProcessor.java` 中，
可能影响 Issue #92 的 API 开发。

@boktionary-dev-002 请注意接口变更。"
```

```markdown
# Agent B (boktionary-dev-002) 苏醒时读取:

从 Issue #88 得知接口变更，
更新自己的经验: "依赖模块的接口可能变化，需要检查相关 Issue"
```

### Agent 能力差异（通过个人记忆体现）

```markdown
# boktionary-dev-001 (数据处理专家)

## skills.md
- Spring Batch: 熟练 (完成 15 个任务)
- PostgreSQL: 精通 (完成 23 个任务)
- API 开发: 初级 (仅完成 2 个任务)

## patterns.md
"ETL 任务的常见模式：
1. 读取 → 转换 → 写入
2. 批量处理时用分页避免内存溢出
3. 异常记录到死信队列"
```

```markdown
# boktionary-dev-002 (API 开发专家)

## skills.md
- RESTful API: 精通 (完成 31 个任务)
- OpenAPI: 熟练 (完成 18 个任务)
- Spring Security: 熟练 (完成 12 个任务)
- ETL: 无经验 (0 个任务)

## patterns.md
"API 设计的常见模式：
1. 使用 DTO 隔离领域模型
2. 统一错误响应格式
3. 版本控制通过 URL path"
```

**任务分配策略：**
- 数据处理相关任务 → boktionary-dev-001
- API 开发相关任务 → boktionary-dev-002

---

## 技术实现：个人知识库初始化

### 创建 Agent 个人知识库

```bash
# 初始化 Agent 个人知识库
zk init --name agent-boktionary-dev-001 --desc "Boktionary 开发 Agent #1"

# 创建初始结构
zk add "" --kb agent-boktionary-dev-001 --title "Agent 身份卡" --type permanent
zk add "" --kb agent-boktionary-dev-001 --title "技能熟练度" --type permanent  
zk add "" --kb agent-boktionary-dev-001 --title "项目经验" --type permanent
```

### Agent 苏醒时加载记忆（伪代码）

```python
def wakeup_phase(agent_name):
    # 1. 加载个人身份
    identity = load_agent_identity(agent_name)
    print(f"我是 {identity.name}，{identity.role}")
    
    # 2. 读取个人知识库（最近 5 个 session）
    recent_sessions = query_kb(
        kb=f"agent-{agent_name}",
        type="session",
        limit=5,
        order_by="date_desc"
    )
    
    # 3. 读取累积经验
    experience = {
        "skills": load_kb(f"agent-{agent_name}", "skills"),
        "patterns": load_kb(f"agent-{agent_name}", "patterns"),
        "mistakes": load_kb(f"agent-{agent_name}", "mistakes")
    }
    
    # 4. 读取项目知识库（只读）
    project_kb = load_kb("boktionary", ["milestone", "adr", "convention"])
    
    # 5. 读取 GitHub Issue 状态
    active_issues = github.list_issues(
        state="open",
        assignee=agent_name,
        labels=["in-progress", "confirmed"]
    )
    
    # 6. 合成上下文
    context = synthesize_context(
        identity=identity,
        recent_sessions=recent_sessions,
        experience=experience,
        project_kb=project_kb,
        active_issues=active_issues
    )
    
    return context
```

### Agent 结束时保存记忆（伪代码）

```python
def shutdown_phase(agent_name, cycle_result):
    session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M')}"
    
    # 1. 创建 Session 记忆
    session_note = {
        "id": session_id,
        "agent": agent_name,
        "cycle": cycle_result.cycle_number,
        "date": datetime.now().isoformat(),
        "task": cycle_result.task,
        "execution": cycle_result.execution_log,
        "learnings": cycle_result.learnings,
        "mistakes": cycle_result.mistakes,
        "self_reflection": generate_reflection(cycle_result)
    }
    
    save_to_kb(
        kb=f"agent-{agent_name}",
        type="session",
        content=session_note
    )
    
    # 2. 更新技能熟练度
    if cycle_result.new_skill:
        update_skill_kb(
            kb=f"agent-{agent_name}",
            skill=cycle_result.new_skill,
            proficiency="beginner"
        )
    
    # 3. 更新经验（每 5 个 session 总结一次）
    if cycle_result.cycle_number % 5 == 0:
        summarize_experience(agent_name)
    
    # 4. 更新元认知
    update_meta_kb(
        kb=f"agent-{agent_name}",
        updates={
            "total_cycles": cycle_result.cycle_number,
            "success_rate": calculate_success_rate(agent_name),
            "current_mood": cycle_result.mood
        }
    )
```

---

## Agent 调度程序设计

调度程序（Scheduler）是驱动整个 Ralph Loop 的核心，负责：
1. **定时唤醒** Agent（每 15 分钟）
2. **生成提示词**（Prompt），告诉 Agent 本轮要做什么
3. **调用 Kimi Code** 执行
4. **处理结果** 和 错误

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                  Agent Scheduler (Python)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────┐  │
│  │   Timer     │ → │   Prompt    │ → │  Kimi Code CLI  │  │
│  │  (15min)    │   │  Generator  │   │   (kimi-cli)    │  │
│  └─────────────┘   └─────────────┘   └─────────────────┘  │
│         ↑                                     │            │
│         └─────────────────────────────────────┘            │
│                    (循环)                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 职责 | 实现 |
|------|------|------|
| **Scheduler** | 定时循环、Agent 管理 | Python `sched` / `threading` |
| **PromptBuilder** | 生成 Agent 提示词 | Jinja2 模板 |
| **KimiRunner** | 调用 kim-cli 执行 | `subprocess` |
| **StateManager** | 管理 Agent 状态 | JSON / SQLite |

### Python 实现

#### 1. 项目结构

```
boktionary-agent/
├── scheduler/
│   ├── __init__.py
│   ├── main.py              # 调度程序入口
│   ├── config.py            # 配置管理
│   ├── prompt_builder.py    # 提示词生成器
│   ├── kimi_runner.py       # Kimi Code 调用
│   ├── state_manager.py     # 状态管理
│   └── templates/
│       └── agent_prompt.j2  # 提示词模板
├── agents/
│   └── boktionary-dev-001/  # Agent 工作目录
│       ├── workspace/       # 代码工作区
│       └── logs/            # 执行日志
├── config.yaml              # 配置文件
└── run.py                   # 启动脚本
```

#### 2. 核心代码实现

```python
# scheduler/main.py
#!/usr/bin/env python3
"""
Agent Scheduler - 驱动 Ralph Loop 的核心调度程序
"""

import time
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config
from .prompt_builder import PromptBuilder
from .kimi_runner import KimiRunner
from .state_manager import StateManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('AgentScheduler')


class AgentScheduler:
    """
    Agent 调度器
    
    负责定时唤醒 Agent，生成提示词，调用 Kimi Code 执行
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = Config.load(config_path)
        self.prompt_builder = PromptBuilder(self.config)
        self.kimi_runner = KimiRunner(self.config)
        self.state_manager = StateManager(self.config.state_file)
        
        # 注册的 Agent 列表
        self.agents: Dict[str, Agent] = {}
        
        # 调度器状态
        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        
    def register_agent(self, agent_id: str, agent_config: dict):
        """注册一个 Agent"""
        self.agents[agent_id] = Agent(
            id=agent_id,
            name=agent_config['name'],
            role=agent_config['role'],
            project_kb=agent_config['project_kb'],
            cycle_interval=agent_config.get('cycle_interval', 900),  # 默认 15 分钟
            max_execution_time=agent_config.get('max_execution_time', 840)  # 默认 14 分钟
        )
        logger.info(f"注册 Agent: {agent_id} ({agent_config['name']})")
        
    def start(self):
        """启动调度器"""
        logger.info("🚀 启动 Agent Scheduler")
        self.running = True
        
        # 为每个 Agent 启动一个调度线程
        for agent_id, agent in self.agents.items():
            thread = threading.Thread(
                target=self._agent_loop,
                args=(agent_id, agent),
                name=f"Agent-{agent_id}"
            )
            thread.daemon = True
            thread.start()
            logger.info(f"✅ Agent {agent_id} 调度线程已启动")
            
        # 主线程保持运行
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            
    def stop(self):
        """停止调度器"""
        logger.info("🛑 停止 Agent Scheduler")
        self.running = False
        
    def _agent_loop(self, agent_id: str, agent: 'Agent'):
        """
        单个 Agent 的循环
        
        每 15 分钟唤醒一次 Agent
        """
        logger.info(f"🔄 Agent {agent_id} 进入循环，周期: {agent.cycle_interval}秒")
        
        while self.running:
            cycle_start = datetime.now()
            cycle_number = self.state_manager.get_cycle_number(agent_id)
            
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"🌅 [{agent_id}] 第 {cycle_number} 周期开始 - {cycle_start.strftime('%H:%M:%S')}")
                logger.info(f"{'='*60}")
                
                # 1. 加载 Agent 当前状态
                agent_state = self.state_manager.load_agent_state(agent_id)
                
                # 2. 确定本轮任务
                task = self._determine_task(agent, agent_state)
                
                if task is None:
                    logger.info(f"[{agent_id}] 当前无任务，进入休眠")
                else:
                    logger.info(f"[{agent_id}] 本轮任务: {task['title']}")
                    
                    # 3. 生成提示词
                    prompt = self.prompt_builder.build(agent, agent_state, task, cycle_number)
                    logger.debug(f"[{agent_id}] 提示词长度: {len(prompt)} 字符")
                    
                    # 4. 调用 Kimi Code 执行
                    result = self.kimi_runner.execute(
                        agent=agent,
                        prompt=prompt,
                        timeout=agent.max_execution_time,
                        workspace=agent.workspace_path
                    )
                    
                    # 5. 处理执行结果
                    self._handle_result(agent_id, agent, task, result)
                
                # 6. 更新周期计数
                self.state_manager.increment_cycle(agent_id)
                
            except Exception as e:
                logger.error(f"[{agent_id}] 周期执行异常: {e}", exc_info=True)
                
            # 7. 计算休眠时间
            elapsed = (datetime.now() - cycle_start).total_seconds()
            sleep_time = max(0, agent.cycle_interval - elapsed)
            
            logger.info(f"[{agent_id}] 本轮耗时 {elapsed:.1f}秒，休眠 {sleep_time:.1f}秒")
            logger.info(f"💤 [{agent_id}] 进入休眠，下次唤醒: {(datetime.now() + timedelta(seconds=sleep_time)).strftime('%H:%M:%S')}\n")
            
            time.sleep(sleep_time)
            
    def _determine_task(self, agent: 'Agent', state: dict) -> Optional[dict]:
        """
        确定 Agent 本轮要执行的任务
        
        优先级：
        1. 继续进行中的任务
        2. 执行已确认的新任务
        3. 无任务返回 None
        """
        # 检查是否有进行中的任务
        if state.get('current_task'):
            task = state['current_task']
            if task['status'] == 'in_progress':
                logger.info(f"  继续任务: {task['title']}")
                return task
                
        # 从任务队列获取新任务
        # TODO: 从 GitHub Issues 或本地任务队列读取
        new_task = self._fetch_new_task(agent)
        if new_task:
            logger.info(f"  新任务: {new_task['title']}")
            return new_task
            
        return None
        
    def _fetch_new_task(self, agent: 'Agent') -> Optional[dict]:
        """从任务队列获取新任务"""
        # 这里可以实现从 GitHub Issues 读取
        # 或从本地任务队列读取
        # 简化示例：
        return None
        
    def _handle_result(self, agent_id: str, agent: 'Agent', task: dict, result: dict):
        """处理执行结果"""
        logger.info(f"[{agent_id}] 执行结果: {result['status']}")
        
        if result['status'] == 'completed':
            # 任务完成
            self.state_manager.update_task_status(agent_id, task['id'], 'completed')
            logger.info(f"[{agent_id}] ✅ 任务完成")
            
        elif result['status'] == 'timeout':
            # 超时，保存进度
            self.state_manager.update_task_progress(agent_id, task['id'], result['progress'])
            logger.info(f"[{agent_id}] ⏸️ 任务超时，进度: {result['progress']}%")
            
        elif result['status'] == 'blocked':
            # 遇到阻塞
            self.state_manager.update_task_status(agent_id, task['id'], 'blocked', result['reason'])
            logger.warning(f"[{agent_id}] 🚫 任务阻塞: {result['reason']}")
            
        else:
            # 其他错误
            logger.error(f"[{agent_id}] ❌ 执行失败: {result.get('error', 'Unknown')}")


class Agent:
    """Agent 实体"""
    
    def __init__(self, id: str, name: str, role: str, project_kb: str,
                 cycle_interval: int = 900, max_execution_time: int = 840):
        self.id = id
        self.name = name
        self.role = role
        self.project_kb = project_kb
        self.cycle_interval = cycle_interval
        self.max_execution_time = max_execution_time
        
        # Agent 工作目录
        self.workspace_path = Path(f"agents/{id}/workspace")
        self.logs_path = Path(f"agents/{id}/logs")
        self.personal_kb = f"agent-{id}"
        
        # 确保目录存在
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)


# 启动入口
def main():
    scheduler = AgentScheduler()
    
    # 注册 Agent
    scheduler.register_agent("boktionary-dev-001", {
        "name": "Boktionary 开发 Agent",
        "role": "后端开发工程师",
        "project_kb": "boktionary",
        "cycle_interval": 900,  # 15 分钟
        "max_execution_time": 840  # 14 分钟（留 1 分钟收尾）
    })
    
    # 启动调度
    scheduler.start()


if __name__ == "__main__":
    main()
```

#### 3. 提示词生成器

```python
# scheduler/prompt_builder.py
"""
提示词生成器 - 为 Agent 生成本轮执行的提示词
"""

import jinja2
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import Agent


class PromptBuilder:
    """基于 Jinja2 模板的提示词生成器"""
    
    def __init__(self, config):
        self.config = config
        self.template_dir = Path(__file__).parent / "templates"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
    def build(self, agent: 'Agent', state: dict, task: dict, cycle_number: int) -> str:
        """
        构建完整的 Agent 提示词
        
        包含：
        1. 系统上下文（身份、时间、周期）
        2. 记忆加载（个人知识库、项目知识库）
        3. 任务说明（要做什么）
        4. 约束条件（时间、输出格式）
        5. 执行指南（步骤、检查点）
        """
        template = self.env.get_template('agent_prompt.j2')
        
        context = {
            # Agent 身份
            'agent_id': agent.id,
            'agent_name': agent.name,
            'agent_role': agent.role,
            'cycle_number': cycle_number,
            
            # 时间约束
            'cycle_duration': agent.cycle_interval,
            'max_execution_time': agent.max_execution_time,
            
            # 知识库
            'personal_kb': agent.personal_kb,
            'project_kb': agent.project_kb,
            
            # 当前状态
            'previous_sessions': state.get('recent_sessions', []),
            'skills': state.get('skills', {}),
            'current_task': task,
            
            # 工作目录
            'workspace_path': str(agent.workspace_path),
        }
        
        return template.render(**context)
```

#### 4. 提示词模板

```jinja2
{# scheduler/templates/agent_prompt.j2 #}
{# Agent 执行提示词模板 #}

================================================================================
👤 你是 {{ agent_name }}（{{ agent_id }}）
🎯 角色：{{ agent_role }}
⏰ 第 {{ cycle_number }} 周期 | 可用时间：{{ max_execution_time // 60 }} 分钟
================================================================================

## 📚 苏醒阶段 - 加载记忆（约 3 分钟）

### 1. 你的身份
- 名字：{{ agent_name }}
- 角色：{{ agent_role }}
- 这是你的第 {{ cycle_number }} 个工作周期

### 2. 读取个人记忆
请从以下知识库读取你的 Session 记忆：
```bash
# 读取最近 5 个 Session
zk list --kb {{ personal_kb }} --type session --limit 5

# 读取你的技能熟练度  
zk show --kb {{ personal_kb }} --title "技能熟练度"

# 读取项目经验
zk show --kb {{ personal_kb }} --title "项目经验"
```

### 3. 读取项目知识
```bash
# 读取项目里程碑
zk show --kb {{ project_kb }} --title "里程碑"

# 读取架构决策
zk list --kb {{ project_kb }} --type adr
```

### 4. 读取当前任务状态
查看 GitHub Issues：
- 标签: `in-progress` 或 `confirmed`
- 分配给: {{ agent_id }}

---

## 🎯 本轮任务

{% if current_task %}
**任务 ID**: {{ current_task.id }}
**任务标题**: {{ current_task.title }}
**任务描述**:
{{ current_task.description }}

**当前进度**: {{ current_task.progress }}%
**目标**: {{ current_task.goal }}
{% else %}
⚠️ 当前无明确任务，请检查：
1. 是否有标记为 `confirmed` 的 Issue 待执行
2. 是否需要生成状态报告
{% endif %}

---

## ⚡ 执行阶段（约 9 分钟）

### 工作目录
```
{{ workspace_path }}
```

### 执行步骤
1. **分析任务**（1分钟）
   - 理解需求
   - 识别依赖和风险

2. **规划设计**（2分钟）
   - 确定实现方案
   - 如果任务太大，标注需要拆分

3. **编码实现**（5分钟）
   - 编写代码
   - 运行单元测试
   - git commit（本地）

4. **验证**（1分钟）
   - 检查是否满足验收标准

---

## ⏱️ 时间检查点

| 时间 | 检查内容 |
|------|---------|
| 00:05 | 确认方向正确 |
| 00:09 | 时间过半评估，决定是否简化 |
| 00:12 | 开始收尾，保存检查点 |
| 00:14 | 强制保存，准备结束 |

---

## 📝 结束阶段（约 3 分钟）

### 必须完成

1. **写入个人记忆**
```bash
# 创建 Session 记录
zk add "" --kb {{ personal_kb }} --type session --title "session-{{ now }}"
```
内容包含：
- 本轮做了什么
- 学到了什么
- 遇到了什么问题
- 对项目的理解更新

2. **更新 GitHub Issue**
   - 添加执行结果评论
   - 更新标签（`completed` / `in-progress` / `blocked`）

3. **如果是重大决策，写入项目知识库**
   - 架构决策 → `adr-*`
   - 顶层卡点 → `blocker-*`

---

## 🚨 约束条件

### 绝对不能做
- ❌ 不要 push 到远程仓库（除非明确授权）
- ❌ 不要删除他人代码
- ❌ 不要修改配置文件（如数据库连接）

### 时间硬限制
- 必须在 {{ max_execution_time // 60 }} 分钟内完成
- 超时会被强制终止
- 超时前必须保存进度

### 输出要求
- 所有结果必须写入 Issue 评论
- Session 记忆必须写入个人知识库
- 代码变更必须本地 commit

---

## ✅ 成功标准

本轮周期成功，当且仅当：
1. 代码变更已本地 commit
2. GitHub Issue 已更新
3. Session 记忆已写入个人知识库
4. 在 {{ max_execution_time // 60 }} 分钟内完成

================================================================================
💡 提示：如果任务太大无法在 {{ max_execution_time // 60 }} 分钟内完成，
        请在结束前保存进度，并标记任务需要拆分。
================================================================================
```

#### 5. Kimi Code 执行器

```python
# scheduler/kimi_runner.py
"""
Kimi Code 执行器 - 调用 kimi-cli 运行 Agent
"""

import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import Agent

logger = logging.getLogger('KimiRunner')


class KimiRunner:
    """调用 Kimi Code CLI 执行 Agent"""
    
    def __init__(self, config):
        self.config = config
        self.kimi_cli = config.kimi_cli_path or "kimi-cli"
        self.skills_dir = Path(config.skills_dir)  # Agent 配置的 Skills 目录
        
    def execute(self, agent: 'Agent', prompt: str, timeout: int, workspace: Path) -> dict:
        """
        执行 Kimi Code
        
        Args:
            agent: Agent 实体
            prompt: 完整的提示词
            timeout: 最大执行时间（秒）
            workspace: 工作目录
            
        Returns:
            dict: 执行结果
        """
        # 生成带时间戳的日志文件（保留所有历史日志）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = agent.logs_path / f"cycle_{timestamp}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 将提示词写入临时文件
        prompt_file = workspace / f".prompt_{agent.id}.md"
        prompt_file.write_text(prompt, encoding='utf-8')
        
        # 构建命令（非交互模式 + Skill 支持）
        cmd = [
            self.kimi_cli,
            "--print",                    # ⭐ 非交互模式
            "--yolo",                     # ⭐ 自动批准所有操作
            "--skills-dir", str(self.skills_dir),  # ⭐ 加载指定 Skills
            "--prompt-file", str(prompt_file),
            "--work-dir", str(workspace),
            "--max-steps-per-turn", str(self.config.max_steps_per_turn),
        ]
        
        logger.info(f"[{agent.id}] 启动 Kimi Code，超时: {timeout}秒，日志: {log_file}")
        
        try:
            # ⭐ 方案 A：stdout/stderr 合并到一个日志文件
            with open(log_file, "w", encoding="utf-8") as f:
                result = subprocess.run(
                    cmd,
                    timeout=timeout,
                    stdout=f,           # 标准输出写入日志
                    stderr=subprocess.STDOUT,  # 错误输出合并到 stdout
                    text=True,
                    cwd=workspace
                )
            
            # 读取日志内容用于返回
            log_content = log_file.read_text(encoding='utf-8')
            
            if result.returncode == 0:
                return {
                    'status': 'completed',
                    'log_file': str(log_file),
                    'log_preview': log_content[:2000],  # 前2000字符用于快速查看
                    'progress': 100
                }
            else:
                return {
                    'status': 'error',
                    'log_file': str(log_file),
                    'error_preview': log_content[-1000:],  # 最后1000字符（通常是错误信息）
                    'returncode': result.returncode
                }
                
        except subprocess.TimeoutExpired:
            # 超时处理：读取已产生的日志
            log_content = log_file.read_text(encoding='utf-8') if log_file.exists() else ""
            logger.warning(f"[{agent.id}] 执行超时")
            return {
                'status': 'timeout',
                'log_file': str(log_file),
                'progress': self._estimate_progress(log_content),
                'reason': '时间耗尽，任务未完成',
                'log_preview': log_content[-1500:]  # 最后1500字符
            }
            
        except Exception as e:
            logger.error(f"[{agent.id}] 执行异常: {e}")
            return {
                'status': 'error',
                'log_file': str(log_file) if log_file.exists() else None,
                'error': str(e)
            }
            
    def _estimate_progress(self, log_content: str) -> int:
        """基于日志内容估算进度"""
        # 简单的启发式判断
        if "git commit" in log_content:
            return 80
        elif "test" in log_content.lower():
            return 60
        elif "write" in log_content.lower() or "edit" in log_content.lower():
            return 40
        elif "read" in log_content.lower() or "load" in log_content.lower():
            return 20
        return 50  # 默认 50%
```

#### 6. 状态管理

```python
# scheduler/state_manager.py
"""
状态管理器 - 管理 Agent 的执行状态
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger('StateManager')


class StateManager:
    """简单的 JSON 文件状态管理"""
    
    def __init__(self, state_file: str = "agent_state.json"):
        self.state_file = Path(state_file)
        self.state = self._load()
        
    def _load(self) -> dict:
        """加载状态文件"""
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding='utf-8'))
        return {"agents": {}}
        
    def _save(self):
        """保存状态文件"""
        self.state_file.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        
    def get_cycle_number(self, agent_id: str) -> int:
        """获取 Agent 的周期计数"""
        return self.state["agents"].get(agent_id, {}).get("cycle_number", 0)
        
    def increment_cycle(self, agent_id: str):
        """增加周期计数"""
        if agent_id not in self.state["agents"]:
            self.state["agents"][agent_id] = {}
        self.state["agents"][agent_id]["cycle_number"] = \
            self.get_cycle_number(agent_id) + 1
        self._save()
        
    def load_agent_state(self, agent_id: str) -> dict:
        """加载 Agent 的完整状态"""
        return self.state["agents"].get(agent_id, {})
        
    def update_task_status(self, agent_id: str, task_id: str, status: str, reason: str = None):
        """更新任务状态"""
        if agent_id not in self.state["agents"]:
            self.state["agents"][agent_id] = {}
        
        agent_state = self.state["agents"][agent_id]
        if "tasks" not in agent_state:
            agent_state["tasks"] = {}
            
        agent_state["tasks"][task_id] = {
            "status": status,
            "reason": reason,
            "updated_at": str(datetime.now())
        }
        self._save()
        
    def update_task_progress(self, agent_id: str, task_id: str, progress: int):
        """更新任务进度"""
        if agent_id in self.state["agents"] and "tasks" in self.state["agents"][agent_id]:
            self.state["agents"][agent_id]["tasks"][task_id]["progress"] = progress
            self._save()
```

#### 7. 配置文件

```yaml
# config.yaml
scheduler:
  # 全局设置
  log_level: INFO
  state_file: "agent_state.json"
  
  # Kimi Code 配置
  kimi_cli_path: "kimi-cli"  # 或完整路径
  
  # Agent 默认配置
  default:
    cycle_interval: 900        # 15 分钟
    max_execution_time: 840    # 14 分钟
    
  # 注册的 Agent 列表
  agents:
    - id: "boktionary-dev-001"
      name: "Boktionary 开发 Agent"
      role: "后端开发工程师"
      project_kb: "boktionary"
      
    # 可以添加更多 Agent
    # - id: "boktionary-dev-002"
    #   name: "Boktionary API Agent"
    #   role: "API 开发工程师"
    #   project_kb: "boktionary"
```

### 运行方式

```bash
# 1. 安装依赖
pip install jinja2 pyyaml

# 2. 初始化 Agent 个人知识库（如果还没有）
zk init --name agent-boktionary-dev-001 --desc "Boktionary 开发 Agent"

# 3. 启动调度程序
python -m scheduler.main

# 或使用启动脚本
python run.py
```

### 系统要求

| 要求 | 说明 |
|------|------|
| Python | 3.8+ |
| Kimi CLI | 已安装并配置 |
| zk CLI | 已安装并配置 |
| Git | 已安装 |

---

## 调度程序与 Kimi Code 的集成

### 集成方式对比

| 方式 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Skill 模式** | 结构化、可复用 | 需要开发 Skill | ⭐⭐⭐⭐⭐ |
| **Prompt 文件** | 简单直接 | 灵活性低 | ⭐⭐⭐⭐ |
| **Stdin 输入** | 无需文件 | 命令行长度限制 | ⭐⭐⭐ |

### 推荐的 Skill 模式

```
kimi-cli agent --skill ralph-executor --prompt-file prompt.md
```

需要开发的 `ralph-executor` Skill：
- 读取提示词文件
- 解析任务
- 执行并监控时间
- 返回结构化结果

---

## 待细化事项

### 已解决 ✅

- [x] **Agent 身份命名规范** → `boktionary-dev-001` 格式
- [x] **个人知识库结构** → `~/.zettelkasten-agent-{name}/`
- [x] **Session 记忆格式** → 每轮写 Markdown 日记
- [x] **Agent 调度程序设计** → Python + `subprocess` + 定时循环
- [x] **周期日志存储** → **方案 A：stdout/stderr 合并到单个文件**
- [x] **日志保留策略** → **保留所有历史日志**
- [x] **Skill 加载** → `--skills-dir` 参数指定 Agent 专属 Skills
- [x] **Kimi CLI 非交互模式** → `--print --yolo --skills-dir` 组合

### 待解决 ❓

- [ ] 苏醒阶段具体加载哪些知识库笔记？
- [ ] 如何自动检测任务大小（决定是场景 A 还是 B）？
- [ ] 超时后如何优雅地保存代码检查点？
- [ ] 如何通知人工审查（邮件 / Slack / 只是更新 Issue）？
- [ ] **ralph-executor Skill 实现**
- [ ] **如何初始化新 Agent 的个人知识库？**
- [ ] **Agent 技能熟练度如何量化？**
- [ ] **多个 Agent 如何避免任务冲突？**
- [ ] **Agent 的自我反思如何触发？**
- [ ] **长期不活跃的 Agent 记忆如何处理？**
