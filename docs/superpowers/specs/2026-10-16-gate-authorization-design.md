# Spec: github-issue-driven 启动时一次性授权（issue #258）

Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T08:38:00+08:00
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T09:05:00+08:00（第 1 轮复核 R1-G1/G2/G3 与 R1-D1~D5 全部接受并改，处置见 `research/spec-review-round-1.md`）
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-10-16T09:20:00+08:00（第 2 轮收敛轮：R2-D1/D2/D3 三条细化全部接受并改——新增 §3.7 覆盖范围清单与 C8、修正碰撞源引证、补 C3/C4 验收归属，见 `research/spec-review-round-2.md`）
Issue: https://github.com/zhuxixi/zima-blue-cli/issues/258
Scope: `pi/github-issue-driven/SKILL.md`（主）+ `pi/zima-pr-monitor/SKILL.md`（接口同步一句）+ `tests/unit/test_issue_driven_contracts.py`（新增）+ `CHANGELOG.md`

## 1. 问题

issue-driven 流程有两道**许可型**闸门——步 4 设计确认（`SKILL.md:22`）与步 9 push/开 PR（`SKILL.md:56`）——它们每次都要求用户重新回一句话，且"许可"只活在对话上下文里。后果是：实现全部完成后 turn 结束，用户不回到那个 session，流程就静默挂起（实证见 `research/round1-机制定位.md`，issue #188 停摆至今）。

同时，这两道闸门落实的其实是用户全局规则「不自动 commit/push **除非我明确说可以**」——一次明确授权即可满足，无需逐次发问。本 spec 因此不改规则语义，只给它加一条「一次性授权」的出口。

## 2. 目标与非目标

**目标**

- **G1**：用户在流程中给出一次授权后，本次 issue 的许可型闸门按档位自动放行；实现完成 → push → 开 PR → 打标签 → CR → 修复重推，全程无需再回话（上限见 §3.6）。
- **G2**：授权落盘且跨 session / 跨 harness 可查；中断后重进 session 能读到授权状态，不重复发问。
- **G3**：**未授权（`stepwise` 档）时行为与现状逐字一致**——包括合并步骤（现状：步 9 获许可后按 `zima-pr-monitor` 在收敛 + CI 全绿时直接合并）；`~/.pi/agent/AGENTS.md` 的规则文本不被修改。

**非目标**

- **N1** 不自动合并（决策见 §3.6）。
- **N2** 不放宽任何质量闸门（`spec-cross-review`、本地 CR、zima CR、验收逐项对账全部保留）——本改动只放宽"许可"类闸门。
- **N3** 不做跨 issue 的批量授权（批量场景另开 issue，见 §7 决策表）。
- **N4** 不改 zima 运行时代码；不做无人值守调度（把流程放进 PJob / goal 模式是另一条路）。

## 3. 设计

### 3.1 三档授权

| 档位 | 标识 | 步 4 设计 gate | 步 9 push/开 PR gate | 覆盖动作 | 上限 |
|---|---|---|---|---|---|
| 逐步确认（默认） | `stepwise` | ⏸ 停 | 🚪 停 | 无（每次都要许可） | 与现状一致（含合并步骤不变） |
| 设计后停一次 | `design-only` | ⏸ 停 | 自动 | push、开 PR、打 `zima:needs-review`、修复重推 | 到「可合并判定」（合并前停） |
| 全自动 | `auto` | 不停 | 自动 | 同上 | 到「可合并判定」（合并前停） |

- `stepwise` 是默认值，也是**任何异常情况的兜底值**（文件缺失、档位值非法、文件不可读 → 一律按 `stepwise`，fail-closed）。
- 两档自动档的差别只在步 4 是否暂停；步 9 之后的行为完全一致。
- 合并步骤的档位归属见 §3.6：只有 `auto` / `design-only` 才新增合并前停顿；`stepwise` 的合并行为**不变**。

### 3.2 授权记录（`authorization.md`）

路径（沿用既有调研目录纪律，跨 harness 共读、不清理）：

```
~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/authorization.md
```

