# Design: git-pull preExec Action Type

**Issue:** #110
**Date:** 2026-05-10
**Status:** Approved

## Problem

When PJobs run on remote machines (e.g., 7700k daemon), the local repo can become stale if not manually pulled. While `scan_pr` fetches PR diffs from GitHub directly (not affected by stale local code), the agent's understanding of codebase context relies on local files being up-to-date. Manual `git pull` before reviews is error-prone for unattended daemon execution.

## Solution

Add `git_pull` as a new preExec action type that runs `git pull` in the agent's workDir before execution.

### Approach

Inline in `ActionsRunner.run_pre()`, matching the existing `scan_pr` pattern. Minimal changes — one constant addition and one new case in the type dispatch.

## Design

### 1. Model Changes (`zima/models/actions.py`)

Add `"git_pull"` to `VALID_PRE_ACTION_TYPES`:

```python
VALID_PRE_ACTION_TYPES = {"scan_pr", "git_pull"}
```

No field changes to `PreExecAction`. The `git_pull` type has no parameters — workDir comes from the agent config at runtime. The existing `validate()` already checks type against this set.

### 2. Runner Changes (`zima/execution/actions_runner.py`)

#### 2a. `run_pre()` signature change

Add optional `workdir` parameter:

```python
def run_pre(self, actions: ActionsConfig, env: dict, workdir: Optional[str] = None) -> dict:
```

#### 2b. New `git_pull` case in type dispatch

Inside the `run_pre()` loop, after the `scan_pr` case:

```python
if action.type == "git_pull":
    if not workdir:
        print("Warning: git_pull skipped, no workdir configured")
    else:
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                print(f"Warning: git pull failed in {workdir}: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            print(f"Warning: git pull timed out in {workdir}")
    # git_pull produces no dynamic vars — continue to next action
```

**Behavior:**
- Runs `git pull` in the agent's workDir
- 60-second timeout — network hangs don't block execution
- Failure logs a warning only — PJob proceeds (diff comes from GitHub anyway)
- Produces no dynamic variables — falls through to next preExec action
- Skipped silently if no workdir is configured
- If workDir is not a git repo, subprocess fails and is caught as warning

### 3. Executor Changes (`zima/execution/executor.py`)

Pass `workdir` to `run_pre()` at the existing call site (step 5, preExec). The executor already has `agent_workdir` available from the resolved config bundle.

```python
dynamic_vars = self._actions_runner.run_pre(
    pjob.spec.actions, pre_env, workdir=agent_workdir
)
```

### 4. YAML Usage

```yaml
actions:
  preExec:
    - type: git_pull           # runs git pull in agent's workDir
    - type: scan_pr
      repo: '{{repo}}'
      label: zima:needs-review
```

`git_pull` runs first (list order), then `scan_pr` operates with the repo freshly updated.

## Tests

### Unit Tests (`tests/unit/test_actions_runner.py`)

Add to `TestActionsRunnerPreExec`:
- `test_git_pull_success` — mock subprocess, verify empty dict returned
- `test_git_pull_failure_continues` — mock non-zero returncode, verify warning printed, empty dict returned
- `test_git_pull_timeout` — mock `subprocess.TimeoutExpired`, verify warning printed
- `test_git_pull_no_workdir` — verify skipped with warning when workdir is None

### Unit Tests (`tests/unit/test_models_actions.py`)

Add to `TestPreExecAction`:
- `test_git_pull_valid_type` — verify `git_pull` passes validation

### Integration Tests

Optional: add to existing `TestPreExecToPostExecFlow` to verify git_pull + scan_pr ordering.

## Files Changed

| File | Change |
|------|--------|
| `zima/models/actions.py` | Add `"git_pull"` to `VALID_PRE_ACTION_TYPES` |
| `zima/execution/actions_runner.py` | Add `workdir` param to `run_pre()`, add `git_pull` case |
| `zima/execution/executor.py` | Pass `workdir=agent_workdir` to `run_pre()` |
| `tests/unit/test_actions_runner.py` | 4 new tests for git_pull |
| `tests/unit/test_models_actions.py` | 1 new test for git_pull validation |

## Out of Scope

- Configurable path field (use agent workDir only)
- Arbitrary command execution (`run_command` preExec type)
- Retry logic on git pull failure
- Authentication handling (assumes git credentials are configured)
