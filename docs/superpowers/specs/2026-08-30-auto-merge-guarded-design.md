# auto-merge-guarded 设计：CR 收敛后的自动 approve + merge（zima daemon 扩展）

- 日期：2026-08-30
- 状态：设计定稿，待实施计划
- 范围：本机 zima daemon 生态（`~/.zima/`），不改 zima-blue-cli 源码、不改任何 GitHub 仓库内容、不新增 GitHub 侧配置

## 背景与问题

zhuxixi/pi-agent-board 的协作者（ccccyk0919，可信同事，工作流与 owner 一致）没有本机 Zima CR，由他 AI 打 `zima:needs-review` 标签触发 owner 机器上的 CR PJob。现有链路已自动化到「CR 收敛、postExec 摘标签」，之后的环节全部人工：

1. owner 判断可以合并
2. `gh pr review N --approve`（owner-approval.yml 要求 APPROVED review 绑定最新 head）
3. `rerun-failed-jobs` 清理 approve 前的旧失败 run（PR 列表图标聚合 commit 上全部 check run，旧失败不清则红叉）
4. `gh pr merge N --squash --delete-branch`

PR #50（issue #48，2026-08-30 合并）完整走了一遍该人工 runbook。本设计把这段 runbook 固化为一个幂等的守护脚本，由 daemon 定时轮询执行。

## 目标 / 非目标

**目标**

- 白名单作者的 PR 在「CI 必过检查全绿 + Zima CR 多流安全收敛」后，全自动 approve + squash merge + Pushover 通知
- 零上游改动：不动 zima-blue-cli 源码、不依赖 GitHub 仓库内 workflow、不新增 secret
- 全程可审计（JSONL 决策日志）、可演练（dry-run / notify-only）、可急停（配置开关）

**非目标**

- 不自动触发 CR（打标签由协作者侧工作流负责，现状已自动化）
- 不替代分支保护（必过检查仍由 GitHub branch protection 强制）
- 不做多仓库批量管理的 UI/CLI（Phase 2 按仓库逐个加配置即可）

## 现有链路（本设计的上游）

```
协作者 AI 打 zima:needs-review
  → GitHub webhook 事件 → 本机 webhook-server（HMAC 验签）
  → 触发 pi-agent-board-pi-cr-job（preExec scan_pr → CR agent → postExec 摘/换标签）
  → [断点] 人工 approve + merge ← 本设计补这段
```

已知上游坑（本设计必须防御，不修复）：

- 同一 head 可能多条 CR 执行流并行（webhook 流 / 手动 pjob 流 / daemon 轮询流），只看最新一条 review 判收敛会被迟到流打爆（jfox #402 教训）
- postExec success 分支只摘 `zima:needs-review`，不摘 `zima:needs-fix`，标签残留需手动清理

## 架构与组件

| 组件 | 位置 | 说明 |
|------|------|------|
| 守护脚本 | `~/.zima/scripts/auto-merge-guarded.py` | 单文件 Python（stdlib + `gh` CLI 子进程），幂等，无第三方依赖 |
| 规则配置 | `~/.zima/configs/auto-merge.yaml` | 白名单、必过检查、敏感路径、通知、开关 |
| 调度 | daemon schedules 条目 | 每 45 分钟触发一次（与 daemon 既有轮询节奏一致） |
| 审计日志 | `~/.zima/logs/auto-merge.log` | JSONL：ts / repo / pr / head_sha / decision / reason |

配置结构（示意）：

```yaml
enabled: true
schedule_interval_minutes: 45
pushover:
  config_file: "~/.config/claude-notify.json"   # 现有共享配置：PUSHOVER_API_KEY / PUSHOVER_USER_KEY
repos:
  zhuxixi/pi-agent-board:
    allow_authors: [ccccyk0919]
    required_checks: ["Test (Node 22)", "Test (Node 24)"]
    expected_failing_checks: ["Owner approval policy"]   # approve 前的预期失败，不算阻塞
    merge_method: squash
    delete_branch: true
    sensitive_paths: [".github/**", "*.pjob.*", "**/branch-protection*"]
```

## 检查链（六道闸门，顺序执行，全过才进动作链）

1. **候选过滤**：PR open、非 draft、作者 ∈ 白名单。不满足则整轮跳过（不通知）。
2. **敏感路径守卫**：`gh pr view --json files` 改动文件命中 sensitive_paths 任一 → 不合并，推 `attention` 通知（理由：workflow/CI 配置能改写审查与门禁判定本身，是被审者的规则改写权，必须人工过目）。
3. **必过检查全绿**：`GET /commits/{head}/check-runs`，required_checks 里每个检查名最近一次 run 为 success。`expected_failing_checks` 中的失败视为预期态（approve 前的 owner-approval policy）。
4. **无冲突**：`mergeable == "MERGEABLE"`。冲突 → `attention` 通知后跳过。
5. **CR 多流安全收敛**，三条件缺一不可：
   a. 读 `~/.zima/history/pjobs/<code>/`，当前 (repo, pr_number, head_sha) 的**所有** CR 执行都已终止（无 running）；
   b. 最新一条 pi-cr-meta review 的 verdict 干净（无未解决 blocking 发现）；
   c. `zima:needs-review` 标签已被 postExec 摘除。
   未收敛 → 静默跳过（waiting 态不通知，防 45 分钟一轮的轰炸）。
