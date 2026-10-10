# Spec — Issue #254：spec-cross-review 自动化——派发复核者 + 全自动循环（路线 A）

- 状态：**v1 草稿，待交叉复核**
- Drafted: kimi-coding/k3 (selected) · kimi-coding/k3 (physical) @ 2026-10-10T00:04:43Z
- 日期：2026-10-10 · 仓库基线：`main`（`1a5e1e1`）
- 上游 issue：zhuxixi/zima-blue-cli#254（enhancement）
- 调研存档：`~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-254/research/`（round1 痛点实证 / round2 路线 A 机制 / round3 路线 B 机制）
- 命名合规：`spec` / `agent` / `reviewer` / `dispatch` / `contract` 均在 ≤5500 词汇内

---

## 1. 背景与问题

`spec-cross-review`（#250 / PR #251，CHANGELOG 的 Unreleased 条目）在试点中证明了价值，但驱动方式是人工的：每开一轮用户要做四次操作（切到复核模型 → 说触发词 → 切回起草模型 → 说触发词），「复核者与起草者异构」这个硬前提由人的手保证，skill 自己在「保证边界」里承认无法证明复核者真的换了模型。

实证（调研 round1，jfox #547，唯一一次生产使用）：2026-09-30 完成第 1 轮复核（复核者 `zai-coding-cn/glm-5.3`，起草者 `deepseek/deepseek-flash`，抓出真缺口 R1-G1——按 spec 字面实现会引入现行代码没有的 `IndexError`）→ 2026-10-01 完成第 1 轮修订 → **之后再无任何动作，issue 至今 OPEN，第 2 轮复核未开，已停 8 天**（调研时点 2026-10-09）。停摆的直接原因是交接动作需要人：人不在循环里，循环就停了。

同一现场还暴露留痕缺口：评论中声称的 `research/spec-review-round-1.md` 与 `spec-cross-review-state.md` 在本机不存在，全盘 `find` 搜 `spec-review-round-*.md` / `spec-cross-review-state.md` 零命中。skill 最看重的四件套留痕只活下来 issue 评论一份（可能是工作目录被人工清理过，也可能是流程未真正落盘——本条不下断言，列为待验证项）。

本 issue 解决：**让「异模型复核」从人工纪律变成机制约束，让循环全自动跑到收敛**，同时保留 #250 的全部质量契约（只读复核、发现必须给定位、不得同轮既审又改、⏸ 人工闸门）。

## 2. 目标

1. **模型身份由 run 契约承载**：复核者作为 fresh-context subagent 由 `subagent` 工具派发，模型由部署侧配置钉死；异构门禁在循环开始前一次性 preflight，fail-closed。
2. **零人工交接**：复核 → 修订 → 复审的循环由父 session 逐轮编排，全自动跑到收敛（真缺口 = 0）或 4 轮上限，用户只在收敛后的 ⏸ 出现。
3. **只读由机制保证**：复核 child 的 tools 白名单不含 `write` / `edit`，「禁止修改任何文件」从纪律变成物理事实。
4. **留痕由机制保证**：父是唯一写者，轮次报告、state 索引、issue 评论的写入由父在循环内完成，不再依赖复核者自觉。

## 3. 非目标

- **不改质量契约本体**：五个复核视角、三档发现分级、4 轮上限、收敛判据（真缺口 = 0）、⏸ 人工闸门——全部保留 #250 定稿语义。
- **不做多顾问形态**：不用 council-mode 当引擎（无修订环节、无版本对账、收敛判据是主观裁定；本机无 `council-*` profile 时 fallback `oracle` 是 fork 上下文，与 D6 冲突）；不做五视角 fan-out（成本乘五且收敛判据需重定义）。
- **不走 zima 外置**：路线 B（pjob 起全新 session）留作后续阶段，本次不建等待通道、提示词模板、取证链路。
- **不自动化起草与修订**：起草者仍是主 session（修订需要设计意图上下文）；本 issue 只把「复核者」搬出主 session。
- **不引入运行时依赖**：改动仍是 skill 文档 + 包内 agent profile + 静态契约测试；机器可校验部分在 `tests/unit/`。

