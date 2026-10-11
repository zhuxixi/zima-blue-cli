# spec-cross-review 自动化（Issue #254）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 spec-cross-review 从「人工切模型 + 人工触发」改造成「preflight 门禁 + 派发 fresh-context spec-reviewer subagent + 父 session 全自动逐轮编排至收敛」。

**Architecture:** 新增包级 agent profile `pi/agents/spec-reviewer.md`（fresh context、tools 无 write/edit、无 model 字段），`package.json` 通过 `pi.subagents.agents` 注册；`pi/spec-cross-review/` 的 SKILL.md 重写为 preflight + 编排契约；新增 `references/dispatch-contract.md` 作为任务模板与 outputSchema 的单一定义源；父是唯一写者（child 只返回结构化输出）。契约测试锁定全部文档契约。

**Tech Stack:** Markdown 契约 + pi-subagents 包级 agent 目录 + pytest（stdlib only，文档契约断言）。

## Global Constraints

- 工作区：`WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-254-spec-cross-review-automation`；所有编辑路径以 `$WT` 开头，git 操作用 `git -C $WT`；**禁碰主 checkout**。
- 测试依赖：首个任务先 `cd $WT && uv sync`（worktree 需要自己的 .venv）。
- 包内文档（`pi/spec-cross-review/**`、`pi/agents/**`、`pi/github-issue-driven/SKILL.md`）**禁写模型字面量**（`BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")`）与 `~/.pi/` 字面量。
- profile **不得含 `model` 字段**——模型由部署侧 `subagents.agentOverrides.spec-reviewer.model` 提供。
- commit 格式 `type(scope): description`；commit message 用英文。
- spec 验收矩阵：S1/A1–A10/U1/U2，每个 task 必须引用验收 ID（见文末对账表）。

## Review Focus

- 进度行与收敛行是**定稿字面量**（A5 断言原样命中），写 SKILL.md 时一个字符都不能改。
- 降级提示两行沿用 #250 D4 定稿字面量，同样逐字保留。
- `dispatch-contract.md` 的任务模板占位符与 outputSchema 字段名是 A4 断言对象，命名必须与本 plan 完全一致。

## S1 证据（已完成，免 spike）

pi-subagents `0.76.1` 发布代码 `src/agents/agents.js`：

- `extractSubagentPathsFromPackageRoot`（L237-268）：依次读取 package.json 的顶层 `"pi-subagents"` 与 `"pi".subagents` 两个 root，对任一 root 取 `root.agents` 字符串数组，resolve 成 agent 目录（相对 packageRoot）。
- 调用点 L379：包发现的标准路径。**两种 manifest 形式均受支持**；本 plan 用 `pi.subagents.agents`（与现有 `pi.skills` 同层）。
- 残余风险：本地路径包（settings 的 `packages: ["<repo>"]`）是否同样进入该发现路径，未实机验证——折进 U1（合并后 `{action:"models", agent:"spec-reviewer"}` 必须能解析）。**fallback**：改顶层 `"pi-subagents": {"agents": ["./pi/agents"]}`；再不行改用 `subagents.agentScanDirs` 部署文档。

---

### Task 1: 契约测试全量重写（failing）+ package.json 注册 + spec-reviewer profile（S1 / A1 / A2 / A3）

**Files:**
- Test: `$WT/tests/unit/test_spec_cross_review_contracts.py`（整体重写）
- Create: `$WT/pi/agents/spec-reviewer.md`
- Modify: `$WT/package.json`

**Interfaces:**
- Produces: 测试常量 `PROGRESS_LINE` / `CONVERGED_LINE` / `DEGRADE_PROMPT`（Task 3 的 SKILL.md 必须逐字命中）；路径常量 `PROFILE` / `DISPATCH` / `AGENTS_DIR`（后续 task 的测试共用）。

- [ ] **Step 1: 准备 worktree 依赖**

```bash
cd $WT && uv sync
```

- [ ] **Step 2: 全量重写测试文件（failing）**

`$WT/tests/unit/test_spec_cross_review_contracts.py` 完整内容：

