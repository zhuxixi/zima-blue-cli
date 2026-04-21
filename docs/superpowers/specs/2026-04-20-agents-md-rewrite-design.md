# Design: AGENTS.md Ground-Up Rewrite

**Date:** 2026-04-20
**Issue:** #31
**Status:** Approved

## Problem

AGENTS.md contains multiple sections that are stale, inaccurate, or describe unimplemented features. This misleads Kimi Code agents that rely on it as their primary context file.

### Specific issues

1. **Project structure** (Section 3) lists legacy modules (`core/daemon.py`, `core/scheduler.py`, `core/state_manager.py`) as active, missing current modules (`commands/daemon.py`, `commands/schedule.py`, `core/daemon_scheduler.py`, `core/claude_runner.py`, `models/schedule.py`).
2. **Command overview** (Section 6.1) has top-level shortcuts (`zima create`, `zima run`) that PR #28 removed. Missing `zima daemon *` and `zima schedule *` subcommand groups.
3. **agent.yaml format** (Section 6.2) describes an old v1 format (knowledgeBases, runtime, capabilities, identity, tasks) completely different from the current `apiVersion: zima.io/v1` / `kind` / `metadata` / `spec` structure.
4. **Vision content** — 三层记忆架构, Agent 命名规范/知识库存储, 安全边界 trust levels — none of this was ever implemented.
5. **Phase checklist** (Section 7) is stale.
6. **Reference links** (Section 8) point to deleted files (RALPH-LOOP-DESIGN.md, KIMIWORLD-DESIGN.md, AGENT-CYCLE-TIMELINE.md).
7. **Architecture diagram** (Section 2.1) mentions only Kimi; project now supports kimi/claude/gemini.

## Design

### Approach: Ground-up rewrite mirroring CLAUDE.md

Rewrite AGENTS.md from scratch as an English document that mirrors CLAUDE.md's structure and content. AGENTS.md serves as the Kimi Code equivalent of CLAUDE.md — both are agent context files loaded by different AI tools.

### Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | English | User preference |
| Scope | Current reality only | No unimplemented vision content |
| Structure | Mirror CLAUDE.md | Both agents get equivalent context; less maintenance overhead |
| Overlap with CLAUDE.md | Intentional duplication | Each file targets a different agent; they must be self-contained |

### New AGENTS.md structure

1. **Header** — "This file provides guidance to Kimi Code agents when working with this repository."
2. **Project Overview** — Same facts as CLAUDE.md
3. **Development Commands** — Install, run, format, lint, test
4. **Architecture** — 6+1 entity system, key layers, execution flow, data layout, legacy note
5. **Code Conventions** — Python 3.10+, dataclasses, hatchling, black, ruff, YAML style, commit format
6. **Testing** — Unit/integration structure, conftest, coverage threshold
7. **CI Pipeline** — GitHub Actions, lint + test jobs
8. **Extension Points** — How to add agent types and config entities
9. **Gotchas** — Daemon/subprocess patterns, GitHub PR review APIs
10. **Documentation** — Pointers to docs/ directory

### Removed content

- Section 2.2 三层记忆架构 (unimplemented)
- Section 4 Agent 命名规范/知识库存储 (unimplemented)
- Section 6.2 old agent.yaml format (unimplemented v1 design)
- Section 7 Phase checklist (stale)
- Section 8 Reference links to deleted files
- 安全边界 trust levels (unimplemented)
- Session History block (lives in SESSION.md)

### Expected outcome

AGENTS.md shrinks from ~488 lines of mixed Chinese/vision/reality to ~170 lines of accurate English documentation — a clean twin of CLAUDE.md for Kimi Code agents.

## Scope

- Single file change: `AGENTS.md` (full rewrite)
- No code changes
- Update CLAUDE.md Documentation section to reflect AGENTS.md's new purpose
