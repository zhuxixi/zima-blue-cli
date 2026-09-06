# Trivial Precheck (Issue #223) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 github-code-review-batch skill 的 Step 1 增加确定性 trivial 判定脚本，让首轮 docs-only PR 秒级输出 PASS + approved 状态报告，不再空跑 LLM 审查。

**Architecture:** 新增 `scripts/trivial_check.py`（stdlib-only，纯函数 + 唯一 gh IO 出口），`--report` 模式直接 import 同目录 `render_status_report.render()` 输出最终报告；`render_status_report.py` 增加可选 `note` 字段（规范化 + XML escape，旧 caller 逐字节兼容）；flow.md/SKILL.md/edge-cases.md 更新契约；测试落在 `tests/unit/test_cr_batch_trivial_check.py` 与 `tests/unit/test_cr_batch_contracts.py`。

**Tech Stack:** Python 3.10+（stdlib only）、gh CLI 2.x、pytest、ruff、black。

## Global Constraints

- 所有脚本改动只在 worktree `$WT`（`/home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-223-trivial-precheck`）内进行；git 操作用 `git -C $WT`；禁止碰 main checkout。
- 脚本 stdlib-only：`trivial_check.py` 只允许 import 同目录 `render_status_report`（本地模块白名单）；禁止第三方依赖、禁止 MCP。
- 退出码契约：`0` = 数据有效（默认模式输出判定 JSON；`--report` 模式 trivial 命中输出完整报告）；`1` = 数据有效但非 trivial（仅 `--report` 模式）；`2` = 数据/API/脚本异常（fail-open）。
- Status 三态 `NEEDS_FIX/PASS/NO_NEW_COMMITS` 不变；trivial 用 `PASS` + `Note`。
- gh 调用：`gh pr view <number> --repo <owner/repo> --json number,state,isDraft,changedFiles,headRefOid,reviews`；文件列表用 `gh api --paginate --slurp "repos/<owner>/<repo>/pulls/<number>/files?per_page=100"`，禁止 `-f/--field`。
- REST 文件字段是 `filename`（不是 GraphQL `path`）；status 白名单 `added/modified/deleted/renamed/copied/changed/unchanged`；`changedFiles` 必须等于 flatten 后文件数；文件名必须唯一。
- 所有 subprocess：argv 列表、`stdin=subprocess.DEVNULL`、`capture_output=True`、`timeout=30`、`check=False`、禁止 `shell=True`。
- note 规范化：删 XML 非法控制字符 → 空白折叠单行 → 截断 240；XML summary 用 `xml.sax.saxutils.escape`；无 note 时输出与改动前逐字节一致。
- 生产代码（非测试 Python）新增 ≤200 行；测试与 .md 不计入。
- 测试命令：`uv run pytest tests/unit/test_cr_batch_trivial_check.py tests/unit/test_cr_batch_contracts.py`；lint：`uv run ruff check tests/ && uv run black --check tests/ --line-length 100`。
- Commit message 用 conventional commits（英文）。

---

### Task 1: render_status_report.py 可选 note（验收 A5）

**Files:**
- Modify: `pi/github-code-review-batch/scripts/render_status_report.py`
- Test: `tests/unit/test_cr_batch_trivial_check.py`（新建，本任务只 import render_status_report）

