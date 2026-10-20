# #264 根因报告 / 设计：wait-cr.py 跨机拓扑下的等待语义

Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-20T23:58:05+08:00
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-21T00:22:00+08:00（round 1 细化项 R1-D1~D4 处置）

Issue: https://github.com/zhuxixi/zima-blue-cli/issues/264
调研证据：`research/01-root-cause-and-solution-space.md`
关联：#189（引入前台阻塞等待的原始设计）、#181（调度器多流去重，非本 issue 范围）

## 1. 根因

**`wait-cr.py` 只有一条观测通道（本机 `$ZIMA_HOME/history/pjobs/...`），却把「观测不到」编码成「触发失败」这一结论**——跨机拓扑下这条通道恒为空集，于是必然误报。

三条叠加事实（定位见调研 §2）：

1. **通道单一**：`wait-cr.py:280-281` 只把 `state_dir` 指向本地目录；全文没有 `gh`、没有 HTTP、没有远端查询路径。
2. **语义折叠**：`load_states`（`wait-cr.py:95-96`）对「目录不存在」与「目录存在但为空」返回同一个空 dict；`run_loop` 的「无活跃执行」分支（`wait-cr.py:236-240`）在过宽限期后统一 exit 2，无法区分「本机没有运行时」与「跑了但没 spawn」。
3. **文案反向**：模块 docstring（`wait-cr.py:14`）把 exit 2 定义为「trigger likely failed」；`SKILL.md:29` 还要求先 `zima pjob ps` 确认 spawn——这两件事在触发机上都不成立。

因此本 issue 不是「脚本有 bug」，而是「脚本的前提（服务与本机同机）在跨机拓扑下不成立，而脚本没有表达这个前提」。修法要给出一个**不依赖本地运行时**的观测通道，并把缺运行时变成即时、可解释的失败。

## 2. 设计决策

### D1 新增 GitHub 原生等待模式 `--pr owner/repo#N`（取代本地通道用于跨机拓扑）

收敛信号 = **目标 head 上存在一条带 `pi-cr-meta` / `cc-cr-meta` 的 review，且其 `submittedAt >= 等待开始时刻 - --since-minutes`**。

- 选 review 而不是标签变化：`SKILL.md:66` 已明确「label 消失 ≠ 审完」；review 是 CR PJob postExec 的终点产物，语义唯一。
- 实测数据形状支持这个判据（调研 §5）：`reviews[].commit.oid` 等于该 review 针对的 head，`reviews[].body` 以 `<!-- pi-cr-meta` 开头。round 1 指向旧 head、round 2 指向新 head，可直接与 `headRefOid` 比对。
- `kimi-cr-meta` 不匹配（已废弃，`SKILL.md:22`）。

### D2 判定用 `submittedAt` 时间窗，不用「review id 基线」

不采用「等待开始时记下已有 review id、只认新 id」：如果 CR 在会话开始等待前就已完成（打标签后先做了别的事），基线法会把刚发出的 review 当成旧结果而白等到超时。
时间窗（默认 10 分钟）同时解决「同一 head 的上一轮旧 review 被误当成本轮」——`--since-minutes` 语义与本地模式的 cutoff 一致，不新增参数。

时钟偏差风险由两点吸收：① head SHA 匹配是主判据（同一 head 上的 review 只可能由该 head 的审查产生）；② 默认 10 分钟窗口远大于常规 NTP 偏差。

### D3 head 变更 → exit 4（不静默重定目标）

等待期间 head 变了，说明这一轮审查的对象已被替换，等到旧 head 的 review 没有意义。**选择快速失败而不是自动改为盯新 head**：自动重定目标会掩盖「有人并发 push / 另一条流在推」的事实，且可能让等待无限延长（每次 push 都重置）。exit 4 把决定权交回会话（重新打标签触发新一轮）。

### D4 PR 已非 OPEN → exit 5

