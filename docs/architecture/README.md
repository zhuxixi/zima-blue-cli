# ZimaBlue CLI 架构设计文档

> 基于 kimi-cli 的 Agent 循环调度系统

---

## 1. 核心概念

### 1.1 什么是 Agent？

在 ZimaBlue 中，**Agent = kimi-cli 的一个实例**。

每次循环，ZimaBlue 会：
1. 生成一个 Prompt 文件
2. 调用 `kimi --print --prompt-file ...` 启动 kimi-cli
3. kimi-cli 执行完成后退出
4. ZimaBlue 等待下一个循环

```
┌─────────────────────────────────────────────────────────────┐
│                    一个循环 = 一次 kimi-cli 调用              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ZimaBlue Scheduler          kim-cli (单次执行)            │
│         │                           │                       │
│         │  1. 生成 prompt.md        │                       │
│         ├──────────────────────────►│                       │
│         │                           │                       │
│         │  2. 启动进程              │                       │
│         │  kimi --print             │                       │
│         │     --prompt-file ...     │                       │
│         ├──────────────────────────►│                       │
│         │                           │  3. 执行 AI 任务       │
│         │                           │     - 读代码          │
│         │                           │     - 写测试          │
│         │                           │     - git commit      │
│         │                           │                       │
│         │  4. 进程退出              │                       │
│         │◄──────────────────────────┤                       │
│         │                           │                       │
│         │  5. 解析结果              │                       │
│         ▼                           ▼                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Session 是什么？

**Session = Agent 的一个工作周期记录**（类似日记）

每个周期结束时，ZimaBlue 会为这个周期写一篇"日记"，记录：
- 这轮做了什么
- 遇到了什么问题
- 进度如何
- 下轮计划做什么

```
Session 记忆（每轮一条）
│
├── 20260325-0800.md  ← 第1轮
├── 20260325-0815.md  ← 第2轮
├── 20260325-0830.md  ← 第3轮
└── ...
```

### 1.3 日志是什么？

**日志 = kimi-cli 执行时的完整输出**（原始记录）

```
日志（每轮一个文件）
│
├── cycle_20260325_080000.log  ← kimi-cli 的 stdout/stderr
├── cycle_20260325_081500.log
└── ...
```

**Session vs 日志 的区别：**

| 对比 | Session | 日志 |
|------|---------|------|
| **谁生成** | ZimaBlue 根据日志整理 | kimi-cli 直接输出 |
| **内容** | 结构化摘要（做了什么、进度、计划） | 原始输出（所有命令、思考过程） |
| **用途** | 下轮唤醒时快速恢复上下文 | 排查问题、审计 |
| **大小** | 小（几百字） | 大（可能几千行） |

---

## 2. 文件结构

```
agents/zk-coverage-agent/           # Agent 工作目录
│
├── agent.yaml                       # Agent 配置（静态）
│   └── 定义：做什么任务、周期多长、超时多久
│
├── state.json                       # 运行状态（动态）
│   └── 当前周期数、进行到哪一步、是否完成
│
├── prompts/                         # 每轮的 Prompt
│   ├── cycle_20260325_080000.md    # 第1轮 Prompt
│   ├── cycle_20260325_081500.md    # 第2轮 Prompt
│   └── ...
│
├── logs/                            # kimi-cli 原始日志
│   ├── cycle_20260325_080000.log   # 第1轮日志
│   ├── cycle_20260325_081500.log   # 第2轮日志
│   └── ...
│
├── sessions/                        # Session 记忆（外部记忆）
│   ├── 20260325-0800.md            # 第1轮 Session
│   ├── 20260325-0815.md            # 第2轮 Session
│   └── ...
│
└── workspace/                       # 代码工作区
    └── zk-cli/                     # 被测试的项目代码
        ├── zk/
        ├── tests/
        └── ...
```

---

## 3. 循环流程图

### 3.1 整体循环架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ZimaBlue 主循环                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  🌅 苏醒阶段（3分钟）                                                    │
│  ├─ 读取 state.json（当前状态）                                          │
│  ├─ 读取最近 3 个 Session（之前做了什么）                                 │
│  └─ 确定本轮任务                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ⚡ 执行阶段（最多 14 分钟）                                              │
│  ├─ 生成 Prompt 文件                                                     │
│  ├─ 启动 kimi-cli 进程                                                   │
│  ├─ kimi 执行 AI 任务（读代码、写测试...）                                │
│  └─ kimi 进程退出                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  📝 结束阶段（1-3 分钟）                                                 │
│  ├─ 解析 kimi 输出 → 提取结果                                            │
│  ├─ 生成 Session 文件（本轮日记）                                         │
│  ├─ 更新 state.json（周期数+1、状态变更）                                 │
│  └─ 判断是否提前完成                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            ┌───────────────┐               ┌───────────────┐
            │  任务已完成？  │               │  继续执行？    │
            │  → 退出循环   │               │  → 休眠 15分钟 │
            └───────────────┘               └───────────────┘
                                                    │
                                                    ▼
                                            ┌───────────────┐
                                            │  😴 休眠       │
                                            │  等待下次唤醒  │
                                            └───────────────┘
                                                    │
                                                    ▼
                                            （回到 🌅 苏醒阶段）
```

