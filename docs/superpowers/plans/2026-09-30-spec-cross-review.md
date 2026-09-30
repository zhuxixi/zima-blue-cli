# spec-cross-review（Issue #250）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `pi/spec-cross-review` skill（人工切模型 + 人工触发的会话内 spec 交叉复核），修订 `pi/github-issue-driven` 步 4 让"草稿完成 → 复核收敛 → ⏸ 用户确认"成为既定顺序，并用仓内契约测试锁住文档契约。

**Architecture:** 纯文档改动（Markdown skill + references）+ 一个 pytest 契约测试文件（stdlib + pytest，无运行时依赖）。复核状态机、模型判定、留痕模板全部写在 skill 文档里；可自动化的部分只锁"该写的写了、不该写的没写、顺序对"，语义质量由 U1 试点兜底。

**Tech Stack:** Markdown（skill 文档）、Python 3.10+ / pytest（契约测试）、uv（`uv run pytest`）。

**Spec:** `docs/superpowers/specs/2026-09-30-spec-cross-review-design.md`（worktree 内，用户已批准 2026-09-30，v4 定稿）

## Global Constraints

- 所有改动只在 worktree `$WT`（`/home/elling/work/git-repo/zima-blue-cli/.pi/worktrees/issue-250-spec-cross-review`）内；git 操作用 `git -C $WT`；**禁止碰 main checkout**。
- **不得写入具体模型名/ID**：新 skill 全部文件与 `pi/github-issue-driven/SKILL.md` 中不得出现 `deepseek-v4`、`zai-coding-cn` 等字面量；不使用形态正则（避免路径中段伪阳性）。模型来源一律表述为 `PI_PROVIDER`/`PI_MODEL` 与草稿头记录。
- **定稿字面量（逐字，不得改写）**：
  - D4 降级提示两行：
    `[spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。`
    `请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。`
  - D12 交接两行：
    `[spec-cross-review] 下一步：切到 <provider>/<model>，然后说 spec-cross-review（第 <k> 轮复核）。`
    `[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。`
  - D13 标记串：`REQUIRED SUB-SKILL: Use spec-cross-review`、`收敛后才 ⏸ 暂停等待用户确认设计`（前者必须出现在后者之前）。
- **Mode 取值**：`cross-model` / `degraded (same-model)` / `cross-model (post-hoc same-physical)`。
- **发现分级**：`真缺口` / `细化` / `核对通过`；编号 `R<轮次>-G<n>` / `R<k>-D<n>` / `R<k>-P<n>`。
- **轮次上限默认 4**（用户 2026-09-30 决定）。
- **sha256 口径**：`sha256sum <spec 绝对路径>`（文件字节流原样）；哈希**只记在轮次文件与 state 索引**，不写回被计算的文件自身。
- 测试命令：单文件 `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`；全套 `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`；lint `uv run ruff check tests/`；format `uv run black --check tests/ --line-length 100`。
- **commit-lint 陷阱**：本仓 commit-lint 钩子解析命令行原文，`git commit -m "$(cat <<'EOF' ...)"` 会被判格式非法**并回滚暂存区**。提交消息一律写成文件后用 `git commit -F <msgfile>`。
- 按文件 `git add <file>`，**禁止 `git add -A`**；commit message 用 conventional commits（英文 subject）。

## Review Focus

以下输入/条件在 spec 中被点名但没有任何自动化断言能证明其行为正确——每条都落到 Task 3 的 edge-cases 断言里（断言"文档写到了"），真实行为由 U1 观察：

1. **触发词由自然语言变体给出**（"复核 spec"）且当前会话没有 issue 上下文 → 期望：skill 要求用户给出 issue 编号，而不是猜目录。
2. **state 索引丢失或过期** → 期望：按轮次文件重建（最大轮次号 + 是否含 `## 修订摘要` 段）并回写 state，同时在 issue 评论说明重建原因。
3. **复核期间 spec 被改动**（hash 不匹配） → 期望：停下要求对齐，不审来历不明的版本。
4. **草稿无 `Drafted:` 头** → 期望：询问起草模型；答"未知"按降级执行并标注。
5. **触发后用户沉默** → 期望：skill 停在提示上，不自动降级、不继续往下走。

---

### Task 1: 结构契约测试 + `pi/spec-cross-review/SKILL.md`（验收 A1）

**Files:**
- Create: `tests/unit/test_spec_cross_review_contracts.py`
- Create: `pi/spec-cross-review/SKILL.md`

**Interfaces:**
- Consumes: 无（仓库根路径由 `Path(__file__).resolve().parents[2]` 得出，与 `tests/unit/test_cr_batch_contracts.py` 同款）。
- Produces: 模块级常量 `_REPO_ROOT` / `SKILL_DIR` / `FLOW` / `README` / `BANNED_LITERALS`；`class TestSkillStructure`；`class TestPinnedLiterals`；辅助函数 `_read(path: Path) -> str`。Task 2–6 在同一文件追加 class 并复用这些常量。

- [ ] **Step 1: 写失败测试（结构与定稿文案）**

创建 `tests/unit/test_spec_cross_review_contracts.py`：

