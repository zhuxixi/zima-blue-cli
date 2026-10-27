# Merge-Strategy-Aware Compliance Checks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the CR skill judge commit/PR metadata rules against the repository's real merge form, and guarantee metadata-class findings can never block a merge by default.

**Architecture:** A stdlib-only probe script (`merge_strategy.py`) classifies the repo as `squash | rebase | merge | unknown` from GitHub flags plus the last 10 merged PRs, then the flow conditionally injects branch commit subjects into the compliance checkers. A deterministic clamp in `issue_policy.py` downgrades guideline-anchored spec findings to advisory. Both harness copies (pi skill + cc plugin) ship the same scripts and the same checker contract.

**Tech Stack:** Python 3.10+ stdlib only, pytest, GitHub CLI (`gh api` / `gh api graphql`), Markdown skill docs.

**Spec:** `docs/superpowers/specs/2026-10-28-cr-merge-strategy-design.md`

## Global Constraints

- Scripts are stdlib-only (no third-party imports, no MCP) and call `gh` via subprocess.
- Scripts carry no `pi-cr` / `cc-cr` literals; they are byte-identical between the two copies.
- Docs are hand-ported per harness (pi dispatch prose vs cc Agent prose); only the checker prompt sections stay byte-identical.
- Use `mergeCommit.message` first line for classification; **never** `messageHeadline` (truncates at 70 chars + `…`).
- History threshold is `ceil(0.8 × n)` with `n ∈ [5,10]`; fewer than 5 samples → `unknown`.
- Ordering inside `is_blocking`: explicit boolean → guideline-anchor clamp → severity derivation.
- Branch naming: `issue-253-cr-merge-strategy`; commit format `type(scope): summary (#253)`.
- Work from `/home/elling/work/git-repo/zima-blue-cli/.pi/worktrees/issue-253-cr-merge-strategy` (absolute paths only, never `cd` into it).

## Review Focus

1. A repo whose squash commit message was customized without `(#N)` — classification falls to `rebase`; the finding must stay `low` and non-blocking.
2. `gh` unauthenticated / offline — probe must exit 0 with `strategy=unknown basis=probe-failed`, never traceback.
3. A finding whose `reason` says `AGENTS.md 规范` (non-canonical) anchored at `AGENTS.md` — clamp must still fire (substring match).
4. A PR that legitimately edits `AGENTS.md` — clamp downgrades it unless the checker sets explicit `blocking: true`.
5. Merged-PR sample shorter than 10 (young repo) — threshold uses `ceil(0.8n)`, not a hard 8.

---

### Task 1: Probe script + pure-function tests (pi copy)

**Files:**
- Create: `pi/github-code-review-batch/scripts/merge_strategy.py`
- Test: `tests/unit/test_cr_batch_merge_strategy.py`

**Interfaces:**
- Produces:
  - `classify_flags(flags: dict[str, bool]) -> tuple[str, str] | None` — returns `(strategy, "flags")` when exactly one method is enabled, else `None`.
  - `classify_headline(pr_number: int, headline: str) -> str` — `"merge" | "squash" | "rebase"`.
  - `classify_history(rows: list[tuple[int, str]]) -> tuple[str, str, dict]` — returns `(strategy, basis, buckets)`; `basis ∈ {"history", "history-ambiguous"}`; `strategy ∈ {"squash","rebase","merge","unknown"}`.
  - `decide(flags_res, hist_res) -> dict` — full probe payload (`schema`, `repo`/`pr` added by caller).
  - `render_policy(strategy: str) -> dict` — `{"inject_branch_subjects", "check_pr_title", "metadata_max_severity"}`.
  - `probe(repo: str, pr: int, run=subprocess.run) -> dict` — IO shell; never raises.
  - CLI: `python scripts/merge_strategy.py --repo o/r --pr N [--json-out PATH]`.