**Interfaces:**
- Produces: `render_status_report.format_note(note: str) -> str`；`render_status_report.render(d: dict) -> str` 支持可选 `note` 字段。

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_cr_batch_trivial_check.py`：

```python
"""Tests for the deterministic trivial-PR precheck (issue #223).

Task 1 covers the render_status_report note extension; later tasks add
trivial_check pure-function, fetch and main-level tests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = _REPO_ROOT / "pi" / "github-code-review-batch" / "scripts"

sys.path.insert(0, str(_SCRIPT_DIR))
import render_status_report  # type: ignore[import-not-found]  # noqa: E402

PASS_PAYLOAD = {
    "pr_number": 123,
    "round": 1,
    "head_sha": "a" * 40,
    "previous_head_sha": None,
    "open_count": 0,
    "new_count": 0,
    "unresolved_count": 0,
    "resolved_count": 0,
    "acknowledged_count": 0,
    "blocking_open_count": 0,
    "blocking_new_count": 0,
    "advisory_open_count": 0,
    "advisory_new_count": 0,
    "critical_count": 0,
    "status": "PASS",
}

GOLDEN_NO_NOTE = """\
=== CR Batch Status Report ===
PR: #123 | Round: 1 | Head SHA: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Previous Head SHA: null
Total open issues: 0
- New this round: 0
- Still open from previous: 0
- Resolved this round: 0
- Acknowledged / Won't Fix: 0
Blocking open issues: 0
- New blocking this round: 0
Advisory open issues: 0
- New advisory this round: 0
Status: PASS
Critical issues: 0
Verdict: READY_TO_MERGE
================================
<zima-review>
<verdict>approved</verdict>
<summary>CR batch PASS: no open issues</summary>
</zima-review>
"""


def test_format_note_collapses_whitespace():
    assert render_status_report.format_note("a\nb\tc  d") == "a b c d"


def test_format_note_strips_control_chars():
    assert render_status_report.format_note("a\x00b\x1fc") == "abc"


def test_format_note_truncates_at_240():
    assert len(render_status_report.format_note("x" * 500)) == 240


def test_format_note_empty():
    assert render_status_report.format_note("") == ""
    assert render_status_report.format_note("   ") == ""


def test_render_no_note_is_byte_identical_golden():
    assert render_status_report.render(PASS_PAYLOAD) == GOLDEN_NO_NOTE


def test_render_empty_note_equals_no_note():
    with_note = dict(PASS_PAYLOAD, note="")
    assert render_status_report.render(with_note) == GOLDEN_NO_NOTE


def test_render_note_line_after_verdict():
    out = render_status_report.render(dict(PASS_PAYLOAD, note="trivial precheck skip: x"))
    lines = out.splitlines()
    verdict_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Verdict:"))
    assert lines[verdict_idx + 1] == "Note: trivial precheck skip: x"


def test_render_note_xml_escaped_and_parses():
    from zima.review.parser import ReviewParser

    out = render_status_report.render(dict(PASS_PAYLOAD, note="docs & <generated>.md"))
    parsed = ReviewParser.parse(out)
    assert parsed.verdict == "approved"
    assert "docs &amp; &lt;generated&gt;.md" in out
    assert "docs & <generated>.md" in parsed.summary
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_cr_batch_trivial_check.py -v`
Expected: FAIL（`format_note` 不存在 / `Note:` 行缺失）

- [ ] **Step 3: 实现 render_status_report.py 的 note 扩展**

在 `render_status_report.py` 顶部 import 区加入：

```python
import re
from xml.sax.saxutils import escape
```

在 `VALID_STATUSES` 之后加入：

```python
_NOTE_MAX_LEN = 240
_NOTE_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def format_note(note: str) -> str:
    """Normalize a free-text note for the human block and XML summary.

    Strips XML-illegal control characters, collapses all whitespace runs
    (including CR/LF) to single spaces, and caps the length at 240 chars.
    """
    if not note:
        return ""
    text = _NOTE_CTRL_RE.sub("", note)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_NOTE_MAX_LEN]
```

在 `render()` 中，`block = TEMPLATE.format(...)` 之后、`# Optional partial-coverage lines (#120)` 之前插入：

```python
    note = format_note(d.get("note") or "")
    if note:
        block += f"Note: {note}\n"
```

把 summary 派生逻辑改为 note 优先：

```python
    if note:
        summary = f"CR batch {effective_status}: {note}"
    elif not has_blocking_policy:
        summary = (
            f"CR batch {effective_status}: {open_count} open issue(s)"
            if verdict == "needs_fix"
            else f"CR batch {effective_status}: no open issues"
        )
    elif blocking_open_count > 0:
        summary = f"CR batch {effective_status}: {blocking_open_count} blocking issue(s)"
    elif advisory_open_count > 0:
        summary = (
            f"CR batch {effective_status}: no blocking issues; "
            f"{advisory_open_count} advisory finding(s) remain"
        )
    else:
        summary = f"CR batch {effective_status}: no open issues"
```

XML trailer 的 summary 写出改为转义：

```python
        f"<summary>{escape(summary)}</summary>\n"
```

模块 docstring 的输入字段列表追加一行：

```text
  note               str  — optional one-line note (optional; normalized + escaped)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_cr_batch_trivial_check.py -v`
Expected: PASS（全部 8 个测试）

- [ ] **Step 5: 回归旧契约**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py -v`
Expected: PASS（旧 caller 无 note 行为不变）

- [ ] **Step 6: Commit**

```bash
git -C $WT add pi/github-code-review-batch/scripts/render_status_report.py tests/unit/test_cr_batch_trivial_check.py
git -C $WT commit -m "feat(cr-batch): add optional note to status report renderer (#223)"
```

---

### Task 2: trivial_check.py 纯函数层（验收 A1、A2、A3）

**Files:**
- Create: `pi/github-code-review-batch/scripts/trivial_check.py`（本任务先落纯函数与常量，main 在 Task 3）
- Test: `tests/unit/test_cr_batch_trivial_check.py`（追加 import 与测试）

**Interfaces:**
- Produces（Task 3 依赖）:
  - `normalize_pr_ref(ref: str, explicit_repo: str | None) -> tuple[str, int]`（repo 为空串表示待解析；冲突/非法抛 `ValueError`）
  - `parse_pr_view(raw: dict) -> dict`（校验 number/state/isDraft/changedFiles/headRefOid/reviews；非法抛 `ValueError`）
  - `inspect_metadata(reviews: list) -> str`（`"empty" | "present" | "unavailable"`）
  - `flatten_file_pages(raw: list) -> list[dict]`（页结构非法抛 `ValueError`）
  - `normalize_file(record: dict) -> dict`（`{path, status, previous_path}`；非法抛 `ValueError`）
  - `classify_files(files: list[dict]) -> dict`（`{files_total, markdown_files, non_markdown_files, rename_copy_files}`；重复路径抛 `ValueError`）
  - `evaluate(pr_data: dict) -> dict`（`{trivial, matched_rules, reason, stats}`）
  - `build_report_payload(pr_data: dict, result: dict) -> dict`
  - 常量：`SHA_RE`、`PR_URL_RE`、`OWNER_REPO_N_RE`、`VALID_FILE_STATUSES`、`PI_MARKER`、`META_MARKER`、`META_RE`、`GH_TIMEOUT`

- [ ] **Step 1: 写失败测试**

在 `tests/unit/test_cr_batch_trivial_check.py` 顶部 import 区追加：

```python
import trivial_check  # type: ignore[import-not-found]  # noqa: E402
```

文件末尾追加：

```python
# ---------------------------------------------------------------------------
# Task 2: trivial_check pure functions
# ---------------------------------------------------------------------------

def _pr_view(**overrides) -> dict:
    base = {
        "number": 123,
        "state": "OPEN",
        "isDraft": False,
        "changedFiles": 2,
        "headRefOid": "a" * 40,
        "reviews": [],
    }
    base.update(overrides)
    return base


def _file(path: str, status: str = "modified", previous: str | None = None) -> dict:
    rec = {"filename": path, "status": status}
    if previous is not None:
        rec["previous_filename"] = previous
    return rec


def _pr_data(files=None, **overrides) -> dict:
    base = {
        "number": 123,
        "state": "OPEN",
        "is_draft": False,
        "head_sha": "a" * 40,
        "changed_files": 2,
        "metadata_state": "empty",
        "files": files or [_file("README.md"), _file("docs/guide.md")],
    }
    base.update(overrides)
    return base


class TestNormalizePrRef:
    def test_number(self):
        assert trivial_check.normalize_pr_ref("205", None) == ("", 205)

    def test_number_with_repo(self):
        assert trivial_check.normalize_pr_ref("205", "o/r") == ("o/r", 205)

    def test_url(self):
        assert trivial_check.normalize_pr_ref(
            "https://github.com/o/r/pull/205", None
        ) == ("o/r", 205)

    def test_url_trailing_slash(self):
        assert trivial_check.normalize_pr_ref(
            "https://github.com/o/r/pull/205/", None
        ) == ("o/r", 205)

    def test_owner_repo_n(self):
        assert trivial_check.normalize_pr_ref("o/r#205", None) == ("o/r", 205)

    def test_url_repo_conflict(self):
        with pytest.raises(ValueError):
            trivial_check.normalize_pr_ref("https://github.com/o/r/pull/205", "x/y")

    def test_owner_repo_n_conflict(self):
        with pytest.raises(ValueError):
            trivial_check.normalize_pr_ref("o/r#205", "x/y")

    @pytest.mark.parametrize(
        "ref",
        ["", "abc", "https://gitlab.com/o/r/pull/1", "o/r#0", "0"],
    )
    def test_unsupported(self, ref):
        with pytest.raises(ValueError):
            trivial_check.normalize_pr_ref(ref, None)


class TestParsePrView:
    def test_ok(self):
        pr = trivial_check.parse_pr_view(_pr_view())
        assert pr["number"] == 123
        assert pr["state"] == "OPEN"
        assert pr["is_draft"] is False
        assert pr["changed_files"] == 2
        assert pr["head_sha"] == "a" * 40
        assert pr["reviews"] == []

    def test_rejects_bool_changed_files(self):
        with pytest.raises(ValueError):
            trivial_check.parse_pr_view(_pr_view(changedFiles=True))

    def test_rejects_bad_sha(self):
        with pytest.raises(ValueError):
            trivial_check.parse_pr_view(_pr_view(headRefOid="zzz"))

    def test_rejects_missing_reviews(self):
        view = _pr_view()
        del view["reviews"]
        with pytest.raises(ValueError):
            trivial_check.parse_pr_view(view)

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            trivial_check.parse_pr_view([])


class TestInspectMetadata:
    def test_empty_no_reviews(self):
        assert trivial_check.inspect_metadata([]) == "empty"

    def test_empty_other_comments(self):
        assert (
            trivial_check.inspect_metadata([{"body": "human comment"}]) == "empty"
        )

    def test_present(self):
        body = (
            "Generated with pi-coding-agent\n<!-- pi-cr-meta\n"
            '{"round": 1}\n-->\n'
        )
        assert trivial_check.inspect_metadata([{"body": body}]) == "present"

    def test_unavailable_broken_json(self):
        body = "Generated with pi-coding-agent\n<!-- pi-cr-meta\n{broken\n-->\n"
        assert trivial_check.inspect_metadata([{"body": body}]) == "unavailable"

    def test_unavailable_non_dict_review(self):
        assert trivial_check.inspect_metadata(["not a dict"]) == "unavailable"

    def test_unavailable_non_str_body(self):
        assert trivial_check.inspect_metadata([{"body": 42}]) == "unavailable"


class TestFlattenFilePages:
    def test_two_pages(self):
        raw = [[_file("a.md")], [_file("b.md")]]
        assert len(trivial_check.flatten_file_pages(raw)) == 2

    def test_rejects_non_list(self):
        with pytest.raises(ValueError):
            trivial_check.flatten_file_pages({})

    def test_rejects_non_list_page(self):
        with pytest.raises(ValueError):
            trivial_check.flatten_file_pages([[_file("a.md")], {}])


class TestNormalizeFile:
    def test_ok(self):
        assert trivial_check.normalize_file(_file("README.md")) == {
            "path": "README.md",
            "status": "modified",
            "previous_path": None,
        }

    def test_previous_filename(self):
        out = trivial_check.normalize_file(_file("b.md", "renamed", "a.py"))
        assert out["previous_path"] == "a.py"

    def test_rejects_missing_filename(self):
        with pytest.raises(ValueError):
            trivial_check.normalize_file({"status": "modified"})

    def test_rejects_unknown_status(self):
        with pytest.raises(ValueError):
            trivial_check.normalize_file(_file("a.md", "mystery"))

    def test_rejects_non_str_previous(self):
        with pytest.raises(ValueError):
            trivial_check.normalize_file(_file("a.md", "renamed", 42))


class TestClassifyFiles:
    def test_all_markdown(self):
        stats = trivial_check.classify_files([_file("a.md"), _file("docs/b.md")])
        assert stats == {
            "files_total": 2,
            "markdown_files": 2,
            "non_markdown_files": 0,
            "rename_copy_files": 0,
        }

    def test_mixed(self):
        stats = trivial_check.classify_files([_file("a.md"), _file("b.py")])
        assert stats["non_markdown_files"] == 1

    def test_rename_copy(self):
        stats = trivial_check.classify_files(
            [_file("b.md", "renamed", "a.py"), _file("c.md", "copied", "d.md")]
        )
        assert stats["rename_copy_files"] == 2

    def test_duplicate_raises(self):
        with pytest.raises(ValueError):
            trivial_check.classify_files([_file("a.md"), _file("a.md")])


class TestEvaluate:
    def test_trivial_hit(self):
        result = trivial_check.evaluate(_pr_data())
        assert result["trivial"] is True
        assert result["matched_rules"] == ["markdown-only"]

    def test_closed_not_trivial(self):
        assert trivial_check.evaluate(_pr_data(state="CLOSED"))["trivial"] is False

    def test_draft_not_trivial(self):
        assert trivial_check.evaluate(_pr_data(is_draft=True))["trivial"] is False

    def test_empty_files_not_trivial(self):
        assert (
            trivial_check.evaluate(_pr_data(files=[], changed_files=0))["trivial"]
            is False
        )

    def test_rename_not_trivial(self):
        data = _pr_data(files=[_file("b.md", "renamed", "a.py")])
        assert trivial_check.evaluate(data)["trivial"] is False

    def test_mixed_not_trivial(self):
        data = _pr_data(files=[_file("a.md"), _file("b.py")])
        assert trivial_check.evaluate(data)["trivial"] is False

    def test_metadata_present_not_trivial(self):
        data = _pr_data(metadata_state="present")
        assert trivial_check.evaluate(data)["trivial"] is False


class TestBuildReportPayload:
    def test_fixed_fields(self):
        result = trivial_check.evaluate(_pr_data())
        payload = trivial_check.build_report_payload(_pr_data(), result)
        assert payload["pr_number"] == 123
        assert payload["round"] == 1
        assert payload["previous_head_sha"] is None
        assert payload["status"] == "PASS"
        assert payload["blocking_open_count"] == 0
        assert payload["note"].startswith("trivial precheck skip: ")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_cr_batch_trivial_check.py -v`
Expected: FAIL（`import trivial_check` 失败）

- [ ] **Step 3: 实现 trivial_check.py 纯函数层**

创建 `pi/github-code-review-batch/scripts/trivial_check.py`：

```python
#!/usr/bin/env python3
"""Deterministic trivial-PR precheck for the github-code-review-batch skill.