```python
"""Contract gate for the `spec-cross-review` skill (issue #250).

These tests lock the *external contracts* of the new step-4 cross-review skill:

  1. Structure — frontmatter, required sections, references files.
  2. Pinned literals — the degrade prompt and the two handoff lines.
  3. Step-4 wiring — REQUIRED SUB-SKILL marker precedes the pause sentence.
  4. Portability — no hardcoded model literals in the touched skill docs.
  5. Report template — the fields a round report must carry.
  6. README registry — the skill table lists the new skill and cr-batch.

They assert *documentation contracts* only; semantic quality and real-session
behavior are covered by the U1 pilot (issue #250 acceptance matrix).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = _REPO_ROOT / "pi" / "spec-cross-review"
FLOW = _REPO_ROOT / "pi" / "github-issue-driven" / "SKILL.md"
README = _REPO_ROOT / "pi" / "README.md"

BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")

REQUIRED_SECTIONS = (
    "## 触发与前置",
    "## 模型判定与分流",
    "## 复核轮硬规则",
    "## 发现分级",
    "## 收敛与轮次上限",
    "## 留痕纪律",
    "## 保证边界",
)

DEGRADE_PROMPT = (
    "[spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。"
)
DEGRADE_PROMPT_2 = "请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。"

NEXT_STEP_LINE = (
    "[spec-cross-review] 下一步：切到 <provider>/<model>，然后说 spec-cross-review（第 <k> 轮复核）。"
)
CONVERGED_LINE = (
    "[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestSkillStructure:
    """A1: the skill bundle exists and carries the contracted skeleton."""

    @pytest.fixture(scope="class")
    def skill(self) -> str:
        return _read(SKILL_DIR / "SKILL.md")

    def test_skill_file_exists(self) -> None:
        assert (SKILL_DIR / "SKILL.md").is_file()

    def test_reference_files_exist(self) -> None:
        for name in ("checklist.md", "report-template.md", "edge-cases.md"):
            assert (SKILL_DIR / "references" / name).is_file(), name

    def test_frontmatter(self, skill: str) -> None:
        assert skill.startswith("---\n")
        head = skill.split("---", 2)[1]
        assert "name: spec-cross-review" in head
        assert "description:" in head
        assert len(head.split("description:", 1)[1].strip()) > 20

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_sections(self, skill: str, section: str) -> None:
        assert section in skill


class TestPinnedLiterals:
    """A1 (continued): the degrade prompt and handoff lines are verbatim."""

    @pytest.fixture(scope="class")
    def skill(self) -> str:
        return _read(SKILL_DIR / "SKILL.md")

    def test_degrade_prompt_pinned(self, skill: str) -> None:
        assert DEGRADE_PROMPT in skill
        assert DEGRADE_PROMPT_2 in skill

    def test_handoff_lines_pinned(self, skill: str) -> None:
        assert NEXT_STEP_LINE in skill
        assert CONVERGED_LINE in skill

    def test_convergence_cap_is_four(self, skill: str) -> None:
        assert "默认上限 4 轮" in skill
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: FAIL（`FileNotFoundError` / 断言失败：`pi/spec-cross-review/SKILL.md` 不存在）

- [ ] **Step 3: 写 `pi/spec-cross-review/SKILL.md`（完整正文，逐字落地）**

```markdown
---
name: spec-cross-review
description: |
  对 github-issue-driven 步 4 产出的 spec / 根因报告草稿做交叉复核：人工切换模型后人工触发，
  六个分流分支、五个复核视角、三档发现分级、收敛判定，以及四件套留痕（轮次报告 / 修订摘要 /
  state 索引 / sha256 对账）。

  Use when: 步 4 草稿完成、用户切换到异构模型后手动触发；或收到
  "[spec-cross-review] 下一步：..." 交接提示后继续复核循环。

  触发词: "spec-cross-review", "复核 spec", "spec 交叉复核"
---

# Spec Cross Review

步 4 的内嵌复核环节：起草者写完 spec / 根因报告草稿后，由**异构模型**按固定视角清单对抗性复核，
发现分级后交给起草者处置，循环至收敛（无真缺口）或轮次上限。本 skill 只审设计文档，
不碰代码 CR（步 8/9 原样）。

## 触发与前置

- 触发词：`spec-cross-review`；中文自然语言「复核 spec / spec 交叉复核」等效。
- 前置：步 4 的 spec 或根因报告草稿已落盘；草稿头部含起草记录行，格式固定为
  `Drafted: <provider>/<model> (selected) · <provider>/<model> (physical) @ <ISO8601>`
  （每次修订追加同格式的 `Revised:` 行）。
- 草稿头部缺记录行：询问用户起草模型；答「未知」则按降级执行并在报告头标注。
- 完全没有草稿文件：不执行复核，提示用户先完成步 4 草稿。
- 触发词是自然语言变体、且当前会话没有 issue 上下文时：要求用户给出 issue 编号，不猜目录。
- 留痕目录：`~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/`；轮次文件放其 `research/` 下。

## 模型判定与分流

触发时依次读取：

1. `PI_PROVIDER` / `PI_MODEL` → `selected_now`（**门禁基准**；该值在每条 bash 命令启动时重新解析，
   用户切模型后下一条命令即生效）；
