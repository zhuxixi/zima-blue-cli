# Spec：zima 执行用量账本（issue #213）

- **状态**：draft，待用户批准
- **日期**：2026-09-14
- **父 issue**：#213（feat(observability): zima 执行历史缺少 token/cost 落盘）
- **上游依赖方**：#212（优化点 4、5 的决策依赖本账本产出实测数据）
- **调研记录**：`~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-213/research/`

---

## 1. 目标

让 zima 的每次执行记录里带上这次执行真实消耗的 tokens 与估算成本，覆盖父 agent 与全部子代理，从而让 #212 的降本改动可以用数据验证，而不是靠"被阻止的执行数 × 预估单次成本"估算。

**成功判据**：跑完一轮真实 CR 后，能在 `zima pjob history <code> --detail <id>` 里读到与 pi 本地统计一致的 tokens/cost，并且能按 model 看出 fast 档与 strong 档各消耗多少。

## 2. 非目标

- 不做聚合查询命令（如"按 provider 统计过去 30 天"）。数据落盘后需要时另开 issue。
- 不采集 kimi / claude 类型 agent 的用量（字段设计对类型中立，实现先只做 pi）。
- 不长期留存 transcript：会话文件写在本次执行的 temp 目录，随执行结束删除。
- 不改 daemon 的 `~/.zima/daemon/history/*.jsonl`，不改 CR skill 的任何文件。
- 不做成本归因（哪部分是现金、哪部分是订阅额度）——只记录 provider/model + tokens + 估算 cost。

## 3. 术语

| 术语 | 含义 |
|------|------|
| session 文件（会话文件） | pi 把一次对话的每条消息写成 JSONL 的记录文件；每条 assistant 消息带 `usage`（input/output/cacheRead/cacheWrite/totalTokens/cost） |
| `--session-dir` | pi 启动参数，指定会话文件写到哪个目录（替代默认的 `~/.pi/agent/sessions`） |
| `--no-session` | pi 启动参数，"不写会话文件"，用内存 session；**优先级高于 `--session-dir`** |
| 子代理（subagent） | CR 工作流通过 subagent 工具派发的子 agent，CR 的主要成本在这里 |
| `subagent-artifacts` | pi-subagents 存放子代理产物的目录，每个子代理一份 `*_meta.json`（带 model + usage + turns） |

## 4. 已拍板的设计决策

| # | 决策 | 理由 |
|---|------|------|
| D1 | 采集范围 = 父 agent + 全部子代理，且存分维度明细（按 role/agent/provider/model 聚合） | 实测一次执行中子代理 input 650 万 token，CR 主成本在子代理；temp 目录跑完即删，明细是唯一一次采集机会 |
| D2 | **不设开关**：pi 类型的命令一律传 `--session-dir <temp>/pi-sessions`，彻底移除 `--no-session` 分支 | 用户决策。`--session-dir` 指向 temp 后不碰全局会话目录（实测验证），净效果与"用完就扔"等价，却多出可观测性 |
| D3 | `noSession` 字段退役：从 pi 默认参数中删除；已有 YAML 里的残留当未知参数忽略 | `validate()` 不校验参数键，残留不会报错；避免留一个"看着像开关但无效"的字段 |
| D4 | 展示层只做 `pjob history --detail` 一行汇总 | YAGNI；聚合命令留给后续 issue |

## 5. 数据面设计

### 5.1 采集来源与排除规则

采集根目录：`<temp_dir>/pi-sessions/`（`temp_dir = ~/.zima/temp/pjobs/<pjob_code>-<execution_id>/`）。

| 来源 | 覆盖 | 处理 |
|------|------|------|
| `<root>/*.jsonl`（顶层会话文件） | 父 agent | 逐行读，取 `type == "message"` 且 `message.role == "assistant"` 且有 `message.usage` 的记录累加 |
| `<root>/subagent-artifacts/*_meta.json` | 子代理 | 每个文件一条子代理记录，取 `agent` / `model` / `usage{input,output,cacheRead,cacheWrite,cost,turns}` |
| `<root>/forks/**` | 子代理 fork 的父上下文副本 | **排除**——含父消息副本，纳入会重复计数 |
| `<root>/subagent-artifacts/*_transcript.jsonl` | 子代理逐轮明细 | **排除**——与 meta.json 的汇总重复 |

pi 会自行递归创建 `--session-dir` 指向的目录（实测 `--session-dir <absent>/nested` 仍成功并落盘），zima 无需预建；但预建一次无副作用，允许实现时顺手 `mkdir(parents=True, exist_ok=True)`。

### 5.2 落盘数据形状

成功：