Decides whether a PR is safe to skip LLM review (v1: open, non-draft,
first-round, complete file list, no rename/copy, all changed files end in
.md). Exit codes:
  0  data valid; trivial decision in stdout JSON (default mode) or the full
     status report (--report mode, trivial only)
  1  data valid but not trivial (--report mode only)
  2  data/API error — caller must fail open to the normal Step 1 path
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_status_report  # noqa: E402  (same-directory skill script)

GH_TIMEOUT = 30
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PR_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?$")
OWNER_REPO_N_RE = re.compile(r"^([^/\s]+)/([^/\s]+)#(\d+)$")
VALID_FILE_STATUSES = {
    "added",
    "modified",
    "deleted",
    "renamed",
    "copied",
    "changed",
    "unchanged",
}
PI_MARKER = "Generated with pi-coding-agent"
META_MARKER = "<!-- pi-cr-meta"
META_RE = re.compile(r"<!--\s*pi-cr-meta\s*\n(.*?)\n\s*-->", re.DOTALL)


def normalize_pr_ref(ref: str, explicit_repo: str | None) -> tuple[str, int]:
    """Parse a PR number, github.com PR URL, or owner/repo#N into (repo, number).

    The repo part is "" when only a bare number was given (caller resolves it
    later). Raises ValueError for unsupported refs or repo conflicts.
    """
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("empty PR ref")
    if ref.isdigit():
        number = int(ref)
        if number <= 0:
            raise ValueError(f"invalid PR number: {ref}")
        return (explicit_repo or ""), number
    match = PR_URL_RE.match(ref)
    if match:
        repo = f"{match.group(1)}/{match.group(2)}"
        number = int(match.group(3))
        if number <= 0:
            raise ValueError(f"invalid PR number: {ref}")
        if explicit_repo and explicit_repo.lower() != repo.lower():
            raise ValueError(f"repo conflict: URL says {repo}, --repo says {explicit_repo}")
        return repo, number
    match = OWNER_REPO_N_RE.match(ref)
    if match:
        repo = f"{match.group(1)}/{match.group(2)}"
        number = int(match.group(3))
        if number <= 0:
            raise ValueError(f"invalid PR number: {ref}")
        if explicit_repo and explicit_repo.lower() != repo.lower():
            raise ValueError(f"repo conflict: ref says {repo}, --repo says {explicit_repo}")
        return repo, number
    raise ValueError(f"unsupported PR ref: {ref!r}")


