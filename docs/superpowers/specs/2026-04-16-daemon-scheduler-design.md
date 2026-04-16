# 守护进程模式设计：32 周期定时调度 Agent

> Issue: #21  
> 设计日期: 2026-04-16  
> 状态: 已确认，待实施

---

## 1. 设计目标

在 Zima v2 单次执行模型的基础上，叠加一个可选的**全局守护进程调度层**。守护进程按固定周期运行，在每个周期内部按时间切片触发不同阶段的 PJob 执行，PJob 本身保持单次执行语义不变。

---

## 2. 核心概念

### 2.1 时间模型

| 维度 | 值 |
|------|-----|
| 周期时长 | 45 分钟 |
| 每日周期数 | 32 个（24h × 60min / 45min = 32）|
| 周期编号 | 0 – 31 |
| 周期对齐 | 以当天 00:00 为基准，固定边界对齐 |

### 2.2 周期内阶段划分

每个 45 分钟周期固定划分为 3 个阶段：

| 阶段 | 偏移 | 时长 | 语义 |
|------|------|------|------|
| `work` | T+0m | 20 分钟 | 工作时间，价值输出 |
| `rest` | T+20m | 15 分钟 | 自我反省、能力提升 |
| `dream` | T+35m | 10 分钟 | 整理日志、归纳总结、写入知识库 |

### 2.3 周期类型与映射

只需定义 **5 种周期类型**（type A–E），每日 32 个周期按映射表重复或轮空：

```
cycle 0  -> A
cycle 1  -> A
cycle 2  -> B
cycle 3  -> B
cycle 4  -> C
...
cycle 15 -> 第一次 15 周期结束
cycle 16 -> idle (轮空)
cycle 17 -> A (开始第二次 15 周期迭代)
...
```

- `idle` 表示该周期什么都不执行，守护进程直接睡到下一个周期边界。

---

## 3. 守护进程运行时行为

### 3.1 启动流程

1. 加载 `Schedule` 配置。
2. 计算当前时间所处的周期编号（基于 00:00 对齐）。
3. 等待到下一个周期边界，开始主循环。

### 3.2 周期内部调度

进入周期后，守护进程启动 3 个阶段定时器：

1. **T+0m** → 触发当前 `cycleType` 的 `work` 阶段 PJobs。
2. **T+20m** → 触发 `rest` 阶段 PJobs，同时 **kill 未完成的 work 进程**。
3. **T+35m** → 触发 `dream` 阶段 PJobs，同时 **kill 未完成的 rest 进程**。
4. **T+45m（周期结束）** → 进入下一周期，同时 **kill 未完成的 dream 进程**。

### 3.3 进程管理与超时记录

- 守护进程内部维护 `active_pjobs: dict[str, subprocess.Popen]`。
- 阶段切换时，遍历 `active_pjobs`，对仍在运行的进程：
  1. 先 `kill()`（发送 SIGTERM / taskkill）。
  2. `wait(timeout=5)` 等待优雅退出。
  3. 若仍存活，强制 `kill(force=True)`。
- 每个被 kill 的 PJob 写入历史记录：

```json
{
  "pjobCode": "xxx",
  "scheduleCode": "daily-32",
  "cycleNum": 5,
  "stage": "work",
  "status": "killed_timeout",
  "scheduledAt": "2026-04-16T10:00:00+08:00",
  "killedAt": "2026-04-16T10:20:00+08:00"
}
```

---

## 4. Schedule 配置实体

### 4.1 文件存储

`~/.zima/schedules/{code}.yaml`

### 4.2 Schema

