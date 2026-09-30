# Spec — Issue #250：新增 `spec-cross-review`（github-issue-driven 步 4 的 spec 交叉复核）

- 状态：**v4 定稿（两轮复核收敛 + 用户已确认设计）**；进 worktree 后落 `docs/superpowers/specs/2026-09-30-spec-cross-review-design.md` 作为首个 commit
- Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-09-30T14:23:46Z
- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-09-30T14:32:30Z（第 1 轮发现的处置见 §12）
- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-09-30T14:39:45Z（第 2 轮收尾处置见 §13）
- Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-09-30T14:46:00Z（用户 ⏸ 确认：轮次上限改 4、开放项 1/2 采纳、A6-b 转为既定——见 §11）
- 日期：2026-09-30 · 仓库基线：`main`（本仓）
- 上游 issue：zhuxixi/zima-blue-cli#250（enhancement）
- 调研存档：`~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-250/research/`（round1 现状与既有机制 / round2 可行性与边界 / round3 当前模型读取）
- 命名合规：`spec` / `cross` / `review` 均在 ≤5500 词汇内

---

## 1. 背景与问题

步 4 现在的形态是「起草模型写 spec → 直接 ⏸ 等用户确认」，spec 质量完全依赖起草模型的单视角；用户在实现阶段才成为事实上的 reviewer，而步 8/9 的 CR 只管代码，设计缺陷此时修复成本已被放大。

实证（voice-input #29，2026-09-30）：spec 草稿完成后连续三轮对抗性复核，**每轮都挖出前一轮漏掉的真问题**——① 失败分支无验收项 + 用户实测步骤缺 `git pull`（会在旧代码上验收，结论无效）；② 测试接缝不可行（按 spec 设计驱动 `_deliver` 需要伪造全局路径 + 与在跑 daemon 相撞，必须重构出两层接缝）；③ 回归命令只跑单文件，与 README 钉住的全仓套件冲突。

调研补充的实证：`~/.claude/github-issue-driven/zhuxixi/voice-input/issue-29/` 只有 `spec.md` + `research/root-cause-and-contracts.md`，**三轮复核零产物**——复核过程只存在于会话里，issue 正文的"三轮发现表"是事后追述。同目录下 jfox #561、pi-agent-board #95/#145/#150 同样只有 research + spec。留痕缺口是系统性缺口，不是单次疏忽。

## 2. 目标

1. 新增 `pi/spec-cross-review/SKILL.md`（+ references），作为 github-issue-driven **步 4 的内嵌 REQUIRED SUB-SKILL**，插在"草稿完成"与"⏸ 等用户确认"之间。
2. 复核由**人工切模型 + 人工触发**驱动：起草者 M1 写草稿 → 用户切到异构模型 M2 → 触发复核 → 用户切回 M1 → 触发修订 → 再切 M2 复审 …… 循环至收敛或轮次上限。
3. 每轮的复核报告、修订摘要、状态索引**固定落盘**，轮次结论评论回 issue，使复核可追溯、可跨会话。
4. 修订 `pi/github-issue-driven/SKILL.md` 步 4：spec 完成后先走 spec-cross-review 收敛，收敛后才 ⏸；同步流程图与关键纪律。
5. 用真实 issue 试点走通（≥2 轮异模型复核 → 收敛 → 用户确认）。

## 3. 非目标

- **不做代码 CR**：步 8 的 `requesting-code-review` / 步 9 的 zima 单 Bot CR 原样不动。本 skill 只管设计文档。
- **不自动拍板**：复核收敛后仍然 ⏸ 等用户确认设计；skill 提高的是"送到用户面前那一版"的质量下限。
- **不做自动修订合并**：复核只产出发现，修订由起草者执行、用户可见。
- **不引入运行时依赖**：纯 skill 文档（Markdown）；机器可校验的部分放本仓 `tests/unit/`（pytest + stdlib），不进 skill 的运行时路径。
- **不改 cc（Claude Code）版**：`github-issue-driven` 目前只有 pi 版；cc 版随 #221 的同步机制后续处理。
- **不碰 worktree / commit / PR**：skill 全程只读仓库 + 写 `~/.claude/...` 留痕目录；git 操作仅限只读查询。

## 4. 关键事实依据（调研对齐）

