# Gate Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `github-issue-driven` 流程加「启动时一次性授权」——用户给一次档位（`stepwise` / `design-only` / `auto`），步 4 设计 gate 与步 9 push/开 PR gate 按档位自动放行，授权落盘可跨 session 查证。

**Architecture:** 纯文档契约改动 + 一份新的文档契约测试。新机制写在 `pi/github-issue-driven/SKILL.md` 的新节里（三档表 + 授权记录 schema + gate 判定四步 + 授权来源 + 失败处理 + 优先级条款）；步 4/步 9/关键纪律三处改写指向该节；`pi/zima-pr-monitor/SKILL.md` 合并句加档位限定；`pi/spec-cross-review/SKILL.md` 两处无 pin 的 ⏸ 表述加档位限定。可自动化验证全部落在 `tests/unit/test_issue_driven_contracts.py`：纯函数断言（`str -> None`）+ 单一只读 IO 边界 + mutation 负控。

**Tech Stack:** Python 3.10+ / pytest；Markdown 文档契约；`uv run pytest`。

**Spec:** `docs/superpowers/specs/2026-10-16-gate-authorization-design.md`（issue #258）

## Global Constraints

- 只改文档与新增测试文件；**不改动** `tests/unit/test_spec_cross_review_contracts.py` 与 `tests/unit/test_cr_batch_contracts.py`（spec A4）。
- `pi/github-issue-driven/SKILL.md` 必须保留既有 pinned 子串「收敛后才 ⏸ 暂停等待用户确认设计」，且 `REQUIRED SUB-SKILL: Use spec-cross-review` 仍出现在它之前（spec C2）。
- `pi/spec-cross-review/SKILL.md:64` 的 pinned 收敛行与 `references/report-template.md` 的 PROGRESS/CONVERGED 行**不得改动**（spec C8）。
- 文档中不得出现具体模型名字面量（`BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")`，沿用既有先例）。
- 档位令牌一律反引号包裹（`` `auto` ``），避免与文中已有的 `automated E2E` 子串碰撞（spec A5 / R2-D2）。
- 合并停顿只限 `auto` / `design-only` 两档；`stepwise` 档行为与现状逐字一致（spec G3 / C5）。
- 全部编辑路径以 `$WT` 开头；`$WT = /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-258-gate-authorization`。
- 测试命令在 `$WT` 下跑：`uv run pytest tests/unit/test_issue_driven_contracts.py -q`。

---

### Task 1: 授权节骨架 + 三档表（spec C1(a)、A1、A5）

**Files:**
- Create: `tests/unit/test_issue_driven_contracts.py`
- Modify: `pi/github-issue-driven/SKILL.md`（新增节，置于「## 关键纪律」之前）