```yaml
apiVersion: zima.io/v1
kind: Schedule
metadata:
  code: daily-32
  name: "每日32周期调度"
spec:
  cycleMinutes: 45
  dailyCycles: 32
  stages:
    - name: work
      offsetMinutes: 0
      durationMinutes: 20
    - name: rest
      offsetMinutes: 20
      durationMinutes: 15
    - name: dream
      offsetMinutes: 35
      durationMinutes: 10

  cycleTypes:
    - typeId: A
      work: [pjob-a1, pjob-a2]
      rest: [pjob-a3]
      dream: [pjob-a4]
    - typeId: B
      work: [pjob-b1]
      rest: [pjob-b2]
      dream: [pjob-b3]
    - typeId: C
      work: [pjob-c1]
      rest: []
      dream: [pjob-c2]
    - typeId: D
      work: []
      rest: []
      dream: []
    - typeId: E
      work: [pjob-e1]
      rest: [pjob-e2]
      dream: [pjob-e3]

  cycleMapping:
    - A   # 0
    - A   # 1
    - B   # 2
    - B   # 3
    - C   # 4
    - C   # 5
    - D   # 6
    - D   # 7
    - E   # 8
    - E   # 9
    - A   # 10
    - B   # 11
    - C   # 12
    - D   # 13
    - E   # 14
    - idle # 15  轮空
    - A   # 16  第二次迭代开始
    - A   # 17
    - B   # 18
    - B   # 19
    - C   # 20
    - C   # 21
    - D   # 22
    - D   # 23
    - E   # 24
    - E   # 25
    - A   # 26
    - B   # 27
    - C   # 28
    - D   # 29
    - E   # 30
    - idle # 31
```

### 4.3 验证规则

- `metadata.code` 必填，符合 `validate_code` 规则。
- `cycleMinutes` 必须 > 0。
- `dailyCycles` 固定为 32（当前设计）。
- `stages` 内的 `offsetMinutes + durationMinutes` 不能超出 `cycleMinutes`；且 `stages` 必须按 `offsetMinutes` 升序排列。
- `cycleMapping` 长度必须等于 `dailyCycles`。
- `cycleMapping` 中出现的所有 `typeId` 必须在 `cycleTypes` 中已定义（`idle` 除外）。
- 可选验证：若 `resolve_refs=True`，校验 `cycleTypes` 中引用的所有 PJob 都存在。

---

## 5. CLI 设计

### 5.1 Schedule 管理命令组

```bash
zima schedule create --code daily-32 --name "每日32周期"
zima schedule list
zima schedule show daily-32
zima schedule update daily-32 --name "新名称"
zima schedule delete daily-32
zima schedule validate daily-32

# 快捷编辑
zima schedule set-type daily-32 --typeId A --stage work --pjobs p1,p2
zima schedule set-mapping daily-32 --index 15 --type idle
```

### 5.2 守护进程命令

```bash
zima daemon start --schedule daily-32
zima daemon stop
zima daemon status
zima daemon logs [--tail 50]
```

- `start`：
  - 检查是否已有守护进程在运行（读取 `~/.zima/daemon.pid`）。
  - 校验 `schedule` 配置是否合法。
  - 以 detached 进程启动守护进程，记录 PID。
- `stop`：读取 PID 文件，发送终止信号，清理 PID。
- `status`：显示守护进程 PID、挂载的 schedule、当前周期编号、当前阶段、运行中的 PJob 数量。
- `logs`：读取 `~/.zima/daemon.log` 并输出尾部内容。

---

## 6. 守护进程内部架构

### 6.1 模块划分

| 模块 | 职责 |
|------|------|
| `zima/models/schedule.py` | `ScheduleConfig`、`ScheduleStage`、`ScheduleCycleType` 数据模型 |
| `zima/commands/schedule.py` | `zima schedule *` CLI 子命令 |
| `zima/core/daemon_scheduler.py` | 守护进程主调度器：`DaemonScheduler` 类 |
| `zima/daemon_runner.py` | 守护进程入口模块（重写旧的 v1 版本） |

### 6.2 DaemonScheduler 核心类

```python
class DaemonScheduler:
    def __init__(self, schedule: ScheduleConfig):
        self.schedule = schedule
        self.running = False
        self.current_cycle = -1
        self.current_stage = None
        self.active_pjobs: dict[str, subprocess.Popen] = {}

    def run(self) -> None:
        # 对齐到周期边界，进入主循环
        ...

    def stop(self) -> None:
        self.running = False

    def _start_stage(self, stage_name: str, pjob_codes: list[str]) -> None:
        # 先清理上一阶段未完成的 PJob
        self._kill_active_pjobs(stage_name="previous")
        # 然后启动本阶段所有 PJob
        ...

    def _kill_active_pjobs(self, stage_name: str) -> None:
        # 遍历 active_pjobs，kill 并记录 killed_timeout 历史
        ...
```