```json
"usage": {
  "collected": true,
  "totals": {"input": 6550000, "output": 10700, "cache_read": 76800,
             "cache_write": 0, "total_tokens": 6560700, "cost_usd": 0.4941},
  "by_role": {
    "parent": {"input": 17000, "output": 163, "cache_read": 0,
               "cache_write": 0, "total_tokens": 17163, "cost_usd": 0.0015},
    "children": {"input": 6533000, "output": 10537, "cache_read": 76800,
                 "cache_write": 0, "total_tokens": 6543537, "cost_usd": 0.4926}
  },
  "by_model": [
    {"role": "parent", "agent": null, "provider": "zai-coding-cn", "model": "glm-5.3",
     "input": 17000, "output": 163, "cache_read": 0, "cache_write": 0,
     "total_tokens": 17163, "cost_usd": 0.0015, "turns": null},
    {"role": "child", "agent": "checker", "provider": "zai-coding-cn",
     "model": "glm-5.3-flash", "input": 6533000, "output": 10537, "cache_read": 76800,
     "cache_write": 0, "total_tokens": 6543537, "cost_usd": 0.4926, "turns": 24}
  ],
  "children_count": 1,
  "cost_note": "estimated"
}
```

失败（fail-open）：

```json
"usage": {"collected": false, "reason": "no_session_dir"}
```

`reason` 取值集合：`no_session_dir` | `empty` | `parse_error` | `unsupported_agent_type`。

**采集只对真正启动过 agent 的执行发生**：dry-run 与 `SKIPPED`（去重跳过、熔断冷却、trivial 跳过）不采集，`usage` 保持缺失（展示为 `unknown (not_collected)`）——不伪造 `no_session_dir` 这类失败原因，记录自身的 `status` 字段已说明原因。

**约束**：

- `by_model` 按 `(role, agent, provider, model)` 四元组聚合，**不逐条消息存**。
- 失败形状**不含** `totals` 字段——不允许用 0 冒充"没采到"。
- `cost_note` 固定 `"estimated"`：pi 的 cost 来自内置价格表，订阅制 provider 上是估算值（实测 `zai-coding-cn` 也产出非零 cost），不代表现金支出。
- 只存数字，不存 prompt / stdout / 文件路径。

### 5.3 展示形状

`zima pjob history <code> --detail <id>` 新增一行：

```
Usage:  in 6.55M / out 10.7K  ·  est. $0.49  ·  parent 3% / children 97%

（无数据时）  Usage:  unknown (no_session_dir)
（非 pi 时）  Usage:  unknown (unsupported_agent_type)
（老记录/执行中）  Usage:  unknown (not_collected)
```

数值用人类可读单位（K/M）保留两位小数；`parent/children` 占比按 `total_tokens` 算。

`not_collected` 是**展示侧**的标记（记录里根本没有 `usage` 字段，或执行仍在 running），不属于 §5.2 的 `reason` 取值集合；`reason` 只用于 `collected: false` 的记录。

## 6. 命令构造设计

**保持 `AgentConfig` 对 temp 目录零依赖**，用现有 `extra_args` 机制注入运行时参数。

1. `zima/models/agent.py`
   - `AGENT_PARAMETER_TEMPLATES["pi"]`：删除 `"noSession": True`。
   - `_build_pi_command()`：删除 `noSession → --no-session` 分支；新增
     `if params.get("sessionDir"): cmd.extend(["--session-dir", str(params["sessionDir"])])`。
   - 文档字符串同步更新（把 `--no-session` 那行换成 `--session-dir`）。
2. `zima/models/config_bundle.py`
   - `build_command(self, prompt_file: Path, runtime_args: Optional[dict] = None) -> list[str]`：
     透传 `extra_args=runtime_args` 给 `AgentConfig.build_command`。
3. `zima/execution/executor.py`
   - 构造命令处改为
     `command = bundle.build_command(prompt_file, runtime_args={"sessionDir": str(temp_dir / "pi-sessions")})`。
   - 对 claude/kimi 无害：两个 builder 按 key 取值，未知参数被忽略。

## 7. 采集与落盘链路

采集点必须在 temp 目录被删之前：`PJobExecutor.execute()` 的 `finally` 块内，**postExec actions 与 FailureGuard 之后、`shutil.rmtree(temp_dir)`（`executor.py:842-846`）之前**。

改动点清单（缺一处数据就丢失）：

| # | 文件 | 改动 |
|---|------|------|
| 1 | `zima/execution/usage_collector.py`（新增） | 解析/合并/采集/格式化 |
| 2 | `zima/execution/executor.py` | `ExecutionResult.usage: Optional[dict] = None`；`to_dict()` 条件输出；finally 内调用采集 |
| 3 | `zima/execution/history.py` | `ExecutionRecord.usage` + `to_dict`/`from_dict`/`from_result`（**不加则在读路径被静默丢弃**，见下方说明）；`_STATE_FILE_FIELDS` 同步登记（legacy `add()` 走该白名单） |
| 4 | `zima/execution/background_runner.py` | 终态 `update_runtime_state(...)` 增加 `usage=result.usage` |
| 5 | `zima/commands/pjob.py` | `history --detail` 打印 usage 行 |