- [ ] **Step 1: Write failing tests** for `classify_flags` (4 cases), `classify_headline` (`Merge pull request #` → merge; `... (#249)` → squash; `... (issue #95)` → rebase; trailing `…` input is never produced by the pipeline — assert `classify_headline` is only fed `message` first lines by testing `probe` with a stub), `classify_history` (n=10 9/1 → squash; n=5 all squash → squash; n=4 → unknown; n=10 split 5/5 → unknown), `decide` (probe-failed/ambiguous → unknown), `render_policy` (4 strategies), `probe` happy path and failure path (stub `run` returning rc=1).

- [ ] **Step 2: Run tests, expect ImportError**

Run: `uv run pytest tests/unit/test_cr_batch_merge_strategy.py -v`

- [ ] **Step 3: Implement the script** per spec §4.1–§4.2. Core logic:

```python
def classify_headline(pr_number: int, headline: str) -> str:
    if headline.startswith("Merge pull request #"):
        return "merge"
    if headline.endswith(f" (#{pr_number})"):
        return "squash"
    return "rebase"

def classify_history(rows):
    buckets = {"squash": 0, "rebase": 0, "merge": 0}
    for number, headline in rows:
        buckets[classify_headline(number, headline)] += 1
    n = len(rows)
    if n < 5:
        return "unknown", "history-ambiguous", {**buckets, "merged_sampled": n}
    threshold = math.ceil(0.8 * n)
    for strategy, count in buckets.items():
        if count >= threshold:
            return strategy, "history", {**buckets, "merged_sampled": n}
    return "unknown", "history-ambiguous", {**buckets, "merged_sampled": n}
```

`probe()` steps: flags query → `classify_flags`; on `None`, GraphQL query with `mergeCommit{ message }`, take `message.split("\n")[0]`; any subprocess failure → `unknown/probe-failed`; always return a dict with `policy` from `render_policy`.

- [ ] **Step 4: Run tests, expect PASS**; also run `uv run ruff check pi/github-code-review-batch/scripts/merge_strategy.py` and `uv run black --check --line-length 100`.

- [ ] **Step 5: Commit** `feat(cr-batch): merge strategy probe with pure classification (#253)`.

---

### Task 2: Deterministic blocking clamp (both copies)

**Files:**
- Modify: `pi/github-code-review-batch/scripts/issue_policy.py` (`is_blocking`)
- Modify: `plugins/pr-automation/skills/github-code-review-batch/scripts/issue_policy.py` (same edit, verbatim)
- Test: `tests/unit/test_cr_batch_issue_policy.py`

**Interfaces:**
- Consumes: existing `is_blocking(issue) -> bool`.
- Produces: guideline-anchored spec findings return `False` unless `blocking` is an explicit boolean.

- [ ] **Step 1: Write failing tests** — `test_guideline_anchor_is_not_blocking` (`reason="AGENTS.md"`, `file="AGENTS.md"`, `severity="medium"` → False), `test_guideline_anchor_non_canonical_reason` (`reason="AGENTS.md 规范"` → False), `test_explicit_blocking_override_wins` (`blocking=True` → True), `test_code_anchor_keeps_severity_policy` (`reason="AGENTS.md"`, `file="src/a.py"`, severity medium → True).
- [ ] **Step 2: Run, expect failure** on the first two.
- [ ] **Step 3: Implement** the clamp after the explicit-boolean branch:

```python
reason = str(issue.get("reason", ""))
if any(name in reason for name in ("CLAUDE.md", "AGENTS.md")):
    anchor = PurePosixPath(str(issue.get("file", ""))).name
    if anchor in {"CLAUDE.md", "AGENTS.md"}:
        return False
```

- [ ] **Step 4: Copy the edited file verbatim into the cc copy**, then run both test files of `test_cr_batch_issue_policy.py -v`.
- [ ] **Step 5: Commit** `fix(cr): clamp guideline-anchored metadata findings to advisory (#253)`.

---

