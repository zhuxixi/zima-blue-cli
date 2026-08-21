# issue-181 spec：执行层同 PR 同 head 查重（防双流重复审查）

> 2026-08-22 · github-issue-driven / issue-research → design
> 根因与修复落点见 `research/去重机制盘点与修复落点.md`

## 背景与根因

打标签触发 webhook 审查流 + 手动 `zima pjob run` 流并行审同一 PR 同一 head：各自独立维护 round 计数、发 round 相同且 new_count 不同的 `pi-cr-meta` review；迟到的流打破收敛判定（jfox PR #402 实测：一条流收敛即合并，另一条迟到 12h 带 high bug）。

现有 60s 去重（`zima/webhook/server.py` 的 `_dup_key`）只在 **webhook server 单进程内存** 里防瞬时重复投递，防不住「manual 流」——它完全不经过 server。

实测场景（用户确认）：此问题**很少见**，上次是 agent 手动补跑了一条 `zima pjob run`，与 webhook 流形成并行。核心诉求 = **执行前查重：同 PR 同 head 已有现存/完成的执行 → 跳过**。

## 三条流统一经过 executor（本次修复的关键事实）

```
webhook 流: server spawn `zima pjob run`（注入 --set-var=repo/pr_number/pr/head_sha/source）
manual 流:  用户  `zima pjob run ... --set-var=repo/pr_number/pr`
daemon 流:  调度器 spawn `zima pjob run`
         ↓ 全部
CLI pjob run → 先写 running 状态文件 → spawn background_runner → PJobExecutor.execute()
```

- CLI 在 spawn 前已写 `~/.zima/history/pjobs/<code>/<execution_id>.json`（status=running）——**跨进程共享**，查重的天然载体。
- `execute()` preExec scan_pr 后，`scan_pr_result = {repo, pr_number}` 已持久化（权威、三流一致）。
- head_sha 仅 webhook 流可得（`--set-var=head_sha`）；manual/daemon 流通常没有 → 查重需有 head_sha 缺失的退化路径。
- 现有 `ExecutionStatus.SKIPPED` + preExec 的 `except SkipAction → SKIPPED + 不跑 postExec` 可完整复用 = 被查重拦截的执行**不发 review、不动标签**。

## 目标 / 非目标

**目标**
1. 同一 PJob 对同一 `(repo, pr_number, head_sha)` 的重复审查被拦截（running 或近期已成功）。
2. 拦截后执行走 SKIPPED 路径：不发 review、不跑 postExec、不动标签。
3. 新 commit（head_sha 变化）触发的合法新一轮**不**被误拦。
4. 逃生舱：手动明确要跑时可用 `--dedup-off` 强制。

**非目标（本 issue 不做）**
- review meta 加 `source`/`execution_id` 字段（Phase 2 可选，收敛判定侧辅助；查重从源头消灭多流后价值下降）。
- postExec 标签仲裁（查重后无多流并发收尾，不再需要）。
- zima-pr-monitor skill 的多流纪律（PR #182 已落，见 issue 尾部说明）。

## 详细设计

### 1. 状态文件扩展：`scan_pr_result` 增加 `head_sha`

`zima/execution/executor.py` scan_pr_result 组装处（约 line 493），从 bundle/overrides 变量读 `head_sha`（webhook 注入者才有；缺失则省略该键）：

```python
result.scan_pr_result = {
    k: v for k, v in {
        "repo": _persistable_repo,
        "pr_number": _persistable_pr,
        "head_sha": (……从 runtime overrides / bundle 变量读 head_sha，规范化为小写 hex 或空……),
    }.items() if v
}
```

向后兼容：旧状态文件无 `head_sha` → 按「head 未知」处理（见决策表）。

#### 1b. 【关键】scan_pr_result 必须**立即落盘**，不能等执行结束

现状：`result.scan_pr_result` 只是内存赋值，状态文件里的 `scan_pr_result` 要等 `background_runner` 在 execute() **全部结束后**才写。若查重依赖状态文件，则「正在跑的对方」在审完（7-13 分钟）之前都不携带 repo/pr_number——查重窗口内双方互相看不见，双流照跑。

修法：preExec scan 完成、`result.scan_pr_result` 赋值后**立即** `self._history.update_runtime_state(pjob_code, execution_id, scan_pr_result=result.scan_pr_result)`（仅 `not dry_run`；CLI 已写过 running 状态文件，update 是合并更新）。这样任何流一旦 scan 完成，全机可见其目标键。

剩余竞态窗口：从 spawn 到 scan 完成（fetch_diff 数秒）。窗口内触发的新流查不到对方 → 放行，与现状行为相同，不是回归；scan 完成后的新流必然能拦。

### 2. 查重 guard：`ExecutionHistory.find_recent_duplicate()`

`zima/execution/history.py` 新增方法（内聚 + 单测友好）：

```python
def find_recent_duplicate(
    self,
    pjob_code: str,
    repo: str,
    pr_number: str,
    head_sha: str,
    exclude_execution_id: str,
    window_minutes: int = 30,
) -> Optional[dict]:
    """Return the first recent execution that duplicates the given review target.

    A duplicate is: same (repo, pr_number) AND (running OR success within
    window). Two executions with *different known* head_sha values are NOT
    duplicates (new commit → new review round is legitimate). Missing head_sha
    on either side is treated conservatively as "same head".
    """
```

实现要点：
- 遍历 `self.list_executions(pjob_code)`（自动把 stale running 标 dead，安全）。
- `exclude_execution_id`：跳过自己（当前执行的状态文件）。
- repo 比较小写归一（server 层已是小写 full_name；scan 出来也是 full_name）。
- pr_number 用 `normalize_pr_number` 归一比较。
- 决策（命中即返回该记录）：

