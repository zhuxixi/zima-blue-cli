# Output Schema Single Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `spec-reviewer` dispatch consume a machine-readable JSON schema instead of manually transcribing a Markdown copy, with structural contract tests that prevent both observed failures.

**Architecture:** Add `references/output-schema.json` as the sole schema definition. Contract tests parse that JSON and recursively validate its structure; dispatch documentation and orchestration only reference the JSON file and never duplicate its fields. The implementation uses TDD and isolated-worktree commits.

**Tech Stack:** Python 3.10+, pytest, stdlib `json`, Markdown, JSON, uv.

## Global Constraints

- Work only in `/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-274-output-schema-single-source`; use absolute paths for file tools and `git -C "$WT"` for git.
- Branch: `issue-274-output-schema-single-source`; implementation base: `origin/main` commit `59fcec9c4ce3bd1899ac20c02fa5c474a3a1678d`.
- Acceptance IDs: Task 1 covers A1/A2; Task 2 covers A3/A5; Task 3 covers A4/A6; Task 4 covers U1 after merge.
- Do not modify `package.json`, pi-subagents, reviewer output semantics, the main checkout, or `zima-blue-cli-mdbot`.
- `output-schema.json` is the only complete schema. Do not copy its full fields into Markdown or test code.
- All enum nodes must have `type:"string"`; every object node's `required` keys must exist in its `properties`; no `mode` field.
- Keep `_read(path)` IO separate from the pure recursive schema walker and independent test assertions.
- Each implementation task follows RED → verified failure → minimal GREEN → full contract-file test → commit. Run tests from the worktree root.
- Merge always requires explicit user approval. U1 remains `pending` until the post-merge steps in Task 4 are actually performed.

---

### Task 1: Machine-readable schema and structural tests

**Acceptance:** A1, A2.

**Files:**
- Create: `pi/spec-cross-review/references/output-schema.json`
- Modify: `tests/unit/test_spec_cross_review_contracts.py`

**Interfaces:**
- Consumes: existing `_read(path: Path) -> str`, `SKILL_DIR`, stdlib `json`, pytest fixtures.
- Produces: `SCHEMA: Path`, `_walk_schema(node: object) -> Iterator[dict]`, and `TestOutputSchema`; Task 2 retains these names and does not duplicate schema fields in Markdown.

- [ ] **Step 1: Write the failing structural tests**

Add `from collections.abc import Iterator` and `SCHEMA = SKILL_DIR / "references" / "output-schema.json"`. Add this pure walker after `_read`:

```python
def _walk_schema(node: object) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_schema(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_schema(item)
```

Add `TestOutputSchema` before `TestDispatchContract`:

```python
class TestOutputSchema:
    """A1/A2: the JSON schema is structurally valid and semantically stable."""

    @pytest.fixture(scope="class")
    def schema(self) -> dict:
        value = json.loads(_read(SCHEMA))
        assert isinstance(value, dict)
        return value

    def test_schema_file_is_json_object(self) -> None:
        assert SCHEMA.is_file()
        value = json.loads(_read(SCHEMA))
        assert isinstance(value, dict)

    def test_required_keys_reference_properties(self, schema: dict) -> None:
        for node in _walk_schema(schema):
            if "properties" in node:
                assert isinstance(node["properties"], dict)
            if "required" in node:
                assert isinstance(node["required"], list)
                assert all(isinstance(key, str) for key in node["required"])
                assert "properties" in node
                assert set(node["required"]) <= set(node["properties"])

    def test_all_enum_nodes_have_string_type(self, schema: dict) -> None:
        enum_nodes = [node for node in _walk_schema(schema) if "enum" in node]
        assert enum_nodes
        for node in enum_nodes:
            assert node["type"] == "string"

    def test_root_contract(self, schema: dict) -> None:
        assert schema["type"] == "object"
        assert set(schema["required"]) == {
            "round", "reviewedSha256", "lenses", "findings", "counts", "convergence"
        }
        assert set(schema["properties"]) == set(schema["required"])
        assert "mode" not in schema["properties"]

    def test_nested_contract(self, schema: dict) -> None:
        root = schema["properties"]
        lenses = root["lenses"]
        assert lenses["type"] == "array"
        assert lenses["minItems"] == 5
        assert lenses["maxItems"] == 5
        lens_item = lenses["items"]
        assert set(lens_item["required"]) == {"lens", "verdict", "findingIds"}
        lens_props = lens_item["properties"]
        assert lens_props["findingIds"]["type"] == "array"
        assert lens_props["findingIds"]["items"] == {"type": "string"}
        assert lens_props["lens"]["type"] == "string"
        assert lens_props["verdict"] == {"type": "string", "enum": ["核对通过", "有发现"]}

        finding = root["findings"]["items"]
        assert set(finding["required"]) == {
            "id", "level", "location", "why", "suggestion", "costIfSkipped"
        }
        assert finding["properties"]["level"] == {
            "type": "string", "enum": ["真缺口", "细化", "核对通过"]
        }
        assert set(root["counts"]["required"]) == {"gaps", "details", "passes"}
        assert set(root["convergence"]["required"]) == {"converged", "summary"}

    def test_lens_enum_matches_checklist(self, schema: dict) -> None:
        checklist = _read(SKILL_DIR / "references" / "checklist.md")
        headings = [line for line in checklist.splitlines() if line.startswith("## ")]
        lens = schema["properties"]["lenses"]["items"]["properties"]["lens"]
        assert lens["type"] == "string"
        assert len(lens["enum"]) == 5
        for value in lens["enum"]:
            assert any(value in heading for heading in headings), value
```