```python
"""Contract gate for the automated `spec-cross-review` skill (issue #254).

These tests lock the *external contracts* of the dispatched cross-review loop:

  1. Profile — `pi/agents/spec-reviewer.md` frontmatter (fresh context, no
     write/edit tools, no model field).
  2. Package registration — `pi.subagents.agents` exposes the agent dir.
  3. Dispatch contract — task-template placeholders + outputSchema fields.
  4. Skill orchestration — required sections + pinned literals.
  5. Report template — round-report / state-index fields, new Mode enum,
     verbatim JSON appendix.
  6. Edge cases — every failure branch the spec names.
  7. Step-4 wiring — auto-entry documented, markers ordered, Drafted kept.
  8. Portability — no hardcoded model literals or machine-private config.
  9. README registry — skill row updated, profile mentioned.

They assert *documentation contracts* only; real-session behavior is covered
by the U1/U2 pilots (issue #254 acceptance matrix).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = _REPO_ROOT / "pi" / "spec-cross-review"
AGENTS_DIR = _REPO_ROOT / "pi" / "agents"
FLOW = _REPO_ROOT / "pi" / "github-issue-driven" / "SKILL.md"
README = _REPO_ROOT / "pi" / "README.md"
PACKAGE_JSON = _REPO_ROOT / "package.json"

PROFILE = AGENTS_DIR / "spec-reviewer.md"
DISPATCH = SKILL_DIR / "references" / "dispatch-contract.md"

BANNED_LITERALS = ("deepseek-v4", "zai-coding-cn")

REQUIRED_SECTIONS = (
    "## 触发与前置",
    "## Preflight 门禁",
    "## 每轮编排",
    "## 写入归属",
    "## 发现分级",
    "## 收敛与轮次上限",
    "## 降级",
    "## 失败处理",
    "## 留痕纪律",
    "## 保证边界",
    "## 部署前置",
)

DEGRADE_PROMPT = "[spec-cross-review] 当前模型 <provider>/<model> 与起草/修订记录相同（记录：<provider>/<model>）。"
DEGRADE_PROMPT_2 = "请切到异构模型后重新触发；若确定用当前模型降级复核，请明确回复「降级复核」。"

PROGRESS_LINE = "[spec-cross-review] 第 <k> 轮完成：复核者 <effective-model> (fresh)，真缺口 <N>、细化 <M>，报告 <绝对路径>。"
CONVERGED_LINE = (
    "[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestProfileContract:
    """A1: the spec-reviewer agent profile carries the contracted frontmatter."""

    @pytest.fixture(scope="class")
    def profile(self) -> str:
        return _read(PROFILE)

    def test_profile_file_exists(self) -> None:
        assert PROFILE.is_file()

    def test_frontmatter_fields(self, profile: str) -> None:
        assert profile.startswith("---\n")
        head = profile.split("---", 2)[1]
        assert "name: spec-reviewer" in head
        assert "description:" in head
        assert "defaultContext: fresh" in head
        assert "inheritProjectContext: true" in head
        assert "inheritSkills: false" in head
        assert "systemPromptMode: replace" in head
        assert "thinking:" in head

    def test_no_model_field(self, profile: str) -> None:
        head = profile.split("---", 2)[1]
        assert "model:" not in head

    def test_tools_have_no_write_or_edit(self, profile: str) -> None:
        head = profile.split("---", 2)[1]
        tools_line = next(line for line in head.splitlines() if line.startswith("tools:"))
        tools = {item.strip() for item in tools_line.split(":", 1)[1].split(",")}
        assert "write" not in tools
        assert "edit" not in tools
        assert "bash" in tools  # sha256 对账与只读 git/gh 查询需要


class TestPackageRegistration:
    """A2: package.json exposes the agent directory to pi-subagents."""

    def test_pi_subagents_agents(self) -> None:
        pkg = json.loads(_read(PACKAGE_JSON))
        agents = pkg["pi"]["subagents"]["agents"]
        assert "./pi/agents" in agents


class TestDispatchContract:
    """A4: dispatch contract pins task template, variables and outputSchema."""

    @pytest.fixture(scope="class")
    def doc(self) -> str:
        return _read(DISPATCH)

    def test_file_exists(self) -> None:
        assert DISPATCH.is_file()

    @pytest.mark.parametrize(
        "placeholder",
        (
            "<REPO_ABS_PATH>",
            "<ROUND_K>",
            "<ISSUE_N>",
            "<SPEC_ABS_PATH>",
            "<EXPECTED_SHA256>",
            "<PREV_OPEN_FINDINGS>",
            "<CHECKLIST_CONTENT>",
        ),
    )
    def test_task_template_placeholders(self, doc: str, placeholder: str) -> None:
        assert placeholder in doc

    @pytest.mark.parametrize(
        "field",
        (
            "round",
            "reviewedSha256",
            "lenses",
            "findings",
            "counts",
            "convergence",
            "gaps",
            "details",
            "passes",
            "id",
            "level",
            "location",
            "why",
            "suggestion",
            "costIfSkipped",
        ),
    )
    def test_output_schema_fields(self, doc: str, field: str) -> None:
        assert f'"{field}"' in doc

    def test_finding_levels(self, doc: str) -> None:
        assert "真缺口" in doc
        assert "细化" in doc
        assert "核对通过" in doc

    def test_checklist_single_source(self, doc: str) -> None:
        # 五视角清单的单一定义源是 references/checklist.md，由父读盘后注入。
        assert "references/checklist.md" in doc


class TestSkillStructure:
    """A5: the rewritten SKILL.md carries the orchestration contract."""

    @pytest.fixture(scope="class")
    def skill(self) -> str:
        return _read(SKILL_DIR / "SKILL.md")

    def test_skill_file_exists(self) -> None:
        assert (SKILL_DIR / "SKILL.md").is_file()

    def test_frontmatter(self, skill: str) -> None:
        assert skill.startswith("---\n")
        head = skill.split("---", 2)[1]
        assert "name: spec-cross-review" in head
        assert "description:" in head

    @pytest.mark.parametrize("section", REQUIRED_SECTIONS)
    def test_required_sections(self, skill: str, section: str) -> None:
        assert section in skill


class TestPinnedLiterals:
    """A5 (continued): progress lines, degrade prompt and preflight markers."""

    @pytest.fixture(scope="class")
    def skill(self) -> str:
        return _read(SKILL_DIR / "SKILL.md")

    def test_progress_line_pinned(self, skill: str) -> None:
        assert PROGRESS_LINE in skill

    def test_converged_line_pinned(self, skill: str) -> None:
        assert CONVERGED_LINE in skill

    def test_degrade_prompt_pinned(self, skill: str) -> None:
        assert DEGRADE_PROMPT in skill
        assert DEGRADE_PROMPT_2 in skill

    def test_convergence_cap_is_four(self, skill: str) -> None:
        assert "默认上限 4 轮" in skill

    def test_preflight_markers(self, skill: str) -> None:
        assert "spec-reviewer" in skill
        assert "fail-closed" in skill
        assert "agentOverrides" in skill


class TestReportTemplate:
    """A6: the round-report / state-index template carries every field."""

    @pytest.fixture(scope="class")
    def template(self) -> str:
        return _read(SKILL_DIR / "references" / "report-template.md")

    def test_template_file_exists(self) -> None:
        assert (SKILL_DIR / "references" / "report-template.md").is_file()

    @pytest.mark.parametrize(
        "field",
        (
            "Round k",
            "Reviewer: spec-reviewer",
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

    def test_template_pins_mode_enum(self, template: str) -> None:
        assert "`cross-model (preflight verified)`" in template
        assert "`cross-model (post-hoc same-physical)`" in template
        assert "`degraded (same-model, user-confirmed)`" in template

    def test_template_has_verbatim_json_appendix(self, template: str) -> None:
        assert "verbatim" in template

    def test_template_pins_progress_lines(self, template: str) -> None:
        assert PROGRESS_LINE in template
        assert CONVERGED_LINE in template


class TestEdgeCaseCoverage:
    """A7: every failure branch the spec names must be documented."""

    def test_checklist_file_exists(self) -> None:
        assert (SKILL_DIR / "references" / "checklist.md").is_file()

    def test_edge_cases_file_exists(self) -> None:
        assert (SKILL_DIR / "references" / "edge-cases.md").is_file()

    @pytest.fixture(scope="class")
    def edge(self) -> str:
        return _read(SKILL_DIR / "references" / "edge-cases.md")

    @pytest.mark.parametrize(
        "marker",
        (
            "fail-closed",
            "未注册",
            "modelScope",
            "超时",
            "schema",
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


class TestFlowStep4:
    """A8: step 4 gates on the automated cross-review before the ⏸ pause."""

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

    def test_auto_entry_documented(self, flow: str) -> None:
        assert "自动进入" in flow


class TestNoHardcodedModels:
    """A3: skill docs and the agent profile must not name concrete models.

    Portable by design: a literal blacklist, no shape regex, and no
    machine-private config reference (same style as #250 R2-D3).
    """

    def _docs(self) -> list[tuple[str, str]]:
        docs: list[tuple[str, str]] = [("github-issue-driven/SKILL.md", _read(FLOW))]
        for path in sorted(SKILL_DIR.rglob("*.md")):
            docs.append((str(path.relative_to(_REPO_ROOT)), _read(path)))
        for path in sorted(AGENTS_DIR.rglob("*.md")):
            docs.append((str(path.relative_to(_REPO_ROOT)), _read(path)))
        return docs

    @pytest.mark.parametrize("literal", BANNED_LITERALS)
    def test_no_hardcoded_banned_literal(self, literal: str) -> None:
        for name, text in self._docs():
            assert literal not in text, f"{literal!r} found in {name}"

    def test_no_hardcoded_machine_private_config_reference(self) -> None:
        for name, text in self._docs():
            assert "~/.pi/" not in text, name


class TestReadmeTable:
    """A9: the pi package README registers the skill and mentions the profile."""

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

    def test_spec_reviewer_profile_mentioned(self, readme: str) -> None:
        assert "spec-reviewer" in readme
```

