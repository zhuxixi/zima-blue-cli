# spec-reviewer thinking max Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `spec-reviewer` 的思考档位从 `high` 提到 `max`，并把「复核者模型必须支持 max」写成部署前置条件。

**Architecture:** 纯文本契约改动，无运行时代码。profile frontmatter 是唯一事实源，契约测试锁住它；部署文档补前置条件，避免换模型后到派发时才炸。

**Tech Stack:** pi-subagents agent profile（Markdown frontmatter）+ pytest 契约测试。

**Spec:** `docs/superpowers/specs/2026-11-06-spec-reviewer-thinking-max-design.md`

## Global Constraints

- `pi/spec-cross-review/` 下任何文档**禁止**出现 `~/.pi/` 字面量（`tests/unit/test_spec_cross_review_contracts.py:361` 锁定）。
- 不改 `pi/agents/spec-reviewer.md` 的 `model` 字段（模型是部署策略）。
- 不追写 `docs/` 下历史 spec/plan 里的 `thinking: high`。
- 测试命令：`uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`。
- 只 `git add <file>`，不用 `git add -A`。

## Review Focus

- 断言与 profile 是否成对改动（只改一边会让 CI 红）。
- 新增的 SKILL.md 措辞是否撞 `~/.pi/` 禁令。
- CHANGELOG 落在现行 `### Changed` 小节，而不是新造 `### Changes`。

---

### Task 1: profile 档位 high → max（A1、A2）

**Files:**
- Modify: `pi/agents/spec-reviewer.md:9`
- Modify: `tests/unit/test_spec_cross_review_contracts.py:86`

**Interfaces:** 无（纯文本契约）。

- [ ] **Step 1: 先把断言改成 max（制造红色）**

```python
# tests/unit/test_spec_cross_review_contracts.py:86
assert "thinking: max" in head
```

- [ ] **Step 2: 跑测试确认红**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py::TestProfileContract -q`
Expected: FAIL（`thinking: max` 不在 profile 里）

- [ ] **Step 3: 改 profile**

```yaml
# pi/agents/spec-reviewer.md:9
thinking: max
```

- [ ] **Step 4: 跑测试确认绿**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS

- [ ] **Step 5: 静态核对（A2）**

Run: `rg -n '^thinking:' pi/`
Expected: 唯一命中 `pi/agents/spec-reviewer.md:9:thinking: max`

- [ ] **Step 6: commit**

```bash
git add pi/agents/spec-reviewer.md tests/unit/test_spec_cross_review_contracts.py
git commit -m "feat(agents): raise spec-reviewer thinking to max (#270)"
```

---

### Task 2: 部署前置写明 max 前提（A3）

**Files:**
- Modify: `pi/spec-cross-review/SKILL.md`（「部署前置」节）
- Modify: `tests/unit/test_spec_cross_review_contracts.py`（新增断言）

**Interfaces:** 无。

- [ ] **Step 1: 写失败断言**

```python
# 在 TestSkillStructure 内新增
def test_deploy_prerequisite_requires_max_thinking(self, skill: str) -> None:
    """A3: the reviewer model must support the `max` thinking level."""
    section = skill.split("## 部署前置", 1)[1].split("## ", 1)[0]
    assert "max" in section
```

- [ ] **Step 2: 跑测试确认红**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -k max_thinking -q`
Expected: FAIL

- [ ] **Step 3: SKILL.md 部署前置补前置条件**

顺序固定为「先放 allow，再设 model」，并写明复核者模型需支持 `max` 档；措辞沿用「用户级 settings.json」，**不得**写 `~/.pi/`。

- [ ] **Step 4: 跑测试确认绿**

Run: `uv run pytest tests/unit/test_spec_cross_review_contracts.py -q`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add pi/spec-cross-review/SKILL.md tests/unit/test_spec_cross_review_contracts.py
git commit -m "docs(spec-cross-review): reviewer model must support max thinking (#270)"
```

---

### Task 3: CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`（`[Unreleased]` → `### Changed`）

- [ ] **Step 1: 追加一条**

```markdown
- **skill (spec-cross-review)**: `spec-reviewer` thinking raised to `max`; deploy
  prerequisite now states the reviewer model must support `max` (#270)
```

- [ ] **Step 2: commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): note spec-reviewer thinking bump (#270)"
```

---

### Task 4: 收尾验证

- [ ] **Step 1: 全量单测**

Run: `uv run pytest tests/unit -q`
Expected: PASS

- [ ] **Step 2: lint**

Run: `uv run ruff check tests/ pi/ 2>/dev/null || uv run ruff check tests/`
Expected: no new findings

- [ ] **Step 3: 工作区干净核对**

Run: `git status --short`
Expected: 空

## 验收追溯

| 验收 ID | 覆盖任务 |
|---|---|
| A1 | Task 1 Step 1–4 |
| A2 | Task 1 Step 5 |
| A3 | Task 2 |
| U1 | 合并后用户实测（本 plan 不覆盖） |
