# Design: PJob Actions CLI (#73)

## Problem

`pjob create` and `pjob update` lack any options for configuring postExec actions (`add_label`, `add_comment`) or the action `provider`. The only way to set them is by manually editing the YAML file.

## Approach

Add a `zima pjob actions <code>` subcommand group to the existing `pjob` Typer app. This keeps action management separate from create/update, avoiding parameter bloat on those commands.

## Subcommand Structure

```
zima pjob actions <code> list              — List all postExec actions (table)
zima pjob actions <code> add               — Add a postExec action
zima pjob actions <code> remove --index N  — Remove action by index
zima pjob actions <code> provider [name]   — Get/set provider
```

## Commands

### `actions <code> list`

Lists all postExec actions in a Rich table with columns: Index, Condition, Type, Details.

For `add_label` type, details show add/remove labels, repo, issue.
For `add_comment` type, details show body (truncated), repo, issue.

### `actions <code> add`

```
zima pjob actions <code> add \
  --condition success \
  --type add_label \
  --add-label reviewed \
  --remove-label needs-review \
  --repo owner/repo \
  --issue "{{pr_number}}" \
  --body "comment text"
```

Parameters:

| Parameter | Required | Repeatable | Notes |
|-----------|----------|------------|-------|
| `--condition` | Yes | No | `success`, `failure`, `always` |
| `--type` | Yes | No | `add_label`, `add_comment` |
| `--add-label` | No | Yes | For `add_label` type |
| `--remove-label` | No | Yes | For `add_label` type |
| `--repo` | No | No | `owner/repo` format, supports `{{VAR}}` |
| `--issue` | No | No | Supports `{{VAR}}` templates |
| `--body` | No | No | For `add_comment` type, supports `{{VAR}}` |

Validation at input time:
- `--condition` must be one of `success`, `failure`, `always`
- `--type` must be one of `add_label`, `add_comment`
- `add_label` type: warn if no `--add-label` or `--remove-label` provided
- `add_comment` type: warn if no `--body` provided

On success: appends to `spec.actions.postExec` list and saves the PJob config.

### `actions <code> remove --index N`

Removes the postExec action at the given 0-based index. Validates index is in range before removal.

### `actions <code> provider [name]`

- Without argument: prints current provider (default: `github`).
- With argument: sets `spec.actions.provider` to the given value and saves.

## `show` Command Enhancement

`pjob show <code>` tree output adds an "Actions" branch when actions are configured:

```
Actions
├── Provider: github
└── PostExec
    ├── [0] success / add_label: +reviewed -needs-review (owner/repo #123)
    └── [1] failure / add_comment: "Review failed" (owner/repo #123)
```

If no actions are configured (default state), the branch is omitted.

## Implementation Details

### File Changes

1. **`zima/commands/pjob.py`** — Add `actions_app` Typer sub-app with 4 commands (`list`, `add`, `remove`, `provider`), register on main `app`. Update `show` command to render actions tree.

2. **`zima/models/actions.py`** — No changes. Existing `ActionsConfig`, `PostExecAction`, validation constants are sufficient.

3. **Tests** — Unit tests for the new commands in `tests/unit/test_commands_pjob_actions.py`.

### Key Patterns

- Load PJob via `ConfigManager.load_config` → `PJobConfig.from_dict`, modify in-memory, then `save_config`. Same pattern as `pjob update`.
- Reuse `VALID_ACTION_CONDITIONS` and `VALID_POST_ACTION_TYPES` from `zima.models.actions` for input validation.
- Error output uses `console.print("[red]✗[/red] ...")` pattern consistent with existing commands.

### Edge Cases

- `remove` with out-of-range index: error with valid range message.
- `add` with `--type add_label` but no labels: warning, still adds (user may add labels later via YAML).
- `provider` without argument on a PJob with no actions section: prints `github` (default).

## Out of Scope

- PreExec actions CLI management (only `scan_pr` type, too niche for now).
- `--provider` parameter on `pjob create` / `pjob update` (all provider management goes through the actions subcommand).
- New action types beyond `add_label` / `add_comment`.