- [ ] **Step 3: 跑测试确认 failing**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -x -q`
Expected: FAIL——首个失败是 `TestDispatchContract`（`dispatch-contract.md` 尚不存在，属预期；A4–A9 断言随后续 task 逐个转绿）

- [ ] **Step 4: 新建 profile**

`$WT/pi/agents/spec-reviewer.md` 完整内容：

```markdown
---
name: spec-reviewer
description: Adversarial cross-reviewer for step-4 spec / root-cause drafts (fresh context, read-only)
tools: read, grep, find, ls, bash
defaultContext: fresh
inheritProjectContext: true
inheritSkills: false
systemPromptMode: replace
thinking: high
---

You are the spec-reviewer: an adversarial cross-reviewer for step-4 design
documents (spec / root-cause drafts).

Your only job is to review the draft named by the dispatch task against five
lenses and return the structured report the task defines. You are read-only:
your tool allowlist has no write or edit capability, and you must not modify
any file — including the spec itself.

Working rules:

- Read the spec, the real code it cites, and the repo conventions
  (AGENTS.md / CLAUDE.md / README / existing specs and tests) from disk.
  Never rely on conversation memory; the dispatch task is your only brief.
- Before reviewing, verify `sha256sum <spec path>` matches the hash in the
  dispatch task. On mismatch, stop and report the mismatch instead of
  reviewing.
