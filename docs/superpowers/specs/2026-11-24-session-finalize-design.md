# session-finalize — 会话收尾编排（issue #279）

Drafted: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-11-24T08:12:00+08:00
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-11-24T08:22:00+08:00
Revised: deepseek/deepseek-flash (selected) · deepseek/deepseek-flash (physical) @ 2026-11-24T08:50:00+08:00 — 实现期按 PR #280 CR advisory 调整 §3.1 幂等检查上限与兜底

## 1. 摘要

新增 pi skill `session-finalize`，作为会话收尾的唯一入口。它按固定四段执行：**旅程回放 → 主线判定 → jfox 沉淀 → 收尾展示**。用户在长会话末尾只需说一次「finalize」，不需要分别记住并触发 `jfox-session-to-permanent` 与 `jfox-session-summary`。

本 skill 只做编排与呈现，不改两个 jfox skill 的规则，也不改 jfox CLI。

## 2. 决策表（issue 中的 D1–D7 + 新增 D8）

| # | 决策点 | 结论 | 依据 |
|---|--------|------|------|
| D1 | 名称 | `session-finalize` | 动词式，与 `issue-research` 同构；用户已确认 |
| D2 | 归属 | zima-blue-cli `pi/session-finalize/` | 依赖 pi 专属 `$PI_SESSION_FILE`，不适用 cc/kimi；避开 jfox 四副本同步契约；本仓已有跨包技能依赖先例（superpowers） |
| D3 | 旅程回放是否派子 agent | 不派，主 session 直读脚本输出 | 主线判定依赖「在场感」；派发只增加一轮上下文传递，收益不抵复杂度 |
| D4 | 幂等 | 落库前用 `jfox list --type session --json` 的 `session_file` 精确匹配 | 第 1 轮调研实测该字段存在 |
| D5 | 与 issue-driven 的关系 | 独立手动入口；不挂步 10 | 先验证入口价值；自动挂接留二期 |
| D6 | 提问风格 | 主线 gate 用 `question` 工具；过程汇报用散文 | 与 permanent 审阅交互一致；散文只用于状态报告 |
| D7 | 失败处理 | permanent 失败即停止链路，不写 summary | 两者都依赖 jfox；失败后写半套沉淀会制造不一致 |
| D8 | 未结束时是否写 session 笔记 | 默认不写；用户可显式选择「也写 session 笔记」 | permanent 记现状，未收尾时现状未定；session 记历史，可单独成立 |

## 3. 触发与前置条件

### 3.1 触发

- 显式：`/skill:session-finalize`
- 自然语言：`finalize`、`session finalize`、`会话收尾`、`收尾`、`结束会话`、`把这个会话沉淀一下`

### 3.2 前置检查（第 0 段，任一失败即停）

| 检查 | 命令 | 失败处置 |
|------|------|----------|
| 知识库可用 | `jfox kb current --json` | 停止，提示先跑 `/skill:jfox-common` 初始化 |
| 两个被编排 skill 可用 | 在可用技能列表中按名查找 `jfox-session-to-permanent`、`jfox-session-summary` | 停止，提示安装 jfox pi 技能包 |
| 会话文件 | 读 `$PI_SESSION_FILE` | 为空/不存在 → 旅程回放降级（见 §7），不停止 |

`jfox kb current` 的 `name` 只用于报告当前库；本 skill 不写死库名，写入时沿用两个 jfox skill 的默认库规则。

## 4. 四段编排

### 第 1 段：旅程回放

**输入**：`python3 <skill-dir>/scripts/session_journey.py --file "$PI_SESSION_FILE" --json` 的结构化输出。`<skill-dir>` 是本技能目录（系统提示里给出绝对路径）；触发会话的 cwd 通常是别的项目，脚本必须用绝对路径调用，并显式加 `python3 ` 前缀（git 新增文件默认无执行位）。

**输出**（用户可见，中文，3–8 个阶段）：

```markdown
本会话共 <N> 轮、跨 <时长>，改动 <M> 个文件。

### 阶段 1 — <一句话诉求>
- 诉求：<用户原话摘要，≤120 字>
- 动作：bash ×12、read ×8、edit ×5；写入 a.py / b.md
- 结论：<该阶段最后一条 assistant 叙述，≤120 字>

### 阶段 2 — ...
```