2. 草稿头部的 `Drafted:` / 最近一条 `Revised:` → 起草者与上一位修订者记录的模型（selected + physical）；
3. **本轮回答产生之后**，`PI_SESSION_FILE` JSONL 中最后一条 assistant message 的 `model`
   → `physical_this_round`（只能事后读取，写入报告头作审计）。

门禁：`selected_now` 与记录里的 selected / physical **都比对**，任一相等即视为同模型（走下方降级分支）。
原因：触发时刻本轮回答尚未发生，「最后一条 assistant message」必然是**上一个模型**——用它做门禁会把
「刚切完模型就触发」这一最高频路径误判为同模型。

`physical_this_round` 不参与门禁，只作事后审计；虚拟模型（router 每请求选真身）场景下它是唯一的真身证据。
**保守优先**：`selected_now` 是虚拟模型且与记录相同时，即使 router 可能换真身，也按同模型处理。
**事后撞真身**：写报告头时若 `physical_this_round` 等于起草 / 修订记录中的任一模型，`Mode` 改记
`cross-model (post-hoc same-physical)` 并在 issue 评论说明；该轮按降级轮对待。

**k 的判定来源**：`research/spec-cross-review-state.md` 是轮次号 k 的唯一权威来源。state 缺失、过期或与
文件系统矛盾时，按 `research/spec-review-round-*.md` 重建（取最大轮次号，查该文件是否已含
`## 修订摘要` 段），重建后立即回写 state 并在 issue 评论说明原因。

六分支（触发时判一次）：

| 当前模型 | 状态（第 k 轮） | 动作 |
|---|---|---|
| ≠ 起草者 | 报告 k 不存在 | **复核**：只读 spec + 真实代码 + 仓约定，写报告 k |
| ≠ 起草者 | 报告 k 已存在，且为收敛轮 | 提示已收敛，等用户确认设计（不重开轮次） |
| ≠ 起草者 | 报告 k 已存在（未收敛） | 提示"本轮已完成，等起草者修订" |
| == 起草者 | 有报告 k、无修订摘要 k | **修订**：逐条处置发现，追加 `## 修订摘要`；收敛轮则改完直接进 ⏸ |
| == 起草者 | 有报告 k、有修订摘要 k、未收敛 | 提示切到复核模型，开第 k+1 轮 |
| == 起草者 | 有修订摘要 k、本轮回合为收敛轮 | **收尾 → ⏸**：交用户确认设计 |

**降级分支（忘切模型）**：`selected_now` 与记录的 selected / physical 任一相等（或起草者未知）时停下，
输出下面两行（定稿文案）并等待，**不自动降级、不继续**：

```
[spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。
请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。
```

只有用户明确回复「降级复核」才继续，并在报告头写 `Mode: degraded (same-model)`、在 issue 评论留痕。
降级轮强制加码对照三类材料：被引用的真实代码与测试（核到行）、仓约定文档
（AGENTS.md / CLAUDE.md / README / 既有 spec 与测试）、设计文档自身的验收矩阵与可测性拆分。

## 复核轮硬规则

- 只读：禁止修改任何文件（包括 spec）；禁止 `git add/commit/push`；只读查询（`git log/show/diff`、`gh` 读）可用。
- 每条发现必须给定位：`文件:行号` 或引用 spec 原句；给不出定位的降级为「待证」，不计入真缺口。
- 禁止引用起草时的会话记忆，必须从磁盘重读 spec、真实代码与仓约定；发现表每条都要能指向被核对的材料。
- 不得同一轮既审又改；修订只能由起草者在独立触发中执行。
- 复核期间发现 spec 的 sha256 与本轮报告头记录不一致：停下要求对齐，不审来历不明的版本。

## 发现分级

- 三档：`真缺口`（阻塞，必须修订）/ `细化`（应修订）/ `核对通过`。
- 编号：`R<轮次>-G<n>`（真缺口）/ `R<轮次>-D<n>`（细化）/ `R<轮次>-P<n>`（核对通过，可省）。
- 每条发现必须写：级别、定位、为什么是问题、建议修订、**若不复核会在实现阶段付出什么代价**。
- 五个复核视角（每轮全过，详见 `references/checklist.md`）：
  ① 验收矩阵完备性 ② 可测性拆分可实现性 + 触发时序 ③ 部署/执行路径真实性 ④ 契约与边界 ⑤ 命令与命名可追溯。

## 收敛与轮次上限

- 判定时点：每轮复核结束时。真缺口 = 0 → 该轮为收敛轮（细化项由起草者改完即进 ⏸，不再开新一轮）；
  真缺口 > 0 → 起草者修订后开下一轮。
- 默认上限 4 轮；用户可在当轮明确提高上限（记录在 state 索引与 issue 评论）。
- 到达上限仍有真缺口：停止循环，如实交用户决定（继续 / 降级接受 / 改设计），不允许自动继续或假装收敛。
- 修订处置：起草者对每条发现三选一——`接受并改` / `部分接受并说明边界` / `拒绝并给证据`
  （证据指到文件行或仓约定出处）；三种处置全部写入当轮 `## 修订摘要`。真缺口不得静默跳过；
  用户明确说跳过时，记录"用户决定跳过"及理由。