- [ ] **Step 2: Verify RED for the missing definition source**

Run:

```bash
cd "$WT" && uv run pytest tests/unit/test_spec_cross_review_contracts.py::TestOutputSchema::test_schema_file_is_json_object -v
```

Expected: FAIL at `assert SCHEMA.is_file()` because `output-schema.json` does not exist. Do not create production data before observing this failure.

- [ ] **Step 3: Add the minimal JSON definition source**

Create `pi/spec-cross-review/references/output-schema.json` with exactly this semantic content (formatting may be pretty-printed):

```json
{
  "type": "object",
  "required": ["round", "reviewedSha256", "lenses", "findings", "counts", "convergence"],
  "properties": {
    "round": {"type": "integer", "minimum": 1},
    "reviewedSha256": {"type": "string"},
    "lenses": {
      "type": "array",
      "minItems": 5,
      "maxItems": 5,
      "items": {
        "type": "object",
        "required": ["lens", "verdict", "findingIds"],
        "properties": {
          "lens": {
            "type": "string",
            "enum": ["验收矩阵完备性", "可测性拆分可实现性 + 触发时序", "部署/执行路径真实性", "契约与边界", "命令与命名可追溯"]
          },
          "verdict": {"type": "string", "enum": ["核对通过", "有发现"]},
          "findingIds": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "level", "location", "why", "suggestion", "costIfSkipped"],
        "properties": {
          "id": {"type": "string"},
          "level": {"type": "string", "enum": ["真缺口", "细化", "核对通过"]},
          "location": {"type": "string"},
          "why": {"type": "string"},
          "suggestion": {"type": "string"},
          "costIfSkipped": {"type": "string"}
        }
      }
    },
    "counts": {
      "type": "object",
      "required": ["gaps", "details", "passes"],
      "properties": {
        "gaps": {"type": "integer", "minimum": 0},
        "details": {"type": "integer", "minimum": 0},
        "passes": {"type": "integer", "minimum": 0}
      }
    },
    "convergence": {
      "type": "object",
      "required": ["converged", "summary"],
      "properties": {
        "converged": {"type": "boolean"},
        "summary": {"type": "string"}
      }
    }
  }
}
```

- [ ] **Step 4: Verify GREEN and no contract-file regressions**

Run:

```bash
cd "$WT" && uv run pytest tests/unit/test_spec_cross_review_contracts.py
```

Expected: exit 0; all 99 tests pass (93 baseline + 6 new), with no deselected tests. This is the shared A1/A2 command; record the actual count if later upstream changes alter the baseline.

- [ ] **Step 5: Commit Task 1**

```bash
git -C "$WT" add pi/spec-cross-review/references/output-schema.json tests/unit/test_spec_cross_review_contracts.py
git -C "$WT" commit -m "fix(skill): add machine-readable reviewer output schema (#274)"
```

---

### Task 2: Dispatch documents consume JSON and fail closed

**Acceptance:** A3, A5.

**Files:**
- Modify: `tests/unit/test_spec_cross_review_contracts.py`
- Modify: `pi/spec-cross-review/references/dispatch-contract.md`
- Modify: `pi/spec-cross-review/SKILL.md`
- Modify: `pi/spec-cross-review/references/edge-cases.md`

