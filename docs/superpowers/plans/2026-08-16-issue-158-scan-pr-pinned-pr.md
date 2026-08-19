# Plan: issue #158 — trust pinned PR in preExec scan_pr

Spec: `docs/superpowers/specs/2026-08-16-issue-158-scan-pr-pinned-pr-design.md`
Branch: `issue-158-scan-pr-pinned-pr` (worktree)

## Task 1: Pinned-PR short-circuit in ActionsRunner.run_pre

**File**: `zima/execution/actions_runner.py` (scan_pr branch, ~line 190)

Insert after the existing repo/label empty-guards, before `provider.scan_prs`:

```python
# Caller pinned the exact PR (webhook event / manual --set-var): trust it
# instead of rescanning the label. GitHub's search index lags a few seconds
# behind the just-delivered label event, so a rescan at trigger time can
# miss the PR that caused this very run (#158).
pinned = (env.get("pr_number") or env.get("pr") or "").strip()
if pinned:
    discovered["repo"] = repo
    discovered["pr_number"] = pinned
    discovered["pr_title"] = ""
    discovered["pr_url"] = f"https://github.com/{repo}/pull/{pinned}"
    continue
```

**Verify**: `uv run pytest tests/unit/test_actions_runner.py -x -q`

## Task 2: Unit tests — pinned branch (test_actions_runner.py)

New test class `TestRunPrePinnedPr`, mock provider per existing pattern. Cases:

1. `env={"pr_number": "11"}` → `scan_prs` NOT called; result has repo/pr_number/pr_url (`https://github.com/owner/repo/pull/11`), pr_title ""
2. `env={"pr": "11"}` → same as 1 (back-compat name)
3. `env={"pr_number": "11", "pr": "22"}` → pr_number wins (result == "11")
4. `env={"pr_number": " 11 "}` → stripped, result == "11"
5. `env={"pr_number": ""}` + scan_prs returns a PR → original path runs (scan_prs called, discovered from scan)
6. `env={}` → scan_prs called once (regression lock of current behavior)
7. repo empty (action.repo="") + pr_number set → SkipAction raised (guard order: empty-repo guard precedes pinned branch)
8. `env={"pr_number": "11"}` + scan_prs returns [] → NO SkipAction (the actual bug: pinned wins over empty rescan); also assert fetch_diff NOT called

**Verify**: `uv run pytest tests/unit/test_actions_runner.py -x -q` all green

## Task 3: server.py injection rename + test

**File**: `zima/webhook/server.py` (~line 163): `f"--set-var=pr={event.pr_number}"` → `f"--set-var=pr_number={event.pr_number}"`

**Test**: `tests/unit/test_webhook_server.py` (locate existing spawn-args assertion; update + keep any legacy-name coverage if present). Assert args contain `--set-var=pr_number=<n>` and no bare `--set-var=pr=`.

**Verify**: `uv run pytest tests/unit/test_webhook_server.py -x -q`

## Task 4: Executor-level pinned flow tests (test_executor_preexec.py)

New tests, mock provider + fake PJob, offline:

1. overrides `pr_number=11` + scan_pr action + template `batch review pr {{ pr_url }}` → rendered prompt contains `https://github.com/owner/repo/pull/11`; scan_prs not called
2. overrides `pr_number=11` + variable config has static `pr_number: "999"` → rendered prompt uses pinned value (override priority lock; mirrors existing `test_preexec_priority_runtime_override_wins`)

**Verify**: `uv run pytest tests/unit/test_executor_preexec.py -x -q`

## Task 5: Full suite + lint + format

- `uv run pytest tests/unit/ -q` (all unit green)
- `uv run ruff check zima/ tests/`
- `uv run black zima/execution/actions_runner.py zima/webhook/server.py tests/unit/test_actions_runner.py tests/unit/test_executor_preexec.py --line-length 100 --check`

**Verify**: exit 0 for all three.

## Task 6: Commit (staged per-file, no `git add -A`)

Two commits:
1. `fix(executor): trust pinned PR in preExec scan_pr (#158)` — actions_runner.py + its tests
2. `fix(webhook): inject pr_number instead of pr set-var (#158)` — server.py + its test

## Task 7: Local quick CR (requesting-code-review, in-worktree)

Self-review diff against main: guard order, no behavior change on unpinned path, black/ruff clean. Then push + PR per zima-pr-monitor flow (Step 9 of github-issue-driven) — PR body links issue #158.

## Out of scope (recorded in spec Non-Goals)

- retry/backoff on scan_prs; pr_diff/pr_title for pinned runs; skip-set filter changes.