## 留痕纪律

```
~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/
├── spec.md                              # 头部：Drafted / Revised 行（模型 + 时间）
└── research/
    ├── spec-cross-review-state.md       # 一屏索引：状态 / 轮次表 / open findings / 轮次上限
    ├── spec-review-round-1.md           # 复核报告 + 修订摘要（同一文件两段，追加不覆盖）
    └── spec-review-round-2.md
```

轮次报告固定五段（模板见 `references/report-template.md`）：

1. **头**：`Round k` / `Reviewer: <selected> (selected) · <physical> (physical)` / `Drafter:` /
   `Reviewed spec sha256:` / `Mode:` / 时间戳。
2. **五视角核对表**：每个视角的结论与发现编号。
3. **发现表**：级别、定位、为什么是问题、建议修订、不复核的代价。
4. **收敛判定**：真缺口数 / 细化数 / 本轮结论 + 下一轮目标。
5. **`## 修订摘要`**（起草者追加）：逐条处置 + 改动位置。

- **写入归属**：state 索引由复核者创建/更新；起草者追加修订摘要时同步更新状态字段与新 hash。
  轮次文件第 1–4 段由复核者写，第 5 段由起草者写；两人都只追加不覆盖。
- **版本对账**：sha256 口径固定 `sha256sum <spec 绝对路径>`（文件字节流原样，UTF-8，不规范化）；
  **哈希只记在轮次文件与 state 索引里，不写回被计算的文件自身**（否则自引用，下一轮对账永不相等）。
- **issue 评论**：每轮一条（模型、轮次、真缺口/细化计数、下一步），收敛时追加一条汇总。
- **交接提示**（每轮结束输出，用户照做即可；下列两行为定稿字面量）：

```
[spec-cross-review] 下一步：切到 <provider>/<model>，然后说 spec-cross-review（第 <k> 轮复核）。
[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。
```

## 保证边界

- 无法证明「复核者真的换了模型」——只能记录会话级事实（`PI_*` + assistant message 的 `model`）并如实呈现；
  本 skill 是 Markdown 契约，不强制 agent 行为。
- 会话内复核与起草**共享对话上下文**，"异"只是模型层面；「禁引用会话记忆 + 从磁盘重读」是纪律约束，
  不是机制强制。
- 降级（同模型）轮的质量天然弱于异模型路径；降级必须留痕，不得在报告中隐去 `Mode`。

## 边界情况

见 `references/edge-cases.md`（忘切模型 / 虚拟模型 / 草稿无 Drafted 行 / 轮次上限 / 复核零发现 /
复核中 spec 被改 / hash 不匹配 / state 缺失重建 / 自然语言触发无 issue 上下文）。
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS（`-k structure` 与 `-k pinned` 相关的用例全绿；Task 2–6 的 class 尚未加入）

- [ ] **Step 5: Commit**

```bash
cd $WT
git add tests/unit/test_spec_cross_review_contracts.py pi/spec-cross-review/SKILL.md
git commit -F /tmp/t250-1.txt   # subject: feat(skill): add spec-cross-review skeleton + structure contracts (#250)
```

---

### Task 2: 报告模板 + state 索引模板（验收 A4）

**Files:**
- Create: `pi/spec-cross-review/references/report-template.md`
- Modify: `tests/unit/test_spec_cross_review_contracts.py`（追加 `class TestReportTemplate`）

**Interfaces:**
- Consumes: Task 1 的 `SKILL_DIR` / `_read`。
- Produces: `class TestReportTemplate`（`-k template`）。

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_spec_cross_review_contracts.py` 追加：

```python
class TestReportTemplate:
    """A4: the round-report / state-index template carries every field."""

    @pytest.fixture(scope="class")
    def template(self) -> str:
        return _read(SKILL_DIR / "references" / "report-template.md")

    @pytest.mark.parametrize(
        "field",
        (
            "Round k",
            "Reviewer:",
            "Drafter:",
            "Reviewed spec sha256:",
            "Mode:",
            "真缺口",
            "细化",
            "核对通过",
            "## 修订摘要",
            "当前状态",
            "Open findings",
        ),
    )
    def test_template_fields(self, template: str, field: str) -> None:
        assert field in template, field

    def test_template_pins_hash_command(self, template: str) -> None:
        assert "sha256sum" in template
        assert "不写回被计算的文件自身" in template
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k template -q`
Expected: FAIL（`references/report-template.md` 不存在）

- [ ] **Step 3: 写 `pi/spec-cross-review/references/report-template.md`**

```markdown
# 轮次报告 / state 索引模板（复制即用）

## 轮次报告 — `<issue 目录>/research/spec-review-round-<k>.md`

第 1–4 段由复核者写；第 5 段由起草者追加。两人都只追加，不覆盖。