**两处容易被误判的细节**：

- **`_STATE_FILE_FIELDS` 不是写路径的门禁**。`update_runtime_state(**fields)` 会把任意字段 merge 进 JSON（`history.py:330-352`），所以 `usage` 一定能写进文件；丢失发生在**读路径**——`get_record()` / `get_history()` 返回的是 `ExecutionRecord.from_dict(state)`，`from_dict` 只复制已知字段。因此 `ExecutionRecord` 加字段是硬要求，`_STATE_FILE_FIELDS` 登记是为了让 legacy `add()` 写入路径同样带上该字段（`history.py:585`）。
- **为什么第 4 处必须改**：终态记录不是由 executor 自己写的，而是后台执行进程 `background_runner.run_pjob_in_background()` 用显式字段列表写的（`background_runner.py:120`）。daemon 路径自己只写"启动失败/被 kill"两种终态，正常终态同样经过 background_runner，因此只需改这一处。

`claude` / `kimi` 类型：`executor` 判断 `bundle.agent.type != "pi"` 时不调用采集，直接写
`{"collected": false, "reason": "unsupported_agent_type"}`。

## 8. 失败与降级（fail-open 硬约束）

1. 采集整体包在 `try/except Exception` 中；任何异常只产生 `collected: false` + `parse_error`，**不抛给调用方**。
2. 采集结果**不得**影响：`result.status`、`result.returncode`、`result.error_detail`、`result.action_errors`。
3. 采集失败不打印 warning 到 stdout/stderr（避免污染 CR 输出契约）；如需诊断，写入 `reason` 字段即可。
4. 采集不得阻止 temp 目录清理——`rmtree` 仍在同一个 `finally` 中无条件执行（`keep_temp` 时除外）。

## 9. 可测性拆分设计（实现阶段硬约束）

| 单元 | 签名 | 职责 | 依赖 |
|------|------|------|------|
| `parse_parent_usage` | `(session_files: Sequence[Path]) -> dict` | 读顶层会话文件 → `{"totals": …, "by_model": […]}`；跳过非 assistant / 无 usage / 非法 JSON 行 | 文件系统（读） |
| `parse_child_usage` | `(artifacts_dir: Path) -> dict` | 读 `*_meta.json` → 同上；缺 usage 的 meta 跳过 | 文件系统（读） |
| `merge_usage` | `(parent: dict, children: dict) -> dict` | 合并 totals/by_role/by_model + `children_count` + `cost_note` | 无（纯计算） |
| `collect_usage` | `(session_dir: Optional[Path]) -> dict` | IO 薄层：glob → 调上面三个 → 产出最终 `usage` dict；fail-open | 文件系统 |
| `format_usage_line` | `(usage: Optional[dict]) -> str` | usage dict → 展示行（含 unknown 三态） | 无（纯计算） |

**测试边界**：

- `parse_*` 与 `merge_usage`/`format_usage_line` 为纯函数级测试，fixture 用临时目录写小样本 jsonl/json，不依赖 pi、不联网。
- `collect_usage` 的 fail-open 通过参数注入异常路径覆盖（不存在的目录、非法 JSON、空目录）。
- 命令构造继续走 `AgentConfig.build_command` 纯函数测试，断言 `--session-dir <path>` 出现、`--no-session` 不再出现。
- 端到端只验一次：用 `mockCommand` 起假 agent，脚本在 cwd（即 temp 目录）下自建 `pi-sessions/*.jsonl` 与 `pi-sessions/subagent-artifacts/*_meta.json`，断言 history JSON 的 `usage` 正确、temp 目录仍被清理。

## 10. 验收矩阵

### 自动化验证

