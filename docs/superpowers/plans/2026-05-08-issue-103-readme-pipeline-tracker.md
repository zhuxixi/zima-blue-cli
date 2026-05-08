# README Pipeline Coverage Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "AI Coding Pipeline" section to README.md showing current automation coverage of the issue-driven AI coding pipeline.

**Architecture:** Single README.md edit — insert a new section between Documentation and Development with a pipeline flow diagram, coverage table, and PJob list.

**Tech Stack:** Markdown only

---

### Task 1: Add AI Coding Pipeline section to README.md

**Files:**
- Modify: `README.md:226-228` (between Documentation section end and Development section start)

- [ ] **Step 1: Insert new section into README.md**

Insert the following content after line 226 (the `---` closing the Documentation section) and before line 228 (`## Development`):

```markdown
## AI Coding Pipeline

Zima automates the issue-driven AI coding pipeline — from code review through deployment — using configurable PJob compositions.

### Pipeline Stages

```
issue → brainstorm/spec → plan → impl → create-PR → CR → post-fix → post-merge → integration-test → deploy-prod
```

### Automation Coverage

| Stage | Status | PJob |
|-------|--------|------|
| brainstorm/spec | ❌ Manual (by design) | — |
| plan | ❌ Not implemented | — |
| impl | ❌ Not implemented | — |
| create-PR | ❌ Not implemented | — |
| CR | ⚠️ Partial | `jfox-kc-code-review-job`, `jfox-zc-code-review-job` |
| post-fix | ❌ Not implemented | — |
| post-merge | ❌ Not implemented | — |
| integration-test | ❌ Not implemented | — |
| deploy-prod | ❌ Not implemented | — |

### Supported PJobs

| PJob Code | Description | Stage |
|-----------|-------------|-------|
| `jfox-kc-code-review-job` | Code review via Kimi CLI | CR |
| `jfox-zc-code-review-job` | Code review via Zhipu-driven Claude Code | CR |

---
```

- [ ] **Step 2: Verify README renders correctly**

Run: `cat README.md | head -280 | tail -50`
Expected: New "AI Coding Pipeline" section visible between Documentation and Development sections, with table formatting intact.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): add AI coding pipeline coverage tracker (#103)"
```