def parse_pr_view(raw: dict) -> dict:
    """Validate and normalize `gh pr view --json number,state,isDraft,changedFiles,headRefOid,reviews`."""
    if not isinstance(raw, dict):
        raise ValueError("pr view payload is not an object")
    number = raw.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise ValueError("pr view: number missing or invalid")
    state = raw.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("pr view: state missing or invalid")
    is_draft = raw.get("isDraft")
    if not isinstance(is_draft, bool):
        raise ValueError("pr view: isDraft missing or invalid")
    changed_files = raw.get("changedFiles")
    if isinstance(changed_files, bool) or not isinstance(changed_files, int) or changed_files < 0:
        raise ValueError("pr view: changedFiles missing or invalid")
    head_sha = raw.get("headRefOid")
    if not isinstance(head_sha, str) or not SHA_RE.match(head_sha):
        raise ValueError("pr view: headRefOid missing or invalid")
    reviews = raw.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("pr view: reviews missing or invalid")
    return {
        "number": number,
        "state": state,
        "is_draft": is_draft,
        "head_sha": head_sha,
        "changed_files": changed_files,
        "reviews": reviews,
    }


def inspect_metadata(reviews: list) -> str:
    """Classify pi-cr metadata presence: 'empty' | 'present' | 'unavailable'.

    'unavailable' covers malformed review records and pi-cr-marked comments
    whose metadata JSON cannot be parsed — the caller must fail open.
    """
    candidates: list[str] = []
    for review in reviews:
        if not isinstance(review, dict):
            return "unavailable"
        body = review.get("body")
        if not isinstance(body, str):
            return "unavailable"
        if PI_MARKER in body and META_MARKER in body:
            candidates.append(body)
    if not candidates:
        return "empty"
    for body in candidates:
        match = META_RE.search(body)
        if not match:
            return "unavailable"
        try:
            meta = json.loads(match.group(1))
        except json.JSONDecodeError:
            return "unavailable"
        if not isinstance(meta, dict):
            return "unavailable"
    return "present"


def flatten_file_pages(raw: list) -> list[dict]:
    """Flatten `gh api --paginate --slurp` output (array of page arrays)."""
    if not isinstance(raw, list):
        raise ValueError("paginated files payload is not an array")
    records: list[dict] = []
    for page in raw:
        if not isinstance(page, list):
            raise ValueError("paginated files page is not an array")
        records.extend(page)
    return records