| 事实 | 来源 |
|---|---|
| `PI_PROVIDER` / `PI_MODEL` 在**每条 bash 命令启动时重新解析**；切模型立即影响下一条命令；文档明示"被问当前模型时看这两个变量，不要从 system prompt 推断" | pi `docs/environment-variables.md` |
| session JSONL 在用户中途切模型时写 `model_change`（`provider` + `modelId`）；assistant message 的 `model` 字段记的是**真实答话的物理模型**（虚拟模型场景下与 `PI_MODEL` 不同） | pi `docs/session-format.md`；实测本会话 JSONL |
| `agent-board/view_*/meta.json` 的 `defaultModel` 是面板**启动默认值**，不是当前模型——不可用作判据 | JFox《agent-board 状态目录里各文件的职责》；实测 |
| 仓内 skill 布局：`pi/<skill>/SKILL.md`（+ `references/`、`scripts/`），`package.json` 的 `pi.skills: ["./pi"]` 注册；`pi/README.md` 有技能索引表 | 仓库实测 |
| 包内文档**禁止写具体模型名**（模型名是部署策略）；本仓 #217 已有契约测试在挡 | pi-subagents `references/prompting-and-roles.md:102`；#216/#217 |
| 本机 `subagents.modelScope.allow` 仅含 deepseek-flash / deepseek-v4-pro / glm-5.3(-flash/-highspeed) / kimi-coding/k3 / kimi-for-coding | 实测 `~/.pi/agent/settings.json` |

## 5. 与 issue 原文的设计修订（需用户知悉）

issue 原文提案假设"复核 subagent + 独立模型变量 + preflight（格式 → registry → modelScope）"。用户澄清后改为**人工切模型 + 人工触发的会话内复核**，因此：

1. **取消**模型环境变量与 subagent preflight —— 异模型由人保证，skill 只读取、比对、留痕。
2. **证据强度上升**：`PI_PROVIDER`/`PI_MODEL` 是会话级事实，比"父 agent 声称传了 model 字段"强；subagent 派发路径下 `workflow-receipt.json` 不含 model（读源码确认），异步 run 的模型投影不持久化。
3. **新增必要条件**：起草者模型必须被记录（草稿头部 `Drafted:` 行），否则无从判定"异"。
4. **上下文性质**：会话内复核 = 异模型但**共享起草时的对话上下文**，故硬规则要求复核者从磁盘重读 spec 与真实代码、禁止引用会话记忆。

## 6. 设计

### D1 · 触发与前置

- 触发词：`spec-cross-review`；中文自然语言"复核 spec / spec 交叉复核"等效。
- 前置：步 4 的 spec 或根因报告草稿已落盘；草稿头部含起草记录行，格式固定为
  `Drafted: <provider>/<model> (selected) · <provider>/<model> (physical) @ <ISO8601>`
  （每次修订追加同格式的 `Revised:` 行）。
- 草稿头部缺该行时：询问用户起草模型；用户答"未知"则按降级执行并在报告头标注。
- 根本没有草稿文件时：不执行复核，直接提示先完成步 4 草稿。
- 适用范围：**spec 与根因报告**（步 4 的两种产物）。本轮试点只在 spec 上验证。

### D2 · 模型判定

触发时依次读取：

1. `PI_PROVIDER` / `PI_MODEL` → `selected_now`（**门禁基准**；该值在每条 bash 命令启动时重新解析，用户切模型后下一条命令即生效，是「本轮将用哪个模型」的唯一即时信号）；
2. 草稿头部的 `Drafted:` / 最近一条 `Revised:` → 起草者与上一位修订者记录的模型（各含 selected 与 physical 两个值）；
3. **本轮回答产生之后**，`PI_SESSION_FILE` JSONL 中最后一条 assistant message 的 `model` → `physical_this_round`（真实答话模型；只能事后读取，写入报告头作审计）。

**门禁基准是 `selected_now`**，与记录里的 selected 和 physical **都比对**：任一相等即视为同模型，走 D4。理由（第 1 轮复核 R1-G1 实测）：触发时刻本轮回答尚未发生，「最后一条 assistant message」必然是**上一个模型**——用它做门禁会把「刚切完模型就触发」这一最高频的合法路径误判为同模型。

