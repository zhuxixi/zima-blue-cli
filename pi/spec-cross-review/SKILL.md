---
name: spec-cross-review
description: |
  对 github-issue-driven 步 4 产出的 spec / 根因报告草稿做交叉复核：草稿落盘后自动进入，
  preflight 校验复核者模型与起草者异构（fail-closed），派发 fresh-context 的
  spec-reviewer subagent 逐轮复核，起草者逐条修订，全自动循环至收敛（无真缺口）或轮次上限。

  Use when: 步 4 草稿完成自动进入；或显式触发做 state 重建 / 中断恢复 / 显式降级复核。

  触发词: "spec-cross-review", "复核 spec", "spec 交叉复核"
---

# Spec Cross Review

步 4 的内嵌复核环节：复核者是 fresh-context 的 `spec-reviewer` subagent，父 session（起草者）
逐轮编排并统一写留痕。循环全自动跑到收敛，人只在收敛后的 ⏸ 出现。本 skill 只审设计文档，
不碰代码 CR（步 8/9 原样）。

## 触发与前置

- **步 4 自动进入**：spec / 根因报告草稿落盘（含 `Drafted:` 行）后，直接进入下方 preflight →
  每轮编排，不等用户说触发词。
- 显式触发词（`spec-cross-review` / 中文自然语言）保留为边界情况入口：state 重建、
  中断恢复、显式降级复核。自然语言触发且会话没有 issue 上下文时：要求用户给出 issue 编号。
- 前置：草稿头部含起草记录行，格式固定为
  `Drafted: <provider>/<model> (selected) · <provider>/<model> (physical) @ <ISO8601>`；
  每次修订追加同格式的 `Revised:` 行。缺该行：询问用户起草模型；答「未知」则停在
  preflight 前，不得自动降级。
- 留痕目录：`~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/`；轮次文件与 state 放其
  `research/` 下。

## Preflight 门禁（循环开始前，一次）

1. 读草稿头 `Drafted:` / 最近一条 `Revised:` → 起草模型（selected + physical）。
2. 调 `subagent({action:"models", agent:"spec-reviewer"})` → 评审者 effective model / source /
   override file / current session model。
3. **fail-closed**：评审者 effective model 与起草记录的 selected / physical 任一相等 →
   不进循环，输出部署指引（见「部署前置」），等用户处理后重新触发。不自动降级。
   评审者 effective model 为 `(unresolved)` / 空，或起草记录缺失 → 视同无法证明异构，
   同样 fail-closed。
4. 异构 → 输出一行 preflight 结论（起草模型 / 评审模型 / 异构确认 / 轮次上限 4 /
   每轮 1 个 fresh-context child），进入循环。
5. 事后审计：每轮报告头记录 child run 的 `model`（来自 run 产物）与主会话该轮 physical
   （`PI_SESSION_FILE` JSONL 最后一条 assistant message 的 `model`）。撞真身则 `Mode` 记
   `cross-model (post-hoc same-physical)`，该轮按降级轮对待。`PI_SESSION_FILE` 在 ephemeral
   session 下可能未设置；读不到时报告头 physical 记 `(unavailable, ephemeral session)`，
   本轮跳过撞真身判定并在报告头注明。

## 每轮编排（父逐轮，至收敛或上限）

1. 父算被审版本 `sha256sum <spec 绝对路径>`，按 `references/dispatch-contract.md` 渲染任务
   （注入变量 + 从 `references/checklist.md` 读盘注入五视角清单全文），派发
   `spec-reviewer`（cwd 为目标仓库），等待 native 完成通知，不轮询。
2. child 核对 hash 一致 → 从磁盘重读 spec + 真实代码 + 仓约定 → 五视角全过 →
   返回结构化报告（dispatch-contract.md 的 outputSchema）。
3. 父裁定：真缺口 = 0 → 收敛轮；> 0 → 父逐条处置（接受并改 / 部分接受并说明边界 /
   拒绝并给证据），改 spec、写修订摘要，开第 k+1 轮。
4. 每轮结束输出一行进度，不停下：

   [spec-cross-review] 第 <k> 轮完成：复核者 <effective-model> (fresh)，真缺口 <N>、细化 <M>，报告 <绝对路径>。