## 4. 关键事实依据（调研对齐）

| 事实 | 来源 |
|---|---|
| run 产物记录每个 step 的解析模型：`status.json` 的 step result 含 `model` / `thinking` / `requestedModel`，并有 child 的 `sessionFile`（JSONL）与 `transcriptPath` | pi-subagents `0.76.1` 本机实测（`/tmp/pi-subagents-uid-1000/async-subagent-runs/5707b392-…/status.json`）；`docs/observability.md` |
| 模型解析优先级：per-run override → provider-scoped role override → `agentOverrides.<name>.model` → frontmatter `model` → `subagents.defaultModel` → 父 session | pi-subagents `docs/models.md` |
| `modelScope` 是政策层白名单（只拒绝不选型）；`enforce + strict` 下继承链越界也 fail-closed；agent 级 `modelScope.agents.<name>.allow` 只能收紧不能放宽 | pi-subagents `docs/models.md`；KB《Pi subagent 模型解析优先级与 modelScope 硬限制》 |
| 本机白名单已含 `zai-coding-cn/glm-5.3`（非 flash），spec-reviewer 钉它无需改白名单；省钱靠 `defaultModel: zai-coding-cn/glm-5.3-flash` + 各 agent pin，不靠白名单隔离 | 实测 `~/.pi/agent/settings.json`（2026-10-10） |
| 一个 child 越界会让整个 workflow run 失败；已完成 child 的产物保留 | KB（2026-09-14 实测） |
| 内置 `reviewer` 工具白名单只读，派复核任务被任务分类器拒（"tool allowlist has no mutation-capable tools"）；绕行是 `worker` / `delegate` + READ-ONLY 声明 | KB《pi standalone binary 下派 subagent 的三个已知限制》 |
| 内置 `oracle` 的 `defaultContext: fork` + `inheritProjectContext: true`，人设是「保护继承来的决策」——与 fresh-context 异构复核者角色相反 | pi-subagents `agents/oracle.md` |
| 已安装的 Pi 包可通过 `{"pi-subagents":{"agents":["./agents"]}}` 或 `{"pi":{"subagents":{"agents":["./agents"]}}}` 暴露 agent 目录；优先级 builtin 之上、user/project 之下 | pi-subagents `docs/agents.md:32` |
| `subagent({action:"models", agent:"<name>"})` 返回 Effective model / Source / Thinking / Override file / **Current session model**——异构门禁一次调用可比两值 | 本 issue 会话实测（2026-10-10） |
| workflowScript 沙箱无 `process.env`；环境变量只能由父经 bash 读取后以字面量填进派发项 | KB（2026-09-08 实测） |
| 派发 vs 单会话的成本差由三块构成：parent 编排开销（最大头）、fresh context 重读、子 session 冷启动；每轮 1 个 child 时编排占比远小于 5-child fanout | KB《多 agent fanout 派发不省 token：A/B 实测 4.7 倍差距的构成》 |
| `subagent` 工具支持 `outputSchema` 结构化输出 | pi-subagents tool schema |
| pi-subagents `0.68.0` 起移除 fallbackModels 与同次启动内模型切换——resolved model 在运行中固定 | KB（2026-09-20 增量） |

## 5. 与 issue 原文的设计修订（用户已定）

issue 原文列了「sub-agent 派发 / zima 外置 agent」两条路线待选。brainstorming 阶段用户拍板三点，本 spec 据此设计：

1. **范围 = 只自动化复核者**（起草与修订留在主 session）。
2. **自动化程度 = 全自动到收敛**（中途无停点；每轮输出一行进度可见性，不停下）。
3. **模型来源 = 新建专用 `spec-reviewer` profile + preflight fail-closed**（不复用内置 oracle——其人设与 fresh-context 复核者相反）。

## 6. 设计