def normalize_file(record: dict) -> dict:
    """Normalize one REST PR-file record into {path, status, previous_path}."""
    if not isinstance(record, dict):
        raise ValueError("file record is not an object")
    path = record.get("filename")
    if not isinstance(path, str) or not path:
        raise ValueError("file record: filename missing or invalid")
    status = record.get("status")
    if not isinstance(status, str) or status not in VALID_FILE_STATUSES:
        raise ValueError(f"file record: unknown status {status!r}")
    previous = record.get("previous_filename")
    if previous is not None and not isinstance(previous, str):
        raise ValueError("file record: previous_filename invalid")
    return {"path": path, "status": status, "previous_path": previous or None}


def classify_files(files: list[dict]) -> dict:
    """Count markdown/non-markdown/rename-copy files and detect duplicates."""
    seen: set[str] = set()
    markdown = 0
    non_markdown = 0
    rename_copy = 0
    for file in files:
        path = file["path"]
        if path in seen:
            raise ValueError(f"duplicate file path: {path}")
        seen.add(path)
        if file["status"] in ("renamed", "copied") or file["previous_path"]:
            rename_copy += 1
        if path.lower().endswith(".md"):
            markdown += 1
        else:
            non_markdown += 1
    return {
        "files_total": len(files),
        "markdown_files": markdown,
        "non_markdown_files": non_markdown,
        "rename_copy_files": rename_copy,
    }


def evaluate(pr_data: dict) -> dict:
    """Apply G0-G4; returns {trivial, matched_rules, reason, stats}.

    metadata_state 'unavailable' is handled by the caller (exit 2); here any
    non-'empty' state simply cannot be trivial.
    """
    stats = classify_files(pr_data["files"])
    if pr_data["metadata_state"] != "empty":
        return {"trivial": False, "matched_rules": [], "reason": "metadata not empty", "stats": stats}
    if pr_data["state"] != "OPEN" or pr_data["is_draft"]:
        return {"trivial": False, "matched_rules": [], "reason": "not open or draft", "stats": stats}
    if pr_data["changed_files"] <= 0:
        return {"trivial": False, "matched_rules": [], "reason": "no changed files", "stats": stats}
    if stats["rename_copy_files"] > 0:
        return {"trivial": False, "matched_rules": [], "reason": "rename/copy present", "stats": stats}
    if stats["non_markdown_files"] > 0:
        return {"trivial": False, "matched_rules": [], "reason": "non-markdown files present", "stats": stats}
    return {
        "trivial": True,
        "matched_rules": ["markdown-only"],
        "reason": f"all {stats['files_total']} changed files have .md extension",
        "stats": stats,
    }


def build_report_payload(pr_data: dict, result: dict) -> dict:
    """Assemble the fixed Round-1 PASS payload for render_status_report."""
    return {
        "pr_number": pr_data["number"],
        "round": 1,
        "head_sha": pr_data["head_sha"],
        "previous_head_sha": None,
        "open_count": 0,
        "new_count": 0,
        "unresolved_count": 0,
        "resolved_count": 0,
        "acknowledged_count": 0,
        "blocking_open_count": 0,
        "blocking_new_count": 0,
        "advisory_open_count": 0,
        "advisory_new_count": 0,
        "critical_count": 0,
        "status": "PASS",
        "note": f"trivial precheck skip: {result['reason']}",
    }
```

（`fetch_pr_data` / `_resolve_repo` / `main` 在 Task 3 加入。）

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_cr_batch_trivial_check.py -v`
Expected: PASS（Task 1 的 8 个 + Task 2 新增全部通过）

- [ ] **Step 5: Commit**

```bash
git -C $WT add pi/github-code-review-batch/scripts/trivial_check.py tests/unit/test_cr_batch_trivial_check.py
git -C $WT commit -m "feat(cr-batch): add trivial_check pure-function layer (#223)"
```

---

### Task 3: trivial_check.py fetch 层与 main（验收 A4、A5）

**Files:**
- Modify: `pi/github-code-review-batch/scripts/trivial_check.py`（追加 fetch/main）
- Test: `tests/unit/test_cr_batch_trivial_check.py`（追加 fetch/main 测试）

**Interfaces:**
- Consumes: Task 2 的全部纯函数与常量。
- Produces: `fetch_pr_data(ref: str, repo: str | None) -> dict`（抛 `ValueError`/`RuntimeError`/`subprocess.TimeoutExpired`/`OSError`）；`main(argv: list[str] | None = None) -> int`。

- [ ] **Step 1: 写失败测试**

文件末尾追加：

