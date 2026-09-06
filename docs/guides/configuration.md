# Configuration Guide

This guide explains where Zima reads its configuration, the two ways to manage it, and how to validate it before running.

## Config Root

`${ZIMA_HOME:-~/.zima}/configs/` is the **only** directory the runtime reads. Set the `ZIMA_HOME` environment variable to relocate everything.

Configs are one YAML file per entity, named after its `code`:

| Subdirectory | Entity | File |
|---|---|---|
| `agents/` | AI executor (kimi / claude / pi) | `<code>.yaml` |
| `workflows/` | Prompt template (Jinja2) | `<code>.yaml` |
| `variables/` | Template variable values | `<code>.yaml` |
| `envs/` | Environment variables and secret references | `<code>.yaml` |
| `pmgs/` | Dynamic CLI parameter groups | `<code>.yaml` |
| `pjobs/` | Executable task (composes the five above) | `<code>.yaml` |
| `schedules/` | Daemon 32-cycle scheduling | `<code>.yaml` |

> YAML written anywhere else — for example a project directory — is **not** auto-discovered. Copy or write configs into the config root.

## Two Ways to Configure

- **YAML path** — copy a working pack from `examples/webhook/` or `examples/sdd/` into the config root, edit, validate, run. Best for agents, bulk setup, and version control:

  ```bash
  ZIMA_HOME="${ZIMA_HOME:-$HOME/.zima}"
  mkdir -p "$ZIMA_HOME/configs/"
  cp -r examples/webhook/{agents,workflows,variables,envs,pjobs} "$ZIMA_HOME/configs/"
  ```

- **CLI path** — `zima quickstart` bootstraps a complete task interactively; `zima <kind> create --example` prints a starter YAML; fine-grained commands (`zima variable set`, `zima pmg add-param`, ...) handle small edits. `validate` is the shared quality gate for both paths.

Run-time overrides (`zima pjob run <code> --set-var/--set-env/--set-param`) apply to that execution only — they never write back to any YAML file.

## Entity Reference

Every entity shares the Kubernetes-style envelope: `apiVersion`, `kind`, `metadata` (with `code` + `name`), `spec`.

### Agent

The AI executor. Selects the CLI binary and its parameters:

```yaml
apiVersion: zima.io/v1
kind: Agent
metadata:
  code: my-agent
  name: My Agent
spec:
  type: kimi              # kimi | claude | pi
  parameters:
    model: moonshot-v1-8k
  defaults:               # fallback refs when a PJob omits them
    workflow: my-workflow
    env: my-env
```

### Workflow

The prompt template sent to the agent, with typed variable definitions:

```yaml
apiVersion: zima.io/v1
kind: Workflow
metadata:
  code: my-workflow
  name: My Workflow
spec:
  format: jinja2          # jinja2 | mustache | plain
  template: |
    You are {{ role }}.
    Please help me with {{ task }}.
  variables:
    - name: role
      type: string
      required: true
    - name: task
      type: string
      required: true
```

### Variable

Holds the values a workflow template renders with:

```yaml
apiVersion: zima.io/v1
kind: Variable
metadata:
  code: cr-vars
  name: CR Variables
spec:
  values:
    repo: ""
    pr: ""
    head_sha: ""
```

### Env

Plain environment variables plus secret *references* (values are resolved at run time, never stored):

```yaml
apiVersion: zima.io/v1
kind: Env
metadata:
  code: github-env
  name: GitHub Env
spec:
  forType: kimi           # metadata only; not enforced at resolution
  variables:
    DEBUG: "false"
  secrets:
    - name: GITHUB_TOKEN
      source: cmd
      command: gh auth token
```

### PMG

A reusable group of CLI parameters injected into the agent command:

```yaml
apiVersion: zima.io/v1
kind: PMG
metadata:
  code: my-pmg
  name: My Parameter Group
spec:
  forTypes: [kimi, claude, pi]
  parameters:
    - name: verbose
      type: flag
      enabled: true
    - name: model
      type: long
      value: "moonshot-v1-8k"
```

### PJob

The executable task. Composes agent + workflow (+ optional variable/env/pmg) and adds execution options and actions:

```yaml
apiVersion: zima.io/v1
kind: PJob
metadata:
  code: claude-cr
  name: Claude Code Review
spec:
  agent: claude
  workflow: cr-claude
  variable: cr-vars
  env: github-env
  actions:
    provider: github
    preExec:
      - type: scan_pr
        repo: "{{repo}}"
        label: "zima:needs-review"
    postExec:
      - condition: success
        type: add_comment
        repo: "{{repo}}"
        issue: "{{pr}}"
        body: "Code review completed by Claude."
```

### Schedule

Daemon scheduling over a 32-cycle day, mapping each cycle to a cycle type:

```yaml
apiVersion: zima.io/v1
kind: Schedule
metadata:
  code: daily-32
  name: Daily 32-cycle Schedule
spec:
  cycleMinutes: 45
  dailyCycles: 32
  stages:
    - name: work
      offsetMinutes: 0
      durationMinutes: 20
    - name: rest
      offsetMinutes: 20
      durationMinutes: 15
    - name: dream
      offsetMinutes: 35
      durationMinutes: 10
  cycleTypes:
    - typeId: A
      work: [review-job]
      rest: [summarize-job]
      dream: []
  # exactly 32 entries; A runs in mapped cycles, "idle" runs nothing
  cycleMapping: [A, A, idle, A, A, idle, A, A, idle, A, A, idle,
                 A, A, idle, idle, A, A, idle, A, A, idle, A, A,
                 idle, A, A, idle, A, A, idle, idle]
```

## Secrets

Env configs separate plain `variables` from `secrets`. A secret entry stores only a **reference** — the value is resolved at read time (during execution or `zima env get --resolve`) and is never written to disk by Zima.

| Source | Resolves from | Required field |
|---|---|---|
| `env` | An environment variable | `key` (name of the source variable) |
| `file` | A file's contents (trimmed) | `path` |
| `cmd` | A shell command's stdout (30 s timeout) | `command` |
| `vault` | HashiCorp Vault | *not yet implemented* — validation accepts it, resolution raises; use `env`, `file`, or `cmd` |

```yaml
secrets:
  - name: GITHUB_TOKEN
    source: cmd
    command: gh auth token
  - name: API_KEY
    source: env
    key: MY_API_KEY
  - name: CERT
    source: file
    path: ~/.secrets/cert.txt
```

Inspect a resolved value on demand:

```bash
zima env get github-env --key GITHUB_TOKEN --resolve
```

## Validation Workflow

Validate after every edit — all three commands exit non-zero on failure, so they are safe to use in CI or pre-commit checks:

```bash
zima <kind> validate <code>                # entity-level checks
zima pjob validate <code> --check-render   # cross-entity refs + template render
zima pjob run <code> --dry-run             # full preview: prompt, command, env — no execution
```

- `validate <code>` loads the entity through its domain model and reports structural errors (missing fields, bad `code` format, invalid secret sources, Jinja2 syntax).
- `pjob validate --check-render` additionally verifies every referenced entity exists and that the workflow template renders.
- `pjob run --dry-run` renders the exact prompt and command line that would execute, with sensitive environment values masked.