### D1 · 触发与前置

- 步 4 流程内**自动进入**：spec / 根因报告草稿落盘（含 `Drafted:` 行）后，父 session 直接进入本 skill 的 preflight → 循环，不再等用户说触发词。
- 显式触发词（`spec-cross-review` / 「复核 spec」）保留，作为边界情况入口：state 重建、外部恢复中断的循环、用户显式降级复核。
- 前置不变：草稿已落盘；草稿头部含 `Drafted: <provider>/<model> (selected) · <provider>/<model> (physical) @ <ISO8601>`；每次修订追加 `Revised:` 行。缺 `Drafted:` 行：询问用户起草模型；答「未知」则停在 preflight 前（门禁无法执行，不得自动降级）。
- 留痕目录不变：`~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/`；轮次文件与 state 放其 `research/` 下。

### D2 · `spec-reviewer` agent profile 契约（新增 `pi/agents/spec-reviewer.md`）

```yaml
name: spec-reviewer
description: Adversarial cross-reviewer for step-4 spec drafts (fresh context, read-only)
tools: read, grep, find, ls, bash   # 无 write/edit——只读由机制保证
defaultContext: fresh               # 不继承主会话历史（oracle 的 fork 正是要避开的）
inheritProjectContext: true         # 仓约定（AGENTS.md/CLAUDE.md）注入；不违反「禁会话记忆」（那是项目文件不是对话）
inheritSkills: false                # 防 child 自己加载 spec-cross-review 造成回环
systemPromptMode: replace
thinking: high
# model 故意不写——由部署侧 subagents.agentOverrides.spec-reviewer.model 提供（见 D14）
```

system prompt 内嵌**稳定契约**：只读（且 tools 不含 write/edit）、五个复核视角（与现 `references/checklist.md` 一致）、发现三档分级（真缺口 / 细化 / 核对通过）、每条发现必须给 `文件:行号` 或 spec 原句定位（给不出定位降级为「待证」，不计入真缺口）、报告五段结构、`Reviewed spec sha256` 回填义务。

### D3 · 包注册（package.json）

`package.json` 的 `pi` 块新增：`"subagents": {"agents": ["./pi/agents"]}`。依据 pi-subagents `docs/agents.md:32`（包级 agent 目录，优先级 builtin 之上、user/project 之下）。

**待核实项（S1，必须进 plan 首个 task）**：字段名生效性——注册后 `subagent({action:"models", agent:"spec-reviewer"})` 能解析到包内 profile；若不生效，备选 `{"pi-subagents":{"agents":["./pi/agents"]}}` 形式。spike 产出写进 round 报告。

### D4 · Preflight 门禁（循环开始前，一次）

1. 父读草稿头 `Drafted:` 行 → 起草模型（selected + physical）；
2. 父调 `subagent({action:"models", agent:"spec-reviewer"})` → 评审者 effective model + source + override file；
3. 比对：评审者 effective model 与起草记录的 selected / physical **任一相等** → **fail-closed**：不进循环，输出部署指引（在 `~/.pi/agent/settings.json` 的 `subagents.agentOverrides.spec-reviewer.model` 换异构模型，并给出当前 override file 路径），等用户处理后重新触发。
4. 异构 → 输出一行 preflight 结论（起草模型 / 评审模型 / 异构确认 / 轮次上限 4 / 每轮 1 个 fresh-context child），进入循环。
5. **每轮报告头仍记录实际值**（child run 的 `model` 字段来自 run 产物；主会话该轮的 physical 来自 `PI_SESSION_FILE` JSONL 最后一条 assistant message 的 `model`）。若事后撞真身（virtual router 场景）：`Mode` 记 `cross-model (post-hoc same-physical)`，该轮按降级轮对待（细化照常处置，不得宣称本轮独立）——沿用 #250 D2 语义。

### D5 · 每轮编排（父逐轮，循环至收敛或上限）