### Task 3: pi docs + contract tests

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md`, `references/subagent-prompts.md`, `references/edge-cases.md`, `SKILL.md`
- Test: `tests/unit/test_cr_batch_contracts.py`

**Interfaces:**
- Produces: `TestMergeStrategyDisambiguation` (class name pinned) and `merge_strategy.py` added to `TestPortability.SCRIPT_NAMES`.

- [ ] **Step 1: Write the contract tests first** (they must fail): assert `## Step 2.5` exists with `--json-out /tmp/pi-cr-merge-strategy.json`, `mergeCommit{ message }`, the word `仅完整轮执行`, `ceil(0.8`, and no `messageHeadline` in the probe command; assert Step 4 input bullets mention `{merge_strategy}` and `{pr_title}` and conditional injection; assert both checker sections contain `输入边界`, `不得自行`, `severity=low`, `blocking: true`; assert validator section mentions `merge_strategy`; assert edge-cases list has 7 items ending with the merge-strategy class; assert `SKILL.md` overview table has a `Step 2.5` row.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_cr_batch_contracts.py -k MergeStrategy -v` → FAIL.
- [ ] **Step 3: Edit the four docs** exactly as spec §4.1/§4.3/§4.4/§4.5/§5 prescribe (Step 2.5 section, Step 4/5 input bullets, checker task items and prompt skeleton with `PR 标题：{pr_title}`, validator branch, edge-cases item 7, SKILL row + constraint bullet).
- [ ] **Step 4: Run the same pytest selector → PASS**, plus the whole file to prove no regression.
- [ ] **Step 5: Commit** `docs(cr-batch): merge-strategy-aware checker contract (#253)`.

---

### Task 4: cc mirror + contract tests

**Files:**
- Create: `plugins/pr-automation/skills/github-code-review-batch/scripts/merge_strategy.py` (byte-identical copy of Task 1)
- Modify: `plugins/.../references/flow.md`, `references/subagent-prompts.md`, `references/edge-cases.md`, `SKILL.md`
- Test: `tests/unit/test_cr_batch_plugin_contracts.py`

**Interfaces:**
- Produces: `TestCcMergeStrategyMirror` (class name pinned).

- [ ] **Step 1: Copy the script** (`cp`), then write failing mirror tests: script exists and is byte-identical, cc flow mentions `/tmp/cc-cr-merge-strategy.json`, checker sections carry the same contract tokens as pi, edge-cases has 7 classes.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_cr_batch_plugin_contracts.py -k MergeStrategy -v` → FAIL.
- [ ] **Step 3: Port the docs** with cc harness wording (Agent dispatch prose, `cc-cr` temp paths). Keep checker sections byte-identical to pi.
- [ ] **Step 4: Run** the selector → PASS, then the whole plugin contract file.
- [ ] **Step 5: Commit** `docs(plugin): mirror merge-strategy checker contract (#253)`.

---

### Task 5: Full regression + acceptance run

- [ ] **Step 1:** `uv run pytest tests/ -m "not slow" --cov=zima --cov-fail-under=60`
- [ ] **Step 2:** `uv run ruff check zima/ tests/` and `uv run black --check zima/ tests/ --line-length 100`
- [ ] **Step 3:** `uv run pytest tests/unit/test_cr_batch_merge_strategy.py tests/unit/test_cr_batch_issue_policy.py tests/unit/test_cr_batch_contracts.py tests/unit/test_cr_batch_plugin_contracts.py -q`
- [ ] **Step 4:** Commit any formatting fixups as `chore(cr-batch): formatting (#253)`.

---

## Acceptance traceability

| Spec ID | Plan task | Verification |
|---|---|---|
| A1, A2, A3, A4, A5, A6 | Task 1 | `pytest -k "classify_flags or classify_history or decide or render_policy or probe"` |
| A7 | Task 2 | `pytest tests/unit/test_cr_batch_issue_policy.py -k guideline_anchor` |
| A8 | Task 3 | `pytest tests/unit/test_cr_batch_contracts.py -k MergeStrategy` |
| A9 | Task 4 | `pytest tests/unit/test_cr_batch_plugin_contracts.py -k MergeStrategy` |
| A10 | Task 5 | full suite + ruff + black |
| U1, U2 | post-implementation manual run | spec §9 protocol (pi-agent-board #251, Step 0–8 only, evidence = Step 2.5 stdout + JSON + Step 8 findings) |