Schema（固定键名，便于 grep 与契约测试）：

```
# Authorization — issue <N>
Gate: auto
Granted-by-user-quote: "全自动跑完，不用问我"
Granted-at: 2026-10-16T08:40:00+08:00
Session: pi/<session-id>
Scope: spec-gate, push, pr-create, label-trigger, fix-loop-push
Merge: requires-explicit-user-approval
```

生命周期规则：

1. **文件不存在 = 未授权 = `stepwise`**。
2. 用户中途改口径（例：「在这里停下等我」）→ 覆写 `Gate:` 行并追加 `Amended-at:` + 原话，不删除文件。
3. 档位值不在 `{stepwise, design-only, auto}` 内 → 视为 `stepwise`，并在报告中提示档位非法。
4. 读取时校验路径中的 `<owner>/<repo>/issue-<N>` 与当前 issue 一致——防止误读别的 issue 的授权。
5. 该文件随 issue 目录留档，与 `research/`、`spec.md` 同纪律（流程结束后不清理）。

### 3.3 gate 判定（步 4 / 步 9 共用）

1. 读本 issue 的 `authorization.md`（按 §3.2 规则 1/3/4 归一化档位）。
2. 本步骤被该档位覆盖 → **不停**，直接执行；报告（含每条 issue 评论）首行标注依据：`[auth] gate=<档位> · 依据 <授权文件绝对路径>`。
3. 未被覆盖 → 按现行方式暂停等许可（步 4 / 步 9 的原文语义不变）。
4. **用户给出的任何许可都要落盘**（新建或更新 `authorization.md`）：这是让"每次都要问"自然收敛为"只问一次"的关键一步；口头许可不落盘 = 下次仍然会问。

### 3.4 授权从哪来（散文确认，不弹 question）

- **起手已说明**：用户在起始 prompt 里说了（如「全自动跑完 #N」「不用问我」）→ 直接落盘对应档位，不再发问。
- **未说明**：在第一次 gate 触发时按**散文风格**问一次：

  > 本次流程的授权档位？逐步确认（默认）/ 设计后停一次 / 全自动（合并前仍停）

  用户选定后落盘，后续不再问。
- **不默认弹结构化 `question` 工具**——项目确认风格是散文（JFox `202608061804503041`），且非交互 session 下 `question` 直接返回 error。该条款必须成文（由 A1 断言覆盖，见 §5/§6）。

### 3.5 与全局 AGENTS.md 的关系（法理）

授权由用户明确给出，**满足**「不自动 commit/push 除非我明确说可以」；本 skill 不修改、不放宽该规则文本。未授权时逐步确认的行为与引入本机制前逐字一致。

### 3.6 合并闸门（决策记录）

`auto` / `design-only` 档的授权上限是「CR 收敛 + CI 全绿 + 可合并判定」，**这两档下 `gh pr merge` 前仍需用户明确许可**（授权文件固定 `Merge: requires-explicit-user-approval`；本 spec 不提供"允许自动合并"的写法，属非目标 N1）。

`stepwise` 档**不新增**合并前停顿——现状（步 9 获许可 → 收敛 + CI 全绿 → 直接合并）原样保留，以满足 G3。

理由三条：① 合并是唯一不可逆动作；② JFox `202608160204183409` 记录了未经确认合并另一 session 仍在开发的 PR 的事故（CR 收敛 + `mergeState CLEAN` 仍不足以防住）；③ 「自动合并」在本仓已有独立承载路径——`examples/auto-merge/auto-merge-guarded.py` 守门脚本（六道闸门，调度宿主为用户 crontab；JFox `202608302227191813`），session 内不重复造。

### 3.7 与 `spec-cross-review` 收敛提示的关系（判定优先级）

`spec-cross-review` 有一条**被契约测试钉死**的收敛提示行（`pi/spec-cross-review/SKILL.md:64`，由 `tests/unit/test_spec_cross_review_contracts.py:59` 断言）：

> `[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。`

优先级规则（写进 C1 新节）：