**Interfaces:**
- Consumes: 无
- Produces: `load_skill_texts(repo_root: Path = _REPO_ROOT) -> dict[str, str]`；`assert_three_tiers(text: str) -> None`；常量 `TIERS = ("stepwise", "design-only", "auto")`、`BANNED_LITERALS`、`FLOW` / `MONITOR` / `CROSS` 路径常量

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_issue_driven_contracts.py`：

```python
"""Contract gate for the one-shot gate authorization mechanism (issue #258).

These tests lock the *documentation contracts* of the tiered authorization
feature: three tiers, the gate branching rules, the authorization record
schema, the failure branches, and the precedence clause that resolves the
pinned spec-cross-review convergence line.

They assert documentation contracts only; runtime behaviour is covered by the
U1/U2 pilots (issue #258 acceptance matrix).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
FLOW = _REPO_ROOT / "pi" / "github-issue-driven" / "SKILL.md"
MONITOR = _REPO_ROOT / "pi" / "zima-pr-monitor" / "SKILL.md"
CROSS = _REPO_ROOT / "pi" / "spec-cross-review" / "SKILL.md"

TIERS = ("stepwise", "design-only", "auto")
BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")


def load_skill_texts(repo_root: Path = _REPO_ROOT) -> dict[str, str]:
    """Read every document this contract spans. Sole IO boundary."""
    paths = {
        "github-issue-driven/SKILL.md": repo_root / "pi" / "github-issue-driven" / "SKILL.md",
        "zima-pr-monitor/SKILL.md": repo_root / "pi" / "zima-pr-monitor" / "SKILL.md",
        "spec-cross-review/SKILL.md": repo_root / "pi" / "spec-cross-review" / "SKILL.md",
    }
    texts: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            pytest.fail(f"missing contract document: {path}")
        texts[name] = path.read_text(encoding="utf-8")
    return texts


def assert_three_tiers(text: str) -> None:
    """Three tier tokens exist and each is anchored in a tier-table row.

    Backtick anchoring is deliberate: the document already contains
    ``automated E2E`` (a bare ``auto`` substring), so a raw substring match
    would pass even after the tier table is deleted.
    """
    assert "| 档位 |" in text, "tier table header missing"
    for tier in TIERS:
        token = f"`{tier}`"
        if token not in text:
            raise AssertionError(f"tier token not documented: {token}")
        rows = [
            line
            for line in text.splitlines()
            if line.startswith("|") and token in line
        ]
        if not rows:
            raise AssertionError(f"tier token {token} is not in a table row")
    default_row = [line for line in text.splitlines() if "`stepwise`" in line]
    assert default_row, "`stepwise` tier row missing"


class TestThreeTiers:
    @pytest.fixture(scope="class")
    def flow(self) -> str:
        return load_skill_texts()["github-issue-driven/SKILL.md"]

    def test_three_tiers_documented(self, flow: str) -> None:
        assert_three_tiers(flow)

    def test_loader_fails_loudly_on_missing_document(self, tmp_path: Path) -> None:
        with pytest.raises(BaseException, match="missing contract document"):
            load_skill_texts(tmp_path)

    def test_mutation_deleting_tier_row_breaks_assertion(self) -> None:
        flow = load_skill_texts()["github-issue-driven/SKILL.md"]
        mutated = "\n".join(
            line for line in flow.splitlines() if "`auto`" not in line
        )
        assert "automated E2E" in mutated, "mutation must keep the collision source"
        with pytest.raises(AssertionError):
            assert_three_tiers(mutated)

    def test_mutation_deleting_table_header_breaks_assertion(self) -> None:
        flow = load_skill_texts()["github-issue-driven/SKILL.md"]
        mutated = flow.replace("| 档位 |", "| 档位X |")
        with pytest.raises(AssertionError):
            assert_three_tiers(mutated)

    def test_mutation_backtick_stripped_tier_is_not_matched(self) -> None:
        flow = load_skill_texts()["github-issue-driven/SKILL.md"]
        mutated = flow.replace("`stepwise`", "stepwise")
        with pytest.raises(AssertionError):
            assert_three_tiers(mutated)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: FAIL —— 4 个用例失败（`tier table header missing` / 缺 `stepwise` 令牌等），`test_loader_fails_loudly_on_missing_document` 通过。

- [ ] **Step 3: 写最小实现（文档新增节的第一块）**

在 `pi/github-issue-driven/SKILL.md` 的「## 关键纪律」**之前**插入：

```markdown
## 授权与档位（步 4 / 步 9 的许可闸门）

用户在会话里给出**一次**明确授权，流程就按档位放行；授权落盘后可跨 session / 跨 harness 查证。

| 档位 | 标识 | step 4 设计 gate | step 9 push/开 PR gate | 覆盖动作 | 上限 |
|---|---|---|---|---|---|
| 逐步确认（默认） | `stepwise` | ⏸ 停 | 🚪 停 | 无（每次都要许可） | 与现状一致（含合并步骤不变） |
| 设计后停一次 | `design-only` | ⏸ 停 | 自动 | push、开 PR、打 `zima:needs-review`、修复重推 | 到「可合并判定」（合并前停） |
| 全自动 | `auto` | 不停 | 自动 | 同上 | 到「可合并判定」（合并前停） |

- `stepwise` 是默认值，也是**任何异常情况的兜底值**：授权文件缺失、档位值非法、文件不可读 → 一律按 `stepwise`（fail-closed）。
- 两档自动档的差别只在步 4 是否暂停；步 9 之后的行为完全一致。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
cd $WT
git add tests/unit/test_issue_driven_contracts.py pi/github-issue-driven/SKILL.md
git commit -m "test(skill): pin three-tier authorization table (issue #258)"
```

---

### Task 2: 授权记录 schema + gate 判定 + 授权来源 + 失败处理 + 优先级条款（spec C1(b)–(f)、A1、A2）

**Files:**
- Modify: `tests/unit/test_issue_driven_contracts.py`
- Modify: `pi/github-issue-driven/SKILL.md`（续写新增节）

**Interfaces:**
- Consumes: `load_skill_texts()`、`assert_three_tiers()`（Task 1）
- Produces: `assert_gate_branching(text) -> None`、`assert_authorization_schema(text) -> None`、`assert_failure_branches(text) -> None`、`assert_precedence_clause(text) -> None`、`assert_authorization_discipline(text) -> None`

- [ ] **Step 1: 写失败测试**（追加到测试文件，函数定义放在 `assert_three_tiers` 之后）

```python
def assert_gate_branching(text: str) -> None:
    """Gate decision rules + the audit marker + prose (non-question) confirmation."""
    assert "[auth] gate=" in text, "audit marker missing"
    for fragment in ("读本 issue 的 `authorization.md`", "**不停**", "暂停等许可", "落盘"):
        if fragment not in text:
            raise AssertionError(f"gate branching fragment missing: {fragment}")
    for fragment in ("散文", "不默认弹结构化 `question`"):
        if fragment not in text:
            raise AssertionError(f"confirmation-style fragment missing: {fragment}")


def assert_authorization_schema(text: str) -> None:
    """Record path template, schema keys, and the lifecycle rules."""
    assert "~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/authorization.md" in text, (
        "authorization record path missing"
    )
    for key in (
        "Gate:",
        "Granted-by-user-quote:",
        "Granted-at:",
        "Session:",
        "Scope:",
        "Merge: requires-explicit-user-approval",
    ):
        if key not in text:
            raise AssertionError(f"authorization schema key missing: {key}")
    for fragment in ("文件不存在 = 未授权", "Amended-at:", "视为 `stepwise`"):
        if fragment not in text:
            raise AssertionError(f"lifecycle rule missing: {fragment}")


def assert_failure_branches(text: str) -> None:
    """The three failure branches that guard against silent authorization."""
    for fragment in (
        "issue 号与当前 issue 不一致",
        "停下报告",
        "非交互宿主",
    ):
        if fragment not in text:
            raise AssertionError(f"failure branch missing: {fragment}")


def assert_precedence_clause(text: str) -> None:
    """Tier rules outrank every ⏸ statement inside spec-cross-review."""
    for fragment in (
        "唯一权威",
        "`pi/spec-cross-review/SKILL.md`",
        ":16",
        ":62",
        ":64",
        ":86",
        "edge-cases.md:19",
        "进度提示",
    ):
        if fragment not in text:
            raise AssertionError(f"precedence clause fragment missing: {fragment}")


def assert_authorization_discipline(text: str) -> None:
    """The 关键纪律 entry: authorization must be written down to count."""
    for fragment in ("授权落盘", "口头授权不落盘等于没有授权"):
        if fragment not in text:
            raise AssertionError(f"discipline entry missing: {fragment}")


class TestGateRules:
    @pytest.fixture(scope="class")
    def flow(self) -> str:
        return load_skill_texts()["github-issue-driven/SKILL.md"]

    def test_gate_branching_documented(self, flow: str) -> None:
        assert_gate_branching(flow)

    def test_authorization_schema_documented(self, flow: str) -> None:
        assert_authorization_schema(flow)

    def test_failure_branches_documented(self, flow: str) -> None:
        assert_failure_branches(flow)

    def test_precedence_clause_documented(self, flow: str) -> None:
        assert_precedence_clause(flow)

    def test_mutation_dropping_schema_key_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("Merge: requires-explicit-user-approval", "Merge: auto")
        with pytest.raises(AssertionError):
            assert_authorization_schema(mutated)

    def test_mutation_dropping_audit_marker_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("[auth] gate=", "")
        with pytest.raises(AssertionError):
            assert_gate_branching(mutated)

    def test_mutation_dropping_failure_branch_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("停下报告", "继续")
        with pytest.raises(AssertionError):
            assert_failure_branches(mutated)

    def test_mutation_dropping_precedence_scope_breaks_assertion(self, flow: str) -> None:
        mutated = flow.replace("edge-cases.md:19", "")
        with pytest.raises(AssertionError):
            assert_precedence_clause(mutated)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: FAIL —— 新增 8 个用例失败（缺 `[auth] gate=`、缺授权路径、缺失败分支等）。

- [ ] **Step 3: 写实现（续写新增节）**

在 Task 1 已插入内容的末尾（即新节内）追加：

```markdown
### 授权记录

路径（与 research/spec 同目录纪律，跨 harness 共读，不清理）：

```
~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/authorization.md
```

字段（固定键名，便于 grep 与契约测试）：

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

1. **文件不存在 = 未授权** = `stepwise`。
2. 用户中途改口径（例：「停下等我」）→ 覆写 `Gate:` 行并追加 `Amended-at:` + 原话，不删除文件。
3. 档位值不在 `{stepwise, design-only, auto}` 内 → 视为 `stepwise`，并在报告中提示档位非法。
4. 读取时校验路径中的 `<owner>/<repo>/issue-<N>`；**issue 号与当前 issue 不一致**时视为未授权（不跨 issue 复用）。
5. 该文件随 issue 目录留档，流程结束后不清理。

### gate 判定（步 4 / 步 9 共用）

1. 读本 issue 的 `authorization.md`（按上节规则 1/3/4 归一化档位）。
2. 本步骤被该档位覆盖 → **不停**，直接执行；报告（含每条 issue 评论）首行标注依据：`[auth] gate=<档位> · 依据 <授权文件绝对路径>`。
3. 未被覆盖 → 按现行方式**暂停等许可**。
4. 用户给出的任何许可都要**落盘**（新建或更新 `authorization.md`）：让「每次都要问」收敛为「只问一次」；口头许可不落盘 = 下次仍会问。

### 授权从哪来

- 起手已说明（如「全自动跑完 #N」）→ 直接落盘对应档位，不再发问。
- 否则在第一次 gate 触发时按**散文**风格问一次：「本次流程的授权档位？逐步确认（默认）/ 设计后停一次 / 全自动（合并前仍停）」。
- **不默认弹结构化 `question`** 工具（项目确认风格为散文；非交互 session 下 `question` 返回 error）。

### 失败处理

| 情形 | 行为 |
|---|---|
| 授权目录不存在 / 不可写 | 尝试 `mkdir -p`；仍失败则**停下报告**，不得以「我记得被授权了」继续 |
| 档位值非法 / 文件不可读 | 视为 `stepwise`（fail-closed） |
| **非交互宿主**（PJob 等） | 无用户在场时必须预先落盘授权文件，否则按 `stepwise` 暂停——非交互下不做隐式授权 |

### 与 spec-cross-review 收敛提示的关系（判定优先级）

**档位判定以本节为唯一权威**；`pi/spec-cross-review/SKILL.md` 内的 ⏸ / 「待用户确认设计」表述一律视为**进度提示**，不构成独立暂停指令。覆盖范围：`:16`、`:62`、`:64`（pinned 收敛行，不改写）、`:86`，外加 `references/edge-cases.md:19`；其中 `:62` / `:86` 已按档位限定改写。`auto` 档照常输出收敛行，随后不停顿、直接进入步 5，并输出 `[auth] gate=auto · 依据 <路径>`。
```

在「## 关键纪律」末尾追加一条：

```markdown
- **授权落盘**：任何许可（起手授权或临时许可）都要写进 `authorization.md`，执行时在报告首行注明依据路径；**口头授权不落盘等于没有授权**。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: PASS（13 passed）

- [ ] **Step 5: 提交**

```bash
cd $WT
git add tests/unit/test_issue_driven_contracts.py pi/github-issue-driven/SKILL.md
git commit -m "feat(skill): document gate authorization record, branching and failure rules (issue #258)"
```

---

### Task 3: 步 4 / 步 9 改写 + 既有契约回归（spec C2、C3、C8、A2、A4）

**Files:**
- Modify: `pi/github-issue-driven/SKILL.md`（步 4 `:22`/`:29`、步 9）
- Modify: `pi/spec-cross-review/SKILL.md`（`:62`、`:86`）
- Modify: `tests/unit/test_issue_driven_contracts.py`

**Interfaces:**
- Consumes: Task 1/2 的断言函数
- Produces: `assert_step4_pause_substring_preserved(text) -> None`、`assert_step9_gate_tier_qualified(text) -> None`

- [ ] **Step 1: 写失败测试**（追加）

```python
def assert_step4_pause_substring_preserved(text: str) -> None:
    """The pinned step-4 pause sentence survives, still after the cross-review marker."""
    marker = "REQUIRED SUB-SKILL: Use spec-cross-review"
    pinned = "收敛后才 ⏸ 暂停等待用户确认设计"
    if marker not in text or pinned not in text:
        raise AssertionError("pinned step-4 strings missing")
    if text.index(marker) > text.index(pinned):
        raise AssertionError("cross-review marker no longer precedes the pause sentence")


def assert_step9_gate_tier_qualified(text: str) -> None:
    """Step 9 keeps both the pause fallback and the tier-qualified phrasing."""
    for fragment in ("按授权档位判定", "未授权 = 暂停等许可", "zima:needs-review", "前台阻塞等待"):
        if fragment not in text:
            raise AssertionError(f"step-9 fragment missing: {fragment}")


class TestStepWiring:
    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        return load_skill_texts()

    def test_step4_pinned_substring_preserved(self, texts: dict[str, str]) -> None:
        assert_step4_pause_substring_preserved(texts["github-issue-driven/SKILL.md"])

    def test_step9_gate_tier_qualified(self, texts: dict[str, str]) -> None:
        assert_step9_gate_tier_qualified(texts["github-issue-driven/SKILL.md"])

    def test_step4_no_unconditional_pause_left(self, texts: dict[str, str]) -> None:
        flow = texts["github-issue-driven/SKILL.md"]
        assert "收敛后才进入本步的 ⏸。" not in flow

    def test_cross_review_pause_lines_are_tier_qualified(self, texts: dict[str, str]) -> None:
        cross = texts["spec-cross-review/SKILL.md"]
        assert "收敛后输出并进入 ⏸（`auto` 档不停" in cross
        assert "细化项改完即进 ⏸（`auto` 档不停" in cross

    def test_cross_review_pinned_lines_untouched(self, texts: dict[str, str]) -> None:
        cross = texts["spec-cross-review/SKILL.md"]
        assert "[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。" in cross

    def test_mutation_stripping_step9_pause_breaks_assertion(self, texts: dict[str, str]) -> None:
        mutated = texts["github-issue-driven/SKILL.md"].replace("未授权 = 暂停等许可", "未授权 = 继续")
        with pytest.raises(AssertionError):
            assert_step9_gate_tier_qualified(mutated)

    def test_mutation_reordering_pinned_strings_breaks_assertion(self, texts: dict[str, str]) -> None:
        flow = texts["github-issue-driven/SKILL.md"]
        marker = "REQUIRED SUB-SKILL: Use spec-cross-review"
        pinned = "收敛后才 ⏸ 暂停等待用户确认设计"
        start = flow.index(marker)
        end = flow.index(pinned) + len(pinned)
        reordered = flow[:start] + flow[end:] + flow[start:end]
        with pytest.raises(AssertionError):
            assert_step4_pause_substring_preserved(reordered)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: FAIL —— 步 9 缺「按授权档位判定」、`spec-cross-review` 两行未加限定、`:29` 无条件句仍在。

- [ ] **Step 3: 写实现**

`pi/github-issue-driven/SKILL.md` 步 4（`:22` 行所在句）改为：

```markdown
   **收敛后按授权档位决定是否 ⏸——未授权时与现行一致：收敛后才 ⏸ 暂停等待用户确认设计；已授权 `auto` 则直接进入步 5（见「授权与档位」节，含优先级条款）。** 交接方式：
```

同段 `:29` 行改为：

```markdown
     轮次结论评论回 issue；收敛后按档位进入本步的 ⏸（`auto` 档直接进入步 5）。
```

步 9 首句改为（其余原样保留）：

```markdown
9. **PR + Zima 单 Bot CR + 前台阻塞等待** → **REQUIRED SUB-SKILL: Use zima-pr-monitor**（**🚪 push/开 PR 前按授权档位判定（见「授权与档位」节；未授权 = 暂停等许可，用户 AGENTS.md 硬规则不变）**；开 PR、打 `zima:needs-review`、**同 turn 立即前台阻塞等待 CR job 完成（禁止结束 turn，helper 见 zima-pr-monitor）**、解析 review meta（`cc-cr-meta` / `pi-cr-meta` 前缀区分；`kimi-cr-meta` 忽略）、worktree 修、重打标签、收敛判定、合并）。**zima 缺席降级**：…（原样）
```

`pi/spec-cross-review/SKILL.md`：

- `:62` → `5. 收敛后输出并进入 ⏸（`auto` 档不停，见 github-issue-driven「授权与档位」节）：`
- `:86` → `- 判定时点：每轮复核回收后。真缺口 = 0 → 收敛轮（细化项改完即进 ⏸（`auto` 档不停）；> 0 → 修订后开下一轮。`

（`:64` pinned 收敛行、`references/report-template.md`、`references/edge-cases.md` 一律不动。）

- [ ] **Step 4: 跑新旧测试确认全绿**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py tests/unit/test_spec_cross_review_contracts.py tests/unit/test_cr_batch_contracts.py -q`
Expected: PASS（新增 20 passed；两个既有契约文件全绿）

- [ ] **Step 5: 提交**

```bash
cd $WT
git add pi/github-issue-driven/SKILL.md pi/spec-cross-review/SKILL.md tests/unit/test_issue_driven_contracts.py
git commit -m "feat(skill): tier-qualify step 4/9 gates and cross-review pause lines (issue #258)"
```

---

### Task 4: 合并闸门按档位限定（spec C5、A3）

**Files:**
- Modify: `pi/zima-pr-monitor/SKILL.md`（「## 每轮」的合并环节）
- Modify: `tests/unit/test_issue_driven_contracts.py`

**Interfaces:**
- Consumes: `load_skill_texts()`
- Produces: `assert_merge_scoped_to_auto_tiers(flow: str, monitor: str) -> None`

- [ ] **Step 1: 写失败测试**（追加）

```python
def assert_merge_scoped_to_auto_tiers(flow: str, monitor: str) -> None:
    """The merge pause is scoped to auto tiers; stepwise keeps today's behaviour."""
    assert "`auto` / `design-only`" in monitor, "merge pause is not tier-scoped"
    assert "gh pr merge" in monitor, "merge command documentation missing"
    assert "`stepwise`" in monitor, "stepwise carve-out missing from monitor skill"
    assert "Merge: requires-explicit-user-approval" in flow