### 3.2 详细执行流程

```
单周期详细流程
│
├─ 00:00 苏醒
│   ├─ 读 state.json
│   │   └─ {current_cycle: 5, stage: "fix_failures", async_task: null}
│   │
│   ├─ 读最近 Session
│   │   ├─ 20260325-0800.md: "分析了覆盖率，发现3个命令未覆盖"
│   │   ├─ 20260325-0815.md: "触发了全量测试，正在运行中"
│   │   └─ 20260325-0830.md: "测试完成，5个失败，开始修复"
│   │
│   └─ 确定任务: "继续修复失败的测试"
│
├─ 00:03 执行
│   ├─ 生成 prompt_20260325_084500.md
│   │   └─ "你是 zk-coverage-agent，第5轮，继续修复测试..."
│   │
│   ├─ 启动 kimi
│   │   └─ subprocess.run([
│   │          "kimi", "--print", "--yolo",
│   │          "--prompt-file", "prompt_20260325_084500.md",
│   │          "--work-dir", "./workspace/zk-cli"
│   │      ])
│   │
│   ├─ kimi 执行（约 10 分钟）
│   │   ├─ 读取失败测试文件
│   │   ├─ 分析失败原因
│   │   ├─ 修改测试代码
│   │   ├─ 运行局部测试验证
│   │   └─ 写入结果文件 .zima/result_20260325_084500.json
│   │       └─ {status: "partial", progress: 60, fixed: 3, remaining: 2}
│   │
│   └─ kimi 进程退出（return code 0）
│
├─ 00:13 结束
│   ├─ 读取结果文件
│   ├─ 生成 session_20260325-0845.md
│   │   └─ "修复了3个测试，剩余2个，下轮继续"
│   ├─ 更新 state.json
│   │   └─ {current_cycle: 6, stage: "fix_failures"}
│   └─ 判断: 未完成任务，继续循环
│
└─ 00:14 休眠（因为提前完成，多休眠1分钟）
    └─ 下次唤醒: 00:30
```

---

## 4. 模拟执行：5 轮循环示例

### 场景设定

- **目标**: 检查 zk-cli 测试覆盖率，修复缺失的测试
- **Agent**: zk-coverage-agent
- **周期**: 15 分钟

---

### 第 1 轮：分析覆盖率

**时间**: 08:00 - 08:12（提前 3 分钟完成）

**流程图**:

```
苏醒
│
├─ 读 state.json: {current_cycle: 0, stage: "analyze_coverage"}
├─ 读 Session: （无，第一轮）
└─ 任务: "分析当前测试覆盖率"
│
执行
│
├─ 生成 Prompt:
│   "分析 zk-cli 的测试覆盖率。
│    1. 读取 zk/cli.py 识别所有命令
│    2. 对比 tests/ 目录中的测试文件
│    3. 生成覆盖率报告"
│
├─ 启动 kimi-cli
│
└─ kimi 执行:
    ├─ 读取源代码
    ├─ 识别出 15 个 CLI 命令
    ├─ 对比测试文件
    └─ 发现 3 个命令未覆盖：kb import, kb export, note merge
│
结束
│
├─ 结果: {status: "completed", progress: 100}
├─ 生成 Session:
│   文件: sessions/20260325-0800.md
│   内容:
│     本轮任务: 分析测试覆盖率
│     执行过程: 读取了 cli.py，识别了15个命令
│     结果: 发现3个命令未覆盖
│     产出: 覆盖率报告
│     下轮计划: 触发全量测试
│
├─ 更新 state:
│   {current_cycle: 1, stage: "run_full_test"}
│
└─ 提前完成 → 休眠至 08:15
```

**产出物**:

```
prompts/cycle_20260325_080000.md      # 生成的 Prompt
logs/cycle_20260325_080000.log        # kimi 执行日志（约 200 行）
sessions/20260325-0800.md             # Session 记忆
```

---

### 第 2 轮：触发全量测试

**时间**: 08:15 - 08:18（提前 12 分钟完成，因为是异步任务）