1. **档位判定以「授权与档位」节为唯一权威**；`spec-cross-review` 内的 ⏸ / 「待用户确认设计」表述一律视为**进度提示**，不构成独立暂停指令。
2. `stepwise` / `design-only`：收敛行照常输出，随后 ⏸ 等用户确认设计。
3. `auto`：收敛行照常输出（**不改写其文本**——它被契约测试 pin 住），随后**不停顿**，直接进入步 5，并输出一行 `[auth] gate=auto · 依据 <路径>` 说明为何未暂停。
4. 该条款的**覆盖范围**（R2-D1 修订）：`pi/spec-cross-review/SKILL.md` 全部四处表述——`:16`「人只在收敛后的 ⏸ 出现」、`:62`「收敛后输出并进入 ⏸：」、`:64` pinned 收敛行、`:86`「真缺口 = 0 → 收敛轮（细化项改完即进 ⏸）」——**外加** `pi/spec-cross-review/references/edge-cases.md:19`「进入 ⏸ 等用户…」。其中 `:62` 与 `:86` **无测试 pin**，按 C8 直接改写为带档位限定的表述；`:64`（pinned）与 `edge-cases.md:19` 不改写，由本条款裁定。
5. 同理处理步 4 段内另一处无条件表述（`pi/github-issue-driven/SKILL.md:29`「收敛后才进入本步的 ⏸。」）——该句**无测试 pin**，按 C2 直接改写为带档位的表述。

## 4. 文档改动（逐处 + 兼容约束）

| # | 文件 | 位置 | 改动 | 兼容约束 |
|---|---|---|---|---|
| C1 | `pi/github-issue-driven/SKILL.md` | 新增节（建议置于「关键纪律」前后） | 新增「## 授权与档位（步 4 / 步 9 的许可闸门）」全文，内容**必须含**六块：(a) 三档表；(b) 授权记录 schema + 五条生命周期规则；(c) gate 判定四步 + `[auth] gate=` 标记；(d) 授权来源（散文确认、不默认弹 question）；(e) **失败处理条款**（issue 号校验不符=未授权 / 落盘失败=停下报告不得凭记忆继续 / 非交互宿主无预置文件=按 stepwise 暂停）；(f) **与 spec-cross-review 收敛提示的优先级条款**（§3.7，含**覆盖范围清单**：SKILL.md `:16`/`:62`/`:64`/`:86` + `edge-cases.md:19`） | 不得出现具体模型名（既有 `BANNED_LITERALS` 契约） |
| C2 | 同上 | 步 4 段（`:22` 与 `:29` 两处） | `:22` 改写为「**收敛后按授权档位决定是否 ⏸——未授权时与现行一致：收敛后才 ⏸ 暂停等待用户确认设计；`auto` 档则直接进入步 5（见「授权与档位」节，含优先级条款）**」；`:29` 改写为「轮次结论评论回 issue；收敛后按档位进入本步的 ⏸（`auto` 档直接进入步 5）。」 | **必须保留既有 pinned 子串**「收敛后才 ⏸ 暂停等待用户确认设计」在 `:22` 内连续存在——`tests/unit/test_spec_cross_review_contracts.py::TestFlowStep4::test_marker_precedes_pause_sentence` 用 `flow.index(...)` 断言它，且 `spec-cross-review` 标记必须仍在其之前（第 1 轮 R1-P1 已核实该改写方式成立）。`:29` 无测试 pin，可自由改写 |
| C3 | 同上 | 步 9 行 | 把「**🚪 push/开 PR 前暂停，等用户明确许可**——用户 AGENTS.md 硬规则…」改写为「**🚪 push/开 PR 前按授权档位判定（见「授权与档位」节；未授权 = 暂停等许可，用户 AGENTS.md 硬规则不变）**」，其余（打标签、同 turn 阻塞等待、meta 前缀、降级路径）原样保留 | 句中 `zima:needs-review`、`pi-cr-meta`、`cc-cr-meta`、`前台阻塞等待` 属**生态契约词**（webhook 触发标签 / review meta 前缀），保留以防文档间漂移；**注意：本文件当前无测试 pin 这些词**（`tests/` 内只有 `test_spec_cross_review_contracts.py` 引用该 SKILL.md），不要声称为测试守卫 |
| C4 | 同上 | 「## 关键纪律」 | 追加一条：**授权落盘**——任何许可（起手授权或临时许可）都要写进 `authorization.md`，执行时在报告首行注明依据路径；口头授权不落盘等于没有授权 | 与既有纪律条目风格一致（加粗引导句 + 一句话展开） |
| C5 | `pi/zima-pr-monitor/SKILL.md` | 「每轮」决策树内的合并环节 | 追加一句：**在 `auto` / `design-only` 档位下**，合并（`gh pr merge`）前需用户明确许可；两档授权的上限是「可合并判定」。`stepwise` 档的合并行为不变（收敛 + CI 全绿即合并，同现状） | 不改动该 skill 的 meta 解析、收敛判定、多流纪律等既有内容；措辞必须带档位限定，避免给默认档新增停顿（G3） |
| C8 | `pi/spec-cross-review/SKILL.md` | `:62`「5. 收敛后输出并进入 ⏸：」与 `:86`「真缺口 = 0 → 收敛轮（细化项改完即进 ⏸）」 | 两处各追加档位限定（如「…进入 ⏸（`auto` 档不停，见 github-issue-driven「授权与档位」节）」） | 这两句**均无测试 pin**（`grep tests/` 零命中，R2-D1 已核实）；**不得**触碰 `:64` pinned 收敛行与 `references/report-template.md` 的 PROGRESS/CONVERGED 行；`edge-cases.md:19` 不改写（由 C1(f) 优先级条款裁定） |
| C6 | `tests/unit/test_issue_driven_contracts.py` | 新增文件 | 新增契约测试（见 §5、§6） | 新文件独立于 `test_cr_batch_contracts.py` / `test_spec_cross_review_contracts.py`；不改动既有断言 |
| C7 | `CHANGELOG.md` | Unreleased | 记录本次 skill 变更（一条） | 遵循既有 CHANGELOG 格式 |

