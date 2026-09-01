# auto-merge-guarded Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-file Python daemon script that auto-approves and squash-merges whitelisted collaborators' PRs after CI green + Zima CR convergence, with Pushover notifications, scheduled by cron every 45 minutes.

**Architecture:** One stdlib-only Python script (`examples/auto-merge/auto-merge-guarded.py`) with pure gate functions (unit-testable, fixture JSON in → decision out) and side-effecting action functions (gh CLI subprocess wrappers). A six-gate check chain runs per open PR; all gates pass → five-step action chain (remove needs-fix → approve → rerun-failed-jobs → verify CLEAN → squash merge). Config lives at `~/.zima/configs/auto-merge.yaml` (not in repo); the repo ships an example template. Audit trail is JSONL at `~/.zima/logs/auto-merge.log`.

**Tech Stack:** Python 3.10+ stdlib only (argparse, dataclasses, json, subprocess, urllib, fcntl, fnmatch, pathlib). `gh` CLI for all GitHub operations. pytest for unit tests. Pushover HTTP API for notifications.

## Global Constraints

- Zero upstream changes: no `zima/` package source modifications; script lives in `examples/auto-merge/` and is deployed by copying to `~/.zima/scripts/`
- Python 3.10+; stdlib only; no third-party dependencies
- All secrets externalized: Pushover keys read from `~/.config/claude-notify.json` (fields `PUSHOVER_API_KEY` / `PUSHOVER_USER_KEY`); GitHub auth via existing `gh` login state; no secrets in repo
- Scheduler: user crontab `*/45 * * * *` (daemon schedules cannot run non-PJob scripts — confirmed in `zima/core/daemon_scheduler.py` `_start_pjob`)
- Code comments and commit messages in English; Black 100-char formatting; ruff clean
- Phase 0 ships with `--notify-only` in the crontab entry; real merge enabled in Phase 1 by removing the flag
- Pushover message body truncated by **characters** (max 250), never bytes (UTF-8 Chinese would corrupt)
- Whitelist is the authorization boundary: approve is issued as the owner account, only for configured (repo, author) pairs

---

## File Structure

| File | Responsibility |
|------|----------------|
| `examples/auto-merge/auto-merge-guarded.py` | The whole script: config load, audit log, 6 gates, CR-meta parsing, action chain, Pushover notify, CLI, flock |
| `examples/auto-merge/auto-merge.yaml.example` | Config template with example values (no real whitelist) |
| `examples/auto-merge/README.md` | Deployment guide: copy script, write config, crontab entry, Phase 0→1 upgrade |
| `tests/unit/test_auto_merge_guarded.py` | Unit tests for all pure functions + orchestration with injected fakes |
| `~/.zima/scripts/auto-merge-guarded.py` | Deployed copy (not in repo) |
| `~/.zima/configs/auto-merge.yaml` | Real config: whitelist, checks, cr_pjob_code (not in repo) |
| `~/.zima/logs/auto-merge.log` | JSONL audit log (runtime, not in repo) |

---

### Task 1: Script skeleton — config loading + audit logger

**Files:**
- Create: `examples/auto-merge/auto-merge-guarded.py`
- Test: `tests/unit/test_auto_merge_guarded.py`

**Interfaces:**
- Produces: `AppConfig` / `RepoConfig` dataclasses, `load_config(path: Path) -> AppConfig`, `AuditLogger(path: Path)` with `.log(entry: dict) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_auto_merge_guarded.py`:

```python
"""Unit tests for examples/auto-merge/auto-merge-guarded.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "auto-merge" / "auto-merge-guarded.py"
)


def _load_script():
    """Load the script as a module via importlib (file has a hyphen, not importable by name)."""
    spec = importlib.util.spec_from_file_location("auto_merge_guarded", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


amg = _load_script()


class TestLoadConfig:
    def test_load_config_parses_repos(self, tmp_path):
        cfg_file = tmp_path / "auto-merge.yaml"
        cfg_file.write_text(
            """
enabled: true
pushover:
  config_file: "~/.config/claude-notify.json"
repos:
  zhuxixi/pi-agent-board:
    allow_authors: [ccccyk0919]
    required_checks: ["Test (Node 22)", "Test (Node 24)"]
    expected_failing_checks: ["Owner approval policy"]
    merge_method: squash
    delete_branch: true
    sensitive_paths: [".github/**", "*.pjob.*"]
    cr_pjob_code: pi-agent-board-pi-cr-job
""",
            encoding="utf-8",
        )
        cfg = amg.load_config(cfg_file)
        assert cfg.enabled is True
        assert cfg.pushover_config_file == "~/.config/claude-notify.json"
        repo = cfg.repos["zhuxixi/pi-agent-board"]
        assert repo.allow_authors == ["ccccyk0919"]
        assert repo.required_checks == ["Test (Node 22)", "Test (Node 24)"]
        assert repo.expected_failing_checks == ["Owner approval policy"]
        assert repo.merge_method == "squash"
        assert repo.delete_branch is True
        assert repo.sensitive_paths == [".github/**", "*.pjob.*"]
        assert repo.cr_pjob_code == "pi-agent-board-pi-cr-job"

    def test_load_config_missing_file_raises(self, tmp_path):
        import pytest

        with pytest.raises(FileNotFoundError):
            amg.load_config(tmp_path / "nope.yaml")


class TestAuditLogger:
    def test_log_writes_jsonl_line(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = amg.AuditLogger(log_path)
        logger.log({"ts": "2026-08-30T00:00:00+00:00", "repo": "r", "pr": 1, "decision": "skip"})
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["decision"] == "skip"

    def test_log_appends_not_overwrites(self, tmp_path):
        log_path = tmp_path / "audit.log"
        logger = amg.AuditLogger(log_path)
        logger.log({"n": 1})
        logger.log({"n": 2})
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `FileNotFoundError` from `spec_from_file_location` (script does not exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `examples/auto-merge/auto-merge-guarded.py`:

```python
#!/usr/bin/env python3
"""auto-merge-guarded: auto approve + squash merge after CR convergence.

Whitelisted collaborators' PRs are merged automatically once CI required
checks are green and the Zima CR round has safely converged.  Scheduled by
cron every 45 minutes.  All secrets live outside this file (Pushover keys
in ~/.config/claude-notify.json, GitHub auth via the gh CLI login state).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoConfig:
    """Per-repo rules loaded from auto-merge.yaml."""

    allow_authors: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    expected_failing_checks: list[str] = field(default_factory=list)
    merge_method: str = "squash"
    delete_branch: bool = True
    sensitive_paths: list[str] = field(default_factory=list)
    cr_pjob_code: str = ""


@dataclass
class AppConfig:
    """Top-level config loaded from auto-merge.yaml."""

    enabled: bool = True
    pushover_config_file: str = "~/.config/claude-notify.json"
    repos: dict[str, RepoConfig] = field(default_factory=dict)


def load_config(path: Path) -> AppConfig:
    """Load auto-merge.yaml into an AppConfig.  Raises FileNotFoundError."""
    data = json.loads(json.dumps(_read_yaml(path)))
    cfg = AppConfig()
    cfg.enabled = bool(data.get("enabled", True))
    pushover = data.get("pushover") or {}
    cfg.pushover_config_file = pushover.get("config_file", cfg.pushover_config_file)
    for repo_name, repo_data in (data.get("repos") or {}).items():
        cfg.repos[repo_name] = RepoConfig(
            allow_authors=list(repo_data.get("allow_authors") or []),
            required_checks=list(repo_data.get("required_checks") or []),
            expected_failing_checks=list(repo_data.get("expected_failing_checks") or []),
            merge_method=repo_data.get("merge_method", "squash"),
            delete_branch=bool(repo_data.get("delete_branch", True)),
            sensitive_paths=list(repo_data.get("sensitive_paths") or []),
            cr_pjob_code=repo_data.get("cr_pjob_code", ""),
        )
    return cfg


def _read_yaml(path: Path) -> dict:
    """Minimal YAML subset parser: flat key/value maps and lists of scalars.

    The config schema only needs nested dicts and scalar lists, so a tiny
    indentation-based parser avoids a third-party dependency.  Raises
    FileNotFoundError when the file is missing.
    """
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if ":" in content:
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                child: dict = {}
                parent[key] = child
                stack.append((indent, child))
            elif value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                parent[key] = [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
            else:
                parent[key] = _scalar(value)
    return root


def _scalar(value: str):
    """Coerce a YAML scalar string to bool/int/float/str."""
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip("'\"")


class AuditLogger:
    """Append-only JSONL audit log."""

    def __init__(self, path: Path):
        self.path = path

    def log(self, entry: dict) -> None:
        """Append one JSON object as a single line."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): script skeleton with config loading and JSONL audit logger"