`state` 已在同一次 `gh pr view` 调用里返回，零额外成本；不判会让已合并/已关闭的 PR 空等满 2100s。

### D5 本地模式加 preflight：无 `history/pjobs` 目录 → exit 3（立即，不睡宽限期）

`(zima_home / "history" / "pjobs").is_dir()` 为假 = 本机没有任何 zima 运行态可读。此时继续等宽限期没有任何信息增益，只会把误导加深。
仍然保留 exit 2：`history/pjobs` 存在但该 PJob 目录为空/无新执行 → **「本机运行时未见该 PJob 的执行」**。注意这句话**不断言**「这轮没 spawn」：在双运行态拓扑（本机有 zima 运行态、但该 PR 的 CR 由另一台机触发）下，exit 2 的真实含义仍是「观测不到」（见 §8.7）。

### D6 gh 调用失败分两种处置

- **启动期**（还没有拿到 target head）：重试 3 次仍失败 → exit 6，附带 gh stderr。避免仓库名写错/未登录时空等 35 分钟。
- **循环中**（已有 target head）：打印告警并按 `--poll` 继续，由总超时兜底。网络抖动不该让已经触发的 CR 白等。

### D7 用法错误统一 exit 64，避免与运行时 exit 2 混淆

`argparse` 默认的用法错误退出码是 2，和本脚本「本地模式没等到执行」的 2 撞车。自定义 `ArgumentParser.error()` → exit 64。

### D8 不改本地模式的行为（除 preflight 外），不改 `run_loop` 签名

`tests/unit/test_wait_cr.py`（328 行）已锁定本地模式的 sticky / stale / grace / timeout 语义；`CLAUDE.md:9` 也把 `history/pjobs` 布局钉成契约。本次只新增旁路模式 + 前置检查，`run_loop` 一字不动。

### 决策表

| 决策点 | 选择 | 依据 |
|---|---|---|
| 远程观测信号 | 目标 head 上的 meta review | review 是终点产物；标签不可靠（SKILL.md:57） |
| 新鲜度判据 | `submittedAt >= start - --since-minutes` | 兼容「等待开始前已完成」；排除同 head 上轮旧 review（D2） |
| 是否用 id 基线 | 否 | 会造成「已完成 → 白等超时」（D2） |
| head 变更 | exit 4，不重定目标 | 避免掩盖并发 push / 无界延长（D3） |
| PR 非 OPEN | exit 5 | state 免费可得（D4） |
| 本地无运行时 | exit 3，立即返回 | 等待无信息增益（D5） |
| gh 启动失败 | 重试 3 次 → exit 6；循环内仅告警 | 区分配置错误与网络抖动（D6） |
| 用法错误 | exit 64（含 argparse 自身） | 避免与 2 混淆（D7） |
| 本地模式 | 只加 preflight，其余不动 | 回归契约（D8） |
| 远端状态 API（issue 建议 2） | 不做 | 现状不存在，需改 webhook-server + 鉴权，跨出 skill 包范围 |
| 收敛判定（blocking counts） | 不做，仍归 SKILL / 会话 | helper 只回答「本轮报告到了没」，不代替决策树 |

### 新接口

```
wait-cr.py <pjob_code>            [--since-minutes N] [--timeout S] [--poll S] [--grace S] [--zima-home PATH]
wait-cr.py --pr owner/repo#N      [--since-minutes N] [--timeout S] [--poll S]
```

- 两种模式**必须恰好给一个**（都缺或都给 → 64）。
- 远程模式给 `--grace` / `--zima-home` → 64（对远程模式无意义，静默忽略会误导）。
- `--since-minutes` 两模式都有效：本地 = 活跃执行切点（现状），远程 = review 新鲜度窗口（新）。

## 3. 组件契约与可测性拆分

新增/改动全部在 `pi/zima-pr-monitor/scripts/wait-cr.py`（stdlib-only，不新增依赖）。

