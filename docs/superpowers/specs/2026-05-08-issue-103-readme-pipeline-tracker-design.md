# Issue #103: README PJob Automation Coverage Tracker

**Date**: 2026-05-08
**Issue**: #103
**Scope**: Documentation only — README.md update

## Summary

Add an "AI Coding Pipeline" section to README.md showing the current automation coverage of the issue-driven AI coding pipeline, including a coverage table and list of supported PJobs.

## Design

### Location

Insert a new `## AI Coding Pipeline` section in README.md, between the existing Documentation and Development sections.

### Content

1. **Intro sentence** — One-line description of the pipeline purpose
2. **Pipeline flow** — Text diagram showing the 9 stages:
   ```
   issue → brainstorm/spec → plan → impl → create-PR → CR → post-fix → post-merge → integration-test → deploy-prod
   ```
3. **Coverage table** — 3 columns (Stage / Status / PJob or Agent), using emoji markers:
   - ❌ Not automated
   - ⚠️ Partially implemented
   - ✅ Fully automated
4. **PJob list** — Bullet list of existing PJobs with code, description, and pipeline stage

### Current state to reflect

| Stage | Status | PJob |
|-------|--------|------|
| brainstorm/spec | ❌ Not automated (by design) | — |
| plan | ❌ Not implemented | — |
| impl | ❌ Not implemented | — |
| create-PR | ❌ Not implemented | — |
| CR | ⚠️ Partial | `jfox-kc-code-review-job` (Kimi), `jfox-zc-code-review-job` (Zhipu/Claude) |
| post-fix | ❌ Not implemented | — |
| post-merge | ❌ Not implemented | — |
| integration-test | ❌ Not implemented | — |
| deploy-prod | ❌ Not implemented | — |

### PJob list content

- `jfox-kc-code-review-job` — Code review via Kimi CLI, targets CR stage
- `jfox-zc-code-review-job` — Code review via Zhipu-driven Claude Code, targets CR stage

## Out of scope

- Code changes
- Automated update mechanism (manual update per pipeline progress)
- Designing future PJob implementations