`pi/README.md` 的技能表**不需要**改动——本次不新增 skill，只修改既有 skill 的行为契约。

## 5. 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | 新节六块内容成文（含 C4 纪律条目） | 自动化验证（unit/static） | `uv run pytest tests/unit/test_issue_driven_contracts.py -q` | 断言全绿：三档标识（`stepwise` / `design-only` / `auto`）、gate 判定四步、授权文件路径与 schema 键名（`Gate:` / `Granted-by-user-quote:` / `Granted-at:` / `Session:` / `Scope:` / `Merge:`）、`[auth] gate=` 标记、**散文确认 + 不默认弹 question**、**三条失败处理条款**、**收敛提示优先级条款含覆盖范围清单**、**C4 的「授权落盘」纪律条目**均存在 |
| A2 | 未授权=现状，且无无条件暂停残留（含 C3 步 9 行） | 自动化验证（unit/static） | 同上 + `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q` | `stepwise` 为默认/兜底档成文；`Merge: requires-explicit-user-approval` 成文；步 4 的 `:29` 不再无条件成文（断言改写后的带档位表述）；**步 9 行含「按授权档位判定」且保留「暂停等许可」子句**（`assert_step9_gate_tier_qualified`）；`spec-cross-review` 的 `:62`/`:86` 已带档位限定且 `:64` pinned 行原样；既有 pinned 子串仍在且 `spec-cross-review` 标记仍在其之前（由既有测试守卫） |
| A3 | 撤档不误伤：默认档合并行为不变 | 自动化验证（unit/static） | `uv run pytest tests/unit/test_issue_driven_contracts.py -q` | C5 措辞带 `auto` / `design-only` 档位限定（断言 `stepwise` 与合并停顿并不同句出现为一组要求）；`pi/zima-pr-monitor/SKILL.md` 原有合并语义句仍在 |
| A4 | 既有契约零改动全绿 | 自动化验证（unit） | `uv run pytest tests/unit/test_spec_cross_review_contracts.py tests/unit/test_cr_batch_contracts.py -q` | 两个既有契约测试文件保持全绿，且**本 PR 不修改它们**（`git diff --name-only` 证明） |
| A5 | 负控：断言有判别力 | 自动化验证（unit，mutation） | 同 A1 命令 | 每个 `assert_*` 函数至少一条变异用例；变异点含**档位令牌碰撞用例**——碰撞源是**真实存在**的 `automated E2E`（`pi/github-issue-driven/SKILL.md:30/:32`）：删掉三档表整行后，文档里仍存在的该子串不得让 `assert_three_tiers` 误过；如需覆盖 `auto-merge` 类子串，用例须注明是**构造的合成变异文本**（两个目标文件中并不存在该子串，R2-D2 已核实） |
| U1 | 授权后实现完成到 PR 无停顿 | 用户实测（**post-merge**） | 合并后、主 checkout `git checkout main && git pull` 到位，再取一个真实 issue，起手说「全自动跑完 #N」：观察步 4 不停、实现完成后自动 push + 开 PR + 打 `zima:needs-review` + 进入 CR 等待 | 全程无停顿直达 PR；issue 评论首行出现 `[auth] gate=auto · 依据 …`；PR 时间线可见自动创建与打标 |
| U2 | 未授权仍会停（对照） | 用户实测（**post-merge**） | 另开 session 不提授权，跑同一流程到 step 9（并在合并环节观察是否仍为"收敛即合"） | 仍在 push/开 PR 前暂停等许可；合并行为与改动前一致 |