`physical_this_round` 不参与门禁，只作事后审计；虚拟模型（router 每请求选真身）场景下它是唯一的真身证据。**保守优先**：若 `selected_now` 是虚拟模型且与记录相同，即使 router 可能换真身，也按同模型处理（走 D4），并在报告头如实记录事后 physical 供核对。

**事后撞真身**：写报告头时若 `physical_this_round` 等于起草 / 修订记录中的任一模型，`Mode` 改记 `cross-model (post-hoc same-physical)` 并在 issue 评论说明；该轮按降级轮对待（细化项照常处置，但不得宣称本轮独立）。

### D3 · 分流（触发时的六个分支）

**k 的判定来源**：`spec-cross-review-state.md` 是 k 的唯一权威来源。state 缺失、过期或与文件系统矛盾时，按 `research/spec-review-round-*.md` 重建（取最大轮次号，查该文件是否已含 `## 修订摘要` 段），重建后立即回写 state 并在 issue 评论说明重建原因。

| 当前模型 | 状态（第 k 轮） | 动作 |
|---|---|---|
| ≠ 起草者 | 报告 k 不存在 | **复核**：只读 spec + 真实代码 + 仓约定，写报告 k |
| ≠ 起草者 | 报告 k 已存在，且为收敛轮 | 提示已收敛，等用户确认设计（不重开轮次） |
| ≠ 起草者 | 报告 k 已存在（未收敛） | 提示"本轮已完成，等起草者修订" |
| == 起草者 | 有报告 k、无修订摘要 k | **修订**：逐条处置发现，追加 `## 修订摘要`；收敛轮则改完直接进 ⏸ |
| == 起草者 | 有报告 k、有修订摘要 k、未收敛 | 提示切到复核模型，开第 k+1 轮 |
| == 起草者 | 有修订摘要 k、本轮回合为收敛轮 | **收尾 → ⏸**：交用户确认设计 |

### D4 · 忘切模型（同模型触发）

`selected_now` 与草稿记录的 selected / physical 任一相等（或起草者未知）时**停下来**，输出定稿提示（字面量，供 A1 断言）并等待：

```
[spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。
请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。
```

仅当用户明确回复"降级复核"才继续，并在报告头写 `Mode: degraded (same-model)`、在 issue 评论留痕。

### D5 · 降级（同模型）时的强制加码

降级轮必须对照三类材料，逐项留下定位证据：

1. **被引用的真实代码与测试**：打开文件核到行；spec 里写的接缝/函数/参数必须真实存在或明确标注"待新增"。
2. **仓约定文档**：AGENTS.md / CLAUDE.md / README / 既有 spec 与测试钉住的契约；spec 里的命令必须能在仓里找到出处。
3. **设计文档自身**：验收矩阵与可测性拆分的完备性（见 D7 视角 ①②）。

### D6 · 复核轮硬规则

- 只读：禁止修改任何文件（包括 spec）；禁止 `git add/commit/push`；只读查询（`git log/show/diff`、`gh` 读）可用。
- 每条发现必须给定位：`文件:行号` 或引用 spec 原句；给不出定位的降级为「待证」，不计入真缺口。
- 禁止引用起草时的会话记忆，必须从磁盘重读；发现表每条都要能指向被核对的材料。
- **不得同一轮既审又改**；修订只能由起草者在独立触发中执行。

### D7 · 复核视角清单（五个，skill 内置）

| # | 视角 | 判据 | 实证教训（voice-input #29） |
|---|---|---|---|
| ① | 验收矩阵完备性 | 每个设计决策有验收 ID、每个 ID 有归属；失败分支也有验收项 | 失败分支无验收项被第 1 轮拦下 |
| ② | 可测性拆分可实现性 + 触发时序 | 对照**真实代码**核对接缝：按 spec 设计的测试能否真的构造出来；门禁/判定读取的值在**触发时刻**是否真的可得 | 第 2 轮发现按 spec 设计驱动 `_deliver` 不可行，必须重构接缝；本 issue 第 1 轮实测：门禁基准读取时序错误（R1-G1） |
| ③ | 部署/执行路径真实性 | 用户实测步骤会不会跑到旧代码/错误路径上（含部署、拉取、重启、路径指向） | 第 1 轮发现缺 `git pull`，会在旧代码上验收 |
| ④ | 契约与边界 | 与既有 spec/测试/文档钉住的契约是否冲突；非目标是否被越过 | 第 3 轮对账仓约定 |
| ⑤ | 命令与命名可追溯 | 验收命令能在仓里找到出处（README/CI/脚本）；命名符合仓内约定 | 第 3 轮发现回归命令只跑单文件，与 README 钉的全仓套件冲突 |

