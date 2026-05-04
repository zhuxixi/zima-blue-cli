# Issue #83: Quickstart Code-Review Scene Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix quickstart wizard so `zima quickstart` with code-review scene generates a fully functional PJob — no manual edits required.

**Architecture:** Minimal fix to 2 source files. `scenes.py` gets correct code-review scene definition (preExec + complete variables + unified labels). `quickstart.py` gets git remote repo auto-detection to populate the `repo` variable default.

**Tech Stack:** Python 3.10+, dataclasses, no new dependencies.

---

## Problem

`zima quickstart` code-review scene generates configs with 3 bugs that prevent direct use:

1. **Missing preExec scan_pr** — no automatic PR discovery
2. **Missing repo/pr_number variables** — postExec label transitions fail silently
3. **Label name mismatch** — scan_command uses `need-review`, postExec uses `zima:needs-review`

## Solution: Minimal Fix

### File: `zima/scenes.py`

**Changes:**
- Add `PreExecAction` to import
- Add `pre_exec` to code-review scene's `ActionsConfig`:
  ```python
  pre_exec=[
      PreExecAction(type="scan_pr", repo="{{repo}}", label="zima:needs-review"),
  ],
  ```
- Expand `variables` from `{"pr_url": ""}` to `{"pr_url": "", "repo": "", "pr_number": ""}`
- Remove `scan_command` field (no longer needed — preExec handles scanning)
- Unify labels to `zima:needs-review` everywhere

**Result:** Scene definition matches the manually-fixed production configs on vocabo server.

### File: `zima/commands/quickstart.py`

**Changes:**
- Add `_detect_repo_slug()` helper: parses `owner/repo` from `git remote get-url origin`
  - Handles HTTPS (`https://github.com/owner/repo.git`), SSH (`git@github.com:owner/repo.git`), and plain `owner/repo` formats
  - Returns `""` if detection fails (non-git dir, no remote, parse error)
- In `quickstart()` function, after `_resolve_work_dir()`, call `_detect_repo_slug()`
- Pass detected repo slug to `_create_all_configs()` as new parameter
- In `_create_all_configs()`, merge detected repo into `scene.variables.copy()` before creating VariableConfig:
  ```python
  values = scene.variables.copy()
  if detected_repo:
      values["repo"] = detected_repo
  ```
- Remove the scan_command display section (Step 5, lines 312-320) since scan_command is gone

### File: `tests/unit/test_scenes.py`

**Changes:**
- `test_code_review_scene_structure`: update variables assertion to 3 keys, scan_command to None
- `test_code_review_scene_has_default_actions`: add pre_exec assertions (length=1, type=scan_pr, label=zima:needs-review)
- Add new test: `test_code_review_scene_pre_exec_structure` verifying scan_pr repo and label

### File: `tests/unit/test_quickstart.py`

**Changes:**
- Update or add tests verifying:
  - Generated Variable config contains `repo` with detected value
  - Generated PJob config contains preExec scan_pr
  - `_detect_repo_slug()` handles HTTPS, SSH, and failure cases

## Scope Exclusions (YAGNI)

- No `Scene.default_values` abstraction — only code-review needs repo detection
- No user customization of label names — single consistent label is sufficient
- No actions summary in confirmation step — can be added in a future enhancement
- No changes to `custom` scene — it has no actions
- No changes to `load_scenes()` — user scene YAML deserialization already works

## Success Criteria

1. `zima quickstart -s code-review -n test-cr` generates configs that work without manual edits
2. Generated PJob has preExec scan_pr with `{{repo}}` and `zima:needs-review`
3. Generated Variable has `repo` auto-populated from git remote (when available)
4. All existing tests pass (with updated assertions for new scene shape)
5. Generated configs match the shape of manually-fixed production configs on vocabo