**改动→验收归属映射**（R2-D3）：C1→A1/A2；C2→A2/A4；C3→A2；C4→A1；C5→A3；C6→A4；C7（CHANGELOG）→ plan 的验收对账项（无断言）；C8→A2。无未归属的改动项。

**执行时机**：A1–A5 在本 PR 内完成；**U1/U2 依赖合并后主 checkout 生效**（技能包按主 checkout 路径装载，PR 期间分支/worktree 内的改动不会被试点 session 加载），因此在本 PR 内标记 `pending`，合并后执行并回填结论。不宣称已验证。本 issue 自身流程跑在旧 skill 上，其步 9 停顿是**旧行为参照，不等于 U2 已执行**。

## 6. 可测性拆分设计（必答）

改动主体是 Markdown 文档，可自动化部分是**文档契约**。拆分为纯函数断言 + 单一 IO 边界：

| 单元 | 类型 | 签名 | 断言语义 | 测试边界 |
|---|---|---|---|---|
| `load_skill_texts()` | IO 边界（**唯一副作用**，只读） | `(repo_root: Path) -> dict[str, str]` | 返回 `{相对路径: 文本}`；缺文件时 `pytest.fail` 报路径 | 单独一条测试锁"缺文件 → 明确报错"，不静默返回空串 |
| `assert_three_tiers(text)` | 纯函数 | `(str) -> None` | 三档**反引号包裹的令牌**各出现，且三档表上下文存在 | **锚定规则**：匹配反引号包裹 `` `auto` `` **或**「表行 + 档位词 + 语义词」组合；禁止裸子串匹配——目标文件中**真实存在**的碰撞源是 `automated E2E`（`:30`/`:32`，裸匹配 `auto` 会误过）；`auto-merge` 类子串在目标文件中**并不存在**，若用例需要它，必须显式标注为构造的合成变异文本。文档重排不破坏断言 |
| `assert_gate_branching(text)` | 纯函数 | `(str) -> None` | 判定四步语义成文（读文件 / 覆盖则不停 / 未覆盖则暂停 / 许可落盘）+ `[auth] gate=` 标记 + **散文确认且不默认弹 question** | 只断言语义片段，不断言措辞顺序 |
| `assert_authorization_schema(text)` | 纯函数 | `(str) -> None` | 路径模板 + 六个 schema 键名 + 五条生命周期规则（缺文件=stepwise / 非法值 fail-closed / issue 号不符=未授权 / 改口径追加 Amended-at / 不回清理） | 同上 |
| `assert_failure_branches(text)` | 纯函数 | `(str) -> None` | 三条失败处理条款成文（issue 号校验、落盘失败停下报告、非交互宿主按 stepwise） | 同上 |
| `assert_precedence_clause(text)` | 纯函数 | `(str) -> None` | 收敛提示优先级条款成文（档位节为唯一权威 / `auto` 档不改写收敛行 / 不停顿并输出 `[auth]` 依据行） | 同上 |
| `assert_merge_scoped_to_auto_tiers(text)` | 纯函数 | `(str) -> None` | C5 措辞带 `auto` / `design-only` 限定；`stepwise` 与合并停顿不构成无条件要求 | 同上 |
| `assert_step4_pause_substring_preserved(text)` | 纯函数 | `(str) -> None` | 既有 pinned 子串仍在，且 `REQUIRED SUB-SKILL: Use spec-cross-review` 在其之前 | **跨文件契约的本地复述**（真正的守卫仍是既有测试；此处防本 PR 连带改坏） |
| `assert_step9_gate_tier_qualified(text)` | 纯函数 | `(str) -> None` | 步 9 行同时含「按授权档位判定」与「暂停等许可」两个语义片段（C3 的验收归属，R2-D3） | 只断言语义片段，不断言措辞顺序；同时覆盖 `spec-cross-review` `:62`/`:86` 的档位限定成文 |
| `assert_authorization_discipline(text)` | 纯函数 | `(str) -> None` | C4 纪律条目成文（授权落盘、口头授权不落盘等于没有授权） | 同上；与 `assert_gate_branching` 的「许可落盘」判定步骤互补（一条锁判定流程，一条锁关键纪律条目） |
| `assert_no_banned_literals(text, literals)` | 纯函数 | `(str, tuple[str, ...]) -> None` | 禁写清单（沿用既有先例的模型名字面量）不出现在新节 | 与既有 `TestNoHardcodedModels` 同风格（字面量黑名单，不用形态正则） |
| mutation 负控 | 纯函数（测试内） | 变异文本 → 断言必须抛错 | 每个 `assert_*` 至少一条变异用例 | 变异点：删档位行 / 改 `authorization.md` 路径 / 删 `Merge:` 行 / 删 `[auth] gate=` 标记 / 步 9 行删「暂停等许可」子句 / **删三档表整行但保留 `automated E2E` 子串（令牌碰撞用例，碰撞源真实存在）** |