5. 收敛后输出并进入 ⏸：

   [spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。

## 写入归属（父是唯一写者）

- child 的 tools 不含 write/edit，报告以结构化输出返回。
- 父写轮次报告第 1–4 段 + 末尾附 child 结构化输出 verbatim JSON、追加第 5 段修订摘要、
  更新 state 索引、发 issue 评论。任何人可对账正文与 verbatim JSON。
- state 是轮次 k 的唯一权威来源；缺失/矛盾时按轮次文件重建并回写（含「已拒绝裁定」清单，见边界情况）。
- 报告落盘失败：停循环、报错、不重派。

## 发现分级

- 三档：`真缺口`（阻塞，必须修订）/ `细化`（应修订）/ `核对通过`。
- 编号：`R<轮次>-G<n>` / `R<轮次>-D<n>` / `R<轮次>-P<n>`。
- 每条发现：级别、定位、为什么是问题、建议修订、若不复核会在实现阶段付出什么代价。
- 给不出定位的降级为「待证」，不计入真缺口。
- 五个复核视角（每轮全过，清单全文由父从 `references/checklist.md` 读盘注入）：
  ① 验收矩阵完备性 ② 可测性拆分可实现性 + 触发时序 ③ 部署/执行路径真实性
  ④ 契约与边界 ⑤ 命令与命名可追溯。

## 收敛与轮次上限

- 判定时点：每轮复核回收后。真缺口 = 0 → 收敛轮（细化项改完即进 ⏸）；> 0 → 修订后开下一轮。
- 默认上限 4 轮；用户可在当轮明确提高（记录在 state 与 issue 评论）。
- 到达上限仍有真缺口：停止循环，如实交用户决定（继续 / 降级接受 / 改设计），
  不允许自动继续或假装收敛。
- 修订处置：父对每条发现三选一——接受并改 / 部分接受并说明边界 / 拒绝并给证据；
  全部写入当轮修订摘要。真缺口不得静默跳过；用户明确说跳过时记录「用户决定跳过」及理由。
- **拒绝的生命周期**：被「拒绝并给证据」的发现不进 state 的 Open findings（已裁定闭环），
  记入 state 索引的「已拒绝裁定」清单，并每轮随 `<PREV_OPEN_FINDINGS>` 注入（编号 +
  一句话证据 + 轮次）；child 只有在握有拒绝证据未覆盖的新证据时才可重报，且重报必须写明新证据。
- **防空转终止**：若本轮全部新真缺口都是对已裁定拒绝项的无新证据重报，停止循环并如实
  交用户决定（这是起草者与复核者的真实分歧，循环无法收敛）——与到达上限同等处置。

## 降级（同模型）

- 默认无降级路径：preflight fail-closed 保证循环只在异构配置下启动。
- 用户显式要求同模型复核：停在派发前，输出定稿提示并等待：

  [spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。
  请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。

  仅在用户明确回复「降级复核」后继续；报告头写 `Mode: degraded (same-model, user-confirmed)`，
  并强制加码对照三类材料（真实代码与测试核到行 / 仓约定文档 / 验收矩阵与可测性拆分）。
  降级形态下复核改为**同会话**执行（不派发）——隔离与只读均退回纪律，报告头如实标注。

## 失败处理

| 失败 | 处置 |
|---|---|
| `spec-reviewer` 未注册 / 无法解析 | preflight 报错，给出部署指引，不进循环 |
| `modelScope` 拒绝（preflight 或运行期） | 停循环，输出报错形态与当前 allow 实况，交用户处置 |
| 派发失败 / 超时 / 结构化输出缺失或不合 schema | 停循环 + 留痕（原因写 state 与 issue 评论）+ 报错；不静默重派 |
| hash 不匹配（child 复核不一致 / 父回收时与派发时不一致） | 停下要求对齐，不审来历不明的版本 |
| 报告落盘失败 | 停循环、报错、不重派（防重复扣费） |

## 留痕纪律

```
~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/
├── spec.md
└── research/
    ├── spec-cross-review-state.md
    ├── spec-review-round-1.md
    └── spec-review-round-2.md
```

- 轮次报告五段与模板见 `references/report-template.md`。报告头：
  `Round k` / `Reviewer: spec-reviewer (<effective-model>) (selected) · <run-model> (physical from run artifact) (fresh context)` /
  `Drafter:` / `Reviewed spec sha256:` / `Mode:` / 时间戳。
  `Mode:` 取值：`cross-model (preflight verified)` / `cross-model (post-hoc same-physical)` /
  `degraded (same-model, user-confirmed)`。
- sha256 口径：`sha256sum <spec 绝对路径>`（字节流原样）；哈希只记在轮次文件与 state，
  不写回被计算的文件自身。
- issue 评论：每轮一条（复核者模型、轮次、真缺口/细化计数、报告路径），收敛时追加汇总。

## 保证边界

1. preflight 证明的是「解析时异构」，不是「运行中不切换」——运行中模型固定依赖
   pi-subagents ≥0.68 已移除运行中模型切换（fallbackModels 删除），此结论依赖版本行为。
2. child 无 write/edit 是机制保证；**但 child 仍有 bash**（可执行任意命令），「只读」部分
   仍靠纪律。缓解：父侧 sha256 对账能发现 child 改过 spec（hash 不一致即停）。
3. 父是唯一起草者与唯一写者，存在「弱化不利发现」的动机风险——缓解：报告末尾附
   verbatim JSON，正文与原文可对账。
4. run 产物的模型字段是证据链，其保留期与清理策略未核实。
5. 全自动循环无人值守：成本在 preflight 行一次性告知 + 每轮进度行；不设中途停点是与
   用户明确确认的选择。
6. 契约测试只锁文档契约；语义质量与真实可用性由 U1/U2 试点兜底。

## 部署前置

1. 在 `subagent({action:"models", agent:"spec-reviewer"})` 返回的 **Override file** 路径
   （用户级 settings.json）的 `subagents` 块中设置
   `"agentOverrides": {"spec-reviewer": {"model": "<provider>/<model>"}}`——选一个与常用
   起草模型异构、且在 `subagents.modelScope.allow` 内的模型。
2. 可选加固：`subagents.modelScope.agents.spec-reviewer.allow` 钉同一模型，防派发时误传
   或被显式降级。
3. 核实生效：再次 `subagent({action:"models", agent:"spec-reviewer"})`，确认 Effective
   model 与起草模型不同。
4. 「未注册 / 无法解析」排查：profile 随包经 `package.json` 的 `pi.subagents.agents` 注册
   （`./pi/agents`）。未注册通常是 pi-subagents 版本过旧（需 ≥0.76）或包安装过期——
   重新安装 / 升级包后重试 `{action:"models"}`。

## 边界情况

见 `references/edge-cases.md`。