1. 父算本次被审版本 `sha256sum <spec 绝对路径>`，组任务（D6 的变量注入），派发 `spec-reviewer`；等待 native 完成通知，不轮询。
2. child 复核前用 bash 核对 `sha256sum` 与注入值一致（不一致则停止并报告，防「审的版本与改的版本错位」）→ 从磁盘重读 spec + 真实代码 + 仓约定 → 五视角全过 → 返回结构化报告（D6 的 outputSchema）。
3. 父按结构化结果**裁定收敛**：真缺口 = 0 → 收敛轮；> 0 → 父逐条处置（接受并改 / 部分接受并说明边界 / 拒绝并给证据），改 spec、写修订摘要，进入第 k+1 轮。
4. 每轮结束**输出一行进度，不停下**（字面量见 D9）。

### D6 · 派发契约（新增 `references/dispatch-contract.md`）

- **任务模板** = 稳定契约（profile system prompt + 本文件描述的任务骨架）+ **父每轮注入的变量**：issue 号、spec 绝对路径、轮次 k、被审版本 sha256、上一轮 open findings（编号 + 一句话）、state 路径、报告回执要求。
- **outputSchema**（结构化回报，父据此写报告与裁定）：`round`、`reviewedSha256`、`lenses[]`（五视角各：结论 + 发现编号）、`findings[]`（`id`（`R<k>-G<n>` / `R<k>-D<n>` / `R<k>-P<n>`）、`level`、`location`、`why`、`suggestion`、`costIfSkipped`）、`counts`（`gaps` / `details` / `passes`）、`convergence`（`converged: boolean`）、`mode`。
- 这份模板与 profile system prompt 是**单一定义源**：profile 里的稳定契约必须与本文档逐字一致（契约测试锁定），避免两份真相漂移。

### D7 · 写入归属：父是唯一写者

- child 的 tools 不含 `write` / `edit`，报告以 `outputSchema` 结构化返回。
- **父**把报告写入 `research/spec-review-round-<k>.md`（第 1–4 段，标注 `Reviewer: spec-reviewer (<effective model>, fresh context)`）、追加第 5 段修订摘要、更新 `research/spec-cross-review-state.md`、发 issue 评论。
- **防父弱化不利发现**：报告文件末尾以代码块原样附上 child 的结构化输出（verbatim JSON），发现表的正文由父从该 JSON 生成——任何人可对账正文与原始输出是否一致。
- state 仍是轮次 k 的唯一权威来源；缺失/矛盾时按 `spec-review-round-*.md` 重建并回写（沿用 #250 D3），由父执行。
- 写入失败的处置：报告落盘失败 → 停循环、报错、不重派（防重复扣费）。

### D8 · 收敛与轮次上限

- 判定时点：每轮复核回收后。真缺口 = 0 → 收敛轮（细化项由父改完即进 ⏸，不再开新一轮）；> 0 → 修订后开下一轮。
- 上限 4 轮；用户可在当轮明确提高（记录在 state 与 issue 评论）。
- 到达上限仍有真缺口：停止循环，如实交用户决定（继续 / 降级接受 / 改设计），**不允许自动继续或假装收敛**。

### D9 · 进度行（替换 D12 交接提示，新字面量）

每轮结束输出（**进度可见性，不是停点**）：

```
[spec-cross-review] 第 <k> 轮完成：复核者 <effective-model> (fresh)，真缺口 <N>、细化 <M>，报告 <绝对路径>。
[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。
```

第二行沿用 #250 D12 收敛字面量原样；第一行替换原「下一步：切到 `<provider>/<model>`…」——**`tests/unit/test_spec_cross_review_contracts.py` 的 A1 字面量断言必须同步更新**（见 D13）。

### D10 · 降级（同模型）

- 默认无降级路径：preflight fail-closed 保证循环只在异构配置下启动。
- 用户显式要求同模型复核时：停在派发前，输出定稿提示（沿用 #250 D4 字面量），仅在用户明确回复「降级复核」后继续；报告头写 `Mode: degraded (same-model, user-confirmed)`，并强制加码对照三类材料（真实代码与测试核到行 / 仓约定文档 / 验收矩阵与可测性拆分）——沿用 #250 D5。