```python
# ---------------------------------------------------------------------------
# Task 3: fetch layer and main
# ---------------------------------------------------------------------------

VIEW_JSON = json.dumps(
    {
        "number": 123,
        "state": "OPEN",
        "isDraft": False,
        "changedFiles": 2,
        "headRefOid": "a" * 40,
        "reviews": [],
    }
)
FILES_JSON = json.dumps(
    [
        [
            {"filename": "README.md", "status": "modified"},
            {"filename": "docs/guide.md", "status": "added"},
        ]
    ]
)


def _gh_ok(argv: list[str], stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, 0, stdout, "")


def _gh_fail(argv: list[str], stderr: str = "boom") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(argv, 1, "", stderr)


class TestFetchPrData:
    def test_commands_use_paginate_slurp(self, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            if argv[1] == "pr":
                return _gh_ok(argv, VIEW_JSON)
            return _gh_ok(argv, FILES_JSON)

        monkeypatch.setattr(trivial_check.subprocess, "run", fake_run)
        trivial_check.fetch_pr_data("o/r#123", None)
        api_call = next(c for c in calls if c[1] == "api")
        assert api_call[2] == "--paginate"
        assert api_call[3] == "--slurp"
        assert api_call[4] == "repos/o/r/pulls/123/files?per_page=100"
        assert "-f" not in api_call and "--field" not in api_call

    def test_ok(self, monkeypatch):
        def fake_run(argv, **kwargs):
            if argv[1] == "pr":
                return _gh_ok(argv, VIEW_JSON)
            return _gh_ok(argv, FILES_JSON)

        monkeypatch.setattr(trivial_check.subprocess, "run", fake_run)
        data = trivial_check.fetch_pr_data("123", "o/r")
        assert data["number"] == 123
        assert data["metadata_state"] == "empty"
        assert len(data["files"]) == 2

    def test_view_failure_raises(self, monkeypatch):
        monkeypatch.setattr(
            trivial_check.subprocess, "run", lambda argv, **kw: _gh_fail(argv)
        )
        with pytest.raises(RuntimeError):
            trivial_check.fetch_pr_data("123", "o/r")

    def test_count_mismatch_raises(self, monkeypatch):
        view = json.loads(VIEW_JSON)
        view["changedFiles"] = 3

        def fake_run(argv, **kwargs):
            if argv[1] == "pr":
                return _gh_ok(argv, json.dumps(view))
            return _gh_ok(argv, FILES_JSON)

        monkeypatch.setattr(trivial_check.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="incomplete"):
            trivial_check.fetch_pr_data("123", "o/r")

    def test_101_files_hidden_source_fails_open(self, monkeypatch):
        view = json.loads(VIEW_JSON)
        view["changedFiles"] = 101
        files = [[{"filename": f"doc{i}.md", "status": "modified"} for i in range(100)]]

        def fake_run(argv, **kwargs):
            if argv[1] == "pr":
                return _gh_ok(argv, json.dumps(view))
            return _gh_ok(argv, json.dumps(files))

        monkeypatch.setattr(trivial_check.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="incomplete"):
            trivial_check.fetch_pr_data("123", "o/r")

    def test_timeout_raises(self, monkeypatch):
        def fake_run(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 30)

        monkeypatch.setattr(trivial_check.subprocess, "run", fake_run)
        with pytest.raises(subprocess.TimeoutExpired):
            trivial_check.fetch_pr_data("123", "o/r")

    def test_gh_missing_raises(self, monkeypatch):
        def fake_run(argv, **kwargs):
            raise FileNotFoundError("gh")

        monkeypatch.setattr(trivial_check.subprocess, "run", fake_run)
        with pytest.raises(OSError):
            trivial_check.fetch_pr_data("123", "o/r")


class TestMain:
    def _patch_fetch(self, monkeypatch, pr_data):
        monkeypatch.setattr(trivial_check, "fetch_pr_data", lambda ref, repo: pr_data)

    def test_report_trivial_exit0(self, monkeypatch, capsys):
        self._patch_fetch(monkeypatch, _pr_data())
        assert trivial_check.main(["123", "--report"]) == 0
        out = capsys.readouterr().out
        assert "Status: PASS" in out
        assert "<verdict>approved</verdict>" in out
        assert "Note: trivial precheck skip:" in out

    def test_report_not_trivial_exit1(self, monkeypatch, capsys):
        self._patch_fetch(monkeypatch, _pr_data(state="CLOSED"))
        assert trivial_check.main(["123", "--report"]) == 1
        assert capsys.readouterr().out == ""

    def test_report_unavailable_exit2(self, monkeypatch, capsys):
        self._patch_fetch(monkeypatch, _pr_data(metadata_state="unavailable"))
        assert trivial_check.main(["123", "--report"]) == 2
        assert capsys.readouterr().out == ""

    def test_fetch_error_exit2(self, monkeypatch, capsys):
        def boom(ref, repo):
            raise RuntimeError("gh pr view failed")

        monkeypatch.setattr(trivial_check, "fetch_pr_data", boom)
        assert trivial_check.main(["123", "--report"]) == 2
        assert capsys.readouterr().out == ""

    def test_default_mode_json(self, monkeypatch, capsys):
        self._patch_fetch(monkeypatch, _pr_data())
        assert trivial_check.main(["123"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["trivial"] is True
        assert out["metadata_state"] == "empty"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_cr_batch_trivial_check.py -v`
Expected: FAIL（`fetch_pr_data` / `main` 不存在）

- [ ] **Step 3: 实现 fetch 层与 main**

在 `trivial_check.py` 的 `build_report_payload` 之后追加：