- Five lenses, all of them, every round — no skimming:
  1. Acceptance-matrix completeness: every design decision has an acceptance
     ID with an owner; failure branches have acceptance items too; user-test
     items state executable timing and deployment prerequisites.
  2. Testability-split feasibility + trigger timing: verify against real code
     that the seams the spec designs can actually be constructed, and that
     any value a gate reads exists at trigger time.
  3. Deployment/execution-path truth: user-test steps must not run against
     stale code or wrong paths (pull / restart / path targets).
  4. Contracts and boundaries: conflicts with contracts pinned by existing
     specs, tests, and docs; non-goals silently crossed; guarantee
     boundaries stated honestly.
  5. Command and naming traceability: every acceptance command has a source
     in the repo (README / CI / scripts); naming follows repo conventions.
- Findings are graded: `gap` (blocking, must fix) / `detail` (should fix) /
  `pass`. Every finding needs a location (`file:line` or a quoted spec
  sentence). A finding without a location is unproven and does not count as
  a gap.
- Use bash only for read-only queries (git log/show/diff, gh reads,
  sha256sum). Never mutate anything.
- Return only the structured report the dispatch task defines. Do not write
  files, do not spawn children, do not post comments. Evidence beats
  opinion; keep prose tight.
```

- [ ] **Step 5: package.json 注册**

`$WT/package.json` 的 `pi` 块改为（其余字段不动）：

```json
  "pi": {
    "skills": ["./pi"],
    "subagents": { "agents": ["./pi/agents"] }
  }
```

- [ ] **Step 6: 跑测试确认 A1/A2/A3 变绿**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -q -k "Profile or Package or Hardcoded"`
Expected: PASS（其余用例仍 failing，留给后续 task）

- [ ] **Step 7: Commit**

```bash
git -C $WT add pi/agents/spec-reviewer.md package.json tests/unit/test_spec_cross_review_contracts.py
git -C $WT commit -m "feat(skill): spec-reviewer agent profile + package agent-dir registration (#254)

- new pi/agents/spec-reviewer.md (fresh context, read-only tools, no model field)
- package.json pi.subagents.agents registers ./pi/agents (pi-subagents 0.76.1
  parses both pi.subagents.agents and top-level pi-subagents.agents, see
  src/agents/agents.js extractSubagentPathsFromPackageRoot)
- contract tests fully rewritten for the dispatched loop (A1/A2 green; A4-A9
  assertions land with their tasks)"
```

---

### Task 2: 派发契约 `dispatch-contract.md`（A4）

**Files:**
- Create: `$WT/pi/spec-cross-review/references/dispatch-contract.md`
- Test: `$WT/tests/unit/test_spec_cross_review_contracts.py`（Task 1 已含断言）

**Interfaces:**
- Consumes: Task 1 的 `DISPATCH` 路径常量与占位符清单。
- Produces: 任务模板与 outputSchema——Task 3 的 SKILL.md「每轮编排」按此渲染任务；U1 的父 session 按此派发。

- [ ] **Step 1: 写 dispatch-contract.md**

`$WT/pi/spec-cross-review/references/dispatch-contract.md` 完整内容：

````markdown
# 派发契约 — spec-reviewer（任务模板 + outputSchema）

父 session（起草者）每轮按本文档渲染任务并派发 `spec-reviewer`；child 只返回结构化输出，
不写文件。五视角清单的单一定义源是 `references/checklist.md`——父读盘后原样注入
`<CHECKLIST_CONTENT>`，禁止在任何其他文件里复制第二份全文。

## 任务模板（渲染后作为 subagent 的 task 传入）

```text
你是 spec-reviewer。仓库：<REPO_ABS_PATH>（cwd 已设好）。本轮是第 <ROUND_K> 轮复核。

被审对象：<SPEC_ABS_PATH>（issue #<ISSUE_N> 的步 4 spec / 根因报告草稿）。
派发方计算的 sha256：<EXPECTED_SHA256>——先用 `sha256sum <SPEC_ABS_PATH>` 核对，
不一致则停止复核，只回报 hash 不一致。

上一轮 open findings（本轮必须逐条核对是否已被修订）：<PREV_OPEN_FINDINGS>
（第 1 轮为「无」）。

五视角清单（逐条核对，每条结论都要能指向被核对材料）：
<CHECKLIST_CONTENT>

硬规则：
- 只读：禁止修改任何文件（你的 tools 也没有写权限）；bash 只用于只读查询
  （git log/show/diff、gh 读、sha256sum）。
- 禁止引用任何对话记忆，只信磁盘上的材料。
- 每条发现必须给定位（文件:行号 或 spec 原句）；给不出定位的发现按「待证」处理，
  不计入真缺口。
- 发现编号：R<ROUND_K>-G<n>（真缺口）/ R<ROUND_K>-D<n>（细化）/ R<ROUND_K>-P<n>（核对通过，可省）。
- 每条发现写清：为什么是问题、建议修订、若不复核会在实现阶段付出什么代价。
- 只返回结构化报告，不写文件、不派下级、不发评论。
```