**Interfaces:**
- Consumes: Task 1's `SCHEMA`, `_walk_schema`, `TestOutputSchema`, and JSON file.
- Produces: documentation assertions in existing `TestDispatchContract`, `TestSkillStructure`, and `TestEdgeCaseCoverage`; no new schema copy.

- [ ] **Step 1: Write failing single-source and failure-branch tests**

In `TestDispatchContract`, remove the obsolete Markdown-schema tests `test_output_schema_fields`, `test_finding_levels`, `test_lens_enum_matches_checklist_headings`, and `test_lens_item_fields_and_verdict_enum`; their semantic coverage now lives in `TestOutputSchema`. Keep `test_checklist_single_source` and add:

```python
    def test_output_schema_json_single_source(self, doc: str) -> None:
        assert "references/output-schema.json" in doc
        assert "options.outputSchema" in doc
        assert "const outputSchema" not in doc

    def test_output_schema_failure_fails_closed(self, doc: str) -> None:
        assert "不可解析" in doc
        assert "不手写兜底" in doc
        assert "不静默重" in doc
```

Add to `TestSkillStructure`:

```python
    def test_output_schema_json_dispatch(self, skill: str) -> None:
        assert "references/output-schema.json" in skill
        assert "options.outputSchema" in skill

    def test_output_schema_failure_fails_closed(self, skill: str) -> None:
        assert "不可解析" in skill
        assert "不手写兜底" in skill
        assert "不静默重派" in skill
```

In `TestEdgeCaseCoverage.test_edge_case_documented`, add both literal markers `"不手写兜底"` and `"不可解析"` to the parametrized tuple. Do not remove the existing `"schema"` marker.

- [ ] **Step 2: Verify RED before changing documents**

Run:

```bash
cd "$WT" && uv run pytest tests/unit/test_spec_cross_review_contracts.py
```

Expected: FAIL in the new dispatch, skill, and edge-case assertions because the JSON path and new failure literals are absent. The old Markdown-schema tests must already be removed so they do not force restoration of the old copy.

- [ ] **Step 3: Replace the Markdown schema with the read-and-dispatch contract**

In `dispatch-contract.md`, retain the task template and variable table unchanged. Update the opening to name both single sources:

```markdown
不写文件。五视角清单的单一定义源是 `references/checklist.md`——父读盘后原样注入
`<CHECKLIST_CONTENT>`，禁止在任何其他文件里复制第二份全文。outputSchema 的单一定义源是
`references/output-schema.json`——父读盘并解析后传入 `options.outputSchema`，禁止复制第二份全文。
```

Replace the complete `## outputSchema（父在派发时传入）` JavaScript block with:

```markdown
## outputSchema（父在派发时传入）

父使用 read 工具读取 `references/output-schema.json`，将文件内容解析为 JSON object，并把同一
object 传给 subagent 的 `options.outputSchema`。禁止从 Markdown 手工转写、重录字段、增删字段
或按轮重建 schema。

文件缺失或 JSON 不可解析时，按派发失败处理：停止循环、留痕并报告，不手写兜底、不静默重试。
```

- [ ] **Step 4: Update orchestration and edge cases**

In `SKILL.md` 每轮编排 step 1, require both read operations:

```markdown
1. 父算被审版本 `sha256sum <spec 绝对路径>`，按 `references/dispatch-contract.md` 渲染任务
   （注入变量 + 从 `references/checklist.md` 读盘注入五视角清单全文），读取并解析
   `references/output-schema.json`，将同一 JSON object 传给 `options.outputSchema`，派发
   `spec-reviewer`（cwd 为目标仓库），等待 native 完成通知，不轮询。
```

Change step 2's schema reference to `references/output-schema.json`. Add this row to 失败处理:

```markdown
| `output-schema.json` 缺失或 JSON 不可解析 | 停循环 + 留痕 + 报错；不手写兜底、不静默重派 |
```

Add this row to `references/edge-cases.md` immediately before the existing generic 派发失败 row:

```markdown
| `output-schema.json` 缺失或 JSON 不可解析 | 停循环 + 留痕 + 报错；不手写兜底、不静默重派 |
```

- [ ] **Step 5: Verify GREEN, A3 grep, and complete-file coverage**

Run:

```bash
cd "$WT" && uv run pytest tests/unit/test_spec_cross_review_contracts.py
cd "$WT" && rg -n "const outputSchema" pi/spec-cross-review
```

Expected: pytest exits 0 with no deselected tests; rg exits 1 with no matches. The rg no-match result is required by A3 and is not a test failure.

- [ ] **Step 6: Commit Task 2**

```bash
git -C "$WT" add pi/spec-cross-review/SKILL.md pi/spec-cross-review/references/dispatch-contract.md pi/spec-cross-review/references/edge-cases.md tests/unit/test_spec_cross_review_contracts.py
git -C "$WT" commit -m "fix(skill): dispatch reviewer schema from JSON (#274)"
```

---

### Task 3: Changelog and full acceptance checks

**Acceptance:** A4, A6; rechecks A1/A2/A3/A5 on the final tree.

**Files:**
- Modify: `CHANGELOG.md`
- Verify: all Task 1/2 files plus committed spec and this plan.

**Interfaces:**
- Consumes: completed Tasks 1/2 and their commits.
- Produces: an Unreleased Changed entry containing `#274` and recorded A1–A6 evidence. No production interfaces.

- [ ] **Step 1: Add the changelog entry**

Under `## [Unreleased]` → `### Changed`, add:

```markdown
- **skill (spec-cross-review)**: reviewer `outputSchema` now has a machine-readable
  `references/output-schema.json` single source, explicit string enum types, recursive structural
  contract tests, and fail-closed handling for missing or invalid JSON; the Markdown schema copy
  and manual transcription path are removed (#274)
```

This is a documentation-only changelog edit; Task 1/2 already supply the failing-test evidence for the behavior being recorded.

- [ ] **Step 2: Run the complete contract file and A3 check**

```bash
cd "$WT" && uv run pytest tests/unit/test_spec_cross_review_contracts.py
cd "$WT" && rg -n "const outputSchema" pi/spec-cross-review
```

Expected: pytest exit 0, no deselected; rg no matches. Record output for A1/A2/A3/A5.

- [ ] **Step 3: Run A4 full non-slow suite with coverage**

```bash
cd "$WT" && uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60
```

Expected: exit 0, all non-slow tests pass, coverage is at least 60%.

- [ ] **Step 4: Run A6 delivery checks after committing all implementation files**

Commit the changelog first:

```bash
git -C "$WT" add CHANGELOG.md
git -C "$WT" commit -m "docs(changelog): record reviewer schema single source (#274)"
```

Then run:

```bash
WT=/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-274-output-schema-single-source
git -C "$WT" diff --name-only origin/main...HEAD
test -f "$WT/docs/superpowers/specs/2026-11-12-output-schema-single-source-design.md"
test -f "$WT/docs/superpowers/plans/2026-11-12-output-schema-single-source.md"
git -C "$WT" diff origin/main...HEAD -- CHANGELOG.md | rg '^\+.*#274'
git -C "$WT" status --short
```

Expected: diff contains the new JSON, three skill documents, contract tests, CHANGELOG, spec, and plan; both `test` commands and rg exit 0; final status is empty.

---

### Task 4: Post-merge real-dispatch verification

**Acceptance:** U1 only. Execute after PR merge; do not perform it in the pre-merge worktree and do not claim it during Tasks 1–3.

**Files:** no planned repository changes. Record evidence in the issue and issue-274 research directory if the user performs or delegates the pilot.

- [ ] **Step 1: Update the actual skill-loading checkout**

After merge, run in `/home/elling/git-repo/github/zima-blue-cli`:

```bash
git checkout main && git pull --ff-only
git rev-parse HEAD
```

Expected: HEAD is the merge commit or a later main commit containing #274.

- [ ] **Step 2: Start a fresh session and perform one real first dispatch**

From that main checkout, start a new Pi session so the updated SKILL is loaded. Choose a real issue, execute step 4, and have the parent read `references/output-schema.json` for the first `spec-reviewer` dispatch. Do not retry schema construction and do not hand-write a substitute.

- [ ] **Step 3: Record U1 pass/fail evidence**

Pass requires no provider 400 for schema structure/missing type, actual read-only review starts, structured output conforms to the JSON contract, and `reviewedSha256` matches the reviewed spec. Record run ID, physical model, report path, and observations. Until every observation exists, U1 remains `pending`; a failed U1 must be reported rather than hidden by A1–A6.