**纪律**：

- 只呈现「用户在推动什么、做了什么、落到哪里」，不复述 toolResult，不读 `thinking` 块。
- 阶段划分以用户消息为边界；脚本在阶段数超过 `--max-stages` 时按「合并最短相邻对」规则归并。
- 旅程是给用户校准记忆的，不是审计日志：每阶段最多 3 条 bullet。

### 第 2 段：主线判定

**输出**：

```markdown
主线：<一句话，动词开头，说明这个会话要达成的结果>

当前进度：
- <证据 1：todo / git / PR / issue 的客观状态>
- <证据 2：未决问题>

这条主线是否已经结束？
```

证据来源顺序：会话内 todo → `git status --short` / `git log --oneline -5` → `gh pr view`（若会话涉及 PR）→ issue 状态。取不到的证据不编造，标注「未确认」。

**gate**：调用 `question` 工具，三个选项：

| 选项 | 后续 |
|------|------|
| 已结束 | 进入第 3 段 |
| 未结束 | 只输出「未收尾」报告（主线 / 卡点 / 下一步），再问一次「只报状态 / 也写 session 笔记」；**不写 permanent** |
| 其他 | 请用户自由说明，按说明处置后重新提问 |

### 第 3 段：执行沉淀

**顺序固定：先 permanent，后 summary。**

#### 3.1 幂等检查

```bash
jfox list --type session --limit 200 --format json --include-archived
```

按 `$PI_SESSION_FILE` 匹配 `session_file`：

| 结果 | 处置 |
|------|------|
| 命中（活跃） | `question`：更新已有笔记（`jfox edit`）/ 跳过 session 笔记 / 另建一条 |
| 命中（已归档） | 同样三选一，并提示「该笔记已归档」——不加 `--include-archived` 会漏掉这条 |
| 未命中 | 按标题 `jfox search "Session: <topic>" --type session` 二次匹配；仍无 → 直接继续 |
| 老笔记无 `session_file` 字段 | 退化为标题匹配 `Session: <topic>`；仍无结论则继续 |

活跃 + 归档超过 200 条时明确提示「可能漏检」，不得静默新建。

#### 3.2 permanent

按名定位已安装的 `jfox-session-to-permanent` skill，读其 `SKILL.md` 并完整遵循：去重（search + suggest-links）、分批（每批 ≤5）、`question` 审阅、落库。本 skill 不重复其规则，也不放宽其闸门。

#### 3.3 summary

在上一步完成后，按 `jfox-session-summary` 的格式生成并直接写入。编排层有两条硬要求：

1. **保留溯源参数**：写入命令必须带 `--session-path "$PI_SESSION_FILE"`、`--agent pi-coding-agent`、`--agent-model "${PI_PROVIDER}/${PI_MODEL}"`（变量为空则省略）与标题 `Session: <topic>`。`session_file` 字段只在传了 `--session-path` 时才存在，它是 §3.1 幂等匹配的唯一依据；省略即导致 U4 必失败。
2. **回填 permanent 结果**：若本次写入了 permanent 笔记，在「完成的工作」下补一条 `- 沉淀永久笔记：<标题>（<ID>）`。

#### 3.4 失败处理

| 失败点 | 行为 |
|--------|------|
| permanent 任一写入失败 | 停止链路，不写 summary；报告失败笔记与重试命令 |
| permanent 被用户全部跳过 | 继续 summary（用户选择不等于失败） |
| summary 写入失败 | 报告 permanent 已写入的结果 + summary 错误；不重试、不静默 |
| 重复触发且用户选择「跳过」 | 跳过 summary，仍展示上次写入的笔记信息 |

### 第 4 段：收尾展示

```markdown
## 收尾完成

### 会话总结
<session summary 全文>

### 本次写入
| 类型 | 标题 | ID |
|------|------|----|
| session | Session: ... | ... |
| permanent | ... | ... |

### 未完成事项
- <...>

### 下一步
<一句话>
```

## 5. 旅程抽取的数据契约

### 5.1 输入记录（pi session JSONL）