```markdown
# spec-review round <k> — <owner>/<repo> issue #<N>

- Round: <k>
- Reviewer: `<provider>/<model>` (selected) · `<provider>/<model>` (physical)
- Drafter / 修订者: `<provider>/<model>`
- Reviewed spec sha256: `<sha256sum <spec 绝对路径> 的输出>`
- Mode: `cross-model` | `degraded (same-model)` | `cross-model (post-hoc same-physical)`
- 时间：<ISO8601>

## 五视角核对表

| # | 视角 | 结论 |
|---|---|---|
| ① | 验收矩阵完备性 | 核对通过 / 有发现（R<k>-G<n> …） |
| ② | 可测性拆分可实现性 + 触发时序 | … |
| ③ | 部署/执行路径真实性 | … |
| ④ | 契约与边界 | … |
| ⑤ | 命令与命名可追溯 | … |

## 发现表

### 真缺口（阻塞，必须修订）

**R<k>-G1 · <一句话结论>**
- 定位：`<文件:行>` 或 spec 原句
- 问题：…
- 建议：…
- 若不复核的代价：…

### 细化（应修订）

**R<k>-D1 · <一句话结论>** —— 同上四要素。

## 收敛判定

- 真缺口：<n>；细化：<n>
- 结论：<继续 / 收敛>
- 下一轮目标：…

[spec-cross-review] 下一步：切到 <provider>/<model>，然后说 spec-cross-review（第 <k> 轮复核）。

---

## 修订摘要（起草者追加）

修订者：`<provider>/<model>` (selected) · `<provider>/<model>` (physical) @ <ISO8601>
修订后 spec 新 sha256：`<hash>`（外部记录）

| 发现 | 级别 | 处置 | 改动位置 |
|---|---|---|---|
| R<k>-G1 | 真缺口 | 接受并改 / 部分接受 / 拒绝并给证据（附证据） | <章节> |
```

## state 索引 — `<issue 目录>/research/spec-cross-review-state.md`

```markdown
# spec-cross-review state — Issue #<N>

- 状态：reviewing / revising / converged / awaiting-user-confirmation / approved
- 轮次上限：4（被调整时写明调整人与依据）
- 草稿：`../spec.md`（v<k>，当前 sha256 `<hash>`）

| 轮次 | 复核者 | Mode | 真缺口 | 细化 | 结论 |
|---|---|---|---|---|---|
| 1 | <provider>/<model> | cross-model | 2 | 3 | 未收敛 → 起草者修订 |

Open findings：<编号列表或"无">

下一步：<切到哪个模型 + 触发词 + 轮次>
```

## 两条硬规则

- hash 口径固定为 `sha256sum <spec 绝对路径>`（文件字节流原样）；**哈希只记在轮次文件与 state 索引里，不写回被计算的文件自身**——否则自引用，下一轮对账永远不相等。
- 版本对账：下一轮报告头必须核到上一轮修订摘要里的新 hash；不一致则先对齐再审。
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd $WT
git add pi/spec-cross-review/references/report-template.md tests/unit/test_spec_cross_review_contracts.py
git commit -F /tmp/t250-2.txt   # subject: docs(skill): round-report + state-index templates (#250)
```

---

### Task 3: 视角清单 + 边界情况（验收 A1 文件存在性 / U1 内容兜底）

**Files:**
- Create: `pi/spec-cross-review/references/checklist.md`
- Create: `pi/spec-cross-review/references/edge-cases.md`
- Modify: `tests/unit/test_spec_cross_review_contracts.py`（追加 `class TestEdgeCaseCoverage`）

**Interfaces:**
- Consumes: Task 1 的常量与 `_read`。
- Produces: `class TestEdgeCaseCoverage`（`-k edge`），逐条锁 Review Focus 里五个场景被文档覆盖。

- [ ] **Step 1: 写失败测试**

```python
class TestEdgeCaseCoverage:
    """Review Focus: every scenario the spec names must be documented.

    These assertions prove the doc *mentions* the case; real behavior is
    covered by the U1 pilot only.
    """

    @pytest.fixture(scope="class")
    def edge(self) -> str:
        return _read(SKILL_DIR / "references" / "edge-cases.md")

    @pytest.mark.parametrize(
        "marker",
        (
            "自然语言",
            "重建",
            "hash 不匹配",
            "Drafted:",
            "降级复核",
            "轮次上限",
            "复核零发现",
        ),
    )
    def test_edge_case_documented(self, edge: str, marker: str) -> None:
        assert marker in edge, marker
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k edge -q`
Expected: FAIL（文件不存在）

- [ ] **Step 3a: 写 `pi/spec-cross-review/references/checklist.md`**

```markdown
# 复核视角清单（五个，逐条核对，不许泛读）

每个视角都要留下**定位证据**（`文件:行` 或引用原句）；给不出定位的结论降级为「待证」。

## ① 验收矩阵完备性

- 每个设计决策是否都有验收 ID？每个 ID 是否都有归属（自动化层级 + 命令，或用户实测步骤）？
- **失败分支**是否也有验收项？（实证：voice-input #29 第 1 轮拦下"失败分支无验收项"）
- 用户实测项是否写了**可执行时机**与部署前置（拉取、重启、路径指向）？

## ② 可测性拆分可实现性 + 触发时序