**流程图**:

```
苏醒
│
├─ 读 state.json: {current_cycle: 1, stage: "run_full_test"}
├─ 读 Session:
│   ├─ 20260325-0800.md: "发现3个命令未覆盖，下轮触发全量测试"
│   └─ （只有1个 Session）
│
└─ 任务: "触发全量测试"
│
执行
│
├─ 生成 Prompt:
│   "触发 zk-cli 的全量测试。
│    1. 运行 ./run_full_test.ps1
│    2. 测试可能会运行很久（10-30分钟）
│    3. 启动测试后立即返回，记录进程PID
│    4. 在 .zima/result.json 中写入：
│       {status: "async_started", process_id: xxx}"
│
├─ 启动 kimi-cli
│
└─ kimi 执行:
    ├─ 启动 PowerShell 进程
    ├─ 运行 ./run_full_test.ps1
    ├─ 获取进程 PID: 12345
    ├─ 写入结果文件
    └─ 立即退出（不等待测试完成）
│
结束
│
├─ 结果: {status: "async_started", process_id: 12345}
├─ 生成 Session:
│   文件: sessions/20260325-0815.md
│   内容:
│     本轮任务: 触发全量测试
│     结果: 测试已启动，PID 12345
│     下轮计划: 检查测试是否完成
│
├─ 更新 state:
│   {current_cycle: 2,
│    stage: "check_test_result",
│    async_task: {type: "test_run", pid: 12345, started_at: "08:18"}}
│
└─ 提前完成 → 休眠至 08:30
```

**产出物**:

```
prompts/cycle_20260325_081500.md      # Prompt
logs/cycle_20260325_081500.log        # 日志（较短，因为很快退出）
sessions/20260325-0815.md             # Session
state.json                            # 状态更新（标记异步任务）
```

---

### 第 3 轮：检查测试状态（测试仍在运行）

**时间**: 08:30 - 08:35（提前 10 分钟完成）

**流程图**:

```
苏醒
│
├─ 读 state.json:
│   {current_cycle: 2,
│    stage: "check_test_result",
│    async_task: {pid: 12345, status: "running"}}
│
├─ 读 Session:
│   ├─ 20260325-0800.md: "发现3个命令未覆盖"
│   ├─ 20260325-0815.md: "测试已启动，PID 12345"
│   └─ （记住测试在运行）
│
└─ 任务: "检查测试是否完成"
│
执行
│
├─ 生成 Prompt:
│   "检查异步测试任务的状态。
│    1. 检查进程 PID 12345 是否仍在运行
│    2. 如果仍在运行 → 写入 {status: "waiting"}
│    3. 如果已完成 → 读取测试结果，写入 {status: "completed", result: {...}}"
│
├─ 启动 kimi-cli
│
└─ kimi 执行:
    ├─ 检查进程 12345
    ├─ 进程仍在运行（测试还没跑完）
    └─ 写入结果: {status: "waiting", message: "测试仍在运行"}
│
结束
│
├─ 结果: {status: "waiting"}
├─ 生成 Session:
│   文件: sessions/20260325-0830.md
│   内容:
│     本轮任务: 检查测试状态
│     结果: 测试仍在运行，继续等待
│     下轮计划: 继续检查
│
├─ 更新 state:
│   {current_cycle: 3, stage: "check_test_result"}  # 阶段不变
│
└─ 提前完成 → 休眠至 08:45
```

**关键点**: 测试还在跑，所以阶段保持不变，下轮继续检查。

---

### 第 4 轮：检查测试状态（测试完成）

**时间**: 08:45 - 08:52（提前 8 分钟完成）

**流程图**:

```
苏醒
│
├─ 读 state.json: {current_cycle: 3, stage: "check_test_result", ...}
├─ 读 Session:
│   ├─ 20260325-0800.md: "发现3个命令未覆盖"
│   ├─ 20260325-0815.md: "测试已启动"
│   ├─ 20260325-0830.md: "测试仍在运行"
│   └─ （知道已检查2轮，这是第3次检查）
│
└─ 任务: "检查测试是否完成"
│
执行
│
├─ 生成 Prompt:
│   "检查异步测试任务的状态..."
│
├─ 启动 kimi-cli
│
└─ kimi 执行:
    ├─ 检查进程 12345
    ├─ 进程已结束！
    ├─ 读取测试输出文件
    ├─ 解析结果:
    │   ├─ 总测试: 127
    │   ├─ 通过: 122
    │   ├─ 失败: 5
    │   └─ 失败项: test_import, test_export, test_merge, test_search, test_template
    └─ 写入结果:
       {status: "completed",
        total: 127, passed: 122, failed: 5,
        failures: ["test_import", "test_export", ...]}
│
结束
│
├─ 结果: {status: "completed", failed: 5}
├─ 生成 Session:
│   文件: sessions/20260325-0845.md
│   内容:
│     本轮任务: 检查测试状态
│     结果: 测试完成！127个测试，122通过，5失败
│     失败项: test_import, test_export, test_merge, test_search, test_template
│     下轮计划: 开始修复失败的测试
│
├─ 更新 state:
│   {current_cycle: 4,
│    stage: "fix_failures",          # ← 阶段推进！
│    async_task: null,              # ← 清除异步任务
│    test_result: {failed: 5, ...}}  # ← 保存测试结果
│
└─ 提前完成 → 休眠至 09:00
```