## 注入变量（父负责渲染）

| 占位符 | 来源 |
|---|---|
| `<REPO_ABS_PATH>` | 目标仓库绝对路径（同时作为 subagent 的 cwd） |
| `<ROUND_K>` | `spec-cross-review-state.md`（轮次 k 的唯一权威来源） |
| `<ISSUE_N>` | issue 编号 |
| `<SPEC_ABS_PATH>` | `<issue 目录>/spec.md` 绝对路径 |
| `<EXPECTED_SHA256>` | 父侧 `sha256sum <SPEC_ABS_PATH>` 的输出 |
| `<PREV_OPEN_FINDINGS>` | state 的 Open findings（编号 + 一句话）；第 1 轮填「无」 |
| `<CHECKLIST_CONTENT>` | `references/checklist.md` 全文（父读盘后原样注入） |

## outputSchema（父在派发时传入）

```js
const outputSchema = {
  type: "object",
  required: ["round", "reviewedSha256", "lenses", "findings", "counts", "convergence"],
  properties: {
    round: { type: "integer", minimum: 1 },
    reviewedSha256: { type: "string" },
    lenses: {
      type: "array", minItems: 5, maxItems: 5,
      items: {
        type: "object",
        required: ["lens", "verdict", "findingIds"],
        properties: {
          lens: { enum: ["验收矩阵完备性", "可测性拆分可实现性 + 触发时序", "部署/执行路径真实性", "契约与边界", "命令与命名可追溯"] },
          verdict: { enum: ["核对通过", "有发现"] },
          findingIds: { type: "array", items: { type: "string" } }
        }
      }
    },
    findings: {
      type: "array",
      items: {
        type: "object",
        required: ["id", "level", "location", "why", "suggestion", "costIfSkipped"],
        properties: {
          id: { type: "string" },
          level: { enum: ["真缺口", "细化", "核对通过"] },
          location: { type: "string" },
          why: { type: "string" },
          suggestion: { type: "string" },
          costIfSkipped: { type: "string" }
        }
      }
    },
    counts: {
      type: "object",
      required: ["gaps", "details", "passes"],
      properties: {
        gaps: { type: "integer", minimum: 0 },
        details: { type: "integer", minimum: 0 },
        passes: { type: "integer", minimum: 0 }
      }
    },
    convergence: {
      type: "object",
      required: ["converged", "summary"],
      properties: {
        converged: { type: "boolean" },
        summary: { type: "string" }
      }
    }
  }
};
```

## 回报处置（父）

- `structuredOutput` 缺失或不合 schema → 按「派发失败」处理（见 SKILL.md 失败处理）。
- `reviewedSha256` 必须与父派发时的 `EXPECTED_SHA256` 一致；不一致按 hash 不匹配处理。
- 父据结构化输出写轮次报告第 1–4 段、末尾附 verbatim JSON、更新 state、发 issue 评论。
- `Mode` 由父判定（preflight 结果 + 事后撞真身检查），不由 child 填。
````

- [ ] **Step 2: 跑测试确认 A4 变绿**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -q -k "DispatchContract"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git -C $WT add pi/spec-cross-review/references/dispatch-contract.md
git -C $WT commit -m "docs(skill): dispatch contract — task template + outputSchema (#254)

Single source of truth for the review task: parent renders variables and
injects the five-lens checklist from references/checklist.md; child returns
structured output only (no write tools)."
```

---

### Task 3: SKILL.md 重写为 preflight + 编排契约（A5）

**Files:**
- Modify: `$WT/pi/spec-cross-review/SKILL.md`（整体重写）
- Test: `$WT/tests/unit/test_spec_cross_review_contracts.py`（Task 1 已含断言）

**Interfaces:**
- Consumes: Task 1 的 `PROGRESS_LINE` / `CONVERGED_LINE` / `DEGRADE_PROMPT` 字面量；Task 2 的 dispatch 契约。
- Produces: U1 父 session 执行的编排契约。

- [ ] **Step 1: 整体重写 SKILL.md**

`$WT/pi/spec-cross-review/SKILL.md` 完整内容：

```markdown
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
4. 异构 → 输出一行 preflight 结论（起草模型 / 评审模型 / 异构确认 / 轮次上限 4 /
   每轮 1 个 fresh-context child），进入循环。
5. 事后审计：每轮报告头记录 child run 的 `model`（来自 run 产物）与主会话该轮 physical
   （`PI_SESSION_FILE` JSONL 最后一条 assistant message 的 `model`）。撞真身则 `Mode` 记
   `cross-model (post-hoc same-physical)`，该轮按降级轮对待。

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
- state 是轮次 k 的唯一权威来源；缺失/矛盾时按轮次文件重建并回写（见边界情况）。
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

