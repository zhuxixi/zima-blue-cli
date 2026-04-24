# Issue #60: Remove Gemini Agent Type

**Date:** 2026-04-24
**Status:** Approved

## Summary

Remove all references to the "gemini" agent type from the codebase. Gemini was never actually supported — only kimi and claude are active. Removing it reduces confusion and maintenance burden.

## Design

Principle: pure deletion, no refactoring beyond what's needed to remove gemini.

### Source Code Changes (6 files)

| File | Change |
|------|--------|
| `zima/models/agent.py` | Remove `gemini` parameter template from `AGENT_TYPE_PARAMS`, remove `_build_gemini_command()` method, remove gemini branches in `get_cli_command_template()` and `build_command()`, update `VALID_AGENT_TYPES` to `{"kimi", "claude"}`, update docstrings |
| `zima/models/env.py` | Update `VALID_ENV_FOR_TYPES` to `{"kimi", "claude"}`, update docstring |
| `zima/models/pmg.py` | Update `VALID_PMG_FOR_TYPES` to `{"kimi", "claude"}` |
| `zima/commands/agent.py` | Update help text from `kimi/claude/gemini` to `kimi/claude`, remove gemini entry from agent type display list |
| `zima/commands/env.py` | Update help text from `kimi/claude/gemini` to `kimi/claude` |
| `zima/utils.py` | Update `VALID_AGENT_TYPES` to `{"kimi", "claude"}` |

### Test Changes (5 files)

| File | Change |
|------|--------|
| `tests/unit/test_models_agent.py` | Delete `test_create_gemini_agent`, `test_validate_valid_gemini`, `test_get_cli_template_gemini`, `test_build_gemini_command`, `test_build_gemini_command_no_model_by_default`. Update `test_valid_agent_types` assertion to `{"kimi", "claude"}`. Remove gemini YAML fixture data. |
| `tests/unit/test_models_env.py` | Delete `for_type="gemini"` test case |
| `tests/unit/test_utils.py` | Update `VALID_AGENT_TYPES` assertion to `{"kimi", "claude"}`, remove gemini parameterized test row |
| `tests/integration/test_agent_commands.py` | Delete `test_create_gemini_agent` |
| `tests/integration/test_kimi_agent_integration.py` | Remove all gemini agent test code |

### Out of Scope

- `zima/commands/quickstart.py` — only exists in `feat-54` worktree branch, not on main
- CLAUDE.md / AGENTS.md — can be updated separately if needed
- No YAML config or template changes needed (no gemini references found)

## Acceptance Criteria

- No references to "gemini" remain in production code
- All `VALID_*` type sets contain only `{"kimi", "claude"}`
- Help text shows only kimi/claude
- All tests pass after removal