class TestMergeGate:
    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        return load_skill_texts()

    def test_merge_pause_scoped_to_auto_tiers(self, texts: dict[str, str]) -> None:
        assert_merge_scoped_to_auto_tiers(
            texts["github-issue-driven/SKILL.md"], texts["zima-pr-monitor/SKILL.md"]
        )

    def test_monitor_keeps_existing_merge_semantics(self, texts: dict[str, str]) -> None:
        monitor = texts["zima-pr-monitor/SKILL.md"]
        assert "`gh pr merge <N> --squash --delete-branch`" in monitor

    def test_mutation_inverting_scope_breaks_assertion(self, texts: dict[str, str]) -> None:
        flow = texts["github-issue-driven/SKILL.md"]
        monitor = texts["zima-pr-monitor/SKILL.md"].replace("`auto` / `design-only`", "`stepwise`")
        with pytest.raises(AssertionError):
            assert_merge_scoped_to_auto_tiers(flow, monitor)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: FAIL —— `merge pause is not tier-scoped`

- [ ] **Step 3: 写实现**

`pi/zima-pr-monitor/SKILL.md` 的「## 每轮」决策树中，合并语句所在行改为：

```markdown
满足 → `gh pr merge <N> --squash --delete-branch`。**档位限定**：授权档位为 `auto` / `design-only` 时，合并前需用户明确许可（两档授权的上限是「可合并判定」）；`stepwise` 档行为不变——收敛 + CI 全绿即合并。
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: PASS（23 passed）

- [ ] **Step 5: 提交**

```bash
cd $WT
git add pi/zima-pr-monitor/SKILL.md tests/unit/test_issue_driven_contracts.py
git commit -m "feat(skill): scope the merge pause to auto tiers (issue #258)"
```

---

### Task 5: 禁写字面量收口 + CHANGELOG + 全量验收对账（spec C7、A1–A5）

**Files:**
- Modify: `tests/unit/test_issue_driven_contracts.py`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: 全部前述断言
- Produces: 无（收尾任务）

- [ ] **Step 1: 写失败测试**（追加）

```python
class TestPortability:
    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        return load_skill_texts()

    @pytest.mark.parametrize("literal", BANNED_LITERALS)
    def test_no_hardcoded_banned_literal(self, texts: dict[str, str], literal: str) -> None:
        for name, text in texts.items():
            assert literal not in text, f"{literal!r} found in {name}"

    def test_mutation_injecting_banned_literal_breaks_assertion(self, texts: dict[str, str]) -> None:
        mutated = texts["github-issue-driven/SKILL.md"] + "\nmodel: zai-coding-cn/glm-5.3\n"
        with pytest.raises(AssertionError):
            for literal in BANNED_LITERALS:
                assert literal not in mutated, f"{literal!r} found in mutated text"