## 边界情况

见 `references/edge-cases.md`。
```

- [ ] **Step 2: 跑测试确认 A5 变绿**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -q -k "SkillStructure or PinnedLiterals"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git -C $WT add pi/spec-cross-review/SKILL.md
git -C $WT commit -m "feat(skill): rewrite spec-cross-review as dispatched auto-converge loop (#254)

Manual model-switching and manual triggers are replaced by a one-shot
preflight model gate (fail-closed) and a parent-orchestrated round loop;
the parent is the sole writer of all traces."
```

---

### Task 4: 报告模板 + 边界情况两份 references（A6 / A7）

**Files:**
- Modify: `$WT/pi/spec-cross-review/references/report-template.md`（整体重写）
- Modify: `$WT/pi/spec-cross-review/references/edge-cases.md`（整体重写）
- Test: `$WT/tests/unit/test_spec_cross_review_contracts.py`（Task 1 已含断言）

**Interfaces:**
- Consumes: Task 1 的字面量常量与新 Mode 枚举。
- Produces: U1 父 session 写留痕的模板。

- [ ] **Step 1: 重写 report-template.md**

`$WT/pi/spec-cross-review/references/report-template.md` 完整内容：

`````markdown
# 轮次报告 / state 索引模板（复制即用）

## 轮次报告 — `<issue 目录>/research/spec-review-round-<k>.md`

全部由父写入：第 1–4 段据 child 结构化输出渲染，第 5 段为父的修订摘要，末尾附
child 结构化输出的 verbatim JSON。

````markdown
# spec-review round <k> — <owner>/<repo> issue #<N>

- Round k: <k>
- Reviewer: spec-reviewer `<effective-model>` (selected) · `<run-model>` (physical from run artifact) (fresh context)
- Drafter: `<provider>/<model>`
- Reviewed spec sha256: `<sha256sum <spec 绝对路径> 的输出>`
- Mode: `cross-model (preflight verified)` | `cross-model (post-hoc same-physical)` | `degraded (same-model, user-confirmed)`
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

每轮结束输出（进度行，不停下）：

[spec-cross-review] 第 <k> 轮完成：复核者 <effective-model> (fresh)，真缺口 <N>、细化 <M>，报告 <绝对路径>。

收敛时输出：

[spec-cross-review] 收敛：第 <k> 轮无真缺口。待用户确认设计后进入步 5（worktree）。

---

## 修订摘要（父追加）

修订者：`<provider>/<model>` (selected) · `<provider>/<model>` (physical) @ <ISO8601>
修订后 spec 新 sha256：`<hash>`（外部记录）

| 发现 | 级别 | 处置 | 改动位置 |
|---|---|---|---|
| R<k>-G1 | 真缺口 | 接受并改 / 部分接受 / 拒绝并给证据（附证据） | <章节> |

---

## 复核者结构化输出（verbatim JSON，父原样附上，供对账正文）

```json
<child 的 structuredOutput 原样>
```
````

## state 索引 — `<issue 目录>/research/spec-cross-review-state.md`

```markdown
# spec-cross-review state — Issue #<N>

- 当前状态：reviewing / revising / converged / awaiting-user-confirmation / approved
- 轮次上限：4（被调整时写明调整人与依据）
- 草稿：`../spec.md`（v<k>，当前 sha256 `<hash>`）

| 轮次 | 复核者 | Mode | 真缺口 | 细化 | 结论 |
|---|---|---|---|---|---|
| 1 | spec-reviewer (<effective-model>) | cross-model (preflight verified) | 2 | 3 | 未收敛 → 起草者修订 |

Open findings：<编号列表或"无">

每轮成本：tokens <n> / 时长 <s>（U1 回收数据时填）
```

## 两条硬规则

- hash 口径固定为 `sha256sum <spec 绝对路径>`（文件字节流原样）；**哈希只记在轮次文件与 state 索引里，不写回被计算的文件自身**——否则自引用，下一轮对账永远不相等。
- 版本对账：下一轮派发前父必须核到上一轮修订摘要里的新 hash；不一致则先对齐再审。
`````

- [ ] **Step 2: 重写 edge-cases.md**

`$WT/pi/spec-cross-review/references/edge-cases.md` 完整内容：