```

---

### Task 2: Gates 1-2 — candidate filter + sensitive path guard

**Files:**
- Modify: `examples/auto-merge/auto-merge-guarded.py` (append gate functions)
- Test: `tests/unit/test_auto_merge_guarded.py` (append test classes)

**Interfaces:**
- Consumes: nothing new
- Produces: `GateResult(passed: bool, decision: str, reason: str)`; `gate_candidate(pr: dict, allow_authors: list[str]) -> GateResult`; `gate_sensitive_paths(files: list[str], sensitive_paths: list[str]) -> GateResult`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auto_merge_guarded.py`:

```python
class TestGateCandidate:
    def _pr(self, **overrides):
        pr = {
            "number": 1,
            "title": "t",
            "author": {"login": "ccccyk0919"},
            "state": "OPEN",
            "isDraft": False,
        }
        pr.update(overrides)
        return pr

    def test_open_whitelisted_non_draft_passes(self):
        result = amg.gate_candidate(self._pr(), ["ccccyk0919"])
        assert result.passed is True
        assert result.decision == "merge"

    def test_author_not_whitelisted_skips(self):
        result = amg.gate_candidate(self._pr(author={"login": "stranger"}), ["ccccyk0919"])
        assert result.passed is False
        assert result.decision == "skip"
        assert "whitelist" in result.reason

    def test_draft_skips(self):
        result = amg.gate_candidate(self._pr(isDraft=True), ["ccccyk0919"])
        assert result.passed is False
        assert result.decision == "skip"

    def test_closed_state_skips(self):
        result = amg.gate_candidate(self._pr(state="CLOSED"), ["ccccyk0919"])
        assert result.passed is False
        assert result.decision == "skip"


class TestGateSensitivePaths:
    def test_no_match_passes(self):
        result = amg.gate_sensitive_paths(["src/main.ts", "README.md"], [".github/**"])
        assert result.passed is True

    def test_workflow_file_blocks(self):
        result = amg.gate_sensitive_paths(
            ["src/main.ts", ".github/workflows/ci.yml"], [".github/**"]
        )
        assert result.passed is False
        assert result.decision == "attention"
        assert ".github/workflows/ci.yml" in result.reason

    def test_glob_pattern_matches(self):
        result = amg.gate_sensitive_paths(["foo.pjob.bar"], ["*.pjob.*"])
        assert result.passed is False
        assert result.decision == "attention"

    def test_empty_sensitive_paths_passes(self):
        result = amg.gate_sensitive_paths(["anything.ts"], [])
        assert result.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `AttributeError: module 'auto_merge_guarded' has no attribute 'gate_candidate'`

- [ ] **Step 3: Write minimal implementation**

Append to `examples/auto-merge/auto-merge-guarded.py`:

```python
import fnmatch


@dataclass
class GateResult:
    """Outcome of one gate: passed flag plus a decision and human reason.

    decision is one of: merge (keep going), skip (silent, not a candidate),
    attention (notify owner, never auto-merge), waiting (silent, retry next
    round), error (notify owner, abort this PR).
    """

    passed: bool
    decision: str
    reason: str


def gate_candidate(pr: dict, allow_authors: list[str]) -> GateResult:
    """Gate 1: PR must be open, non-draft, and authored by a whitelisted user."""
    if pr.get("state") != "OPEN":
        return GateResult(False, "skip", f"PR #{pr.get('number')} state={pr.get('state')}")
    if pr.get("isDraft"):
        return GateResult(False, "skip", f"PR #{pr.get('number')} is draft")
    author = (pr.get("author") or {}).get("login", "")
    if author not in allow_authors:
        return GateResult(False, "skip", f"author {author!r} not in whitelist")
    return GateResult(True, "merge", "candidate ok")


def gate_sensitive_paths(files: list[str], sensitive_paths: list[str]) -> GateResult:
    """Gate 2: changed files must not match any sensitive glob pattern.

    Sensitive paths (workflows, CI config) can rewrite the review and gate
    rules themselves, so they always require a human.
    """
    for path in files:
        for pattern in sensitive_paths:
            if fnmatch.fnmatch(path, pattern):
                return GateResult(
                    False,
                    "attention",
                    f"sensitive path {path!r} matches {pattern!r}",
                )
    return GateResult(True, "merge", "no sensitive paths")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): gates 1-2 — candidate filter and sensitive path guard"
```

---

### Task 3: Gates 3-4 — required checks green + mergeable

**Files:**
- Modify: `examples/auto-merge/auto-merge-guarded.py` (append gate functions)
- Test: `tests/unit/test_auto_merge_guarded.py` (append test classes)

**Interfaces:**
- Consumes: `GateResult` from Task 2
- Produces: `gate_required_checks(check_runs: list[dict], required: list[str], expected_failing: list[str]) -> GateResult`; `gate_mergeable(mergeable: str) -> GateResult`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auto_merge_guarded.py`:

```python
class TestGateRequiredChecks:
    def _runs(self, *pairs):
        # pairs of (name, conclusion); later entries are newer (API returns newest first)
        return [{"name": n, "conclusion": c, "status": "completed"} for n, c in pairs]

    def test_all_required_success_passes(self):
        runs = self._runs(("Test (Node 22)", "success"), ("Test (Node 24)", "success"))
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is True

    def test_required_failure_waits(self):
        runs = self._runs(("Test (Node 22)", "failure"), ("Test (Node 24)", "success"))
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is False
        assert result.decision == "waiting"
        assert "Test (Node 22)" in result.reason

    def test_expected_failing_check_ignored(self):
        runs = self._runs(
            ("Test (Node 22)", "success"),
            ("Test (Node 24)", "success"),
            ("Owner approval policy", "failure"),
        )
        result = amg.gate_required_checks(
            runs, ["Test (Node 22)", "Test (Node 24)"], ["Owner approval policy"]
        )
        assert result.passed is True

    def test_in_progress_required_check_waits(self):
        runs = [
            {"name": "Test (Node 22)", "conclusion": None, "status": "in_progress"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_missing_required_check_waits(self):
        runs = self._runs(("Test (Node 24)", "success"))
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_newest_run_wins_for_same_name(self):
        # API returns newest first; a newer success overrides an older failure
        runs = self._runs(
            ("Test (Node 22)", "success"),
            ("Test (Node 22)", "failure"),
            ("Test (Node 24)", "success"),
        )
        result = amg.gate_required_checks(runs, ["Test (Node 22)", "Test (Node 24)"], [])
        assert result.passed is True


class TestGateMergeable:
    def test_mergeable_passes(self):
        result = amg.gate_mergeable("MERGEABLE")
        assert result.passed is True

    def test_conflicting_attention(self):
        result = amg.gate_mergeable("CONFLICTING")
        assert result.passed is False
        assert result.decision == "attention"

    def test_unknown_waits(self):
        result = amg.gate_mergeable("UNKNOWN")
        assert result.passed is False
        assert result.decision == "waiting"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `AttributeError: module 'auto_merge_guarded' has no attribute 'gate_required_checks'`

- [ ] **Step 3: Write minimal implementation**

Append to `examples/auto-merge/auto-merge-guarded.py`:

```python
def gate_required_checks(
    check_runs: list[dict], required: list[str], expected_failing: list[str]
) -> GateResult:
    """Gate 3: every required check's newest run must be success.

    check_runs comes from GET /commits/{sha}/check-runs (newest first).
    Checks listed in expected_failing may fail (e.g. Owner approval policy
    before the approve step) without blocking.
    """
    for name in required:
        newest = next((r for r in check_runs if r.get("name") == name), None)
        if newest is None:
            return GateResult(False, "waiting", f"required check {name!r} has no run yet")
        if newest.get("status") != "completed":
            return GateResult(False, "waiting", f"required check {name!r} is {newest.get('status')}")
        if newest.get("conclusion") != "success" and name not in expected_failing:
            return GateResult(
                False,
                "waiting",
                f"required check {name!r} conclusion={newest.get('conclusion')}",
            )
    return GateResult(True, "merge", "all required checks green")


