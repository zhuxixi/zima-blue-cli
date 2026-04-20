# Borobo: GitHub App Bot for Automated Development Workflow

**Date**: 2026-04-20
**Status**: Draft
**Related**: Issue #29 (Zima CLI vNext: Event-Driven Scheduling)
**JFox Note**: 202604191043230289 (GitHub CR Bot ecosystem analysis)

## Background

Issue #29 describes a vision for event-driven Zima CLI with GitHub Webhook integration. This spec extracts the GitHub-facing portion into a separate project called **borobo** — a GitHub App bot that orchestrates automated development workflows via issue labels and PR events.

The user's workflow today uses Claude Code superpowers skills (brainstorming → writing-plans → subagent implementation → code review → manual tests). Borobo automates everything except the initial brainstorming and final manual verification.

## System Boundary

### borobo (new repo) — owns:

- GitHub Webhook receiver (FastAPI)
- FSM state machine for issue lifecycle
- Event logging (JSONL)
- GitHub API client (labels, comments, reviews)
- Task scheduling and dedup with zima daemon
- Multi-repo configuration

### zima-blue-cli (existing, unchanged) — owns:

- Agent orchestration (Kimi/Claude/Gemini subprocess execution)
- 32-cycle daemon scheduler
- PJob configuration and execution
- No GitHub awareness

### Contract between borobo and zima

Both share `~/.zima/` data directory:

- borobo **reads** `~/.zima/configs/pjobs/`, `~/.zima/configs/schedules/` — understands PJob coverage
- borobo **writes** `~/.zima/daemon/queue/` — injects priority tasks
- borobo **writes** `~/.zima/configs/pjobs/` — registers new PJob configs for uncovered repos
- borobo **reads** `~/.zima/agents/<code>/logs/` — checks execution results

Interaction flow:

```
GitHub Webhook
     │
     ▼
┌──────────┐                    ┌──────────────────┐
│  borobo   │                    │  zima daemon     │──subprocess──▶ Claude/Kimi
│  (GitHub  │──enqueue task───▶ │  (32-cycle       │
│   App bot)│                    │   scheduler)     │
│           │◀──read results────│                  │
└──────────┘                    └──────────────────┘
```

Borobo's scheduling is smart: it checks whether zima daemon's upcoming cycles already have PJobs covering the current repo/event type. If yes and scheduled soon, the webhook is discarded (daemon handles it). If not, borobo enqueues or registers new PJob configs.

## FSM State Machine

### States

| State | Label | Meaning | Event Source |
|---|---|---|---|
| open | (none) | Issue created, not in workflow | `issues.opened` |
| needs-spec | `zima:needs-spec` | Needs spec refinement | Human trigger |
| needs-plan | `zima:needs-plan` | Spec done, needs implementation plan | `issues.labeled` |
| needs-impl | `zima:needs-impl` | Plan ready, needs implementation | `issues.labeled` |
| needs-review | `zima:needs-review` | Implementation done, needs code review | `pull_request.opened` |
| needs-fix | `zima:needs-fix` | Review found issues, needs fix | Review result |
| needs-test | `zima:needs-test` | Review passed, needs manual verification | Review passed |
| done | `zima:done` | Complete | Human confirm |

### Transitions

```
(open)            ──human───▶  zima:needs-spec
zima:needs-spec   ──labeled──▶ zima:needs-plan      [guard: issue body has spec section]
zima:needs-plan   ──labeled──▶ zima:needs-impl      [guard: plan file committed to repo]
zima:needs-impl   ──PR opened▶ zima:needs-review    [guard: PR linked to issue]
zima:needs-review ──PR review▶ zima:needs-fix       [guard: review has actionable items]
zima:needs-review ──PR review▶ zima:needs-test      [guard: review approved]
zima:needs-fix    ──PR push──▶ zima:needs-review    [guard: fix committed, max 3 cycles]
zima:needs-test   ──labeled──▶ zima:done            [guard: human confirmed]
```

### Label convention

- All borobo-managed labels use `zima:` prefix to avoid collision with human labels
- borobo only manages `zima:*` labels, other labels (`enhancement`, `bug`, etc.) are untouched
- On transition, borobo removes the "from" label and adds the "to" label

### Loop protection

- `needs-fix → needs-review` loops max 3 times
- Exceeding 3 cycles: borobo pauses and posts an issue comment requesting human intervention
- Cycle count tracked in event log

### Reverse transitions

- `needs-plan → needs-spec`: plan phase discovers incomplete spec (human trigger)
- Other reverse transitions not supported — human manually manages labels if needed

### Hybrid event source model

Not all transitions are label-driven. The event source changes by workflow stage:

**Stage 1 — Issue-driven (labels):**
- Issue creation and spec/plan/impl phases use `issues.labeled` events