**状态变更**: `check_test_result` → `fix_failures`

---

### 第 5 轮：修复失败的测试

**时间**: 09:00 - 09:13（用满 13 分钟）

**流程图**:

```
苏醒
│
├─ 读 state.json: {current_cycle: 4, stage: "fix_failures", test_result: {...}}
├─ 读 Session:
│   ├─ 20260325-0815.md: "测试已启动"
│   ├─ 20260325-0830.md: "测试仍在运行"
│   ├─ 20260325-0845.md: "测试完成，5个失败，开始修复"
│   └─ （知道要修复5个失败的测试）
│
└─ 任务: "修复失败的测试"
│
执行
│
├─ 生成 Prompt:
│   "修复失败的测试。
│    1. 读取失败的测试文件：test_import.py, test_export.py, ...
│    2. 分析失败原因
│    3. 修复测试代码（或修复被测试的代码）
│    4. 运行局部测试验证修复
│    5. 尽可能多修复几个
│    6. 在 .zima/result.json 中报告修复情况"
│
├─ 启动 kimi-cli
│
└─ kimi 执行（约 10 分钟）:
    ├─ 读取 test_import.py
    ├─ 分析：import 命令缺少错误处理测试
    ├─ 添加测试用例
    ├─ 运行 pytest tests/test_import.py -v ✅ 通过
    │
    ├─ 读取 test_export.py
    ├─ 分析：export 路径验证有问题
    ├─ 修改测试代码
    ├─ 运行 pytest tests/test_export.py -v ✅ 通过
    │
    ├─ 读取 test_merge.py
    ├─ 分析：merge 逻辑复杂，需要更多时间
    ├─ 部分修复...
    │
    ├─ ⏰ 时间检查：只剩 2 分钟
    └─ 保存进度，写入结果:
       {status: "partial",
        progress: 60,           # 60% 完成
        fixed: 2,               # 修复了 2 个
        remaining: 3,           # 还剩 3 个
        details: "修复了 test_import, test_export，test_merge 部分修复"}
│
结束
│
├─ 结果: {status: "partial", progress: 60}
├─ 生成 Session:
│   文件: sessions/20260325-0900.md
│   内容:
│     本轮任务: 修复失败的测试
│     执行过程:
│       - 修复 test_import.py：添加错误处理测试 ✅
│       - 修复 test_export.py：修复路径验证 ✅
│       - 部分修复 test_merge.py（时间不够）
│     结果: 修复了 2/5 个，还剩 3 个
│     进度: 60%
│     下轮计划: 继续修复剩余的测试
│
├─ 更新 state:
│   {current_cycle: 5,
│    stage: "fix_failures",    # ← 阶段不变，继续修复
│    fix_progress: {fixed: 2, remaining: 3}}
│
└─ 休眠至 09:15
```

**关键点**: 这轮没修完，阶段保持 `fix_failures`，下轮继续。

---

## 5. 异常处理流程

### 5.1 kimi-cli 执行超时

```
执行阶段
│
├─ 启动 kimi-cli
│
├─ kimi 执行中...
│
├─ ⏰ 时间检查：已运行 14 分钟（达到上限）
│
└─ 强制终止进程
    ├─ subprocess.TimeoutExpired 异常
    ├─ kill 进程
    └─ 读取已产生的日志
│
结束阶段
│
├─ 结果: {status: "timeout"}
├─ 生成 Session:
│   "本轮超时，任务未完成，已保存进度"
├─ 更新 state:
│   {last_timeout: "20260325-0915", retry_count: 1}
│
└─ 决策:
    ├─ 如果 retry_count < 3 → 下轮重试
    └─ 如果 retry_count >= 3 → 标记为 failed，停止 Agent
```

### 5.2 kimi-cli 执行报错