- 对照**真实代码**核对接缝：spec 里设计的测试能否真的构造出来？（实证：#29 第 2 轮发现按 spec 设计驱动
  `_deliver` 需伪造全局路径 + 与在跑 daemon 相撞，必须重构出两层接缝）
- spec 声称存在的函数 / 参数 / 配置项是否真实存在？不存在的是否明确标注"待新增"？
- **触发时序**：门禁或判定读取的值，在**触发时刻**是否真的可得？（实证：#250 第 1 轮 R1-G1——
  「最后一条 assistant message 的物理模型」在触发时必然是上一轮的模型，用它做门禁会误判）

## ③ 部署/执行路径真实性

- 用户实测步骤会不会跑到旧代码 / 错误路径上？（实证：#29 第 1 轮发现缺 `git pull`，
  systemd 指向主 checkout，不拉取就在旧代码上验收）
- 产物落位是否在加载路径上？（实证：#250 R1-G4——pi 包从主 checkout 加载，PR 合并前的 worktree
  改动不会被试点会话加载）

## ④ 契约与边界

- 与既有 spec / 测试 / 文档钉住的契约是否冲突？（对账 CLAUDE.md、AGENTS.md、README、既有 spec 与测试）
- 非目标是否被悄悄越过？范围是否被夹带扩张？
- 是否写出了**保证边界**（做不到的事明说，不用"应该/保证"含糊）？

## ⑤ 命令与命名可追溯

- 每条验收命令能否在仓里找到出处（README / CI / 脚本）？（实证：#29 第 3 轮发现回归命令只跑单文件，
  与 README 钉的全仓套件冲突）
- 命名是否符合仓内约定（kebab-case、skill 目录、测试文件名、commit 格式）？
```

- [ ] **Step 3b: 写 `pi/spec-cross-review/references/edge-cases.md`**

```markdown
# 边界情况与处理（触发时先查这张表）

| 情形 | 处理 |
|---|---|
| 用户忘了切模型（`selected_now` 等于记录的 selected/physical） | 输出定稿降级提示并**停下**；只有用户明确回复「降级复核」才继续 |
| 用户用**自然语言**触发（"复核 spec"）且会话里没有 issue 上下文 | 要求用户给出 issue 编号，不猜目录 |
| 草稿头缺 `Drafted:` 行（记录不完整） | 询问起草模型；答"未知"则按降级执行并在报告头标注起草者未知 |
| 虚拟模型（`PI_MODEL` 是 router） | 门禁按 `selected_now` 保守比对；`physical_this_round` 事后记录；撞真身则 `Mode` 记 `cross-model (post-hoc same-physical)` 并按降级轮对待 |
| state 索引缺失 / 过期 / 与文件系统矛盾 | 按轮次文件**重建**（最大轮次号 + 是否含 `## 修订摘要` 段），回写 state 并在 issue 评论说明 |
| spec 的 hash 不匹配（复核期间 spec 被改） | 停下要求对齐，不审来历不明的版本 |
| 复核零发现 | 仍写轮次报告（五视角逐项"核对通过"）与收敛判定；不省留痕 |
| 到达**轮次上限**（默认 4）仍有真缺口 | 停止循环，如实交用户决定（继续 / 降级接受 / 改设计），不允许自动继续或假装收敛 |
| 起草者触发时报告已存在且已收敛 | 提示已收敛，进入 ⏸ 等用户确认，不重开轮次 |
| 复核者触发时报告已存在（未收敛） | 提示本轮已完成，等起草者修订 |
| 用户要求跳过真缺口 | 允许，但必须在该轮修订摘要里记录"用户决定跳过"+ 理由 |
| 触发后用户长时间沉默 | 停在提示上，不自动降级、不继续往下走 |
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd $WT
git add pi/spec-cross-review/references/checklist.md pi/spec-cross-review/references/edge-cases.md tests/unit/test_spec_cross_review_contracts.py
git commit -F /tmp/t250-3.txt   # subject: docs(skill): review checklist + edge cases (#250)
```

---

### Task 4: `pi/github-issue-driven/SKILL.md` 步 4 修订（验收 A2）

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（步 4 段落 + 关键纪律）
- Modify: `tests/unit/test_spec_cross_review_contracts.py`（追加 `class TestFlowStep4`）

**Interfaces:**
- Consumes: 常量 `FLOW`、`_read`。
- Produces: `class TestFlowStep4`（`-k flow`）。

- [ ] **Step 1: 写失败测试**

```python
class TestFlowStep4:
    """A2: step 4 must gate on the cross-review before the ⏸ pause."""

    @pytest.fixture(scope="class")
    def flow(self) -> str:
        return _read(FLOW)

    def test_required_sub_skill_marker(self, flow: str) -> None:
        assert "REQUIRED SUB-SKILL: Use spec-cross-review" in flow

    def test_marker_precedes_pause_sentence(self, flow: str) -> None:
        before = flow.index("REQUIRED SUB-SKILL: Use spec-cross-review")
        after = flow.index("收敛后才 ⏸ 暂停等待用户确认设计")
        assert before < after

    def test_drafted_header_requirement(self, flow: str) -> None:
        assert "Drafted:" in flow
        assert "Revised:" in flow
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k flow -q`
Expected: FAIL（标记串不存在）

- [ ] **Step 3: 修订步 4**

在 `pi/github-issue-driven/SKILL.md` 步 4 的「**⏸ spec 完成后暂停，等用户确认设计再继续。**」一句处，
替换为下面这段（其余内容不动；验收分层与可测性拆分两条要求原样保留）：

```markdown
   **REQUIRED SUB-SKILL: Use spec-cross-review**——spec / 根因报告草稿完成后先执行交叉复核，
   **收敛后才 ⏸ 暂停等待用户确认设计**。交接方式：
   - 草稿头部必须写 `Drafted: <provider>/<model> (selected) · <provider>/<model> (physical) @ <ISO8601>`；
     每次修订追加同格式的 `Revised:` 行。
   - 草稿完成后输出交接指令（切到异构模型 + 触发 `spec-cross-review`），由用户手动切换模型后手动触发；
     复核循环为「异模型复核 → 起草者修订 → 再审」，**收敛（无真缺口）或到达轮次上限（默认 4）**为止。
   - 复核留痕在 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/research/`，
     轮次结论评论回 issue；收敛后才进入本步的 ⏸。
```