### 3.1 纯函数（无 IO，直接单测）

| 函数 | 签名 | 语义 |
|---|---|---|
| `parse_pr_ref` | `(text: str) -> tuple[str, str, int]` | `owner/repo#123` → `(owner, repo, 123)`；空 owner/repo、非数字、缺 `#` 一律 `ValueError` |
| `meta_marker` | `(body: str) -> str \| None` | 命中 `<!--\s*(pi\|cc)-cr-meta` 返回 `"pi"` / `"cc"`，否则 `None`（`kimi-cr-meta` 不命中） |
| `parse_meta_json` | `(body: str) -> dict \| None` | 尽力解析 meta JSON 供摘要行打印；任何失败返回 `None`，**不影响判定** |
| `select_meta_review` | `(reviews: list[dict], head_sha: str, not_before: datetime) -> dict \| None` | 过滤 `commit.oid == head_sha` + 有 meta + `submittedAt >= not_before`，返回 `submittedAt` 最新的一条 |
| `format_review_summary` | `(review: dict) -> str` | 一行摘要：id / head 前 12 位 / submittedAt / author / meta 种类 / round / blocking counts（缺失记 `-`） |

### 3.2 IO 边界（可注入，测试不碰网络）

| 函数 | 签名 | 语义 |
|---|---|---|
| `has_local_runtime` | `(zima_home: Path) -> bool` | `history/pjobs` 是否为目录（D5） |
| `fetch_pr_state` | `(pr: PrRef, runner=_gh_runner) -> dict` | 拼 `gh pr view <n> --repo <o>/<r> --json reviews,headRefOid,state`，`runner(argv) -> str`，解析失败抛 `GhQueryError` |
| `_gh_runner` | `(argv: list[str]) -> str` | 唯一 `subprocess.run` 调用点（`text=True`, `capture_output=True`, `timeout=120`），非零退出抛 `GhQueryError(stderr)` |

### 3.3 控制循环（注入时钟与 fetcher）

```python
def run_pr_loop(pr, *, timeout, poll, since_minutes,
                fetch, sleep=time.sleep, monotonic=time.monotonic, out=sys.stdout) -> int
```

返回 0 / 1 / 4 / 5；`fetch()` 抛 `GhQueryError` 时告警后继续（D6）。
**单次循环顺序固定**：`fetch → PR state 非 OPEN?5 → head 变更?4 → 命中 review?0 → 到点?1 → 进度行 + sleep`。
这个顺序本身是契约：head 变更优先于 review 命中，否则并发 push 后旧 head 的 review 会被当成收敛。

### 3.4 本地模式

`main()` 里在 `run_loop` 之前插入 `has_local_runtime` 检查（exit 3）。`run_loop` 及其全部辅助函数不改。

### 3.5 测试边界（plan 必须保留）

- 纯函数（3.1）单独测，不构造文件、不 mock 子进程。
- 控制循环（3.3）用假 `fetch` + 假 `sleep` / `monotonic` 驱动，**不 sleep 真时间、不调 gh**（与既有 `TestRunLoop` 同风格）。
- gh argv 契约与启动重试用注入 `runner` 断言 argv 列表与重试次数。
- 本地 preflight 用 `tmp_path` 造/不造 `history/pjobs`，并断言 exit 3 时 `sleep` 未被调用。
- 新增函数不得把 `gh` / `urllib` 引入模块导入期；`main()` 是唯一的 argparse 与真实 IO 编排点。

## 4. 退出码契约

| 码 | 模式 | 含义 |
|---|---|---|
| 0 | 两者 | 收敛：本地=活跃执行全部终态；远程=目标 head 上出现 meta review |
| 1 | 两者 | 超时 |
| 2 | 本地 | 宽限期内没有执行出现（保持现状语义） |
| 3 | 本地 | 本机无 zima 运行态（`history/pjobs` 不存在）→ 改用 `--pr` |
| 4 | 远程 | 等待期间目标 head 变更 |
| 5 | 远程 | PR 已非 OPEN（merged/closed） |
| 6 | 远程 | 启动期 gh 查询失败（重试 3 次后） |
| 64 | 两者 | 用法错误（模式缺失/冲突、参数非法，含 argparse 自身错误） |

