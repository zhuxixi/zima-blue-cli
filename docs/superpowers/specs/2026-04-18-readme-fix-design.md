# README.md Fix — Design Spec

> Issue: #20 — docs: 修复 README.md 审查反馈的问题
> Date: 2026-04-18

## Problem Statement

The current `README.md` was rewritten using the `markdown-pro` skill but left several review issues unaddressed, documented in GitHub Issue #20.

## Design Decisions

### 1. Language Style: Full English

The entire README will be translated to English to eliminate the Chinese-English mixing issue. This aligns with common open-source conventions while the project's internal docs (`AGENTS.md`, architecture docs) remain in Chinese.

### 2. LICENSE: Create MIT License File

A standard `LICENSE` file (MIT, 2026, zhuxixi) will be created. The License badge will use shields.io dynamic badge linking to the file.

### 3. Tests Badge: Real GitHub Actions Badge

Replace the static `tests-passing` SVG with a real GitHub Actions workflow badge pointing to the existing `CI` workflow (`.github/workflows/*.yml`).

### 4. Vision Restoration

Restore the original vision statement from AGENTS.md: "run a 7x24 autonomous AI Agent factory on your own computer" instead of the weakened "execute explicit SOP tasks".

### 5. Cleanup Section: Add Windows Support

Add `cleanup.bat --auto` alongside `./cleanup.sh --auto` with platform labels.

### 6. Symbol Consistency

Use ASCII `7x24` consistently (matching `AGENTS.md`) instead of the Unicode multiplication sign `7×24`.

## Implementation Scope

### Files to Modify
- `README.md` — full rewrite (English, structure optimization)
- `LICENSE` — new file (MIT)

### README Structure

```
# Zima Blue CLI
[Badges: Python, License (shields.io), CI (GitHub Actions)]
> Quote (English translation)

## Table of Contents

## Features
## Architecture
  - Configuration Entities
  - Directory Structure
  - Execution Flow
## Quick Start
  - Installation
  - Basic Usage
  - Advanced Usage: Composed Configuration
  - Cleanup (Unix + Windows)
## CLI Commands
  - Shorthand Commands
  - Full Command Groups
## Documentation
## Development
## Naming Origin
## License
```

### Badge Specification

| Badge | URL |
|-------|-----|
| Python | `https://img.shields.io/badge/python-3.10+-blue.svg` → python.org |
| License | `https://img.shields.io/badge/license-MIT-blue.svg` → LICENSE file |
| CI | `https://github.com/zhuxixi/zima-blue-cli/workflows/CI/badge.svg` → Actions |

## Acceptance Criteria

- [ ] `LICENSE` file exists at repo root (MIT)
- [ ] `README.md` is fully in English
- [ ] License badge links to existing LICENSE file (no 404)
- [ ] Tests badge shows real CI status from GitHub Actions
- [ ] Cleanup section mentions both `cleanup.sh` and `cleanup.bat`
- [ ] Vision statement matches AGENTS.md: "7x24 autonomous AI Agent factory"
- [ ] `Table of Contents` heading is in English (consistent with full-English decision)
- [ ] `7x24` used consistently (ASCII x)