```python
def _run_gh(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def _resolve_repo() -> str:
    proc = _run_gh(["repo", "view", "--json", "nameWithOwner"])
    if proc.returncode != 0:
        raise RuntimeError(f"gh repo view failed: {proc.stderr.strip()}")
    try:
        name = json.loads(proc.stdout).get("nameWithOwner")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh repo view payload invalid: {exc}") from exc
    if not isinstance(name, str) or not name:
        raise RuntimeError("gh repo view: nameWithOwner missing")
    return name


def fetch_pr_data(ref: str, repo: str | None) -> dict:
    """Fetch PR base fields and the complete paginated file list via gh."""
    resolved_repo, number = normalize_pr_ref(ref, repo)
    if not resolved_repo:
        resolved_repo = _resolve_repo()
    view = _run_gh(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            resolved_repo,
            "--json",
            "number,state,isDraft,changedFiles,headRefOid,reviews",
        ]
    )
    if view.returncode != 0:
        raise RuntimeError(f"gh pr view failed: {view.stderr.strip()}")
    try:
        pr = parse_pr_view(json.loads(view.stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"gh pr view payload invalid: {exc}") from exc
    files_proc = _run_gh(
        ["api", "--paginate", "--slurp", f"repos/{resolved_repo}/pulls/{number}/files?per_page=100"]
    )
    if files_proc.returncode != 0:
        raise RuntimeError(f"gh api files failed: {files_proc.stderr.strip()}")
    try:
        records = flatten_file_pages(json.loads(files_proc.stdout))
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"gh api files payload invalid: {exc}") from exc
    files = [normalize_file(record) for record in records]
    if len(files) != pr["changed_files"]:
        raise RuntimeError(
            f"file list incomplete: changedFiles={pr['changed_files']}, got {len(files)}"
        )
    return {
        "number": pr["number"],
        "state": pr["state"],
        "is_draft": pr["is_draft"],
        "head_sha": pr["head_sha"],
        "changed_files": pr["changed_files"],
        "metadata_state": inspect_metadata(pr["reviews"]),
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", help="PR number, github.com PR URL, or owner/repo#N")
    parser.add_argument("--repo", default=None, help="owner/repo override")
    parser.add_argument(
        "--report",
        action="store_true",
        help="emit the full status report on trivial hit (Step 1 mode)",
    )
    args = parser.parse_args(argv)

    try:
        pr_data = fetch_pr_data(args.pr, args.repo)
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"trivial_check: {exc}", file=sys.stderr)
        return 2

    if pr_data["metadata_state"] == "unavailable":
        print("trivial_check: pi-cr metadata state unavailable", file=sys.stderr)
        return 2

    result = evaluate(pr_data)

    if args.report:
        if not result["trivial"]:
            print(f"trivial_check: not trivial: {result['reason']}", file=sys.stderr)
            return 1
        try:
            payload = build_report_payload(pr_data, result)
            sys.stdout.write(render_status_report.render(payload))
        except Exception as exc:  # noqa: BLE001 - renderer must never emit a partial report
            print(f"trivial_check: render failed: {exc}", file=sys.stderr)
            return 2
        return 0

    out = {
        "trivial": result["trivial"],
        "matched_rules": result["matched_rules"],
        "reason": result["reason"],
        "stats": result["stats"],
        "pr": {
            "number": pr_data["number"],
            "state": pr_data["state"],
            "is_draft": pr_data["is_draft"],
            "head_sha": pr_data["head_sha"],
        },
        "metadata_state": pr_data["metadata_state"],
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_cr_batch_trivial_check.py -v`
Expected: PASS（全部测试）

- [ ] **Step 5: 脚本可编译 + 全量回归**

Run: `python -m py_compile pi/github-code-review-batch/scripts/trivial_check.py pi/github-code-review-batch/scripts/render_status_report.py && uv run pytest tests/unit/test_cr_batch_contracts.py -v`
Expected: 编译通过；contract tests 通过（portability 测试此时会因 SCRIPT_NAMES 未含新脚本而仍绿，Task 5 再收紧）

- [ ] **Step 6: Commit**

```bash
git -C $WT add pi/github-code-review-batch/scripts/trivial_check.py tests/unit/test_cr_batch_trivial_check.py
git -C $WT commit -m "feat(cr-batch): add trivial_check fetch layer and CLI (#223)"
```

---

### Task 4: flow.md / SKILL.md / edge-cases.md 契约更新（验收 A6）

**Files:**
- Modify: `pi/github-code-review-batch/references/flow.md`
- Modify: `pi/github-code-review-batch/SKILL.md`
- Modify: `pi/github-code-review-batch/references/edge-cases.md`

**Interfaces:**
- Consumes: Task 3 的 CLI 契约（`trivial_check.py <PR> --report`，exit 0/1/2）。

- [ ] **Step 1: 改 flow.md Step 0.3 / 0.4**

Step 0.3 中把：

```markdown
- 否 → 首次审查 → 走完整流程（Round = 1）
```

改为：

```markdown
- 否 → 首次审查 → 走完整流程（Round = 1）；metadata_state=empty，Step 1 允许运行 trivial precheck
```

Step 0.4 中把：

```markdown
- `gh pr view --json reviews` 失败 → 视为无 previous review，继续正常 Round-1 流程
```

改为：

```markdown
- `gh pr view --json reviews` 失败 → 视为无 previous review，继续正常 Round-1 流程；但此时 metadata 状态未知（unavailable），Step 1 不得运行 trivial precheck，不得走 approved 快速路径
```

- [ ] **Step 2: 改 flow.md Step 1**

把 Step 1 整节（从 `## Step 1: PR 资格审查 {#step-1}` 到 `如何判断 trivial PR` 清单结束）替换为：

```markdown
## Step 1: PR 资格审查 {#step-1}

### 1.0 确定性 trivial precheck（仅首轮，metadata_state=empty）

只有 Step 0 确认无 previous pi-cr metadata（metadata_state=empty）的首轮才运行本小节；NO_NEW_COMMITS、delta-review、metadata 状态未知（unavailable）分支不运行。

使用 `bash` 执行（PR 引用必须带引号，`owner/repo#N` 未引用时 `#` 会被 shell 当作注释起点）：

```bash
set +e
python3 scripts/trivial_check.py "<PR>" --report
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
    # stdout 已是完整状态报告（Status: PASS + approved verdict + Note）
    # 原样保留 stdout 并结束，不走 Step 2-9，不发 PR 评论
    exit 0
elif [ "$rc" -eq 1 ]; then
    # 数据有效但非 trivial（含 closed/draft/rename/非 .md），继续下方检查
    :
else
    # 脚本/API 异常（exit 2），记录 stderr 后继续下方检查（fail-open）
    :
fi
```

trivial 判定权完全属于 `scripts/trivial_check.py`（v1 规则：OPEN + 非 draft + 完整文件列表 + 无 rename/copy + 全部变更文件以 `.md` 结尾）。LLM 不得自行宣布 trivial。

### 1.1 其余资格检查

使用 `bash` 执行 `gh pr view <PR>` 和 `gh pr view <PR> --comments` 检查 PR 状态。

检查以下任一条件：

- PR 是否已关闭 (state: CLOSED)
- PR 是否为草稿 (isDraft: true)
- PR 是否是自动化 PR（PR 标题或描述包含 "automated"、"bot" 等标识）

如果上述任一条件为真，立即停止执行，向用户说明原因，不继续审查。