### 6.3 执行 PJob

守护进程执行 PJob 时，直接复用现有单次执行能力，但改为通过 `subprocess.Popen` 异步启动：

```python
cmd = [sys.executable, "-m", "zima.cli", "pjob", "run", pjob_code]
process = subprocess.Popen(
    cmd,
    stdout=log_file.open("w"),
    stderr=subprocess.STDOUT,
    cwd=...,
)
self.active_pjobs[pjob_code] = process
```

> 注意：不直接复用 `zima.core.executor` 中的同步 `run()`，因为守护进程需要异步跟踪进程生命周期。

---

## 7. 运行时文件

| 文件 | 用途 |
|------|------|
| `~/.zima/daemon.pid` | 当前守护进程 PID |
| `~/.zima/daemon.log` | 守护进程主日志（启动、停止、周期切换、错误） |
| `~/.zima/daemon/state.json` | 运行时状态：当前周期、当前阶段、active_pjobs 列表 |
| `~/.zima/daemon/history/` | PJob 执行历史记录，按日期分文件：`2026-04-16.jsonl` |

---

## 8. 错误处理与边界情况

### 8.1 PJob 启动失败

- 若 `Popen` 抛出异常（如 PJob 配置不存在），守护进程记录错误日志，但该阶段其他 PJob 继续启动。
- 失败记录写入 history：`status: launch_failed`。

### 8.2 守护进程崩溃恢复

- 当前设计**不支持**断点续跑。`zima daemon start` 会重新对齐到当前周期边界，从当前周期开始执行。
- 历史记录保留，供人工排查。

### 8.3 长时间 PJob（超时）

- 阶段切换时统一 kill，不存在 slot 跨周期保留机制（v1 明确不支持）。
- 被 kill 的 PJob 状态为 `killed_timeout`，日志文件保留。

### 8.4 周期边界错过

- 若守护进程因某种原因睡过了头（如系统休眠）， wake 后计算当前周期编号，跳到正确的周期继续，**不补跑**错过的阶段。

---

## 9. 与现有代码的关系

### 9.1 不变的部分

- `AgentConfig`、`AgentRunner` — 完全不变。
- `PJobConfig`、单次执行 `zima run` / `zima pjob run` — 完全不变。
- `zima/core/daemon.py` 中的 `start_daemon` / `stop_daemon` / `is_daemon_running` — 保留作为进程管理工具函数。

### 9.2 废弃的部分

- `zima/core/scheduler.py` 中的 `CycleScheduler`（15 分钟 agent 循环，v1 遗留）— **标记为废弃**，守护进程新调度器由 `DaemonScheduler` 接管。
- `zima/daemon_runner.py`（旧入口）— **重写**，替换为新的 v3 调度入口。

### 9.3 新增的部分

- `zima/models/schedule.py`
- `zima/commands/schedule.py`
- `zima/core/daemon_scheduler.py`
- `zima/daemon_runner.py`
- `zima/cli.py` 中注册 `schedule` 子命令和 `daemon` 命令。

---

## 10. 测试策略

1. **模型测试**：`ScheduleConfig` 的 `from_dict` / `to_dict` / `validate`。
2. **调度逻辑测试**：用 mocked `datetime.now()` 验证周期边界计算、阶段触发时机。
3. **进程管理测试**：mock `subprocess.Popen`，验证阶段切换时的 kill 行为与历史记录写入。
4. **CLI 集成测试**：`zima schedule create` / `show` / `daemon start --dry-run`（若支持 dry-run）。

---

## 11. 未来扩展（记录，不在本阶段实施）

- **Slot 机制**：允许 PJob 跨周期长时间运行，不被阶段切换 kill。
- **动态 schedule 重载**：守护进程运行中 `SIGHUP` 或 `zima daemon reload` 重载配置。
- **Web 状态页**：通过本地 HTTP 端口暴露当前周期、阶段、PJob 状态。