### D8 · 发现分级与编号

- 三档：`真缺口`（阻塞，必须修订）/ `细化`（应修订）/ `核对通过`。
- 编号：`R<轮次>-G<n>`（真缺口）/ `R<轮次>-D<n>`（细化）/ `R<轮次>-P<n>`（核对通过，可省）。
- 每条发现：级别、定位、为什么是问题、建议修订、**若不复核会在实现阶段付出什么代价**（成本论证，供用户判断优先级）。

### D9 · 收敛与轮次上限

- 判定时点：**每轮复核结束时**。真缺口 = 0 → 该轮为收敛轮（细化项由起草者改完即进 ⏸，不再开新一轮）；真缺口 > 0 → 起草者修订后开下一轮。
- 默认上限 4 轮（用户 2026-09-30 ⏸ 确认，初稿为 3）；用户可在当轮明确提高上限（记录在 state 索引与 issue 评论）。
- 第 4 轮仍有真缺口：停止循环，如实交用户决定（继续 / 降级接受 / 改设计），**不允许自动继续或假装收敛**。

### D10 · 修订处置

起草者对每条发现三选一：`接受并改` / `部分接受并说明边界` / `拒绝并给证据`（证据指到文件行或仓约定出处）。三种处置全部写入当轮 `## 修订摘要`。真缺口不得静默跳过；用户明确说跳过时，记录"用户决定跳过"及理由。

### D11 · 产物与留痕

```
~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/
├── spec.md                              # 头部：Drafted / Revised 行（模型 + 时间）
└── research/
    ├── spec-cross-review-state.md       # 一屏索引（模板见 references/report-template.md）
    ├── spec-review-round-1.md           # 复核报告 + 修订摘要（同一文件两段）
    └── spec-review-round-2.md
```

轮次报告固定五段：

1. **头**：`Round k` / `Reviewer: <selected> (selected) / <physical> (physical)` / `Drafter: <provider>/<model>` / `Reviewed spec sha256: <hash>` / `Mode: cross-model | degraded (same-model) | cross-model (post-hoc same-physical)` / 时间戳。
2. **五视角核对表**：每个视角的结论与发现编号。
3. **发现表**：D8 定义的全部字段。
4. **收敛判定**：真缺口数 / 细化数 / 本轮结论（继续 / 收敛）+ 下一轮目标。
5. **`## 修订摘要`**（起草者追加）：逐条处置 + 改动位置 + 末尾写入 spec 新 sha256。

**写入归属**：`spec-cross-review-state.md` 由复核者在本轮创建/更新（轮次行、状态、open findings 计数）；起草者在追加修订摘要时同步更新状态字段与新 hash。轮次文件第 1–4 段由复核者写，第 5 段由起草者写，两人都只追加不覆盖。

**版本对账**：报告头的 sha256 标识"本轮审的是哪一版"；下一轮开头必须核到新 hash，不一致则要求先对齐（防"审的版本与改的版本错位"）。

**sha256 计算口径（定稿）**：`sha256sum <spec 文件绝对路径>`——对文件字节流原样计算（UTF-8，不做换行/空白规范化）；报告头与修订摘要都写同口径的完整 64 位十六进制值。`references/report-template.md` 必须原样写出该命令。**哈希不回写**：某版本的 sha256 只记录在轮次文件与 state 索引里（外部），不追加到被计算的文件自身——否则自引用，下一轮对账时永远不相等。

**state 索引**（一屏）：当前状态（reviewing / revising / converged / awaiting-user-confirmation）、轮次表（轮次 → 复核模型 → 真缺口/细化数 → 结论）、open findings 计数、轮次上限与是否被调整。

**issue 评论**：每轮一条（模型、轮次、真缺口/细化计数、下一步），收敛时追加一条汇总。

### D12 · 交接提示（降低人工记忆负担）