### D11 · 失败处理

| 失败 | 处置 |
|---|---|
| `spec-reviewer` 未注册 / 无法解析 | preflight 报错，给出 D3 注册指引，不进循环 |
| `modelScope` 拒绝（preflight 已挡大部分；运行期仍发生） | 停循环，输出 KB 记录的报错形态与当前 allow 实况，交用户处置 |
| 派发失败 / 超时 / child 返回不合 schema | 停循环 + 留痕（失败原因写 state 与 issue 评论）+ 报错；**不静默重派**（防重复扣费），由用户决定重试 |
| 轮次间 spec 被外部改动（child 复核 hash 不一致 / 父回收时 hash 与派发时不一致） | 停下要求对齐，不审来历不明的版本（沿用 #250 硬规则） |

### D12 · 留痕布局与报告头字段

目录与五段结构沿用 #250 D11（`research/spec-cross-review-state.md` + `spec-review-round-<k>.md`）。报告头字段更新：

- `Reviewer: spec-reviewer (<effective-model>) (selected) · <run-model> (physical from run artifact) (fresh context)`
- `Mode:` 取值改为 `cross-model (preflight verified)` / `cross-model (post-hoc same-physical)` / `degraded (same-model, user-confirmed)`
- `Reviewed spec sha256:` 由 child 回填 + 父校验
- 报告文件末尾附 child 结构化输出 verbatim JSON（见 D7）

### D13 · 与既有契约的同步点（必须一起改）

1. `tests/unit/test_spec_cross_review_contracts.py`：
   - **字面量断言更新**：原 A1 对「下一步：切到 `<provider>/<model>`…」交接提示的断言，改为对 D9 第一行进度行字面量的断言（归 A5）；收敛字面量断言保留（归 A5）。
   - **A3 banned literal 守卫范围扩大**：新增检查 `pi/agents/spec-reviewer.md` 与 `pi/spec-cross-review/references/dispatch-contract.md` 不含 `BANNED_LITERALS`；profile 不得含 `model` 字段。
   - 新增断言：profile frontmatter 契约（归 A1）、`package.json` 注册字段（归 A2）、`dispatch-contract.md` outputSchema 字段（归 A4）。
2. `pi/github-issue-driven/SKILL.md` 步 4：交接说明从「用户切模型后手动触发」改为「草稿落盘后自动进入交叉复核循环，收敛后才 ⏸」；保留 `Drafted:` 强制记录要求；A2 断言的两个标记串保留（`REQUIRED SUB-SKILL: Use spec-cross-review` / `收敛后才 ⏸ 暂停等待用户确认设计`）。
3. `pi/README.md` 技能表：`spec-cross-review` 行描述更新（自动循环 + 派发复核者）；补 agent profile 说明。
4. `CHANGELOG.md` 记录。

### D14 · 部署前置条件

1. `subagents.agentOverrides.spec-reviewer.model` 设为**与常用起草模型异构**的模型（本机现状：`zai-coding-cn/glm-5.3` 已在白名单，起草常用 `deepseek/deepseek-flash` / `kimi-coding/k3`——异构天然成立）。
2. 可选加固：`subagents.modelScope.agents.spec-reviewer.allow` 钉同一模型，防派发时误传或被显式降级。
3. 省钱攻略兼容性：白名单无需新增条目；省钱由 `defaultModel: zai-coding-cn/glm-5.3-flash` + 各 agent pin 承载，不依赖白名单隔离。已知边界：agent 级白名单只能收紧不能放宽，全局放行的高级模型对所有 agent 可解析——此口子今日已存在，非本设计新增。

## 7. 可测性拆分设计（自动化类功能点的实现硬约束）

改动是**文档 + 包内 agent profile**，可自动化验证的对象是契约而非行为。拆分沿用 #250 §7 的三层：