```markdown
# 边界情况与处理（触发时先查这张表）

| 情形 | 处理 |
|---|---|
| preflight 同构（评审者 effective model 等于起草记录的 selected/physical） | **fail-closed**：不进循环，输出部署指引；只有用户改完配置重新触发才继续 |
| `spec-reviewer` 未注册 / `{action:"models"}` 无法解析 | preflight 报错，给出 package.json 注册指引，不进循环 |
| `modelScope` 拒绝（preflight 或运行期） | 停循环，输出报错形态与当前 allow 实况，交用户处置 |
| 草稿头缺 `Drafted:` 行 | 询问起草模型；答「未知」则停在 preflight 前（门禁无法执行），不自动降级 |
| 用户用**自然语言**触发且会话里没有 issue 上下文 | 要求用户给出 issue 编号，不猜目录 |
| state 索引缺失 / 过期 / 与文件系统矛盾 | 按轮次文件**重建**（最大轮次号 + 是否含 `## 修订摘要` 段），回写 state 并在 issue 评论说明 |
| spec 的 hash 不匹配（child 复核不一致，或父回收时与派发时不一致） | 停下要求对齐，不审来历不明的版本 |
| 派发失败 / **超时** / 结构化输出缺失或不合 schema | 停循环 + 留痕 + 报错；不静默重派（防重复扣费），由用户决定重试 |
| 复核零发现 | 仍写轮次报告（五视角逐项「核对通过」）与收敛判定；不省留痕 |
| 到达**轮次上限**（默认 4）仍有真缺口 | 停止循环，如实交用户决定（继续 / 降级接受 / 改设计），不允许自动继续或假装收敛 |
| 用户要求跳过真缺口 | 允许，但必须在该轮修订摘要里记录「用户决定跳过」+ 理由 |
| 用户显式要求同模型**降级复核** | 停在派发前，输出定稿降级提示；仅在明确回复「降级复核」后，同会话按降级轮执行并在报告头标注 |
| 虚拟模型（`PI_MODEL` 是 router） | preflight 按 selected 保守比对；child run 的 model 与主会话 physical 事后记录；撞真身则 `Mode` 记 `cross-model (post-hoc same-physical)` 并按降级轮对待 |
| 报告 / state / 评论写入失败 | 停循环、报错、不重派 |
```

- [ ] **Step 3: 跑测试确认 A6/A7 变绿**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -q -k "ReportTemplate or EdgeCase"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git -C $WT add pi/spec-cross-review/references/report-template.md pi/spec-cross-review/references/edge-cases.md
git -C $WT commit -m "docs(skill): update report template and edge cases for dispatched loop (#254)

New Mode enum, verbatim JSON appendix, progress-line literals; edge cases
now cover preflight fail-closed, unregistered agent, modelScope refusal,
dispatch failure/timeout, and schema violations."
```

---

### Task 5: github-issue-driven 步 4 + README（A8 / A9）

**Files:**
- Modify: `$WT/pi/github-issue-driven/SKILL.md`（步 4 交接方式三行）
- Modify: `$WT/pi/README.md`（技能表 + 前置依赖）
- Test: `$WT/tests/unit/test_spec_cross_review_contracts.py`（Task 1 已含断言）

**Interfaces:**
- Consumes: 无新接口；标记串 `REQUIRED SUB-SKILL: Use spec-cross-review` 与 `收敛后才 ⏸ 暂停等待用户确认设计` 必须保留且顺序不变。

- [ ] **Step 1: 改步 4 交接方式**

`$WT/pi/github-issue-driven/SKILL.md` 步 4 中，把这段：

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

改为：

```markdown
   **REQUIRED SUB-SKILL: Use spec-cross-review**——spec / 根因报告草稿完成后先执行交叉复核，
   **收敛后才 ⏸ 暂停等待用户确认设计**。交接方式：
   - 草稿头部必须写 `Drafted: <provider>/<model> (selected) · <provider>/<model> (physical) @ <ISO8601>`；
     每次修订追加同格式的 `Revised:` 行。
   - 草稿落盘后**自动进入**交叉复核循环：preflight 校验复核者模型与起草者异构（fail-closed），
     然后派发 fresh-context 的 spec-reviewer subagent 逐轮复核，起草者（主 session）逐条修订，
     **收敛（无真缺口）或到达轮次上限（默认 4）**为止；全程无需手动切换模型、无需手动触发。
   - 复核留痕在 `~/.claude/github-issue-driven/<owner>/<repo>/issue-<N>/research/`（父统一写入），
     轮次结论评论回 issue；收敛后才进入本步的 ⏸。
```

- [ ] **Step 2: 改 README**

`$WT/pi/README.md` 技能表中 `spec-cross-review` 行改为：

```markdown
| `spec-cross-review` | 设计文档交叉复核（派发 spec-reviewer + 全自动循环，收敛后才交用户确认） | 步 4 |
```

前置依赖列表末尾新增一条：

```markdown
- 部署前置：`subagents.agentOverrides.spec-reviewer.model` 设为与常用起草模型异构的模型
  （`pi/agents/spec-reviewer.md` 故意不带 model 字段；详见 `pi/spec-cross-review/SKILL.md` 部署前置节）
```

- [ ] **Step 3: 跑测试确认 A8/A9 变绿**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -q -k "FlowStep4 or ReadmeTable"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git -C $WT add pi/github-issue-driven/SKILL.md pi/README.md
git -C $WT commit -m "docs(skill): step-4 auto-entry + README registry (#254)

Step 4 now enters the cross-review loop automatically after the draft
lands (no manual model switch, no manual trigger); README records the
spec-reviewer deployment prerequisite."
```

---

### Task 6: CHANGELOG + 全仓回归（A10）

**Files:**
- Modify: `$WT/CHANGELOG.md`（[Unreleased] 的 Changed 段）

**Interfaces:**
- Consumes: Task 1–5 全部产物。

- [ ] **Step 1: 全量契约测试**

Run: `cd $WT && uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS（全部）