| 记录 | 处理 |
|------|------|
| `type=message`、`message.role=user` | 用户轮次起点；只取 `text` block |
| `type=message`、`message.role=assistant` | 归属当前阶段；取 `text`（叙述）与 `toolCall`（名称 + 关键参数） |
| `message.content` 中的 `thinking` | 丢弃（体积与隐私） |
| `role=toolResult` | 丢弃正文，只保留错误标记用于「卡点」证据 |
| `role=system` | 丢弃 |
| `type=custom` / `custom_message` / `session_info` / `model_change` / `thinking_level_change` | 丢弃 |
| `type=session` | 只取首条记录的 `timestamp` 与 `cwd` 供 `meta`，其余丢弃 |
| 未列出的 type / role（含未来新增） | 一律丢弃 |

非法 JSON 行由 `load_records` 在解析边界跳过并计入 `meta.skipped_lines`，不进入本表。

**活动分支**：pi 会话是 `parentId` 树，`/tree` 分叉后文件里会同时保留被放弃的分支。`select_active_branch` 以最后一条记录的 `id` 为起点沿 `parentId` 回溯，只保留该链上的记录并按原文件顺序输出。**根记录（`parentId` 字段缺失或为 `null`）视为链的正常终点**，不触发回退；仅当 `parentId` 指向文件中不存在的记录 `id` 时判为断裂，退回全量线性扫描，并在 `meta.branch_fallback=true` 标注。

### 5.2 抽取规则

- toolCall 目标：按参数优先级取 `path` > `file_path` > `command` > `pattern` > `url`（pi 内置 `write` / `edit` 用 `path`；`file_path` 兼容其他工具），截断到 120 字符。
- 写入类工具（`write` / `edit`）的目标计入 `written_files`（去重、保留前 5 个）。
- `meta` 字段：`records`、`user_turns`、`first_ts`、`last_ts`、`skipped_lines`、`branch_fallback`。
- 输出只含摘要，不含 assistant 全文。

## 6. 脚本设计：`pi/session-finalize/scripts/session_journey.py`

### 6.1 接口（可测性拆分）

```python
@dataclass(frozen=True)
class ToolCall:
    name: str
    target: str
    is_write: bool

@dataclass(frozen=True)
class Turn:
    role: str            # "user" | "assistant"
    timestamp: str
    text: str
    tool_calls: tuple[ToolCall, ...]

@dataclass(frozen=True)
class Stage:
    index: int
    user_text: str
    turns: tuple[Turn, ...]

# 纯函数（无 IO、无环境依赖）
def select_active_branch(records: list[dict]) -> tuple[list[dict], bool]
def load_turns(records: Iterable[dict]) -> list[Turn]
def segment_stages(turns: list[Turn], max_stages: int = 8) -> list[Stage]
def stage_summary(stage: Stage) -> dict          # tool_counts / written_files / last_text
def render_markdown(stages: list[Stage], meta: dict) -> str
def build_journey(records: Iterable[dict], meta: dict, max_stages: int = 8) -> dict

# IO 边界（唯一读盘与退出码处）
def load_records(path: Path) -> tuple[list[dict], int]   # 已解析记录 + 非法行数
def main(argv: list[str] | None = None) -> int
```

`main` 的调用链固定为 `load_records → select_active_branch → build_journey`。非法 JSON 行的跳过与计数只在 `load_records` 发生，`load_turns` 只接收已解析的 dict。

### 6.2 归并规则

`segment_stages` 在阶段数 > `max_stages` 时，反复合并「用户文本总长最短的相邻阶段对」，直到数量达标；长度相同取索引靠前的一对。规则确定性，测试可锁。

### 6.3 渲染约束

- 每阶段 3 条 bullet：诉求 / 动作 / 结论。
- 单条文本 ≤120 字符；命令与路径 ≤120 字符。
- 顶层 meta 一行。

### 6.4 CLI

```bash
python3 <skill-dir>/scripts/session_journey.py --file "$PI_SESSION_FILE" [--json] [--max-stages 8]
```

- 退出码：0 成功；2 文件缺失/为空/无有效消息。
- `--json` 输出 `{meta, stages}`，供模型读取后再叙事；默认输出 markdown。