```

- [ ] **Step 2: 跑测试确认通过（本任务不改文档，新断言应直接绿）**

Run: `cd $WT && uv run pytest tests/unit/test_issue_driven_contracts.py -q`
Expected: PASS（26 passed）

- [ ] **Step 3: 更新 CHANGELOG**

在 `CHANGELOG.md` 的 `[Unreleased]` 节追加一条（沿用该节既有条目格式）：

```markdown
### Added

- **skill**: `github-issue-driven` 支持启动时一次性授权（`stepwise` / `design-only` / `auto` 三档）——授权落盘 `authorization.md`，step 4 设计 gate 与 step 9 push/开 PR gate 按档位放行；`auto` 两档合并前仍停一次（issue #258）
```

- [ ] **Step 4: 全量验收对账（A1–A5）**

Run（逐条记录实际输出，作为 PR 验收证据）：

```bash
cd $WT
uv run pytest tests/unit/test_issue_driven_contracts.py -q                  # A1/A2/A3/A5
uv run pytest tests/unit/test_spec_cross_review_contracts.py tests/unit/test_cr_batch_contracts.py -q   # A4
git diff --name-only main..HEAD                                             # A4 证明：既有契约文件未被修改
uv run ruff check tests/                                                      # 风格门禁
uv run black --check tests/unit/test_issue_driven_contracts.py --line-length 100
```

Expected: 全部通过；`git diff --name-only main..HEAD` 中**不含** `tests/unit/test_spec_cross_review_contracts.py` 与 `tests/unit/test_cr_batch_contracts.py`。

- [ ] **Step 5: 提交**

```bash
cd $WT
git add CHANGELOG.md tests/unit/test_issue_driven_contracts.py
git commit -m "docs(changelog): note tiered gate authorization (issue #258)"
```

---

## 验收归属映射（spec §5 的落地版）

| spec 验收 | 归属任务 | 验证命令 |
|---|---|---|
| A1 | Task 1（三档）+ Task 2（其余五块） | `uv run pytest tests/unit/test_issue_driven_contracts.py -q` |
| A2 | Task 2（默认档/schema）+ Task 3（步 4/步 9） | 同上 + `test_spec_cross_review_contracts.py` |
| A3 | Task 4 | 同上 |
| A4 | Task 3 Step 4 + Task 5 Step 4 | 既有两个契约测试文件全绿且未被改动 |
| A5 | Task 1/2/3/4/5 各自的 mutation 用例 | 同上 |
| U1 / U2 | **不在本 PR 内**（合并后试点，spec 已标 `pending`） | post-merge 手工执行 |