- [ ] **Step 2: CHANGELOG**

`$WT/CHANGELOG.md` 的 `## [Unreleased]` → `### Changed` 段首新增：

```markdown
- **skill (spec-cross-review)**: manual model-switching replaced by a dispatched
  `spec-reviewer` subagent — new `pi/agents/spec-reviewer.md` profile (fresh context,
  no write/edit tools, no model field), `pi.subagents.agents` package registration,
  one-shot preflight model gate (fail-closed), parent-orchestrated auto-converge loop,
  parent as sole writer of all traces; handoff literal replaced by a per-round
  progress line; contract tests rewritten (#254)
```

- [ ] **Step 3: 全仓回归**

Run: `cd $WT && uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
Expected: 全绿，覆盖率 ≥60

- [ ] **Step 4: Commit**

```bash
git -C $WT add CHANGELOG.md
git -C $WT commit -m "chore(changelog): record spec-cross-review automation (#254)"
```

---

### Task 7: U1 / U2 试点（post-implementation manual verification，验收 U1 / U2）

**Files:**
- 无代码改动；留痕写 `~/.claude/github-issue-driven/zhuxixi/zima-blue-cli/issue-254/research/`

**Interfaces:**
- Consumes: 合并后的 main（pi 包从主 checkout 加载——#250 R1-G4 教训：**worktree 内不执行**）。

- [ ] **Step 1: 执行时机确认**

PR 合并回 main → `git checkout main && git pull` → 从主 checkout 发起新会话。

- [ ] **Step 2: S1 残余验证 + U2 前置**

`subagent({action:"models", agent:"spec-reviewer"})`：
- 能解析到包内 profile → S1 完全闭环；
- 不能解析 → 先换顶层 `"pi-subagents": {"agents": ["./pi/agents"]}` 形式重试；再不行按
  `subagents.agentScanDirs` 写部署文档 fallback。

- [ ] **Step 3: U2（部署前置生效）**

在未配置 `agentOverrides.spec-reviewer.model` 的状态触发一次步 4：preflight 必须
fail-closed，输出的部署指引可直接照做。然后按指引配置模型。

- [ ] **Step 4: U1（真实 issue 全流程试点）**

拿一个真实 issue（候选：下一个真实 bug 的 spec；或复用停滞中的 jfox #547 做外仓验证）
走完整步 4：起草 → 自动进入复核 → 全自动多轮 → 收敛 → ⏸ 用户确认。核对：

- 轮次报告 / 修订摘要 / state / verbatim JSON / issue 评论齐全；
- 报告头记录的评审模型确实 ≠ 起草模型；
- 至少拦下 1 个真缺口（若首轮恰无真缺口，需另取一份更复杂的 spec 再跑一轮）；
- 全程零手动切模型；
- 每轮 token/时长数据填进 state 的「每轮成本」行。

- [ ] **Step 5: 结果评论回 issue**

试点结论（含成本数据与拦下的真缺口）评论回 #254。

---

## 验收对账表（plan ↔ spec 双向追溯）

| spec 验收 ID | 对应 task |
|---|---|
| S1 | 本 plan 开头「S1 证据」（已完成代码级核实）+ Task 7 Step 2（动态残余） |
| A1 | Task 1 Step 4 / 6 |
| A2 | Task 1 Step 5 / 6 |
| A3 | Task 1 Step 2（断言）+ Task 1–5 全部文档遵守 + Task 6 Step 3 |
| A4 | Task 2 |
| A5 | Task 3 |
| A6 | Task 4 Step 1 / 3 |
| A7 | Task 4 Step 2 / 3 |
| A8 | Task 5 Step 1 / 3 |
| A9 | Task 5 Step 2 / 3 |
| A10 | Task 6 |
| U1 | Task 7 Step 3–5 |
| U2 | Task 7 Step 3 |

## 与 spec 的实现级偏差（如实记录，均不改变设计语义）

1. **D6 的「profile 与 dispatch-contract 逐字一致」改为单一定义源**：profile 不内嵌五视角清单全文；清单单一定义源是 `references/checklist.md`，由父每轮读盘后注入 `<CHECKLIST_CONTENT>`。契约测试从「两文件逐字相等」改为「dispatch-contract.md 引用该单一定义源」。避免三份拷贝靠测试锁漂移。
2. **outputSchema 去掉 `mode` 字段**：`Mode` 的判定依赖 preflight 结果与事后撞真身检查，只有父能填；child 填不了。A4 断言清单相应不含 `mode`。
3. **S1 从「spike 待办」改为「已完成代码级核实」**：证据见本 plan 开头；动态残余折进 Task 7。
4. **spec 交付物 #5（`checklist.md` 修订）取消**：其内容已是五视角清单的单一定义源且无人工流程引用，无需与 profile 对齐的改写；偏差 1 的单一定义源方案使其保持原样。