## 7. 降级矩阵

| 情形 | 行为 | 用户可见提示 |
|------|------|--------------|
| `$PI_SESSION_FILE` 为空 | 旅程回放改用当前会话上下文 + git 状态 | 「旅程回放降级：未找到会话文件」 |
| 文件不存在 / 为空 / 0 条有效消息 | 同上（脚本 exit 2） | 同上 |
| `python3` 不可用 | 直接用当前上下文回放 | 「脚本不可用，已降级」 |
| `jfox kb current` 失败 | 第 0 段停止 | 安装 / 初始化指引 |
| 缺 `jfox-session-to-permanent` 或 `jfox-session-summary` | 第 0 段停止 | `pi install` 指引 |
| 旅程阶段 > `max_stages` | 按 §6.2 归并 | 不提示（正常行为） |

## 8. 文件级改动

| 文件 | 动作 |
|------|------|
| `pi/session-finalize/SKILL.md` | 新增：frontmatter + 四段编排 + 决策/失败/降级 |
| `pi/session-finalize/scripts/session_journey.py` | 新增：抽取脚本（纯函数 + CLI） |
| `tests/unit/test_session_finalize_scripts.py` | 新增：脚本单测 |
| `tests/unit/test_session_finalize_contracts.py` | 新增：文档契约 + README/CHANGELOG 注册 |
| `pi/README.md` | 技能表加一行；前置依赖补 jfox 两个 session skill |
| `CHANGELOG.md` | `[Unreleased]` 的 Features 加一条 |

不改 `package.json`（`pi.skills` 指向 `./pi`，递归发现）；不改 jfox 仓库任何文件。

## 9. 验收

### 9.1 部署前置（所有 U 项共用）

用户实测不在 worktree 里执行。实现期改动只存在于 worktree，而 pi 从主 checkout 加载技能包（`packages` 指向主 checkout）。因此：

1. PR 合并后，在主 checkout 执行 `git pull`；
2. 新开一个 pi 会话，或在已有会话执行 `/reload`；
3. 确认可用技能列表里出现 `session-finalize`，且 `jfox-session-to-permanent` / `jfox-session-summary` 可见；
4. 之后再执行 U1–U5。pre-merge 状态下的 U 项一律记 `pending`，不得以 worktree 副本冒充通过。

### 9.2 验收矩阵

| ID | 功能点 | 验收方式 | 具体验证 | 通过标准 |
|----|--------|----------|----------|----------|
| A1 | JSONL 抽取、分支过滤与阶段归并 | 自动化（unit） | `uv run pytest tests/unit/test_session_finalize_scripts.py -q` | §10 的 10 个用例全绿 |
| A2 | skill 文档契约 | 自动化（static/unit） | `uv run pytest tests/unit/test_session_finalize_contracts.py -q` | 章节、两个 jfox skill 名与顺序、前置检查、降级、幂等、禁硬编码全部通过 |
| A3 | README / CHANGELOG 注册 | 自动化（static/unit） | 同上 | 技能表含 `session-finalize` 行；Unreleased 含该条目 |
| A4 | CLI 冒烟 | 自动化（unit） | 脚本对缺失文件、空文件、合法 fixture 各跑一次 | 缺失/空 → exit 2；合法 → exit 0 且 JSON 结构完整 |
| A5 | 失败与降级分支契约 | 自动化（static/unit） | `uv run pytest tests/unit/test_session_finalize_contracts.py -q` | §3.4 四行与 §7 六行的行为句全部存在于 SKILL.md：permanent 失败不写 summary、用户全跳过不等于失败、summary 失败不重试不静默、PI_SESSION_FILE 缺失时出现「旅程回放降级」提示 |
| U1 | 四段可感知且脚本真实执行 | 用户实测 | 按 §9.1 前置后，在一个 ≥20 轮的真实会话执行 `/skill:session-finalize` | 先看到脚本生成的 meta 行（轮数/时长/改动文件数），再看到一句话主线 + 「是否结束」选择题；全程无「旅程回放降级」提示 |
| U2 | 已结束分支 | 用户实测 | 回答「已结束」 | permanent 走完去重/审阅，summary 写入，第 4 段列出两条笔记 ID |
| U3 | 未结束分支 | 用户实测 | 在未收尾会话回答「未结束」 | 不写 permanent；输出主线/卡点/下一步；按选择决定是否写 session |
| U4 | 幂等 | 用户实测 | 同一会话连续 finalize 两次 | 第二次命中 `session_file` 并给出更新/跳过/另建三选一；session 笔记的 `session_file` 字段等于当次 `$PI_SESSION_FILE` |
| U5 | 降级路径 | 用户实测 | `pi --no-session` 开一个不注入 `PI_SESSION_FILE` 的 ephemeral 会话（见 pi docs/sessions.md 的 `pi --no-session` 条目、docs/environment-variables.md:27）后执行 `/skill:session-finalize` | 出现「旅程回放降级：未找到会话文件」提示，主线判定与后续沉淀照常推进 |