| ID | 功能点 | 层级 | 验证命令 / 方式 | 通过标准 |
|----|--------|------|----------------|----------|
| A1 | pi 命令含 `--session-dir`、不含 `--no-session` | unit | `uv run pytest tests/unit/test_models_agent.py -k pi` | 两个断言均通过 |
| A2 | pi 默认参数不再含 `noSession`；YAML 残留 `noSession` 不报错 | unit | 同上 | 默认参数断言 + 带残留参数构造成功 |
| A3 | 父用量解析与按 model 分桶 | unit | `uv run pytest tests/unit/test_usage_collector.py -k parent` | totals 与 by_model 数值精确匹配 fixture |
| A4 | 子代理用量解析 | unit | `... -k child` | 每个 meta 一条记录，agent/model 正确 |
| A5 | 排除规则：`forks/**` 与 `*_transcript.jsonl` 不计入 | unit | `... -k exclusion` | 构造含副本的 fixture，结果不重复计数 |
| A6 | 合并逻辑：totals/by_role/children_count/cost_note | unit | `... -k merge` | 父+子相加正确，`cost_note == "estimated"` |
| A7 | fail-open：目录缺失 / 空目录 / 非法 JSON | unit | `... -k failopen` | 返回 `collected=false` + 对应 reason，不抛异常 |
| A8 | `usage` 字段可写入并经 `get_record()` 读回 | unit | `uv run pytest tests/unit/test_execution_history.py -k usage` | 写入后读回同值；legacy `add()` 路径同样保留该字段 |
| A9 | 老记录（无 usage）读回不报错 | unit | 同上 `-k legacy` | 记录可读，usage 为 None |
| A10 | 展示行三态（正常 / unknown+reason / 占比） | unit | `... -k format` | 输出字符串匹配预期（含 unknown 分支） |
| A11 | 非 pi agent 不采集且不报错 | unit | `... -k unsupported` | `reason == "unsupported_agent_type"` |
| A12 | 端到端：假 agent 产出 session 文件 → history 有 usage | integration | `uv run pytest tests/integration/ -k usage` | history JSON 的 usage 数值正确、status 仍为 success |
| A13 | 采集不阻止 temp 清理 | integration | 同 A12，断言 temp 目录不存在 | 目录已删 |
| A14 | 全量回归 + lint | static/build | `uv run pytest tests/ -m "not slow"`、`uv run ruff check zima/ tests/`、`uv run black --check zima/ tests/ --line-length 100` | 全绿，覆盖率不低于 60% |

### 用户实测

| ID | 功能点 | 步骤 | 观察结果 | 通过标准 |
|----|--------|------|----------|----------|
| U1 | 真实 CR 执行采集 | 部署后对一个真实 PR 触发 `zima-pi-cr-job`，跑完后 `zima pjob history zima-pi-cr-job --detail <id>` | 出现 Usage 行 | 数值非 0；`by_model` 同时有 parent 与 child 记录；子代理占比符合预期（远高于父） |
| U2 | 无全局会话污染 | 同上执行后检查 `~/.pi/agent/sessions/` 与 `~/.pi/agent/agent-board/sessions/` | 目录内容 | 未因该次 CR 新增文件 |
| U3 | 分档可读（服务 #212） | 对同一 PR 的 fast/strong 调用，查看 `by_model` 明细 | 明细含多档模型 | 能分别读出 fast 档与 strong 档的 tokens，支撑 #212 决策 |
| U4 | 老记录与失败态表达 | 打开一条 2026-09-10 之前的历史详情；再造一次采集失败路径 | Usage 行内容 | 显示 `unknown (…)` 而非 `0` |

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `--no-session` → `--session-dir` 悄悄改变所有 pi PJob 行为 | 所有 pi 执行多写一份会话文件到 temp | 实测确认不碰全局会话目录；文件随 temp 删除；本 spec 显式记录该行为变更，需在 CHANGELOG 标注 |
| zima 被 SIGKILL / 清理失败导致会话文件残留 | 磁盘占用、transcript 残留 | 复用既有 `zima cleanup`（temp 目录清理同源）；与 `prompt.md` 同级残留，非新增风险类别 |
| 明细聚合 double counting | 账本数字偏高，误导 #212 决策 | A5 专项测试锁定排除规则；U1 与真实执行对账 |
| cost 被误读为现金 | 决策依据错误 | `cost_note: "estimated"` 硬编码进数据；展示行标 `est.` |
| pi 未来改 `--session-dir` / artifact 布局 | 采集失效 | fail-open：退化为 `collected: false`，不影响执行；reason 字段可诊断 |
| 采集字段膨胀 history 文件体积 | history 读取变慢 | `by_model` 聚合后写入；单次执行最多几十条明细 |

## 12. 待批准后的下一步

1. 在本仓 worktree `issue-213-usage-ledger` 内落 spec（首个 commit）、写 plan、实现、本地 CR、开 PR。
2. 试点顺序建议：本仓 `zima-pi-cr-agent`（已有环境）→ 一轮真实 CR 对账（U1）→ 再评估是否扩到其他 repo 的 CR PJob。

## 附：证据索引

- 探针目录：`/tmp/pi-session-probe/`（父会话 usage、子代理 meta、目录布局）
- pi 源码：`dist/bundle/chunks/chunk-JVUZSMYM.js`（`createSessionManager` 中 `parsed.noSession` 优先于 sessionDir）
- pi 文档：`docs/json.md`、`docs/session-format.md`、`docs/sessions.md`、`docs/environment-variables.md`
- pi-subagents 源码：`src/shared/artifacts.ts`、`src/shared/types.ts`
- 调研笔记：`research/round1-data-sources.md`、`research/round2-zima-change-surface.md`