exit 3 的 stderr 必须包含可直接粘贴的远程模式用法，例如：
`wait-cr: no local zima runtime (missing <path>/history/pjobs); use --pr owner/repo#N to wait on GitHub reviews`。

## 5. 文档改动

1. **`pi/zima-pr-monitor/SKILL.md` §等待节律（24-43 行）**：改为「先按有无本地运行时选模式」——
   - 选择规则（通用表述，**不写主机名**）：`$ZIMA_HOME/history/pjobs` 存在 → 本地模式（现有命令）；不存在 → `--pr` 模式。依据：JFox「机器特异的约束写进常驻 AGENTS.md，不绑定通用技能」。
   - 该规则是**启发式**，不是判据：已知本次 CR 由其他机器/其他会话触发时，即使本机有运行态也直接用 `--pr`（双运行态拓扑见 §8.7）。
   - 远程模式命令：`python3 pi/zima-pr-monitor/scripts/wait-cr.py --pr 'owner/repo#N' --since-minutes 10`。
   - 两模式共同纪律保留：同 turn 前台阻塞、禁止后台监听、禁止结束 turn（`SKILL.md:26`）。
   - 时长预期表（首轮 ~1200s / 增量 ~800s / 上限 2100s）对两模式都适用，不重复写。
   - 退出码表（§4）落进 SKILL，重点是 3/4/5/6 的处置。
2. **`SKILL.md` §多执行流陷阱（68-77 行）**：`zima pjob ps` 标注为**本地模式专属**；远程模式下 in-flight 只能靠「最近触发时间 <15min」推断，并明确这条不构成确定性检查。
3. **`SKILL.md` §合并（85-87 行）**：in-flight 检查按模式分叉（本地 `zima pjob ps`；远程看触发时钟）。
   **必须保留的钉住片段**（既有契约测试会扫这几段，改写时不得丢）：`test_issue_driven_contracts.py::TestMergeGate::assert_merge_scoped_to_auto_tiers` 钉住 `\`auto\` / \`design-only\``、`` `gh pr merge <N> --squash --delete-branch` ``、`` `stepwise` 档行为不变——收敛 + CI 全绿即合并 ``；`test_cr_batch_contracts.py::TestBlockingPolicyDocumentation` 钉住 `blocking_new_count`。改动只在同段内**增补**，不改这些句子。
4. **`wait-cr.py` 模块 docstring**：补两种模式的 usage 与 §4 退出码表。
5. **`CLAUDE.md:9`**：把「block-waits read-only on 本地 state 文件」补成「本地模式读 state 文件；远程模式轮询 PR reviews」，避免后续读者以为脚本只有一条通道。

## 6. 非目标

- 不改 `zima` CLI / daemon / webhook-server，不做远端状态 API（issue 建议 2）。
- 不在 helper 里做收敛判定（blocking / advisory / 多流），仍由 SKILL 会话按 metadata 判。
- 不改本地模式的退出码 0/1/2 与 `run_loop` 语义。
- 不修 `run_loop` 的 `sleep(poll)` 越过 grace/deadline 的既有债务（调研 §1 附带发现）——独立问题，混进来会让本地模式回归面变大。
- 不改 `pi/github-issue-driven/SKILL.md`（其步 9 只说「用 helper 前台阻塞等待」，不写死模式）。
- 不做推送通知、不做自动重打标签。