**Stage 2 — PR-driven (PR events):**
- `pull_request.opened` triggers code review
- `pull_request.synchronize` (new push) triggers re-review after fix
- `pull_request_review.submitted` or inline review check determines pass/fail
- PR ↔ Issue correlation via `Closes #N` in PR body or GitHub linked PRs

**Stage 3 — Issue-driven again (human gate):**
- Final `needs-test → done` uses `issues.labeled` as human confirmation

## Sub-Issue Decomposition

Issue #29 should be split into these sub-issues, ordered by dependency:

### Phase 0: Project scaffold
**Sub 1**: Initialize borobo project
- Python package structure (FastAPI + uvicorn)
- GitHub App registration, JWT auth, Installation Token exchange
- Webhook receiver + signature verification
- Minimal working: receive webhook, verify, print event
- Depends on: nothing

### Phase 1: FSM engine
**Sub 2**: Implement FSM engine
- State definitions, transition rules, guard conditions
- Event logging (JSONL)
- Label management via GitHub API
- Depends on: Sub 1

### Phase 2: Event handlers
**Sub 3**: Issue event handler (spec → plan → impl)
- `issues.labeled` event routing
- Guard condition checks
- Trigger zima daemon task injection
- Depends on: Sub 2

**Sub 4**: PR event handler (review → fix → test)
- `pull_request.opened` / `synchronize` event routing
- PR ↔ Issue correlation
- Review result parsing → `needs-fix` or `needs-test`
- Cycle counting and overflow handling
- Depends on: Sub 2

### Phase 3: Zima integration
**Sub 5**: borobo ↔ zima daemon integration
- Read zima configs to understand PJob coverage
- Dedup decision (is daemon already covering this?)
- Task injection mechanism (queue directory)
- Read execution results
- Depends on: Sub 3, Sub 4

### Phase 4: Multi-repo
**Sub 6**: Multi-repo configuration system
- Per-repo FSM rules and PJob mapping
- Repo registration/deregistration
- Config file format
- Depends on: Sub 2

### Dependency graph
```
Sub1 (scaffold) → Sub2 (FSM) → Sub3 (Issue events) ─┐
                               → Sub4 (PR events)   ─┤→ Sub5 (zima integration)
                               → Sub6 (Multi-repo)  ─┘
```

## Technical Architecture

### Tech stack

| Component | Choice | Reason |
|---|---|---|
| Web framework | FastAPI + uvicorn | Async, auto OpenAPI docs |
| Persistence | JSONL (events) + JSON (state) | Consistent with zima, sufficient for single server |
| GitHub API | PyGithub or requests | Labels, comments, reviews |
| JWT auth | PyJWT + cryptography | GitHub App private key signing |
| Process management | systemd + Nginx reverse proxy | Standard Ubuntu server setup |
| Config | YAML | Consistent with zima style |

### Project structure

```
borobo/
├── pyproject.toml
├── borobo/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry
│   ├── webhook/
│   │   ├── receiver.py      # Webhook receive + signature verify
│   │   └── parser.py        # Event parse and route
│   ├── fsm/
│   │   ├── engine.py        # FSM core
│   │   ├── states.py        # State + transition definitions
│   │   └── guards.py        # Guard condition checks
│   ├── github/
│   │   ├── client.py        # GitHub API wrapper (labels, comments, reviews)
│   │   ├── auth.py          # JWT + Installation Token
│   │   └── linker.py        # PR ↔ Issue correlation
│   ├── scheduler/
│   │   ├── dispatcher.py    # Task scheduling decisions (dedup/inject)
│   │   └── zima_bridge.py   # Interact with zima daemon
│   ├── config/
│   │   └── repo_config.py   # Multi-repo config loading
│   └── store/
│       ├── event_log.py     # JSONL event log
│       └── state_store.py   # State persistence (JSON)
├── configs/
│   └── repos/               # Per-repo config YAMLs
│       ├── zima-blue-cli.yaml
│       └── ...
└── tests/
    ├── unit/
    └── integration/
```

### Deployment

```
Internet (GitHub Webhook)
       │
       ▼
  ┌─ Nginx (443) ──────┐
  │  TLS termination    │
  │  Reverse proxy      │
  └───────┬─────────────┘
          ▼ localhost:8000
  ┌─ borobo (uvicorn) ─┐
  │  FastAPI app        │
  │  systemd managed    │
  └───────┬─────────────┘
          │
          ▼
  ┌─ zima daemon ──────┐
  │  Already running    │
  │  borobo r/w ~/.zima/│
  └─────────────────────┘
```

## Constraints

- Single Ubuntu server, monolith deployment
- CLI subprocess execution model (Claude Code / Kimi CLI as subprocesses)
- File-based persistence (JSONL/SQLite)
- Multi-repo support from day one
- borobo and zima are separate repos
- borobo-zima interaction via shared `~/.zima/` directory (details to be refined later)