**为什么不检查"是否已有 bot 评论"**：与监听模式不同，非监听模式下同一 PR 会被外部调度器多次审查（首次 → 增量 → 增量...），这是预期行为。Step 0 会通过 metadata 和 SHA 对比自动判断是首次审查还是增量审查。

**为什么不跳过 AI 生成的 PR**：AI 生成的 PR 也可能存在规范违规或逻辑错误，因此不跳过。
```

- [ ] **Step 3: 改 SKILL.md 输出契约**

把：

```markdown
每次执行（除 [Step 1](references/flow.md#step-1)/[Step 7](references/flow.md#step-7) 提前终止外）必须产出三个产物：
```

改为：

```markdown
每次执行（除 [Step 7](references/flow.md#step-7) 提前终止外）必须产出三个产物；[Step 1](references/flow.md#step-1) 的 trivial 快速路径豁免终端 review 报告和 PR 评论，但必须产出终端状态报告（产物 3）：
```

- [ ] **Step 4: 改 edge-cases.md trivial 行**

把：

```markdown
| PR 是 trivial/自动化 | [Step 1](flow.md#step-1) 捕获，停止执行并向用户说明 |
```

改为：

```markdown
| PR 是 trivial（首轮、纯 .md） | Step 1 的 `trivial_check.py --report` 确定性判定，输出 PASS + approved 状态报告后结束，不发 PR 评论 |
| PR 是自动化 | [Step 1](flow.md#step-1) 现有检查捕获，停止执行并向用户说明 |
```

- [ ] **Step 5: 验证文档一致性**

Run: `grep -n "trivial_check.py" pi/github-code-review-batch/references/flow.md pi/github-code-review-batch/SKILL.md pi/github-code-review-batch/references/edge-cases.md`
Expected: 三处文件均出现；flow.md 中不再出现 "如何判断 trivial PR"。

- [ ] **Step 6: Commit**

```bash
git -C $WT add pi/github-code-review-batch/references/flow.md pi/github-code-review-batch/SKILL.md pi/github-code-review-batch/references/edge-cases.md
git -C $WT commit -m "docs(cr-batch): wire trivial precheck into Step 0/1 contracts (#223)"
```

---

### Task 5: contract test 收紧与全量验收（验收 A5、A6）

**Files:**
- Modify: `tests/unit/test_cr_batch_contracts.py`

**Interfaces:**
- Consumes: Task 1-4 的全部产物。

- [ ] **Step 1: 写失败测试**

在 `TestPortability` 中把 `SCRIPT_NAMES` 改为：

```python
    SCRIPT_NAMES = [
        "build_review_body.py",
        "compress_diff.py",
        "parse_metadata.py",
        "render_status_report.py",
        "trivial_check.py",
    ]
```

把 stdlib 检查的本地模块白名单从 `m != "issue_policy"` 改为：

```python
            non_stdlib = sorted(
                {
                    m
                    for m in imports
                    if m not in sys.stdlib_module_names
                    and m not in ("issue_policy", "render_status_report")
                }
            )
```

在文件末尾追加 flow 契约测试类（`texts` fixture 是 class-scoped，新类必须自带）：

```python
class TestTrivialPrecheckFlow:
    @pytest.fixture(scope="class")
    def texts(self) -> dict[str, str]:
        return {
            "flow": (SKILL_DIR / "references" / "flow.md").read_text(encoding="utf-8"),
        }

    def test_flow_documents_metadata_state_gate(self, texts):
        flow = texts["flow"]
        assert "metadata_state=empty" in flow
        assert "unavailable" in flow
        assert "trivial_check.py" in flow
        assert "set +e" in flow
        assert "如何判断 trivial PR" not in flow
        assert "LLM 不得自行宣布 trivial" in flow
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_cr_batch_contracts.py -v`
Expected: FAIL（`trivial_check.py` 的 `render_status_report` import 被 portability 检查判为 non-stdlib；flow 断言缺失）

- [ ] **Step 3: 全量验收**

Run: `uv run pytest tests/unit/test_cr_batch_trivial_check.py tests/unit/test_cr_batch_contracts.py -v && python -m py_compile pi/github-code-review-batch/scripts/trivial_check.py pi/github-code-review-batch/scripts/render_status_report.py && uv run ruff check tests/ && uv run black --check tests/ --line-length 100`
Expected: 全部通过

- [ ] **Step 4: 行数核对**

Run: `git -C $WT diff main --numstat -- 'pi/github-code-review-batch/scripts/*.py'`
Expected: 生产代码新增 ≤200 行（tests 与 .md 不计）

- [ ] **Step 5: Commit**

```bash
git -C $WT add tests/unit/test_cr_batch_contracts.py
git -C $WT commit -m "test(cr-batch): enforce trivial precheck contracts (#223)"
```

---

## Self-Review

- **Spec coverage**：§5.1 CLI/退出码 → Task 3；§5.2 数据获取/完整性 → Task 3 + A4 测试；§5.3 metadata 防护 → Task 2 `inspect_metadata` + Task 3 unavailable→exit 2；§5.4 规则 G0-G4 → Task 2 `evaluate`；§6.1 report 接线 → Task 3 `--report`；§6.2 note → Task 1；§7 文档契约 → Task 4；§8 错误处理 → Task 3；§9 可测性拆分 → Task 2/3 函数表；§10 验收 A1-A6/U1/U2 → A1-A6 由 Task 1-5 覆盖，U1/U2 为部署后用户实测（不在本 plan 内执行）。
- **Placeholder scan**：无 TBD/TODO；所有代码块为完整实现。
- **Type consistency**：`normalize_pr_ref -> tuple[str, int]`、`parse_pr_view -> dict`、`inspect_metadata -> str`、`flatten_file_pages -> list[dict]`、`normalize_file -> dict`、`classify_files -> dict`、`evaluate -> dict`、`build_report_payload -> dict`、`fetch_pr_data -> dict`、`main -> int` 在 Task 2/3 的 Interfaces 与测试中一致。