## 10. 可测性拆分与测试边界

### A1 拆分

| 函数 | 测试用例 | 边界 |
|------|----------|------|
| `load_records` | 非法 JSON 行混在合法行中 | 返回已解析记录 + 跳过计数，不抛异常 |
| `load_records` | 缺失 / 空文件 | 返回空列表并让 `main` 以 exit 2 退出 |
| `select_active_branch` | 含被放弃分支的树 | 只保留活动链，按原文件顺序 |
| `select_active_branch` | `parentId` 断裂 | 退回全量线性扫描，`branch_fallback=true` |
| `load_turns` | user/assistant/thinking/toolResult/system/custom 混合 | 只保留 user 与 assistant 的 text+toolCall；其余不进入文本 |
| `segment_stages` | 3 个用户轮次 | 阶段数 = 3，assistant 归属前一个用户 |
| `segment_stages` | 12 个用户轮次、max=8 | 归并到 8，且合并的是最短相邻对（确定性断言） |
| `stage_summary` | write/edit/read/bash 混合 | `written_files` 去重且只含写入类；`tool_counts` 正确 |
| `render_markdown` | 超长 user 文本与命令 | 每阶段 3 条 bullet，单条 ≤120 字符 |
| `build_journey` / `main` | 固定 fixture；缺失、空、合法三种 CLI 输入 | `meta` 计数与 `stages` 结构稳定；exit 2 / 2 / 0 |

测试夹具用 `tmp_path` 内联构造，不引入大文件；不读真实 `$PI_SESSION_FILE`（不可复现）。

### A2/A3/A5 拆分

- 纯文本断言：读 `pi/session-finalize/SKILL.md`、`pi/README.md`、`CHANGELOG.md`。
- 断言项：frontmatter `name: session-finalize`；必需章节标题；`jfox-session-to-permanent` 出现在 `jfox-session-summary` 之前；`PI_SESSION_FILE`、`session_file`、降级关键词存在；§3.4 与 §7 的行为句存在（A5）；README 表格行；CHANGELOG 条目；禁止 `BANNED_LITERALS`（沿用 `test_issue_driven_contracts.py` 的常量）与本机绝对路径 `/home/elling`。

## 11. 非目标

- 不修改 `jfox-session-to-permanent` / `jfox-session-summary` / jfox CLI。
- 不自动归档、删除或合并 session 笔记。
- 不做跨 session 汇总。
- 不把 finalize 挂到 issue-driven 步 10（二期，D5）。
- 不派子 agent 做旅程回放（D3）。

## 12. 风险

| 风险 | 缓解 |
|------|------|
| 长会话 JSONL 达 MB 级 | `load_records` 逐行解析、不拼接全文；只为用户轮次与 toolCall 建结构（实测 265 条记录 / 911 KB 的会话） |
| 分叉会话（`/tree`）的历史顺序 | `select_active_branch` 按 `parentId` 只保留活动链；链断裂退回线性并在 `meta.branch_fallback` 标注 |
| `session_file` 字段在旧笔记缺失 | 退化为标题匹配；再失败则继续并提示 |
| 两个 jfox skill 的交互风格不同（question vs 直接写） | 本 skill 只做顺序编排，不统一其内部交互 |
| 用户在同一会话第二次 finalize 时主线已变 | 幂等检查在写入前，主线段每次重新判定 |