**副作用隔离**：全部断言是 `str -> None` 纯函数；除 `load_skill_texts()` 的只读 IO 外无任何写盘、无 subprocess、无网络。

**由此形成的测试边界**：本组测试只保证「文档契约成文且不被静默改坏」，**不保证模型运行时会照做**——运行时行为不可自动化，由 U1/U2 实测兜底（spec 已如实标注 `pending`）。

## 7. 决策表（含被拒选项）

| 决策 | 选择 | 依据 |
|---|---|---|
| 授权上限 | 到「可合并判定」，两档自动档合并前仍停；默认档合并行为不变 | 用户 2026-10-16 决策；JFox `202608160204183409`（误合并事故）+ `202608302227191813`（自动合并另有承载）；R1-G3 修订 |
| 授权留痕 | 落盘 `authorization.md` + 一条 issue 评论 | 用户 2026-10-16 决策；沿用既有跨 harness 目录纪律 |
| 确认方式 | 散文，不弹 `question` | JFox `202608061804503041`（项目确认风格）；非交互 session 下 `question` 返回 error |
| 收敛提示行 | 不改写（被契约测试 pin），以优先级条款裁定 | R1-G1 修订；`test_converged_line_pinned` / `test_template_pins_progress_lines` |
| ~~环境变量开关 `ZIMA_AUTO_PR`~~ | 拒绝 | 不能跨 session 留痕；与"用户口头授权"语义重复；宿主（agent-board 等）不易传达环境变量 |
| ~~直接删除步 9 gate~~ | 拒绝 | 与全局 AGENTS.md 硬规则冲突，必须同时改用户全局配置，影响面外溢到所有会话 |
| ~~授权跨 issue / 跨仓全局生效~~ | 拒绝（YAGNI） | 一次授权被无限扩大，风险不对等；批量场景（JFox `202609062218071421` 的 6 个 issue 预授权）另开 issue 设计 |
| ~~把授权写进全局 AGENTS.md~~ | 拒绝 | 规则文本属用户所有，本次以 skill 层实现为准（G3） |
| 档位标识用 kebab 小写 + 反引号锚定 | 采纳 | 便于契约测试字面量断言、跨 harness 一致；R1-D1 修订锚定规则 |