每轮结束时输出定稿格式的下一步指令（下列两行为**字面量**，`SKILL.md` 必须原样包含，供 A1 断言），用户照做即可：

```
[spec-cross-review] 下一步：切到 <provider>/<model>，然后说 spec-cross-review（第 <k> 轮复核）。
[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。
```

### D13 · `pi/github-issue-driven/SKILL.md` 步 4 的修订点

1. 步 4 正文的"**⏸ spec 完成后暂停，等用户确认设计再继续。**"改为下面这句（**定稿字面量**，供 A2 断言；A2 断言两个标记串都存在且前者位置更靠前）：
   - 标记串 1：`REQUIRED SUB-SKILL: Use spec-cross-review`
   - 标记串 2：`收敛后才 ⏸ 暂停等待用户确认设计`
   - 改写后的完整句：**REQUIRED SUB-SKILL: Use spec-cross-review**——spec / 根因报告草稿完成后先执行交叉复核，**收敛后才 ⏸ 暂停等待用户确认设计**。
2. 步 4 增加一段：草稿头部必须写 `Drafted: <provider>/<model> (selected) · <provider>/<model> (physical) @ <ISO8601>`，每次修订追加 `Revised:` 行；起草完成后输出交接指令（切模型 + 触发词）。
3. 步 4 的验收分层 / 可测性拆分两条要求原样保留——它们正是复核视角 ①② 的判据来源。
4. 关键纪律新增一条：spec 草稿的模型记录不得省略（异模型判据依赖它）。

### D14 · `pi/README.md`

技能表新增 `spec-cross-review` 行（角色：设计文档交叉复核；对应流程步：步 4）——**无条件执行（A6-a）**；并补上一直漏登记的 `github-code-review-batch`（CR 执行）——**用户已批准保留 (A6-b)**，两行断言均生效。

### D15 · 新 skill 的文件契约

```
pi/spec-cross-review/
├── SKILL.md                  # 骨架：触发与前置 / 模型判定与分流 / 硬规则 / 分级 / 收敛 / 留痕纪律 / 边界
└── references/
    ├── checklist.md          # 五视角各自的核对细则与常见盲区（含 #29 三轮教训）
    ├── report-template.md    # 轮次报告五段 + 修订摘要 + state 索引 的可复制模板
    └── edge-cases.md         # 忘切模型 / 虚拟模型 / 草稿无 Drafted 行 / 轮次上限 / 复核零发现 / 复核中 spec 被改 / hash 不匹配
```

frontmatter 契约（供 A1 断言）：

```yaml
---
name: spec-cross-review
description: |
  对 github-issue-driven 步 4 的 spec / 根因报告草稿做交叉复核……
  Use when: 步 4 草稿完成、用户切换模型后手动触发。
  触发词: "spec-cross-review", "复核 spec", "spec 交叉复核"
---
```

## 7. 可测性拆分设计（自动化类功能点的实现硬约束）

改动是**文档**，可自动化验证的对象是"文档契约"而非行为。拆分：

| 层 | 单元 | 责任 |
|---|---|---|
| 读取 | `_read(path) -> str`（纯函数，无副作用） | 读 SKILL.md / references / github-issue-driven / README |
| 断言 A | `assert_contains(doc, contracts: list[str])` | 契约串存在性（板块、字段、固定文案、模板字段） |
| 断言 B | `assert_no_hardcoded_model(doc) -> None` | 可移植的字面量黑名单（沿用先例 `deepseek-v4` / `zai-coding-cn`），**不用形态正则**；**不得引用机器私有配置**（见 A3） |
| 断言 C | `assert_order(doc, before: str, after: str)` | 顺序约束（spec-cross-review 出现在 ⏸ 之前） |

测试边界（必须在 spec 中如实声明）：

- 只能证明"该写的写了、不该写的没写、顺序对"，**证明不了**"视角清单写得好""skill 在真实会话里会被正确执行"。
- 语义质量与真实可用性由 U1 试点兜底；A1–A6 不得被用来冒充 U1。
- 测试只读文件，不执行 skill，不联网，不依赖 pytest 以外的新依赖。