```
执行阶段
│
├─ 启动 kimi-cli
│
└─ kimi 执行:
    ├─ 读取文件...
    ├─ 修改代码...
    ├─ 运行测试...
    └─ ❌ 报错：测试运行时崩溃
│
结束阶段
│
├─ return code != 0
├─ 结果: {status: "error", error: "测试运行时崩溃"}
├─ 生成 Session:
│   "遇到错误：测试运行时崩溃，下轮重试"
├─ 更新 state:
│   {last_error: "test_crash", retry_count: 1}
│
└─ 决策:
    ├─ retry_count < 3 → 下轮重试
    └─ retry_count >= 3 → failed，停止
```

### 5.3 异步任务卡死

```
场景：测试进程跑了 1 小时还没结束
│
第 4 轮检查
├─ 检查 PID 12345
├─ 进程仍在运行
├─ 但已运行 60 分钟（远超正常时间）
│
结束阶段
├─ 结果: {status: "stuck"}
├─ 生成 Session:
│   "测试进程似乎卡死了，已运行60分钟"
├─ 决策:
│   ├─ kill 进程
│   ├─ 标记为 failed
│   └─ 停止 Agent，等待人工检查
```

---

## 6. Session 文件示例

### 第 1 轮 Session

```markdown
---
id: session-20260325-0800
cycle: 1
agent: zk-coverage-agent
date: 2026-03-25T08:00:00Z
type: session
---

# Session 2026-03-25 08:00

## 本轮任务
- 阶段: analyze_coverage
- 任务: 分析 zk-cli 测试覆盖率

## 执行过程
- 00:02 读取 zk/cli.py，识别所有命令
- 00:05 对比 tests/ 目录
- 00:08 生成覆盖率报告

## 结果
- 状态: ✅ 完成
- 发现: 15 个命令，12 个有测试，3 个缺失
- 缺失命令: kb import, kb export, note merge

## 产出
- 覆盖率报告（在日志中）

## 下轮计划
- 触发全量测试，了解当前测试状态

## 情绪/状态
- 顺利完成任务，对项目结构更清晰了
```

### 第 5 轮 Session

```markdown
---
id: session-20260325-0900
cycle: 5
agent: zk-coverage-agent
date: 2026-03-25T09:00:00Z
type: session
---

# Session 2026-03-25 09:00

## 本轮任务
- 阶段: fix_failures
- 任务: 修复失败的测试（5个）

## 执行过程
- 00:02 读取 test_import.py，分析失败原因
- 00:05 添加错误处理测试用例
- 00:07 运行局部测试 ✅ 通过
- 00:08 读取 test_export.py
- 00:10 修复路径验证逻辑
- 00:12 运行局部测试 ✅ 通过
- 00:13 开始修复 test_merge.py
- 00:14 ⏰ 时间警告：即将超时
- 00:14 保存进度

## 结果
- 状态: ⏸️ 部分完成
- 进度: 60%
- 修复: 2/5 个（test_import, test_export）
- 剩余: 3 个（test_merge, test_search, test_template）

## 遇到的问题
- test_merge 逻辑复杂，需要更多时间
- test_search 依赖外部服务，需要 Mock

## 下轮计划
- 继续修复剩余的 3 个测试

## 学到的经验
- test_import 的错误处理测试模式可以复用
- 局部测试验证很重要，避免回归

## 情绪/状态
- 虽然没修完，但有进展，有信心完成
```

---

## 7. 总结：关键设计要点

### 7.1 循环驱动方式

- **触发**: 定时器（每 15 分钟）
- **执行**: subprocess 调用 kimi-cli（单次执行，执行完即退出）
- **状态**: 通过文件系统传递（state.json + Session 文件）

### 7.2 记忆机制

```
短期记忆（本轮）: Prompt 文件
中期记忆（近期）: 最近 3-5 个 Session 文件
长期记忆（全局）: state.json + 所有 Session
```

### 7.3 异步任务处理

```
启动异步任务 → 记录 PID → 下轮检查 → 完成/继续等待
```

### 7.4 提前完成优化

```
如果任务在 15 分钟内完成 → 立即休眠 → 节省资源
```

---

## 附录：命令速查

```bash
# 创建 Agent
zima agent create \
  --name zk-coverage-agent \
  --workspace ./agents/zk-coverage-agent \
  --task coverage_check

# 启动 Agent
zima agent start zk-coverage-agent

# 查看状态
zima agent status zk-coverage-agent
# 输出:
# Agent: zk-coverage-agent
# 状态: running
# 当前周期: 5
# 阶段: fix_failures
# 进度: 60%

# 查看实时日志
zima agent logs zk-coverage-agent -f

# 停止 Agent
zima agent stop zk-coverage-agent
```