| 层 | 单元 | 责任 |
|---|---|---|
| 读取 | `_read(path) -> str`（纯函数） | 读 profile / SKILL.md / references / package.json / github-issue-driven |
| 断言 A | `assert_contains(doc, contracts)` | 契约串存在性（frontmatter 字段、进度行字面量、outputSchema 字段名、注册字段） |
| 断言 B | `assert_no_hardcoded_model(doc)` | `BANNED_LITERALS` 字面量黑名单（扩到新文件）；profile 不得含 `model` 字段 |
| 断言 C | `assert_order(doc, before, after)` | 顺序约束（步 4 中复核在 ⏸ 之前） |

测试边界（如实声明）：

- 只能证明「该写的写了、不该写的没写、顺序对」，证明不了「派发契约在真实会话里会被正确执行」「报告质量」「收敛判定正确」。
- 语义质量与真实可用性由 S1 spike 与 U1 试点兜底；A 系列不得冒充 U1。
- 测试只读文件，不执行派发，不联网，不依赖 pytest 以外的新依赖。

## 8. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| S1 | 包级 agent 目录注册生效（待核实项） | spike（自动化查询） | 注册后 `subagent({action:"models", agent:"spec-reviewer"})` | 能解析到包内 profile 且返回 effective model；字段名不生效时换 `pi-subagents.agents` 备选形式并记录结论 |
| A1 | spec-reviewer profile 结构契约 | 自动化（static/unit） | `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k "ProfileContract"` | `pi/agents/spec-reviewer.md` 存在；frontmatter 含 D2 全部字段且值匹配；**无 `model` 字段**；tools 不含 `write`/`edit` |
| A2 | 包注册字段 | 自动化（static/unit） | 同上 `-k "PackageRegistration"` | `package.json` 的 `pi.subagents.agents` 含 `./pi/agents` |
| A3 | 禁硬编码模型 | 自动化（static/unit） | 同上 `-k "Hardcoded"` | 新增 profile 与 `dispatch-contract.md` 及修订的 skill 文档不含 `BANNED_LITERALS`；不使用形态正则；不引用机器私有配置 |
| A4 | 派发契约字段齐全 | 自动化（static/unit） | 同上 `-k "DispatchContract"` | `references/dispatch-contract.md` 含 outputSchema 必需字段（`round`/`reviewedSha256`/`lenses`/`findings`/`counts`/`convergence`/`mode`；findings 的 `id`/`level`/`location`/`why`/`suggestion`/`costIfSkipped`）与任务模板的变量占位 |
| A5 | SKILL.md 编排契约 | 自动化（static/unit） | 同上 `-k "SkillStructure or PinnedLiterals"` | 含 preflight 契约（models API + fail-closed）、每轮编排步骤、D9 两条进度行字面量（原样）、D10 降级提示字面量（沿用 #250 D4，原样）、收敛判据、部署前置指引 |
| A6 | 报告模板字段 | 自动化（static/unit） | 同上 `-k "ReportTemplate"` | `report-template.md` 含 `Reviewer: spec-reviewer`、新 Mode 取值、`Reviewed spec sha256`、verbatim JSON 附段 |
| A7 | 边界情况文档 | 自动化（static/unit） | 同上 `-k "EdgeCase"` | `edge-cases.md` 含 D11 全部失败分支 |
| A8 | github-issue-driven 步 4 同步 | 自动化（static/unit） | 同上 `-k "FlowStep4"` | 两个标记串保留且顺序正确（复核在 ⏸ 之前）；含「自动进入」描述与 `Drafted:` 强制记录 |
| A9 | README 登记 | 自动化（static/unit） | 同上 `-k "ReadmeTable"` | `pi/README.md` 技能表 `spec-cross-review` 行描述更新 + agent profile 说明 |
| A10 | 仓内既有测试不回归 | 自动化（build） | `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60` | 全绿，覆盖率达标 |
| U1 | 真实流程可用 | 用户实测 | 拿一个真实 issue 走完整步 4：起草 → 自动进入复核 → 全自动多轮 → 收敛 → ⏸ 用户确认。**可执行时机：PR 合并回 main 之后、从主 checkout 发起的会话中执行（worktree 内不执行）** | 轮次报告 / 修订摘要 / state / verbatim JSON / issue 评论齐全；报告头记录的评审模型确实 ≠ 起草模型；**至少拦下 1 个真缺口**；全程零手动切模型；回收每轮 token/时长数据写进 state |
| U2 | 部署前置生效 | 用户实测 | 在未配置 `agentOverrides.spec-reviewer.model` 的环境触发步 4 | preflight fail-closed，输出的部署指引可直接照做（不静默降级、不进循环） |