## 8. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | 新 skill 文档结构与 frontmatter | 自动化（static/unit） | `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k "structure or pinned" -v` | `pi/spec-cross-review/SKILL.md` 存在；frontmatter 含 `name: spec-cross-review` 与非空 description；D15 列出的必需章节（触发与前置 / 模型判定与分流 / 硬规则 / 分级 / 收敛 / 留痕 / 边界）全部命中；三个 references 文件存在；D4 的降级提示文案与 D12 的两行下一步文案原样命中（字面量断言） |
| A2 | 步 4 修订落位且顺序正确 | 自动化（static/unit） | 同上 `-k flow` | 标记串 `REQUIRED SUB-SKILL: Use spec-cross-review` 与 `收敛后才 ⏸ 暂停等待用户确认设计` 都存在，且前者 index 更小（`assert_order`）；含 `Drafted:` 记录要求 |
| A3 | 禁止硬编码模型 | 自动化（static/unit） | 同上 `-k no_hardcoded` | 本次新增的全部 skill 文件（SKILL.md + references）与修订的 `pi/github-issue-driven/SKILL.md` 中不出现 banned 字面量（先例同款清单：`deepseek-v4`、`zai-coding-cn`；扩展方式只允许往清单加新的具体字面量）；**不使用形态正则**（路径中段伪阳性：`tests/unit/test_x.py` 会命中 `unit/test_x.py`）；**不得引用机器私有配置**（`~/.pi/...`）；模型来源指向 `PI_*` 与草稿头记录 |
| A4 | 报告 / state 模板字段齐全 | 自动化（static/unit） | 同上 `-k template` | `references/report-template.md` 含 Round / Reviewer / Drafter / sha256 / Mode / 三档分级标签 / 修订摘要段 / state 字段 |
| A6 | README 技能表登记 | 自动化（static/unit） | 同上 `-k readme` | **A6-a**：`pi/README.md` 技能表含 `spec-cross-review` 行，且角色/对应流程步列非空；**A6-b**：同表含 `github-code-review-batch` 行、列非空（用户已批准保留） |
| A5 | 仓内既有测试不回归 | 自动化（build） | `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60` | 全绿，覆盖率达标 |
| U1 | skill 在真实流程中可用 | 用户实测 | 拿试点 issue **#244（用户已确认）**走完整循环：起草 → 切模型触发复核 → 起草者修订 → （有真缺口则继续）收敛后用户确认。**可执行时机：PR 合并回 main 之后，从主 checkout（pi 包安装路径，见 `~/.pi/agent/settings.json` 的 packages）发起的会话中执行；worktree 内不执行 U1**（否则静默跑在旧 skill 上） | 轮次报告 / 修订摘要 / state 索引齐全；各轮 reviewer 模型确实不同；**至少拦下 1 个会被带进实现的真缺口**；收敛后用户确认设计；issue 评论留痕完整。轮次路径覆盖要求：第 1 轮出现真缺口即继续（预期 ≥2 轮）；若试点首轮恰无真缺口，需另取一份更复杂的 spec 再走一轮，以覆盖多轮路径 |

## 9. 保证边界（必须写进 skill）

1. 无法证明"复核者真的换了模型"——只能记录会话级事实（`PI_*` + assistant message 的 `model`）并如实呈现；skill 是 Markdown 契约，不强制 agent 行为。
2. 会话内复核共享起草上下文，"异"只是模型层面；D6 的"禁引用会话记忆 + 从磁盘重读"是纪律约束，不是机制强制。
3. 降级（同模型）时复核质量天然弱于异模型路径；降级必须留痕，不得在报告中隐去 `Mode`。
4. 自动化测试只锁文档契约（见第 7 节边界）。

## 10. 交付物清单

| # | 文件 | 动作 |
|---|---|---|
| 1 | `pi/spec-cross-review/SKILL.md` | 新增 |
| 2 | `pi/spec-cross-review/references/checklist.md` | 新增 |
| 3 | `pi/spec-cross-review/references/report-template.md` | 新增 |
| 4 | `pi/spec-cross-review/references/edge-cases.md` | 新增 |
| 5 | `pi/github-issue-driven/SKILL.md` | 修订步 4（正文 + 交接要求 + 关键纪律） |
| 6 | `pi/README.md` | 补 spec-cross-review 行 + 补漏登记的 github-code-review-batch |
| 7 | `tests/unit/test_spec_cross_review_contracts.py` | 新增（A1–A4、A6） |
| 8 | `docs/superpowers/specs/2026-09-30-spec-cross-review-design.md` | 本 spec 进 worktree 后的落位（首个 commit） |
| 9 | `CHANGELOG.md` | skill 变更记录（随 release 流程进版本） |