## 7. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | `parse_pr_ref` / `meta_marker` / `parse_meta_json` 纯函数 | 自动化（unit） | `uv run pytest tests/unit/test_wait_cr.py::TestParsePrRef tests/unit/test_wait_cr.py::TestMetaMarker tests/unit/test_wait_cr.py::TestParseMetaJson -q` | 合法/非法 ref、pi/cc/kimi 三种 meta 体、坏 JSON 均按 spec 返回 |
| A2 | `select_meta_review` 判定 | 自动化（unit） | 同上文件 `::TestSelectMetaReview` | head 不匹配/时间窗之外/无 meta 三种都不返回；多条命中取最新 |
| A3 | 远程循环：收敛（首轮即命中、后续轮命中） | 自动化（unit） | `::TestRunPrLoop` | 返回 0，stdout 含 review id 与 head 前 12 位 |
| A4 | 远程循环：超时 | 自动化（unit） | `::TestRunPrLoop` | 返回 1，stderr 含 `timeout`，**不含** `trigger failed` |
| A5 | 远程循环：head 变更 / PR 非 OPEN / 循环内 gh 失败 | 自动化（unit） | `::TestRunPrLoop` | 分别返回 4 / 5；gh 失败后告警并继续直至命中 |
| A6 | 启动期 gh 失败重试 | 自动化（unit） | `::TestMainRemote` | 连续 3 次失败 → 返回 6，stderr 含 gh 错误 |
| A7 | gh argv 契约 | 自动化（unit） | `::TestFetchPrState` | 注入 runner 捕获 `["pr","view","<n>","--repo","o/r","--json","reviews,headRefOid,state"]` |
| A8 | 本地 preflight exit 3 | 自动化（unit） | `::TestMainLocal` | 无 `history/pjobs` 时返回 3、stderr 含 `--pr`，且 `sleep` 未被调用 |
| A9 | 用法错误 exit 64 | 自动化（unit） | `::TestUsage` | 模式缺失/冲突/远程带 `--grace`/远程带 `--zima-home`/`--pr 'owner/repo'`（缺 `#`）/`--timeout abc` 全部返回 64 |
| A10 | 本地模式行为不变 | 自动化（unit） | `uv run pytest tests/unit/test_wait_cr.py -q` | 既有全部用例通过（含 sticky/stale/grace 回归） |
| A11 | 文档契约（§5.1-§5.5 全覆盖） | 自动化（unit） | `::TestSkillDocContract` + `uv run pytest tests/unit/test_issue_driven_contracts.py tests/unit/test_cr_batch_contracts.py -q` | SKILL.md：两模式命令行、exit 3 改道提示、`--pr` 的 head 判据、禁止后台监听（§5.1）；`zima pjob ps` 带「本地模式」限定（§5.2）；合并节同时含模式分叉与上列钉住片段（§5.3）；docstring 含两模式 usage（§5.4）；CLAUDE.md 含双通道句（§5.5）；既有契约测试全绿 |
| A13 | `format_review_summary` 摘要行 | 自动化（unit） | `::TestFormatReviewSummary` | 含 review id / head 前 12 位 / submittedAt / author / meta 种类 / round；blocking counts 缺失时记 `-` 且不抛错 |
| A12 | 全仓回归 + 静态检查 | 自动化（static） | `uv run pytest tests/ -m "not slow"` / `uv run ruff check zima/ tests/ scripts/` / `uv run black --check zima/ tests/ scripts/ --line-length 100` | 全部通过（命令出处：`.github/workflows/integration-test.yml:62,65,109`） |
| U1 | 真实远端 CR 的 `--pr` 等待 | 用户实测 | 本 issue 的 PR 打 `zima:needs-review` 后，在**触发机**用 worktree 内的脚本执行 `python3 <worktree>/pi/zima-pr-monitor/scripts/wait-cr.py --pr 'zhuxixi/zima-blue-cli#<PR>' --since-minutes 10` | 进程在前台阻塞至 review 出现后 exit 0，打印 review id / head / round；全程不出现 `trigger failed` |
| U2 | 真实环境下的超时分支 | 用户实测 | 同上 PR，在 CR 结果出现**前**执行 `--pr ... --timeout 20 --poll 5` | exit 1，stderr 只含超时说明；不含 `trigger failed`；不误报为「未触发」 |
| U3 | 真实已合并 PR 的 exit 5 | 用户实测 | `python3 <worktree>/pi/zima-pr-monitor/scripts/wait-cr.py --pr 'zhuxixi/zima-blue-cli#260'`（已 MERGED） | 立即 exit 5，stderr 说明 PR 非 OPEN |