def gate_mergeable(mergeable: str) -> GateResult:
    """Gate 4: PR must be mergeable (no conflicts)."""
    if mergeable == "MERGEABLE":
        return GateResult(True, "merge", "mergeable")
    if mergeable == "CONFLICTING":
        return GateResult(False, "attention", "merge conflicts need human resolution")
    return GateResult(False, "waiting", f"mergeable={mergeable}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): gates 3-4 — required checks green and mergeable"
```

---

### Task 4: pi-cr-meta parsing + Gate 5 — CR multi-stream convergence

**Files:**
- Modify: `examples/auto-merge/auto-merge-guarded.py` (append cr-meta + gate 5)
- Test: `tests/unit/test_auto_merge_guarded.py` (append test classes)

**Interfaces:**
- Consumes: `GateResult` from Task 2
- Produces: `parse_cr_meta(body: str) -> dict | None`; `effective_blocking(finding: dict) -> bool`; `review_clean(meta: dict) -> tuple[bool, str]`; `pid_alive(pid: int | None) -> bool`; `gate_cr_convergence(executions: list[dict], reviews: list[dict], head_sha: str, labels: list[str]) -> GateResult`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auto_merge_guarded.py`:

```python
class TestParseCrMeta:
    def test_extracts_json_from_html_comment(self):
        body = "review text\n<!-- pi-cr-meta {\"round\": 1, \"blocking_new_count\": 0} -->\nmore text"
        meta = amg.parse_cr_meta(body)
        assert meta == {"round": 1, "blocking_new_count": 0}

    def test_returns_none_without_meta(self):
        assert amg.parse_cr_meta("plain review, no meta") is None

    def test_returns_none_on_broken_json(self):
        assert amg.parse_cr_meta("<!-- pi-cr-meta {not json -->") is None


class TestEffectiveBlocking:
    def test_boolean_blocking_used_directly(self):
        assert amg.effective_blocking({"blocking": True}) is True
        assert amg.effective_blocking({"blocking": False}) is False

    def test_legacy_severity_fallback(self):
        assert amg.effective_blocking({"severity": "low"}) is False
        assert amg.effective_blocking({"severity": "medium"}) is True
        assert amg.effective_blocking({"severity": "high"}) is True
        assert amg.effective_blocking({"severity": "critical"}) is True

    def test_missing_severity_defaults_to_blocking(self):
        assert amg.effective_blocking({}) is True


class TestReviewClean:
    def test_clean_meta(self):
        meta = {"blocking_new_count": 0, "issues": []}
        ok, reason = amg.review_clean(meta)
        assert ok is True

    def test_blocking_new_count_blocks(self):
        meta = {"blocking_new_count": 1, "issues": []}
        ok, reason = amg.review_clean(meta)
        assert ok is False
        assert "blocking_new_count" in reason

    def test_open_blocking_finding_blocks(self):
        meta = {
            "blocking_new_count": 0,
            "issues": [{"status": "open", "blocking": True}],
        }
        ok, reason = amg.review_clean(meta)
        assert ok is False

    def test_acknowledged_or_resolved_findings_do_not_block(self):
        meta = {
            "blocking_new_count": 0,
            "issues": [
                {"status": "acknowledged", "blocking": True},
                {"status": "resolved", "blocking": True},
            ],
        }
        ok, reason = amg.review_clean(meta)
        assert ok is True

    def test_open_advisory_finding_does_not_block(self):
        meta = {
            "blocking_new_count": 0,
            "issues": [{"status": "open", "blocking": False}],
        }
        ok, reason = amg.review_clean(meta)
        assert ok is True


class TestGateCrConvergence:
    def _exec(self, status, pid=None):
        return {"status": status, "pid": pid}

    def _review(self, head_sha, body):
        return {"commit": {"oid": head_sha}, "body": body}

    def test_all_three_conditions_pass(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("abc", "<!-- pi-cr-meta {\"blocking_new_count\": 0, \"issues\": []} -->")
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True

    def test_running_execution_waits(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("running", 123)]
        result = amg.gate_cr_convergence(executions, [], "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_running_with_dead_pid_counts_as_terminated(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: False)
        executions = [self._exec("running", 123)]
        reviews = [
            self._review("abc", "<!-- pi-cr-meta {\"blocking_new_count\": 0, \"issues\": []} -->")
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True

    def test_needs_review_label_still_present_waits(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("abc", "<!-- pi-cr-meta {\"blocking_new_count\": 0, \"issues\": []} -->")
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", ["zima:needs-review"])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_no_review_for_head_waits(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        result = amg.gate_cr_convergence(executions, [], "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_second_stream_with_blocking_finding_blocks(self, monkeypatch):
        # Multi-stream trap (jfox #402): ALL reviews for this head must be clean.
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("abc", "<!-- pi-cr-meta {\"blocking_new_count\": 0, \"issues\": []} -->"),
            self._review(
                "abc",
                "<!-- pi-cr-meta {\"blocking_new_count\": 0, "
                "\"issues\": [{\"status\": \"open\", \"blocking\": true}]} -->",
            ),
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is False
        assert result.decision == "waiting"

    def test_review_for_other_head_ignored(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        executions = [self._exec("success", 123)]
        reviews = [
            self._review("oldsha", "<!-- pi-cr-meta {\"blocking_new_count\": 5, \"issues\": []} -->"),
            self._review("abc", "<!-- pi-cr-meta {\"blocking_new_count\": 0, \"issues\": []} -->"),
        ]
        result = amg.gate_cr_convergence(executions, reviews, "abc", [])
        assert result.passed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `AttributeError: module 'auto_merge_guarded' has no attribute 'parse_cr_meta'`

- [ ] **Step 3: Write minimal implementation**

Append to `examples/auto-merge/auto-merge-guarded.py`:

```python
import os
import re
import sys

CR_META_RE = re.compile(r"<!--\s*pi-cr-meta\s+(\{.*?\})\s*-->", re.DOTALL)


def parse_cr_meta(body: str) -> dict | None:
    """Extract the pi-cr-meta JSON from a review body, or None.

    The pi CR bot embeds its verdict as an HTML comment:
    <!-- pi-cr-meta {"round": 1, "blocking_new_count": 0, "issues": [...]} -->
    """
    match = CR_META_RE.search(body or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def effective_blocking(finding: dict) -> bool:
    """Whether a finding blocks merge, with legacy severity fallback.

    New metadata carries a boolean `blocking`.  Old metadata only has
    `severity`: low -> False, medium/high/critical -> True, missing or
    invalid severity counts as medium (True).
    """
    blocking = finding.get("blocking")
    if isinstance(blocking, bool):
        return blocking
    severity = finding.get("severity", "medium")
    return severity != "low"


def review_clean(meta: dict) -> tuple[bool, str]:
    """True when one pi-cr-meta review has no blocking findings.

    blocking_new_count == 0 alone is NOT enough: carried open findings from
    earlier rounds must also be checked one by one.
    """
    if meta.get("blocking_new_count", 0) != 0:
        return False, f"blocking_new_count={meta.get('blocking_new_count')}"
    for issue in meta.get("issues") or []:
        if issue.get("status") == "open" and effective_blocking(issue):
            return False, f"open blocking finding: {issue.get('title', issue.get('id', '?'))}"
    return True, "clean"


def pid_alive(pid: int | None) -> bool:
    """True when a process with this pid exists (mirrors wait-cr.py)."""
    if pid is None:
        return False
    try:
        if sys.platform == "win32":
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            try:
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
            return exit_code.value == STILL_ACTIVE
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except (ValueError, Exception):
        return False


def gate_cr_convergence(
    executions: list[dict], reviews: list[dict], head_sha: str, labels: list[str]
) -> GateResult:
    """Gate 5: CR must have safely converged.  Three conditions, all required:

    a. no execution for this (repo, pr) is still running (a running entry
       whose pid is dead counts as terminated — zima never writes a terminal
       state for hard-killed processes);
    b. every pi-cr-meta review for the current head is clean (multi-stream
       trap: one clean stream + one late stream with a blocking finding must
       NOT merge);
    c. the zima:needs-review label has been removed by postExec.
    """
    for execution in executions:
        if execution.get("status") == "running" and pid_alive(execution.get("pid")):
            return GateResult(False, "waiting", f"CR execution {execution.get('execution_id')} still running")
    if "zima:needs-review" in labels:
        return GateResult(False, "waiting", "zima:needs-review label still present")
    head_reviews = [
        r for r in reviews if ((r.get("commit") or {}).get("oid") or "") == head_sha
    ]
    if not head_reviews:
        return GateResult(False, "waiting", "no CR review for current head yet")
    for review in head_reviews:
        meta = parse_cr_meta(review.get("body") or "")
        if meta is None:
            return GateResult(False, "waiting", "review without pi-cr-meta for current head")
        ok, reason = review_clean(meta)
        if not ok:
            return GateResult(False, "waiting", f"CR not converged: {reason}")
    return GateResult(True, "merge", "CR converged")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (38 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): gate 5 — pi-cr-meta parsing and multi-stream CR convergence"
```

---

### Task 5: Gate 6 — head drift guard + gate chain orchestration

**Files:**
- Modify: `examples/auto-merge/auto-merge-guarded.py` (append gate 6 + `run_gates`)
- Test: `tests/unit/test_auto_merge_guarded.py` (append test classes)

**Interfaces:**
- Consumes: `GateResult`, `RepoConfig`, gates 1-5
- Produces: `gate_head_stable(head_before: str, head_now: str) -> GateResult`; `run_gates(pr: dict, check_runs: list[dict], executions: list[dict], repo_cfg: RepoConfig) -> GateResult`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auto_merge_guarded.py`:

```python
class TestGateHeadStable:
    def test_same_head_passes(self):
        result = amg.gate_head_stable("abc", "abc")
        assert result.passed is True

    def test_drifted_head_aborts(self):
        result = amg.gate_head_stable("abc", "def")
        assert result.passed is False
        assert result.decision == "waiting"
        assert "drift" in result.reason


class TestRunGates:
    def _repo_cfg(self):
        return amg.RepoConfig(
            allow_authors=["ccccyk0919"],
            required_checks=["Test (Node 22)", "Test (Node 24)"],
            expected_failing_checks=["Owner approval policy"],
            merge_method="squash",
            delete_branch=True,
            sensitive_paths=[".github/**"],
            cr_pjob_code="pi-agent-board-pi-cr-job",
        )

    def _pr(self, **overrides):
        pr = {
            "number": 1,
            "title": "t",
            "author": {"login": "ccccyk0919"},
            "state": "OPEN",
            "isDraft": False,
            "headRefOid": "abc",
            "mergeable": "MERGEABLE",
            "labels": [],
            "files": [{"path": "src/main.ts"}],
            "reviews": [],
        }
        pr.update(overrides)
        return pr

    def _check_runs(self):
        return [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]

    def test_all_gates_pass(self, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        pr = self._pr(
            reviews=[
                {
                    "commit": {"oid": "abc"},
                    "body": "<!-- pi-cr-meta {\"blocking_new_count\": 0, \"issues\": []} -->",
                }
            ]
        )
        executions = [{"status": "success", "pid": 123}]
        result = amg.run_gates(pr, self._check_runs(), executions, self._repo_cfg())
        assert result.passed is True
        assert result.decision == "merge"

    def test_gate_order_stops_at_first_failure(self, monkeypatch):
        # Non-whitelisted author: gate 1 fails, later gates never consulted.
        pr = self._pr(author={"login": "stranger"})
        result = amg.run_gates(pr, [], [], self._repo_cfg())
        assert result.passed is False
        assert result.decision == "skip"
        assert "whitelist" in result.reason

    def test_sensitive_path_attention(self, monkeypatch):
        pr = self._pr(files=[{"path": ".github/workflows/ci.yml"}])
        result = amg.run_gates(pr, self._check_runs(), [], self._repo_cfg())
        assert result.passed is False
        assert result.decision == "attention"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `AttributeError: module 'auto_merge_guarded' has no attribute 'gate_head_stable'`

- [ ] **Step 3: Write minimal implementation**

Append to `examples/auto-merge/auto-merge-guarded.py`:

```python
def gate_head_stable(head_before: str, head_now: str) -> GateResult:
    """Gate 6: head must not have moved between verification and action.

    A collaborator push between approve and merge invalidates the approve
    (owner-approval policy binds to the head sha).  A drifted head naturally
    returns to the not-converged state and is re-evaluated next round.
    """
    if head_before != head_now:
        return GateResult(False, "waiting", f"head drift: {head_before[:8]} -> {head_now[:8]}")
    return GateResult(True, "merge", "head stable")


def run_gates(
    pr: dict, check_runs: list[dict], executions: list[dict], repo_cfg: RepoConfig
) -> GateResult:
    """Run the six gates in order; return the first non-passing result.

    Gate 6 (head drift) is NOT run here — it is checked inside the action
    chain right before approve, against a freshly fetched head.
    """
    files = [f.get("path", "") for f in pr.get("files") or []]
    labels = [l.get("name", "") for l in pr.get("labels") or []]
    gates = [
        gate_candidate(pr, repo_cfg.allow_authors),
        gate_sensitive_paths(files, repo_cfg.sensitive_paths),
        gate_required_checks(check_runs, repo_cfg.required_checks, repo_cfg.expected_failing_checks),
        gate_mergeable(pr.get("mergeable", "UNKNOWN")),
        gate_cr_convergence(executions, pr.get("reviews") or [], pr.get("headRefOid", ""), labels),
    ]
    for result in gates:
        if not result.passed:
            return result
    return GateResult(True, "merge", "all gates passed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (44 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): gate 6 — head drift guard and gate chain orchestration"
```

---

### Task 6: Action chain — gh CLI wrappers with dry-run semantics

**Files:**
- Modify: `examples/auto-merge/auto-merge-guarded.py` (append action functions)
- Test: `tests/unit/test_auto_merge_guarded.py` (append test classes)

**Interfaces:**
- Consumes: `GateResult` from Task 2
- Produces: `gh_json(args: list[str]) -> dict | list`; `remove_label(repo: str, number: int, label: str, dry: bool) -> None`; `approve(repo: str, number: int, head_sha: str, dry: bool) -> None`; `rerun_failed_jobs(repo: str, head_sha: str, workflow_name: str, dry: bool, timeout: int = 300) -> None`; `merge_pr(repo: str, number: int, method: str, delete_branch: bool, dry: bool) -> None`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auto_merge_guarded.py`:

```python
class TestActions:
    def test_remove_label_builds_command(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.remove_label("r/repo", 5, "zima:needs-fix", dry=False)
        assert calls == [
            ["pr", "edit", "5", "--repo", "r/repo", "--remove-label", "zima:needs-fix"]
        ]

    def test_remove_label_dry_skips_gh(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.remove_label("r/repo", 5, "zima:needs-fix", dry=True)
        assert calls == []

    def test_approve_binds_head_sha(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.approve("r/repo", 5, "abc123", dry=False)
        assert calls == [
            [
                "pr",
                "review",
                "5",
                "--repo",
                "r/repo",
                "--approve",
                "--body",
                "auto-merge: CR converged + CI green",
                "--commit-id",
                "abc123",
            ]
        ]

    def test_merge_pr_squash_delete_branch(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.merge_pr("r/repo", 5, "squash", True, dry=False)
        assert calls == [
            ["pr", "merge", "5", "--repo", "r/repo", "--squash", "--delete-branch"]
        ]

    def test_merge_pr_merge_method_no_delete(self, monkeypatch):
        calls = []
        monkeypatch.setattr(amg, "gh_json", lambda args: calls.append(args) or {})
        amg.merge_pr("r/repo", 5, "merge", False, dry=False)
        assert calls == [["pr", "merge", "5", "--repo", "r/repo", "--merge"]]

    def test_rerun_failed_jobs_no_failed_runs(self, monkeypatch):
        monkeypatch.setattr(
            amg,
            "gh_json",
            lambda args: [
                {"databaseId": 1, "name": "Owner approval policy", "conclusion": "success"}
            ],
        )
        rerun_calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: rerun_calls.append(args))
        amg.rerun_failed_jobs("r/repo", "abc", "Owner approval policy", dry=False)
        assert rerun_calls == []

    def test_rerun_failed_jobs_reruns_and_waits(self, monkeypatch):
        run_list = [
            {"databaseId": 1, "name": "Owner approval policy", "conclusion": "failure"},
            {"databaseId": 2, "name": "Test (Node 22)", "conclusion": "success"},
        ]
        monkeypatch.setattr(amg, "gh_json", lambda args: run_list)
        rerun_calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: rerun_calls.append(args))
        # gh run view returns completed immediately so the poll loop exits
        monkeypatch.setattr(
            amg,
            "gh_json_view",
            lambda args: {"status": "completed", "conclusion": "success"},
        )
        amg.rerun_failed_jobs("r/repo", "abc", "Owner approval policy", dry=False)
        assert rerun_calls == [["run", "rerun", "1", "--failed"]]

    def test_rerun_failed_jobs_dry_skips(self, monkeypatch):
        run_list = [
            {"databaseId": 1, "name": "Owner approval policy", "conclusion": "failure"}
        ]
        monkeypatch.setattr(amg, "gh_json", lambda args: run_list)
        rerun_calls = []
        monkeypatch.setattr(amg, "gh_run", lambda args: rerun_calls.append(args))
        amg.rerun_failed_jobs("r/repo", "abc", "Owner approval policy", dry=True)
        assert rerun_calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `AttributeError: module 'auto_merge_guarded' has no attribute 'gh_json'`

- [ ] **Step 3: Write minimal implementation**

Append to `examples/auto-merge/auto-merge-guarded.py`:

```python
import subprocess
import time


def gh_json(args: list[str]) -> dict | list:
    """Run `gh <args>` and parse stdout as JSON.  Raises on failure."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {proc.stderr.strip()[:500]}")
    return json.loads(proc.stdout)


def gh_run(args: list[str]) -> None:
    """Run `gh <args>` without parsing output.  Raises on failure."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {proc.stderr.strip()[:500]}")


def remove_label(repo: str, number: int, label: str, dry: bool) -> None:
    """Remove a label.  Removing zima:needs-fix does NOT trigger a new CR
    stream (the webhook only listens for zima:needs-review)."""
    if dry:
        return
    gh_json(["pr", "edit", str(number), "--repo", repo, "--remove-label", label])


def approve(repo: str, number: int, head_sha: str, dry: bool) -> None:
    """Approve the PR, binding the review to the verified head sha."""
    if dry:
        return
    gh_json(
        [
            "pr",
            "review",
            str(number),
            "--repo",
            repo,
            "--approve",
            "--body",
            "auto-merge: CR converged + CI green",
            "--commit-id",
            head_sha,
        ]
    )


def rerun_failed_jobs(
    repo: str, head_sha: str, workflow_name: str, dry: bool, timeout: int = 300
) -> None:
    """Rerun failed runs of the expected-failing workflow on this head.

    After approve, the Owner approval policy workflow re-runs and turns
    green; without this the PR list icon stays red from the old failed run.
    Polls until the rerun completes or `timeout` seconds elapse.
    """
    runs = gh_json(
        ["run", "list", "--repo", repo, "--commit", head_sha, "--json", "databaseId,name,conclusion"]
    )
    failed_ids = [
        str(r["databaseId"])
        for r in runs
        if r.get("name") == workflow_name and r.get("conclusion") == "failure"
    ]
    if not failed_ids:
        return
    if dry:
        return
    for run_id in failed_ids:
        gh_run(["run", "rerun", run_id, "--failed"])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        statuses = [
            gh_json_view(["run", "view", run_id, "--repo", repo, "--json", "status,conclusion"])
            for run_id in failed_ids
        ]
        if all(s.get("status") == "completed" for s in statuses):
            return
        time.sleep(15)
    raise RuntimeError(f"rerun of {workflow_name} did not complete within {timeout}s")


def gh_json_view(args: list[str]) -> dict:
    """Alias for gh_json kept separate so tests can mock the poll loop."""
    return gh_json(args)


def merge_pr(repo: str, number: int, method: str, delete_branch: bool, dry: bool) -> None:
    """Squash-merge (or merge) the PR, optionally deleting the branch."""
    if dry:
        return
    cmd = ["pr", "merge", str(number), "--repo", repo]
    if method == "squash":
        cmd.append("--squash")
    else:
        cmd.append("--merge")
    if delete_branch:
        cmd.append("--delete-branch")
    gh_json(cmd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (52 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): action chain — gh wrappers with dry-run semantics"
```

---

### Task 7: Pushover notification

**Files:**
- Modify: `examples/auto-merge/auto-merge-guarded.py` (append notify functions)
- Test: `tests/unit/test_auto_merge_guarded.py` (append test classes)

**Interfaces:**
- Consumes: nothing new
- Produces: `truncate_chars(text: str, limit: int) -> str`; `load_pushover_keys(config_file: str) -> tuple[str, str] | None`; `send_pushover(level: str, title: str, message: str, config_file: str) -> bool`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auto_merge_guarded.py`:

```python
class TestTruncateChars:
    def test_short_text_unchanged(self):
        assert amg.truncate_chars("hello", 250) == "hello"

    def test_chinese_truncated_by_characters_not_bytes(self):
        text = "中" * 300  # 900 bytes, 300 chars
        result = amg.truncate_chars(text, 250)
        assert len(result) == 250
        assert result.endswith("中")  # no broken UTF-8 sequence


class TestLoadPushoverKeys:
    def test_reads_keys(self, tmp_path):
        cfg = tmp_path / "notify.json"
        cfg.write_text(
            '{"PUSHOVER_API_KEY": "k", "PUSHOVER_USER_KEY": "u"}', encoding="utf-8"
        )
        assert amg.load_pushover_keys(str(cfg)) == ("k", "u")

    def test_missing_file_returns_none(self, tmp_path):
        assert amg.load_pushover_keys(str(tmp_path / "nope.json")) is None

    def test_missing_keys_returns_none(self, tmp_path):
        cfg = tmp_path / "notify.json"
        cfg.write_text('{"BUSY_TIME": "x"}', encoding="utf-8")
        assert amg.load_pushover_keys(str(cfg)) is None


class TestSendPushover:
    def test_posts_and_returns_true(self, monkeypatch):
        posted = []

        class FakeResponse:
            status = 200

        def fake_urlopen(req, timeout=None):
            posted.append(req)
            return FakeResponse()

        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        ok = amg.send_pushover("action", "[auto-merge] merged", "body", "unused")
        assert ok is True
        assert len(posted) == 1
        payload = json.loads(posted[0].data.decode("utf-8"))
        assert payload["token"] == "k"
        assert payload["user"] == "u"
        assert payload["title"] == "[auto-merge] merged"
        assert payload["message"] == "body"

    def test_attention_level_sets_priority(self, monkeypatch):
        posted = []

        class FakeResponse:
            status = 200

        def fake_urlopen(req, timeout=None):
            posted.append(req)
            return FakeResponse()

        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        amg.send_pushover("attention", "t", "m", "unused")
        payload = json.loads(posted[0].data.decode("utf-8"))
        assert payload["priority"] == 1

    def test_http_error_returns_false(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            raise amg.urllib.error.URLError("boom")

        monkeypatch.setattr(amg.urllib.request, "urlopen", fake_urlopen)
        assert amg.send_pushover("action", "t", "m", "unused") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `AttributeError: module 'auto_merge_guarded' has no attribute 'truncate_chars'`

- [ ] **Step 3: Write minimal implementation**

Append to `examples/auto-merge/auto-merge-guarded.py`:

```python
import urllib.error
import urllib.parse
import urllib.request

PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
MESSAGE_CHAR_LIMIT = 250

# Pushover priority per notification level
LEVEL_PRIORITY = {"action": 0, "attention": 1, "error": 1}


def truncate_chars(text: str, limit: int) -> str:
    """Truncate by characters, never bytes (UTF-8 Chinese would corrupt)."""
    if len(text) <= limit:
        return text
    return text[:limit]


def load_pushover_keys(config_file: str) -> tuple[str, str] | None:
    """Read (api_key, user_key) from the shared notify config, or None."""
    path = Path(config_file).expanduser()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    api_key = data.get("PUSHOVER_API_KEY")
    user_key = data.get("PUSHOVER_USER_KEY")
    if not api_key or not user_key:
        return None
    return str(api_key), str(user_key)


def send_pushover(level: str, title: str, message: str, config_file: str) -> bool:
    """POST a Pushover message.  Returns False on any failure (callers
    degrade to log-only; notification must never block the merge)."""
    keys = load_pushover_keys(config_file)
    if keys is None:
        return False
    api_key, user_key = keys
    payload = {
        "token": api_key,
        "user": user_key,
        "title": title,
        "message": truncate_chars(message, MESSAGE_CHAR_LIMIT),
        "priority": LEVEL_PRIORITY.get(level, 0),
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(PUSHOVER_URL, data=data)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (60 tests)

- [ ] **Step 5: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): pushover notification with char-based truncation"
```

---

### Task 8: Main flow — data fetching, orchestration, CLI, flock

**Files:**
- Modify: `examples/auto-merge/auto-merge-guarded.py` (append main flow + CLI)
- Test: `tests/unit/test_auto_merge_guarded.py` (append test classes)

**Interfaces:**
- Consumes: everything from Tasks 1-7
- Produces: `load_executions(zima_home: Path, pjob_code: str) -> list[dict]`; `executions_for_pr(executions: list[dict], repo: str, pr_number: int) -> list[dict]`; `process_repo(repo: str, repo_cfg: RepoConfig, cfg: AppConfig, mode: str, gh: object, zima_home: Path, audit: AuditLogger, notify: object) -> None`; `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_auto_merge_guarded.py`:

```python
class TestLoadExecutions:
    def test_reads_state_files(self, tmp_path):
        state_dir = tmp_path / "history" / "pjobs" / "pi-agent-board-pi-cr-job"
        state_dir.mkdir(parents=True)
        (state_dir / "a1.json").write_text(
            json.dumps({"execution_id": "a1", "status": "success"}), encoding="utf-8"
        )
        (state_dir / "b2.json").write_text(
            json.dumps({"execution_id": "b2", "status": "running"}), encoding="utf-8"
        )
        (state_dir / "not-json.txt").write_text("junk", encoding="utf-8")
        executions = amg.load_executions(tmp_path, "pi-agent-board-pi-cr-job")
        assert len(executions) == 2

    def test_missing_dir_returns_empty(self, tmp_path):
        assert amg.load_executions(tmp_path, "nope") == []


class TestExecutionsForPr:
    def test_filters_by_repo_and_pr(self):
        executions = [
            {"scan_pr_result": {"repo": "r/repo", "pr_number": "5"}},
            {"scan_pr_result": {"repo": "r/repo", "pr_number": "6"}},
            {"scan_pr_result": {"repo": "other/repo", "pr_number": "5"}},
            {},
        ]
        result = amg.executions_for_pr(executions, "r/repo", 5)
        assert len(result) == 1
        assert result[0]["scan_pr_result"]["pr_number"] == "5"


class TestProcessRepo:
    def _make_fake_gh(self, prs, check_runs):
        class FakeGh:
            def __init__(self):
                self.calls = []

            def list_prs(self, repo):
                self.calls.append(("list_prs", repo))
                return prs

            def check_runs(self, repo, sha):
                self.calls.append(("check_runs", repo, sha))
                return check_runs

            def view_pr(self, repo, number):
                self.calls.append(("view_pr", repo, number))
                return prs[0]

        return FakeGh()

    def _make_fake_notify(self):
        class FakeNotify:
            def __init__(self):
                self.sent = []

            def send(self, level, title, message):
                self.sent.append((level, title, message))
                return True

        return FakeNotify()

    def _repo_cfg(self):
        return amg.RepoConfig(
            allow_authors=["ccccyk0919"],
            required_checks=["Test (Node 22)", "Test (Node 24)"],
            expected_failing_checks=["Owner approval policy"],
            merge_method="squash",
            delete_branch=True,
            sensitive_paths=[".github/**"],
            cr_pjob_code="pi-agent-board-pi-cr-job",
        )

    def _pr(self, **overrides):
        pr = {
            "number": 1,
            "title": "t",
            "author": {"login": "ccccyk0919"},
            "state": "OPEN",
            "isDraft": False,
            "headRefOid": "abc",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "reviewDecision": None,
            "labels": [],
            "files": [{"path": "src/main.ts"}],
            "reviews": [
                {
                    "commit": {"oid": "abc"},
                    "body": "<!-- pi-cr-meta {\"blocking_new_count\": 0, \"issues\": []} -->",
                }
            ],
        }
        pr.update(overrides)
        return pr

    def test_merged_pr_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        pr = self._pr(state="MERGED")
        gh = self._make_fake_gh([pr], [])
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "dry-run", gh, tmp_path, audit, notify)
        assert notify.sent == []
        lines = (tmp_path / "audit.log").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["decision"] == "skip"

    def test_dry_run_prints_actions_without_executing(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        monkeypatch.setattr(amg, "gh_json", lambda args: [])  # rerun probe: no failed runs
        action_calls = []
        monkeypatch.setattr(
            amg, "approve", lambda *a, **k: action_calls.append("approve")
        )
        monkeypatch.setattr(
            amg, "merge_pr", lambda *a, **k: action_calls.append("merge_pr")
        )
        monkeypatch.setattr(
            amg, "remove_label", lambda *a, **k: action_calls.append("remove_label")
        )
        green_runs = [
            {"name": "Test (Node 22)", "conclusion": "success", "status": "completed"},
            {"name": "Test (Node 24)", "conclusion": "success", "status": "completed"},
        ]
        pr = self._pr()
        gh = self._make_fake_gh([pr], green_runs)
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "dry-run", gh, tmp_path, audit, notify)
        out = capsys.readouterr().out
        assert "would approve" in out
        assert "would merge" in out
        # dry-run never executes actions and never notifies
        assert action_calls == []
        assert notify.sent == []

    def test_notify_only_sends_attention_for_sensitive_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        pr = self._pr(files=[{"path": ".github/workflows/ci.yml"}])
        gh = self._make_fake_gh([pr], [])
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "notify-only", gh, tmp_path, audit, notify)
        assert len(notify.sent) == 1
        assert notify.sent[0][0] == "attention"

    def test_waiting_decision_is_silent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(amg, "pid_alive", lambda pid: True)
        pr = self._pr(mergeable="UNKNOWN")
        gh = self._make_fake_gh([pr], [])
        notify = self._make_fake_notify()
        audit = amg.AuditLogger(tmp_path / "audit.log")
        cfg = amg.AppConfig(enabled=True, repos={"r/repo": self._repo_cfg()})
        amg.process_repo("r/repo", self._repo_cfg(), cfg, "notify-only", gh, tmp_path, audit, notify)
        assert notify.sent == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: FAIL — `AttributeError: module 'auto_merge_guarded' has no attribute 'load_executions'`

- [ ] **Step 3: Write minimal implementation**

Append to `examples/auto-merge/auto-merge-guarded.py`:

```python
import argparse
import fcntl
from datetime import datetime, timezone

LOCK_PATH = "/tmp/auto-merge-guarded.lock"
DEFAULT_CONFIG = "~/.zima/configs/auto-merge.yaml"
DEFAULT_LOG = "~/.zima/logs/auto-merge.log"


def load_executions(zima_home: Path, pjob_code: str) -> list[dict]:
    """Read every CR execution state file for a PJob code.

    Torn files (zima writes non-atomically) are skipped — the next round
    sees the completed file.
    """
    state_dir = zima_home / "history" / "pjobs" / pjob_code
    if not state_dir.is_dir():
        return []
    executions: list[dict] = []
    for path in sorted(state_dir.iterdir()):
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if isinstance(data, dict):
            executions.append(data)
    return executions


def executions_for_pr(executions: list[dict], repo: str, pr_number: int) -> list[dict]:
    """Filter executions to those that scanned this (repo, pr)."""
    result = []
    for execution in executions:
        scan = execution.get("scan_pr_result") or {}
        if scan.get("repo") == repo and str(scan.get("pr_number")) == str(pr_number):
            result.append(execution)
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def process_repo(
    repo: str,
    repo_cfg: RepoConfig,
    cfg: AppConfig,
    mode: str,
    gh,
    zima_home: Path,
    audit: AuditLogger,
    notify,
) -> None:
    """One full round for one repo: fetch PRs, run gates, act, notify.

    mode is "live", "dry-run", or "notify-only".  dry-run prints the action
    chain without executing; notify-only additionally sends notifications.
    """
    dry = mode != "live"
    notify_enabled = mode != "dry-run"  # dry-run is a pure local rehearsal
    for pr in gh.list_prs(repo):
        number = pr.get("number")
        head_sha = pr.get("headRefOid", "")
        check_runs = gh.check_runs(repo, head_sha)
        executions = executions_for_pr(
            load_executions(zima_home, repo_cfg.cr_pjob_code), repo, number
        )
        result = run_gates(pr, check_runs, executions, repo_cfg)
        audit.log(
            {
                "ts": _now_iso(),
                "mode": mode,
                "repo": repo,
                "pr": number,
                "head_sha": head_sha,
                "decision": result.decision,
                "reason": result.reason,
            }
        )
        if not result.passed:
            if result.decision == "attention" and notify_enabled:
                notify.send(
                    "attention",
                    "[auto-merge] needs your eyes",
                    f"{repo}#{number} {pr.get('title', '')}: {result.reason}",
                )
            # skip / waiting / error are silent (45-min rounds must not spam)
            continue
        # Action chain (each step re-checks current state; idempotent)
        fresh = gh.view_pr(repo, number)
        if fresh.get("state") == "MERGED":
            continue
        if (fresh.get("reviewDecision") or "") == "APPROVED":
            print(f"[{repo}#{number}] already approved, skipping approve")
        else:
            drift = gate_head_stable(head_sha, fresh.get("headRefOid", ""))
            if not drift.passed:
                audit.log(
                    {
                        "ts": _now_iso(),
                        "mode": mode,
                        "repo": repo,
                        "pr": number,
                        "head_sha": fresh.get("headRefOid"),
                        "decision": drift.decision,
                        "reason": drift.reason,
                    }
                )
                continue
            print(f"[{repo}#{number}] would approve" if dry else f"[{repo}#{number}] approving")
            if not dry:
                approve(repo, number, head_sha, dry=False)
        labels = [l.get("name", "") for l in fresh.get("labels") or []]
        if "zima:needs-fix" in labels:
            print(f"[{repo}#{number}] removing zima:needs-fix")
            remove_label(repo, number, "zima:needs-fix", dry)
        for workflow_name in repo_cfg.expected_failing_checks:
            print(f"[{repo}#{number}] rerunning failed jobs of {workflow_name}")
            rerun_failed_jobs(repo, head_sha, workflow_name, dry)
        fresh = gh.view_pr(repo, number)
        if fresh.get("mergeStateStatus") != "CLEAN":
            if notify_enabled:
                notify.send(
                    "error",
                    "[auto-merge] error",
                    f"{repo}#{number}: mergeStateStatus={fresh.get('mergeStateStatus')} after rerun",
                )
            continue
        print(
            f"[{repo}#{number}] would merge (squash)" if dry else f"[{repo}#{number}] merging (squash)"
        )
        if not dry:
            merge_pr(repo, number, repo_cfg.merge_method, repo_cfg.delete_branch, dry=False)
        if notify_enabled:
            notify.send(
                "action",
                "[auto-merge] merged",
                f"{repo}#{number} {pr.get('title', '')} by {pr.get('author', {}).get('login', '?')}",
            )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Auto approve + squash merge whitelisted PRs after CR convergence."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="path to auto-merge.yaml")
    parser.add_argument("--log", default=DEFAULT_LOG, help="path to the JSONL audit log")
    parser.add_argument("--zima-home", default=None, help="override ZIMA_HOME")
    parser.add_argument(
        "--repo", default=None, help="only process this OWNER/REPO (debugging)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="run gates, print actions, execute nothing"
    )
    parser.add_argument(
        "--notify-only",
        action="store_true",
        help="run gates, send notifications, never touch GitHub",
    )
    args = parser.parse_args(argv)

    cfg = load_config(Path(args.config).expanduser())
    if not cfg.enabled:
        print("auto-merge disabled by config (enabled: false)")
        return 0
    mode = "dry-run" if args.dry_run else ("notify-only" if args.notify_only else "live")
    zima_home = Path(args.zima_home) if args.zima_home else Path(
        os.environ.get("ZIMA_HOME") or Path.home() / ".zima"
    )
    audit = AuditLogger(Path(args.log).expanduser())

    lock_file = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another auto-merge round is already running (flock held)")
        return 0

    try:
        for repo, repo_cfg in cfg.repos.items():
            if args.repo and repo != args.repo:
                continue
            process_repo(repo, repo_cfg, cfg, mode, GhClient(), zima_home, audit, Notifier(cfg))
    except Exception as exc:  # noqa: BLE001 — top-level guard: log, notify, exit
        audit.log({"ts": _now_iso(), "mode": mode, "decision": "error", "reason": str(exc)})
        Notifier(cfg).send("error", "[auto-merge] error", str(exc)[:250])
        return 1
    return 0


class GhClient:
    """Thin gh CLI adapter (subclassed/mocked in tests)."""

    def list_prs(self, repo: str) -> list[dict]:
        return gh_json(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--json",
                "number,title,author,state,isDraft,headRefOid,mergeable,mergeStateStatus,"
                "reviewDecision,labels,files,reviews",
            ]
        )

    def check_runs(self, repo: str, head_sha: str) -> list[dict]:
        data = gh_json(
            ["api", f"repos/{repo}/commits/{head_sha}/check-runs", "--paginate"]
        )
        return data.get("check_runs", []) if isinstance(data, dict) else []

    def view_pr(self, repo: str, number: int) -> dict:
        return gh_json(
            [
                "pr",
                "view",
                str(number),
                "--repo",
                repo,
                "--json",
                "state,headRefOid,reviewDecision,labels,mergeStateStatus",
            ]
        )


class Notifier:
    """Pushover adapter with log-only degradation."""

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

    def send(self, level: str, title: str, message: str) -> bool:
        return send_pushover(level, title, message, self.cfg.pushover_config_file)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run pytest tests/unit/test_auto_merge_guarded.py -v`
Expected: PASS (69 tests)

- [ ] **Step 5: Run lint and format**

Run: `cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded && uv run black examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py --line-length 100 && uv run ruff check examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py`
Expected: black reformats (if needed); ruff reports no errors

- [ ] **Step 6: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge-guarded.py tests/unit/test_auto_merge_guarded.py
git commit -m "feat(auto-merge): main flow — orchestration, CLI, flock, gh client"
```

---

### Task 9: Config template, README, and local deployment (Phase 0)

**Files:**
- Create: `examples/auto-merge/auto-merge.yaml.example`
- Create: `examples/auto-merge/README.md`
- Deploy (local, not committed): `~/.zima/scripts/auto-merge-guarded.py`, `~/.zima/configs/auto-merge.yaml`, crontab entry

**Interfaces:**
- Consumes: the finished script from Task 8

- [ ] **Step 1: Write the config template**

Create `examples/auto-merge/auto-merge.yaml.example`:

```yaml
# auto-merge-guarded config template.  Copy to ~/.zima/configs/auto-merge.yaml
# and fill in real values.  Never commit the real file (whitelist + machine
# paths are local policy, not repo content).
enabled: true
pushover:
  config_file: "~/.config/claude-notify.json"   # shared: PUSHOVER_API_KEY / PUSHOVER_USER_KEY
repos:
  OWNER/REPO:
    allow_authors: [collaborator-login]        # authorization boundary: approve is issued as owner
    required_checks: ["Test (Node 22)", "Test (Node 24)"]
    expected_failing_checks: ["Owner approval policy"]   # fails before approve; rerun after
    merge_method: squash                        # squash | merge
    delete_branch: true
    sensitive_paths: [".github/**", "*.pjob.*", "**/branch-protection*"]
    cr_pjob_code: <repo>-pi-cr-job              # PJob whose execution history feeds gate 5
```

- [ ] **Step 2: Write the README**

Create `examples/auto-merge/README.md`:

```markdown
# auto-merge-guarded

Auto approve + squash merge whitelisted collaborators' PRs after CI green
and Zima CR convergence.  Runs on the owner's machine, scheduled by cron
every 45 minutes.  See `docs/superpowers/specs/2026-08-30-auto-merge-guarded-design.md`
for the full design.

## Deploy

```bash
mkdir -p ~/.zima/scripts ~/.zima/configs ~/.zima/logs
cp examples/auto-merge/auto-merge-guarded.py ~/.zima/scripts/
cp examples/auto-merge/auto-merge.yaml.example ~/.zima/configs/auto-merge.yaml
# edit ~/.zima/configs/auto-merge.yaml: real repo, whitelist, checks, cr_pjob_code
```

## Schedule (Phase 0: notify-only)

```bash
crontab -e
# add:
*/45 * * * * /usr/bin/python3 /home/<you>/.zima/scripts/auto-merge-guarded.py --notify-only >> /home/<you>/.zima/logs/auto-merge-cron.log 2>&1
```

Phase 0 runs notify-only for about a week: every round pushes what it
*would* merge; the owner compares against their own judgment.  Phase 1
enables real merging by removing `--notify-only` from the crontab entry.

## Modes

- `--dry-run`: full gate chain, prints the action chain, executes nothing
- `--notify-only`: gates + notifications, never touches GitHub
- live (no flag): gates + actions + notifications

## Emergency stop

Set `enabled: false` in `~/.zima/configs/auto-merge.yaml`, or remove the
crontab entry.  The flock at `/tmp/auto-merge-guarded.lock` prevents
concurrent rounds.

## Audit

`~/.zima/logs/auto-merge.log` — one JSON line per PR per round:
`ts / mode / repo / pr / head_sha / decision / reason`.
```

- [ ] **Step 3: Deploy locally (Phase 0)**

```bash
mkdir -p ~/.zima/scripts ~/.zima/configs ~/.zima/logs
cp /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded/examples/auto-merge/auto-merge-guarded.py ~/.zima/scripts/
# write ~/.zima/configs/auto-merge.yaml with the real whitelist:
#   repos.zhuxixi/pi-agent-board: allow_authors [ccccyk0919],
#   required_checks ["Test (Node 22)", "Test (Node 24)"],
#   expected_failing_checks ["Owner approval policy"],
#   sensitive_paths [".github/**", "*.pjob.*", "**/branch-protection*"],
#   cr_pjob_code pi-agent-board-pi-cr-job
```

- [ ] **Step 4: Smoke test the deployed script**

Run: `python3 ~/.zima/scripts/auto-merge-guarded.py --dry-run --repo zhuxixi/pi-agent-board`
Expected: exit 0; prints per-PR gate decisions; audit lines in `~/.zima/logs/auto-merge.log`; no GitHub mutation (verify with `gh pr view` on any open PR)

- [ ] **Step 5: Install the crontab entry (Phase 0, notify-only)**

```bash
(crontab -l 2>/dev/null | grep -v auto-merge-guarded; echo "*/45 * * * * /usr/bin/python3 /home/elling/.zima/scripts/auto-merge-guarded.py --notify-only >> /home/elling/.zima/logs/auto-merge-cron.log 2>&1") | crontab -
crontab -l | grep auto-merge
```

- [ ] **Step 6: Commit**

```bash
cd /home/elling/git-repo/github/zima-blue-cli/.pi/worktrees/issue-204-auto-merge-guarded
git add examples/auto-merge/auto-merge.yaml.example examples/auto-merge/README.md
git commit -m "docs(auto-merge): config template and deployment README"
```

---

## Self-Review Notes

- Spec coverage: six gates (candidate / sensitive paths / required checks / mergeable / CR convergence / head drift) → Tasks 2-5; action chain (remove needs-fix → approve → rerun → CLEAN check → merge) → Tasks 6+8; Pushover with char truncation → Task 7; flock / audit JSONL / enabled kill-switch → Tasks 1+8; dry-run / notify-only → Tasks 6+8; config template + deployment → Task 9. Phase 0 crontab uses `--notify-only` per the spec's staged rollout.
- Known traps defended: multi-stream convergence requires ALL pi-cr-meta reviews for the head to be clean (Task 4 `test_second_stream_with_blocking_finding_blocks`); needs-fix removal does not trigger new CR streams (Task 6); char-based truncation (Task 7 `test_chinese_truncated_by_characters_not_bytes`); approve binds head sha and drift aborts (Tasks 5-6, 8); rerun-failed-jobs before mergeStateStatus check (Tasks 6, 8).
- Scheduler deviation from spec: daemon schedules cannot run non-PJob scripts (verified in `zima/core/daemon_scheduler.py`); user approved cron `*/45 * * * *` as the replacement host.