| 候选执行状态 | head_sha 同/异/未知 | 结果 |
|---|---|---|
| running | 同 / 未知 | **拦**（同 PR 正在审，勿并行） |
| running | 异 | **不拦**（新 head 不能等旧轮） |
| success 且 started_at ≥ now-30min | 同 / 未知 | **拦**（同 head 近期已审出结果） |
| success 且 started_at ≥ now-30min | 异 | **不拦**（新一轮） |
| failed / timeout / cancelled / skipped / dead / success 超窗 | 任意 | **不拦**（没产出有效 review，重跑合法） |

- head 比较：双方都有 head_sha 才判「异」；任一缺失 → 按「同」处理（保守）。

### 3. 调用点：preExec **try 块内**，scan_pr_result 赋值 + 立即落盘之后

⚠️ 位置约束：`except SkipAction` 只包住 preExec 的内部 try（executor.py ~line 497-505）。抛在 try 之外会被最外层 `except Exception` 捕获 → status=FAILED，且会走 postExec failure 分支（错误改标签）。guard 必须放 preExec try 块内。

`zima/execution/executor.py`（`result.scan_pr_result = {...}` 与 §1b 立即落盘之后、preExec try 结束前）：

```python
if not dry_run and result.scan_pr_result:
    dup = self._history.find_recent_duplicate(
        pjob_code=pjob_code,
        repo=result.scan_pr_result.get("repo", ""),
        pr_number=result.scan_pr_result.get("pr_number", ""),
        head_sha=result.scan_pr_result.get("head_sha", ""),
        exclude_execution_id=execution_id,
    )
    if dup and not dedup_off:
        raise SkipAction(
            f"dedup: same ({repo}, PR #{pr_number}) already "
            f"{dup.get('status')} by execution {dup.get('execution_id')} "
            f"(started {dup.get('started_at', '?')}); skipping duplicate review. "
            f"Use --dedup-off to force."
        )
```

- 抛 `SkipAction` → 被既有 `except SkipAction` 捕获 → `status=SKIPPED`、return、**跳过 postExec**。零新增状态处理。
- `dry_run` 跳过查重（dry-run 不实际 spawn，不该拦）。

### 4. 逃生舱：`--dedup-off`

- `zima/commands/pjob.py run` 新增 `--dedup-off` flag → 传入 `execute(..., dedup_off=True)`（或经 overrides 带标记）。
- `PJobExecutor.execute()` 签名加 `dedup_off: bool = False`。
- `background_runner.run_pjob_in_background` 透传（可选，保持 CLI 层已足够——手动优先用 CLI；webhook/daemon 默认不开）。
- webhook server / daemon 不传 → 默认查重生效。

### 5. 竞态处理

两条流同时启动、都还没跑到 scan_pr 完成时，先 scan 完的立即落盘 scan_pr_result 后查重看不到另一条（对方未落盘）→ 放行；后 scan 完的会看到先者的 running → 拦截。几乎总能拦到后到者；极端同微秒双跑 = 现状行为，不算回归。

### 6. 边界决策（显式记录，防将来被「修坏」）

- **只查同 `pjob_code`，不跨 PJob**：历史上 cc/kimi 双 bot 并行审同一 PR 是设计行为（跨 PJob 查重会误拦）。跨 PJob 去重不是本 issue 的语义。
- **异 head 放行后的残留**：同 PR 不同 head 的双流可并行（合法，旧轮收尾快），其 postExec 标签竞争仍存在 → Phase 2 的仲裁项，spec 已排除。
- **影响面**：查重对**所有**带 scan_pr 的 PJob 通用生效（非仅 CR）。同 (repo, pr, head) 30min 内重复执行统一语义，`--dedup-off` 为逃生舱。
- **坏数据容忍**：候选记录缺 started_at / 时间戳解析失败 / repo 大小写 → 前者保守按「同 head + 在窗」拦（宁可多拦避免双流），后者小写归一比较。

## 变更清单（文件级）

| 文件 | 改动 |
|---|---|
| `zima/execution/history.py` | 新增 `find_recent_duplicate()` |
| `zima/execution/executor.py` | scan_pr_result 加 head_sha；加查重 guard（抛 SkipAction）；`execute()` 加 `dedup_off` 参数 |
| `zima/commands/pjob.py` | `run` 加 `--dedup-off` flag 并透传 |
| `tests/unit/test_history_dedup.py`（新） | `find_recent_duplicate` 决策表单测 |
| `tests/unit/test_executor_dedup.py`（新/并入） | 查重拦截→SKIPPED、dry-run 不拦、dedup-off 绕过 |

## 验证计划

1. **单测（决策表）**：running/近期 success 同 head→拦；异 head→放；failed→放；超窗→放；head 未知（旧状态文件）→按同 head 保守拦；排除自身；跨 PJob 不拦。
2. **单测（立即落盘）**：preExec 后状态文件即刻含 scan_pr_result（含 head_sha）；dry_run 不写状态文件。
3. **集成**：`pjob run`（带 --set-var repo/pr_number）连续跑同键两次——第二次 SKIPPED，history 有 skipped 记录且无 postExec 副作用；第二次的 skipped 记录含 scan_pr_result（供后续流可见）。
4. **手动端到端（可选）**：webhook 触发 + 立即手动 `pjob run` 同 repo/pr_number —— 确认先 scan 完者存活、后到者被拦。

## 遗留 / 后续（Phase 2，另行评估）

- review meta 加 `source`+`execution_id`；postExec 标签仲裁；`zima-pr-monitor` 的 `zima pjob ps` in-flight 归因修正（并行开发仓库误报，见 JFox note 202608211102533541）。