同时在「关键纪律」列表末尾追加一条：

```markdown
- **spec 草稿的模型记录不得省略**（`Drafted:` / `Revised:` 行）：异模型判据依赖它，缺了只能按降级复核。
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd $WT
git add pi/github-issue-driven/SKILL.md tests/unit/test_spec_cross_review_contracts.py
git commit -F /tmp/t250-4.txt   # subject: docs(skill): gate step 4 on spec-cross-review convergence (#250)
```

---

### Task 5: 禁硬编码模型守卫（验收 A3）

**Files:**
- Modify: `tests/unit/test_spec_cross_review_contracts.py`（追加 `class TestNoHardcodedModels`）

**Interfaces:**
- Consumes: `SKILL_DIR`、`FLOW`、`BANNED_LITERALS`、`_read`。
- Produces: `class TestNoHardcodedModels`（`-k no_hardcoded`）。

- [ ] **Step 1: 写测试**

```python
class TestNoHardcodedModels:
    """A3: skill docs must not name concrete models (deployment policy).

    Portable by design: a literal blacklist (same style as
    test_cr_batch_contracts.py::test_docs_no_hardcoded_deepseek_models),
    no shape regex (paths like tests/unit/x.py would false-positive),
    and no machine-private config (§250 R1-G3 / R2-D3).
    """

    def _docs(self) -> list[tuple[str, str]]:
        docs: list[tuple[str, str]] = [("github-issue-driven/SKILL.md", _read(FLOW))]
        for path in sorted(SKILL_DIR.rglob("*.md")):
            docs.append((str(path.relative_to(_REPO_ROOT)), _read(path)))
        return docs

    @pytest.mark.parametrize("literal", BANNED_LITERALS)
    def test_no_banned_literal(self, literal: str) -> None:
        for name, text in self._docs():
            assert literal not in text, f"{literal!r} found in {name}"

    def test_no_machine_private_config_reference(self) -> None:
        for name, text in self._docs():
            assert "~/.pi/agent/settings.json" not in text, name
```

- [ ] **Step 2: 运行测试**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k no_hardcoded -q`
Expected: PASS（Task 1–4 的文档按 Global Constraints 写作即已合规；若 FAIL，把违规字面量改写为
`PI_PROVIDER`/`PI_MODEL` 或"部署侧配置"表述后重跑）

- [ ] **Step 3: Commit**

```bash
cd $WT
git add tests/unit/test_spec_cross_review_contracts.py
git commit -F /tmp/t250-5.txt   # subject: test(skill): portable no-hardcoded-model guard (#250)
```

---

### Task 6: `pi/README.md` 技能表补录（验收 A6）

**Files:**
- Modify: `pi/README.md`（技能列表）
- Modify: `tests/unit/test_spec_cross_review_contracts.py`（追加 `class TestReadmeTable`）

**Interfaces:**
- Consumes: `README`、`_read`。
- Produces: `class TestReadmeTable`（`-k readme`）。

- [ ] **Step 1: 写失败测试**

```python
class TestReadmeTable:
    """A6: the pi package README registers both skills."""

    @pytest.fixture(scope="class")
    def readme(self) -> str:
        return _read(README)

    @pytest.mark.parametrize("skill", ("spec-cross-review", "github-code-review-batch"))
    def test_skill_row_present(self, readme: str, skill: str) -> None:
        rows = [line for line in readme.splitlines() if line.startswith("|") and skill in line]
        assert rows, f"no table row for {skill}"
        cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
        assert len(cells) >= 3
        assert all(cells[1:3]), f"empty role/step cell for {skill}"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k readme -q`
Expected: FAIL（`github-code-review-batch` 无行；`spec-cross-review` 无行）

- [ ] **Step 3: 补两行**

在 `pi/README.md` 的技能表末尾追加（保持三列结构）：

```markdown
| `spec-cross-review` | 设计文档交叉复核（人工切模型多轮，收敛后才交用户确认） | 步 4 |
| `github-code-review-batch` | 批量/调度式代码审查（CR 执行，多 Agent 并行 + issue 验证） | 步 8-9 |
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd $WT
git add pi/README.md tests/unit/test_spec_cross_review_contracts.py
git commit -F /tmp/t250-6.txt   # subject: docs(pi): register spec-cross-review and cr-batch in README (#250)
```

---

### Task 7: CHANGELOG 记录 + 全仓回归（验收 A5）

**Files:**
- Modify: `CHANGELOG.md`（`## [Unreleased]` 段追加条目）