## 9. 保证边界（必须写进 skill）

1. preflight 证明的是「**解析时**异构」，不是「运行中不切换」——依据 0.68.0 已移除运行中模型切换（fallbackModels 删除），resolved model 在 run 内固定；但此结论依赖版本行为，写进保证边界。
2. child 无 `write`/`edit` 是机制保证；**但 child 仍有 `bash`**——bash 可执行任意命令，「只读」在 bash 存在时部分仍靠纪律。缓解：父侧 sha256 对账能发现 child 改过 spec（hash 不一致即停）。
3. 父是唯一起草者与唯一写者，存在「父弱化不利发现」的动机风险——缓解：报告末尾附 child 结构化输出 verbatim JSON，正文与原文可对账（D7）。
4. run 产物（status.json）的模型字段是证据链，但其**保留期与清理策略未核实**——本轮证据依赖 async run 目录在场，列为待验证项。
5. 全自动循环无人值守运行，成本在启动前一次性告知（preflight 行）+ 每轮进度行；不设中途停点是用户明确选择。
6. 契约测试只锁文档契约（§7 边界）。

## 10. 交付物清单

| # | 文件 | 动作 |
|---|---|---|
| 1 | `pi/agents/spec-reviewer.md` | 新增（agent profile，无 model 字段） |
| 2 | `package.json` | 修订（`pi.subagents.agents: ["./pi/agents"]`） |
| 3 | `pi/spec-cross-review/SKILL.md` | 重写（D1/D4/D5/D7–D12；六分支分流表退役） |
| 4 | `pi/spec-cross-review/references/dispatch-contract.md` | 新增（任务模板 + outputSchema） |
| 5 | `pi/spec-cross-review/references/checklist.md` | 修订（五视角稳定契约与 profile system prompt 对齐，单一定义源） |
| 6 | `pi/spec-cross-review/references/report-template.md` | 修订（报告头新字段 + verbatim JSON 附段） |
| 7 | `pi/spec-cross-review/references/edge-cases.md` | 重写（D11 失败分支 + 沿用边界情况） |
| 8 | `pi/github-issue-driven/SKILL.md` | 修订步 4（自动进入描述 + 保留 Drafted 强制 + 标记串） |
| 9 | `pi/README.md` | 修订（技能表描述 + profile 说明） |
| 10 | `tests/unit/test_spec_cross_review_contracts.py` | 修订（A1/A3 更新 + A1/A2/A4–A9 新增断言） |
| 11 | `docs/superpowers/specs/2026-10-10-spec-cross-review-automation-design.md` | 本 spec 进 worktree 后的落位（首个 commit） |
| 12 | `CHANGELOG.md` | skill 变更记录 |

## 11. 试点与后续

- **S1 spike** 是 plan 的第一个 task：验证包级 agent 目录注册字段名、preflight API 返回形态、一轮派发成本。
- **U1 试点 issue** 待 ⏸ 时与用户确认候选（建议：下一个真实 bug 的 spec；或复用停滞中的 jfox #547 做外仓验证——其第 2 轮复核恰好悬而未决，可兼作「循环恢复」场景）。
- 路线 B（zima 外置）与五视角 fan-out 作为后续阶段另行立项，不在本 issue。