## 11. ⏸ 时的用户决定（2026-09-30，已定）

1. **设计批准**：v3 收尾稿获批准，进 worktree（步 5）。
2. **试点 issue**：#244（executor 超时不杀子进程）——U1 的执行对象。
3. **README 补录**：批准，A6-a + A6-b 均为既定断言（D14 全集）。
4. **轮次上限**：**4**（初稿 3）；本次实测 2 轮收敛，4 提供余量。

## 12. 第 1 轮复核发现的处置（修订记录）

复核报告：`research/spec-review-round-1.md`（复核者 `zai-coding-cn/glm-5.3`，被审版本 sha256 `6534b6d6…`）

| 发现 | 级别 | 处置 | 改动位置 |
|---|---|---|---|
| R1-G1 触发时判定基准时序错误 | 真缺口 | 接受并改：门禁改用 `selected_now`（env，命令级即时生效），与记录的 selected/physical 都比对；`physical_this_round` 转为事后审计；补虚拟模型的保守规则 | D2、D4 |
| R1-G2 草稿缺 `Drafted:` 头 | 真缺口 | 接受并改：补 `Drafted:` / `Revised:` 行（起草模型取自 session 证据）；D13 保持「步 4 强制记录」 | 头部、D13 |
| R1-G3 A3 不可移植 + 正则伪阳性 | 真缺口 | 接受并改：改为可移植 banned 字面量清单（沿用先例），形态正则须排除路径前缀与 `.md`，禁引用机器私有配置 | A3、§7 断言 B |
| R1-G4 U1 缺可执行时机 | 真缺口 | 接受并改：U1 增加「PR 合并后、从主 checkout 发起的会话中执行；worktree 内不执行」 | U1 |
| R1-D1 断言锚点未定稿 | 细化 | 接受并改：D4/D12 标注定稿字面量，D13 给出改写句与两个标记串，A1/A2 按字面量断言 | D4、D12、D13、A1、A2 |
| R1-D2 D3 缺「复核者 + 已收敛」分支 | 细化 | 接受并改：补第六分支 | D3 |
| R1-D3 D14 无验收归属 | 细化 | 接受并改：新增 A6 承载 README 两行的验收 | A6、§10 #7 |
| R1-D4 sha256 口径未定义 | 细化 | 接受并改：定稿 `sha256sum <spec 路径>`（文件字节流原样），写入 D11 与模板要求 | D11 |

无拒绝项。修订后 spec 新 sha256 见 `research/spec-review-round-1.md` 的修订摘要（**外部记录，不写回被计算的文件本身——否则自引用**）。

## 13. 第 2 轮复核发现的处置（收尾修订记录）

复核报告：`research/spec-review-round-2.md`（复核者 `zai-coding-cn/glm-5.3`，被审版本 sha256 `30ae3dca…`；本轮真缺口 0 → 收敛轮）

| 发现 | 级别 | 处置 | 改动位置 |
|---|---|---|---|
| R2-D1 事后撞真身无处置动作 | 细化 | 接受并改：报告头 `Mode` 记 `cross-model (post-hoc same-physical)`、issue 评论说明、该轮按降级轮对待 | D2 |
| R2-D2 分流轮次 k 判定来源未钉 | 细化 | 接受并改：state 为唯一权威来源；缺失/矛盾时按 `spec-review-round-*.md` 重建并回写 | D3 |
| R2-D3 A3 形态正则中段伪阳性 | 细化 | 接受并改（采纳复核者建议 b）：删除形态正则，只用可移植字面量黑名单，扩展方式限于新增具体字面量 | A3、§7 断言 B |
| R2-D4 开放项 2 与 A6 耦合 | 细化 | **部分接受**：不改用户待决事项的性质，改为条件断言拆分（A6-a 无条件 / A6-b 依赖开放项 2），两种结局下 spec 均自洽 | D14、A6、§11-2 |

无真缺口；收敛轮无需开第 3 轮。修订后 spec 升为 v3，新 sha256 见 `research/spec-review-round-2.md` 的修订摘要（外部记录）。