**Interfaces:**
- Consumes: 前序任务的最终文档形态。
- Produces: 无（收口任务）。

- [ ] **Step 1: 追加 CHANGELOG 条目**

在 `CHANGELOG.md` 的 `## [Unreleased]` 段下（若无 `### Features`，则新建该子标题）写入：

```markdown
### Features

- **skill**: new `spec-cross-review` — step-4 design-doc cross-review (manual model switch, five
  lenses, three-tier findings, convergence gate before user confirmation) (#250)
```

- [ ] **Step 2: lint + format**

Run: `uv run ruff check tests/ && uv run black --check tests/ --line-length 100`
Expected: 无输出（通过）；若 format 失败运行 `uv run black tests/ --line-length 100` 后重跑

- [ ] **Step 3: 全仓回归（A5）**

Run: `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
Expected: 全绿，覆盖率 ≥ 60%

- [ ] **Step 4: 新契约测试单独复核**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -v`
Expected: 全绿；输出中可见 `structure` / `pinned` / `template` / `edge` / `flow` / `no_hardcoded` / `readme` 各组

- [ ] **Step 5: Commit**

```bash
cd $WT
git add CHANGELOG.md
git commit -F /tmp/t250-7.txt   # subject: docs(changelog): record spec-cross-review skill (#250)
```

---

### Task 8: U1 试点（post-implementation manual verification，验收 U1）

**Files:**
- 无仓库文件改动；产物落 `~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-244/research/` 与 issue #244 评论

**Interfaces:**
- Consumes: 已合并到 main 的 `pi/spec-cross-review`（打包路径加载）。
- Produces: U1 证据（两轮以上复核报告 + 修订摘要 + state 索引 + issue 评论）。

- [ ] **Step 1: 前置检查（必须满足才执行，否则标记 pending）**

- [ ] 本 PR 已合并回 `main`
- [ ] 主 checkout 已 `git pull`（`git -C /home/elling/work/git-repo/zima-blue-cli log --oneline -1` 含本 PR 的 merge commit）
- [ ] 当前会话从**主 checkout** 发起（不是 worktree），`pi/spec-cross-review/SKILL.md` 可从包路径读到

**若任一不满足：U1 标记 `pending`，不得宣称验收通过。**

- [ ] **Step 2: 对 #244 走完整循环**

- [ ] 按 github-issue-driven 步 3 调研 #244，步 4 起草 spec（草稿头部写 `Drafted:` 行）
- [ ] 切到异构模型 → 触发 `spec-cross-review` → 第 1 轮复核
- [ ] 切回起草模型 → 触发 → 逐条处置 + 追加修订摘要
- [ ] 若第 1 轮有真缺口 → 切回复核模型再审（预期 ≥2 轮）
- [ ] 收敛后进 ⏸ → 用户确认设计

- [ ] **Step 3: 记录观察结果**

- [ ] `research/spec-review-round-1.md`、`-2.md`（若有多轮）与 `spec-cross-review-state.md` 齐全
- [ ] 每轮报告头的 Reviewer/Drafter 模型确实不同（异模型）
- [ ] 各轮 sha256 对账通过（无"审的版本与改的版本错位"）
- [ ] **至少拦下 1 个会被带进实现的真缺口**（记录是哪一条、若不复核的代价）
- [ ] issue #244 每轮评论齐全
- [ ] 结论写回 #250：U1 通过 / pending（附原因）

---

## 验收对账表（plan ↔ spec 双向追溯）

| spec 验收 ID | 承载 task | 验证命令 / 步骤 |
|---|---|---|
| A1 结构 + 定稿文案 | Task 1（+ Task 3 文件存在性） | `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k "structure or pinned" -v` |
| A2 步 4 落位与顺序 | Task 4 | 同上 `-k flow` |
| A3 禁硬编码模型 | Task 5 | 同上 `-k no_hardcoded` |
| A4 报告/state 模板字段 | Task 2 | 同上 `-k template` |
| A5 全仓不回归 | Task 7 | `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60` |
| A6 README 两行 | Task 6 | 同上 `-k readme` |
| U1 真实流程试点 | Task 8（post-merge 人工） | 按 Task 8 步骤；不满足前置则标 `pending` |

**spec 交付物 → task 反查**：`pi/spec-cross-review/{SKILL.md,references/*}` → Task 1/2/3；
`pi/github-issue-driven/SKILL.md` → Task 4；`pi/README.md` → Task 6；
`tests/unit/test_spec_cross_review_contracts.py` → Task 1/2/3/4/5/6；
`CHANGELOG.md` → Task 7；spec 落位（`docs/superpowers/specs/…-design.md`）→ worktree 首个 commit（已完成，`c5adc86`）。
