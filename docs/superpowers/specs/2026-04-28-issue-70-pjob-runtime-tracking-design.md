# PJob 运行时状态追踪与生命周期管理 — 设计文档

- **Issue**: [#70](https://github.com/zhuxixi/zima-blue-cli/issues/70)
- **日期**: 2026-04-28
- **状态**: 待实现

## 1. 动机

当前 PJob 缺少运行时状态追踪：

- 无 `status`/`ps` 命令查询正在运行的 pjob
- 无 `cancel` 命令终止运行中的 pjob
- 后台运行的 pjob PID 只打印到控制台，不持久化
- 执行历史仅在完成后写入，无法区分"从未运行"和"正在运行中"
- Daemon 调度历史与 CLI 历史分离（`~/.zima/daemon/history/*.jsonl` vs `~/.zima/history/pjobs.json`）

## 2. 设计决定

| 项目 | 决定 |
|------|------|
| 默认运行模式 | 后台（去掉 `-b`/`--background`，去掉前台模式） |
| `zima pjob status <code>` | 列出指定 pjob 的所有执行（running + 最近 completed） |
| `zima pjob ps` | 列出所有正在运行的 pjob（类 docker ps） |
| `zima pjob cancel <code>` | SIGTERM → 等 5s → SIGKILL，支持 `--id` 指定执行 |
| 历史存储 | `~/.zima/history/pjobs/<code>/<id>.json`，启动即创建，完成后更新 |
| 并发 | 允许同一 pjob 并发多个实例 |
| Daemon 统一 | daemon 调度的 pjob 也用同一套 history 目录 |

## 3. 数据布局

### 3.1 目录结构

```
~/.zima/history/pjobs/
├── jfox-kc-code-review-job/
│   ├── a1b2c3d4.json    # status: "success" (已完成)
│   └── e5f6g7h8.json    # status: "running" (正在运行)
├── borobo-pr-review/
│   └── 9i0j1k2l.json    # status: "failed"  (已完成)
└── ...
```

### 3.2 状态文件格式

每个 execution 一个 JSON 文件，承载完整生命周期：

```json
{
  "execution_id": "e5f6g7h8",
  "pjob_code": "jfox-kc-code-review-job",
  "status": "running",
  "pid": 106804,
  "command": ["kimi", "code", "--prompt", "..."],
  "started_at": "2026-04-28T10:30:00+08:00",
  "finished_at": null,
  "duration_seconds": null,
  "returncode": null,
  "stdout_preview": "",
  "stderr_preview": "",
  "error_detail": "",
  "log_path": "~/.zima/logs/background/jfox-kc-code-review-job-e5f6g7h8.log",
  "agent": "kimi",
  "workflow": "code-review"
}
```

**状态值**: `running` | `success` | `failed` | `timeout` | `cancelled` | `dead`

- `running`: 进程正在执行（启动时写入）
- `dead`: 进程已消失但状态未更新（崩溃恢复，由 `status` 命令检测并标记）
- 其余为终态，与现有 `ExecutionRecord.status` 一致

### 3.3 旧格式迁移

`~/.zima/history/pjobs.json` 中的数据按 `pjob_code` 分组拆分为独立文件：

```
pjobs.json
  {
    "foo": [ {execution_id: "a", ...}, {execution_id: "b", ...} ],
    "bar": [ {execution_id: "c", ...} ]
  }
        ↓ 迁移
history/pjobs/
├── foo/
│   ├── a.json
│   └── b.json
└── bar/
    └── c.json
```

迁移由 `ExecutionHistory` 类在首次访问时自动完成（惰性迁移）。

### 3.4 日志文件

后台执行日志仍保留在 `~/.zima/logs/background/<code>-<id>.log`。

## 4. CLI 命令

### 4.1 `zima pjob run <code>`（重构）

- **删除参数**: `--background`/`-b`、`--follow`/`-f`、`--quiet`/`-q`
- **新增参数**: 无（默认后台）
- **行为**:
  1. 生成 8 字符 execution_id
  2. 创建状态文件 `~/.zima/history/pjobs/<code>/<id>.json`（`status: "running"`）
  3. `Popen` 启动子进程 `python -m zima.execution.background_runner <code>`
  4. 子进程 stdout/stderr 重定向到日志文件
  5. 更新状态文件填入实际 PID
  6. 打印摘要，返回

输出示例：
```
✓ PJob 'foo' started
  Execution ID: a1b2c3d4
  PID: 12345
  Log: ~/.zima/logs/background/foo-a1b2c3d4.log
  Status: zima pjob status foo
```

### 4.2 `zima pjob status <code>`（新增）

列出指定 pjob 的所有执行：先显示 running 的，再显示最近 5 条已完成的。

输出示例：
```
jfox-kc-code-review-job — 3 executions
┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ ID         ┃ Status    ┃ Started                ┃ Duration ┃ Log          ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ e5f6g7h8   │ ● running │ 2026-04-28 10:30:00    │ 5m 12s   │ e5f6g7h8.log │
│ a1b2c3d4   │ ✓ success │ 2026-04-28 09:00:00    │ 3m 45s   │ a1b2c3d4.log │
│ 9i0j1k2l   │ ✗ failed  │ 2026-04-27 14:00:00    │ 1m 20s   │ 9i0j1k2l.log │
└────────────┴───────────┴────────────────────────┴──────────┴──────────────┘
1 running, 2 completed
```

对 `status: "running"` 的文件会通过 OS 验证 PID 是否存活。如果 PID 已死，标记为 `dead` 并在表格中显示 `☠ dead`。

### 4.3 `zima pjob ps`（新增）

列出所有正在运行的 pjob。

输出示例：
```
Running PJobs
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Code                    ┃ ID       ┃ PID    ┃ Started              ┃ Duration ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ jfox-kc-code-review-job │ e5f6g7h8 │ 106804 │ 2026-04-28 10:30:00  │ 5m 12s   │
│ borobo-pr-review        │ f9a8b7c6 │ 108912 │ 2026-04-28 10:35:00  │ 0m 30s   │
└─────────────────────────┴──────────┴────────┴──────────────────────┴──────────┘
2 running
```

### 4.4 `zima pjob cancel <code>`（新增）

```
zima pjob cancel <code> [--id <execution_id>]
```

- 无 `--id`: 取消该 pjob 所有 running 实例
- 有 `--id`: 取消指定 execution
- 策略: `SIGTERM` → 等 5s → `SIGKILL`
- Windows: `taskkill /PID <pid>` → `taskkill /F /PID <pid>`
- 取消后更新状态文件: `status: "cancelled"`, 填充 `finished_at`, `duration_seconds`

### 4.5 `zima pjob history <code>`（改造）

- 参数不变: `--limit`, `--status`, `--clear`, `--detail`
- 改用新的目录扫描方式读取历史
- `--clear` 删除 `~/.zima/history/pjobs/<code>/` 下所有文件
- 对于 `status: "running"` 的记录，在表格中用黄色显示，标注 `(running)`

### 4.6 `zima pjob list`（不变）

仅做微小增强：如果该 pjob 有 running 实例，在 Labels 列后加一个 `●` 指示器。

## 5. 执行流程

### 5.1 启动流程

```
zima pjob run foo
  │
  ├─ 1. 生成 execution_id (uuid4 前 8 字符)
  ├─ 2. 创建状态文件: ~/.zima/history/pjobs/foo/<id>.json
  │     status: "running", pid: null, started_at: now
  ├─ 3. Popen 启动子进程:
  │     python -m zima.execution.background_runner <code> \
  │         --execution-id <id> --overrides <json>
  │     stdout/stderr → ~/.zima/logs/background/foo-<id>.log
  ├─ 4. 更新状态文件: pid = process.pid
  ├─ 5. 打印摘要
  └─ 6. 返回
```

### 5.2 子进程

```
background_runner (独立进程)
  ├─ PJobExecutor.execute(foo) — 同步执行
  ├─ 完成后更新状态文件:
  │     status: "success" | "failed",
  │     finished_at: now,
  │     duration_seconds: elapsed,
  │     returncode: <code>,
  │     stdout_preview: <前 500 字符>,
  │     stderr_preview: <前 500 字符>
  └─ 退出
```

### 5.3 状态查询

```
zima pjob status foo
  ├─ 扫描 ~/.zima/history/pjobs/foo/*.json
  ├─ 对 status: "running" 的文件:
  │     OS 查询 PID 是否存在
  │     存在 → 计算 duration，显示为 running
  │     不存在 → 标记 status: "dead"
  └─ 按 started_at 倒序列出
```

### 5.4 取消流程

```
zima pjob cancel foo --id e5f6g7h8
  ├─ 读取状态文件: pid = 106804
  ├─ SIGTERM (Unix) / taskkill (Windows)
  ├─ 轮询 wait(5s)
  │     进程退出 → 更新 status: "cancelled"
  │     未退出 → SIGKILL / taskkill /F → 更新 status: "cancelled"
  └─ 如果 PID 已不存在: 直接标记 status: "dead"
```

## 6. 代码变更范围

### 6.1 新增/修改文件

| 文件 | 变更 |
|------|------|
| `zima/execution/history.py` | 重构：目录扫描替代单文件 JSON，支持 running 状态，惰性迁移 |
| `zima/commands/pjob.py` | 新增 `status`/`ps`/`cancel` 命令，重构 `run`（默认后台），改造 `history` |
| `zima/execution/background_runner.py` | 新增 `--execution-id` 参数，启动时写状态文件、完成时更新 |
| `zima/core/daemon_scheduler.py` | `_start_pjob` 改用新 history 目录写入状态文件 |

### 6.2 公共接口设计

**`ExecutionHistory` 类重构：**

```python
class ExecutionHistory:
    HISTORY_DIR_NAME = "pjobs"

    def write_runtime_state(self, pjob_code, execution_id, state) -> Path:
        """启动时写入 runtime 状态文件（status: running）"""

    def update_runtime_state(self, pjob_code, execution_id, **fields) -> None:
        """完成后更新状态文件（status, returncode, duration 等）"""

    def get_runtime_state(self, pjob_code, execution_id) -> Optional[dict]:
        """读取单个执行的状态文件"""

    def list_executions(self, pjob_code, status=None) -> list[dict]:
        """列出指定 pjob 的所有执行记录"""

    def get_running_executions(self, pjob_code=None) -> list[dict]:
        """获取 running 状态的执行（可选按 pjob_code 过滤）"""

    def get_all_running(self) -> list[dict]:
        """获取所有正在运行的执行"""

    def clear_history(self, pjob_code) -> bool:
        """删除 pjob 目录下所有文件"""

    def get_stats(self, pjob_code) -> dict:
        """统计信息（总数、成功率、平均耗时）"""

    def _migrate_from_legacy(self) -> None:
        """惰性迁移 pjobs.json → 目录结构"""
```

## 7. 测试策略

### 7.1 单元测试 (`tests/unit/`)

- `ExecutionHistory` 的目录读写、状态更新、惰性迁移
- 状态文件字段验证
- `get_running_executions` 过滤逻辑
- 旧格式迁移正确性（`pjobs.json` → 目录）

### 7.2 集成测试 (`tests/integration/`)

- `zima pjob run <code>` 默认后台，状态文件创建
- `zima pjob status <code>` 显示 running 和 completed
- `zima pjob ps` 列出运行中 pjob
- `zima pjob cancel <code>` 终止进程，状态变为 cancelled
- `zima pjob history <code>` 读取新格式
- 并发 run 同一 pjob（多个 execution_id）
- PID 崩溃恢复（标记 dead）

### 7.3 Mock 策略

- 使用 `monkeypatch` 模拟 `subprocess.Popen`
- 使用 `tests/conftest.py` 中的 `isolated_zima_home` fixture
- 模拟 OS 进程查询（`os.kill(pid, 0)` / `psutil.pid_exists`）

## 8. 崩溃恢复

### 8.1 CLI 进程崩溃（启动阶段）

状态文件已创建但子进程未启动（pid: null），或子进程启动后 CLI 崩溃：
- `status` 命令检测到 pid 为 null 且 `started_at` 超过 2 分钟 → 标记为 `dead`

### 8.2 子进程崩溃

- `status` 命令通过 `os.kill(pid, 0)` 检测 PID 是否存在
- PID 不存在且状态仍为 running → 标记为 `dead`

### 8.3 Daemon 崩溃

- Daemon 重启时读取所有 `status: "running"` 的文件
- 通过 PID 验证是否存活，清理已死进程的状态

## 9. Windows 兼容

- `subprocess.CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` 保持
- `taskkill /PID <pid>` 替代 SIGTERM
- `taskkill /F /PID <pid>` 替代 SIGKILL
- 路径使用 `Path`，避免硬编码 `/`