- **可测性拆分**（A1-A11 对应 §3.1-§3.5）：每个功能点都落到独立纯函数或注入式循环；测试不 sleep 真时间、不访问网络、不依赖本机 zima。
- **用户实测时机**：U2 必须在 U1 的 review 落地前执行（同一 PR）；U1 在 review 落地后自然返回；U3 随时可跑（PR 260 已合并）。三者都在 worktree 内执行脚本绝对路径，**不依赖重新安装 pi 包**（部署路径说明见 §8）。

## 8. 保证边界与风险

1. **只回答「报告到了没」，不回答「卡在哪」**：远程模式无法区分「没触发 / 排队中 / agent 执行中 / 失败未发 review」。超时后仍需人去服务端查（本 issue 不解决该可见性缺口）。
2. **多流不判**：同一 head 出现多条 meta review 时，helper 在第一条出现时即返回 0；多流判定仍由 `SKILL.md` §多执行流陷阱 负责。helper 只给事实（id/head/round），不给结论。
3. **轮询粒度 30s**：收敛检测最多滞后一个 `--poll`。
4. **已完成但超窗会白等**：CR 在等待开始前已结束且距今超过 `--since-minutes` 时，helper 会当作旧轮次并等到超时（退出码 1）。处置写在 SKILL：调大 `--since-minutes` 或直接读 review。
5. **时钟**：依赖本地时钟与 GitHub 时间的差距小于 `--since-minutes`（默认 600s）；head SHA 是主判据，偏差只影响「同 head 上轮旧 review」的区分。
6. **不做鉴权/来源判定**：任何账号在目标 head 发的 meta review 都算命中——helper 是观测工具，不是合并门禁；合并门禁的 bot 身份校验仍归 auto-merge / 会话侧。
7. **双运行态拓扑选错模式**：本机有 zima 运行态（`history/pjobs` 存在）但该 PR 的 CR 由另一台机触发时，§5.1 的启发式会选本地模式，exit 2 仍是「观测不到」。这是 #264 误诊链的浅层复发，SKILL 必须同时写出「已知触发在别处 → 直接用 `--pr`」这条覆盖规则（§5.1 已含），不能把启发式当确定性判据教给会话。
8. **部署路径**：pi 包从主 checkout 加载，worktree 里的脚本/文档在合并前不会被新会话加载。U1-U3 因此显式用 worktree 绝对路径执行脚本；文档改动需合并 + 主 checkout `git pull` 后对新会话生效（这正是本 issue 的 dogfood 约束，写在这里防止验收跑到旧代码上）。

## 9. 实现约束（plan 必守）

- §3.1 的函数必须无 IO；§3.3 的循环必须靠注入驱动；不得为了少写参数把 `fetch` / `sleep` / `monotonic` 写死。
- 脚本保持 stdlib-only（`argparse` / `json` / `os` / `re` / `subprocess` / `sys` / `time` / `datetime` / `pathlib` / `typing`）。
- 不修改 `run_loop` 及既有辅助函数的行为与签名（A10 锁定）。
- 新增代码风格与既有脚本一致：`from __future__ import annotations`、Google 风格 docstring、函数级 docstring 说明「为什么」。
- 文档改动保持通用（不写主机名/内网地址），符合「机器特异约束不进通用技能」。