## 8. 边界与失败处理

| 情形 | 行为 |
|---|---|
| `authorization.md` 不存在 | `stepwise`（默认，与现状一致） |
| 档位值非法 / 空值 | `stepwise` + 报告提示档位非法（fail-closed，不猜用户意图） |
| 路径中的 issue 号与当前 issue 不符 | 视为未授权（不跨 issue 复用） |
| 目录不存在 / 不可写（落盘失败） | `mkdir -p` 尝试创建；仍失败则**停下报告**，不得以"我记得被授权了"继续 |
| 用户中途改口径 | 覆写 `Gate:` + 追加 `Amended-at:` 与原话 |
| 上下文被压缩 / 换 session | 重读 `authorization.md` 恢复；读不到即回退 `stepwise` |
| 收敛提示行与档位指令并存 | 按 §3.7 优先级条款处理：档位节为唯一权威，`auto` 档输出依据行后直接进下一步 |
| zima 缺席降级路径 | 不受影响——降级为人工 CR / 本地 `code-review` 的逻辑原样保留 |
| 非交互宿主（PJob 等） | 无用户在场时必须预先落盘授权文件，否则按 `stepwise` 暂停（即：非交互下不做隐式授权） |

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 模型"记得"被授权但文件没写 → 授权状态不可审计 | 强制报告首行标注 `[auth] gate=… · 依据 <路径>`，依据即证据；路径不存在即为越权，可对账 |
| 用户误以为"全自动"包含合并 | 档位问询文案与文档均明写「合并前仍停」（限 `auto`/`design-only`）；授权文件固定 `Merge: requires-explicit-user-approval` |
| 默认档被静默加停顿（R1-G3） | C5 措辞强制带档位限定，A3 断言守卫；`stepwise` 合并路径不变 |
| 收敛提示行（pinned）与 `auto` 档指令冲突（R1-G1） | §3.7 优先级条款 + C1 内容要求 + `assert_precedence_clause` 断言；不改写被 pin 的文本 |
| 断言因令牌碰撞而形同虚设（R1-D1） | 反引号锚定 + 碰撞变异用例（§6） |
| 授权文件被误读/误写 | 路径含 `owner/repo/issue-N`，读取时校验一致性；目录为全局约定目录，非项目目录 |
| 文档改动撞既有 pinned 契约 | C2 保留 pinned 子串；A4 用两个既有契约测试文件全绿 + 本 PR 未改它们做回归证明 |
| 授权成了绕过质量闸门的后门 | 非目标 N2 明写：仅放宽许可类闸门；spec-cross-review、本地 CR、zima CR、验收对账全部保留 |

## 10. 试点与后续

- **本次流程自身**（本 issue）作为「旧行为参照」：它跑在旧 skill 上，会在步 9 停一次——这是改动前的常态记录，**不等于 U2 已执行**。
- **U1 试点**：合并后、主 checkout `git checkout main && git pull` 到位，取一个真实 issue 以 `auto` 档跑通到 PR + 打标签 + 进入 CR；留证 = PR 时间线 + issue 评论首行 `[auth]` 标记。
- **U2 对照**：另开 session 不提授权，确认步 9 仍停、合并仍为"收敛即合"。
- **后续（非本 issue）**：批量授权（跨 issue / 跨仓）；`auto` 档含合并（需在 `auto-merge-guarded` 之上另设计）；cc（Claude Code）版对齐（随 #221 的同步机制）。