6. **head 防漂移**：动作链内 approve 执行前再取一次 `pr.headRefOid`，与第 5 道验证时的 head 一致才继续；漂移 → 中止本轮（新 head 自然回到未收敛态）。

## 动作链（五步，每步前查现状，天然幂等可重试）

```
0. 入口检查：PR 已 MERGED → 跳过整轮；reviewDecision 已 APPROVED(当前 head) → 跳过第 2 步
1. 摘 zima:needs-fix 残留标签（若有；摘标签不触发新 CR 流，webhook 只监听 needs-review）
2. gh pr review N --approve --body "auto-merge: CR converged + CI green"
3. rerun-failed-jobs：仅重跑 head 上 Owner approval policy 的失败 run，轮询至完成（上限 5 分钟）
4. 校验 mergeStateStatus == CLEAN
5. gh pr merge N --squash --delete-branch → 推 action 通知（repo/PR/标题/作者/squash sha）
```

任何一步失败：中止本轮、推 error 通知（含原因）、记日志；下一轮（45 分钟后）从 GitHub 真实状态重新评估，无需专门重试逻辑。

## 通知（复用现有 Pushover 管线）

复用机器上既有 Pushover 约定（pi 扩展 `pushover-notify.ts` 与 Kimi 插件 `pushover-notify.sh` 同源）：同一配置文件读 `PUSHOVER_API_KEY` / `PUSHOVER_USER_KEY`，POST `https://api.pushover.net/1/messages.json`，Python stdlib（urllib）实现，不依赖 curl。

| 级别 | 触发 | Pushover 映射 |
|------|------|---------------|
| action | 执行了合并 | 普通优先级，标题 `[auto-merge] merged` |
| attention | 敏感路径拦截 / 合并冲突 | priority=1，标题 `[auto-merge] needs your eyes` |
| error | gh 认证失效 / API 异常 / 步骤失败 | priority=1，标题 `[auto-merge] error` |
| waiting | 未收敛 / 检查未绿 / 非白名单 | 不推送，仅记日志 |

文案规则：正文按**字符**截断（禁止按字节截断——UTF-8 中文按字节截会乱码，已有踩坑记录），上限 250 字符。pushover 配置缺失或发送失败 → 降级为纯日志，不阻塞合并动作。

## 并发与边界

- **flock 全局锁**（`/tmp/auto-merge-guarded.lock`）：防 daemon 45 分钟轮询流、webhook 流与本脚本调度并发重入。
- **approve 后、merge 前协作者 push**：head 漂移 → approve 失效、policy 变红 → 下轮收敛判定对新 head 不成立 → PR 回到等待新 CR 状态（协作者 agent 修完会重打标签）。检查链天然兜住，无需特殊处理。
- **gh 认证过期**：推 error 一次；重新 `gh auth` 后自愈。
- **API 限流 / 瞬时失败**：本轮中止，下轮重试。

## 安全护栏

- 白名单是授权边界：approve 以 owner 账号发出，仅限配置内 (repo, author) 对。
- 敏感路径硬闸：命中即永不自动合并，只通知人工。
- 两级演练模式：`--dry-run`（走完整检查链，打印将执行的动作，不执行）；`--notify-only`（走检查链 + 动作链预演，只发通知不动 GitHub）——可直接在协作者下一个真 PR 上彩排。
- 急停：配置 `enabled: false` 或删除 schedule 条目。
- 凭证面：只用本机已有 gh 登录态与现有 pushover key，不新增任何 secret。

## 测试与上线

分三阶段：

- **Phase 0（约一周）**：`notify-only` 模式上线。每轮把「本会怎么合」推给 owner，owner 对照自己的判断校准；通知链路同时被验证。
- **Phase 1**：对 `ccccyk0919@zhuxixi/pi-agent-board` 启用真合并。
- **Phase 2**：扩展到其他仓库（voice-input 等）；评估把逻辑 upstream 为 zima-blue-cli 原生 `auto_merge` postExec 动作（事件驱动、零轮询延迟），届时本脚本退役为过渡方案。

测试方式：闸门函数纯函数化（输入 fixture JSON，输出 decision），单测覆盖每个闸门的通过与拒绝分支；两轮真实 PR 彩排（Phase 0）作为集成验证。

## 被否决的替代方案

- **B：zima-blue-cli 新增原生 `auto_merge` postExec 动作**——事件驱动零延迟，但需改 ActionsRunner + 测试 + 发版升级本机；postExec 每次执行结束都触发，多流并发下需额外幂等。留作 Phase 2 后的演进方向。
- **C：CR agent 收敛时自行执行合并**——审查者兼执行者，审计性差，提示词驱动的副作用脆弱，否决。
