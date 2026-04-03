---
name: new-entity
description: Scaffold a new configuration entity type (model, commands, manager integration, CLI registration)
disable-model-invocation: true
---

# New Config Entity Scaffold

Scaffold a new configuration entity type for the Zima Blue CLI platform.

## Usage

- `/new-entity Trigger` — create a new entity called "Trigger"
- `/new-entity Schedule` — create a new entity called "Schedule"

## Instructions

Follow the 4-step extension pattern documented in CLAUDE.md:

### Step 1: Create Model

Create `zima/models/<entity>.py`:

- Follow the pattern from existing models (e.g., `zima/models/agent.py`)
- Inherit from `BaseConfig` or create a standalone dataclass
- Include `Metadata` with `code`, `name`, `description`
- YAML structure: `apiVersion: zima.io/v1` / `kind: <Entity>` / `metadata` / `spec`
- Add `KIND = "<entity>"` class constant
- Implement `from_dict` classmethod and `to_dict` method
- Add validation for `metadata.code`: lowercase letters, numbers, hyphens only, max 64 chars

### Step 2: Register in ConfigManager

Edit `zima/config/manager.py`:

- Add the new kind string to `ConfigManager.KINDS` set
- No other changes needed — `ConfigManager` handles all entity types generically

### Step 3: Create Commands

Create `zima/commands/<entity>.py`:

- Follow the pattern from existing commands (e.g., `zima/commands/agent.py`)
- Use Typer `app = typer.Typer(help="<Entity> management commands")`
- Implement standard CRUD: `list`, `get`, `create`, `delete`
- For `create`: accept YAML file via `--file` option, validate and save
- Use `ConfigManager` for all config operations
- Use `rich` for formatted output

### Step 4: Register CLI Subcommand

Edit `zima/cli.py`:

- Import the new command app: `from zima.commands.<entity> import app as <entity>_app`
- Register: `app.add_typer(<entity>_app, name="<entity>")`

### Step 5: Create Test Fixtures (Optional)

Create sample YAML config in `tests/fixtures/configs/`:

```yaml
apiVersion: zima.io/v1
kind: <Entity>
metadata:
  code: sample-<entity>
  name: Sample <Entity>
  description: For testing
spec:
  # entity-specific fields
```

### Verification

After scaffolding, verify:
1. `python -c "from zima.models.<entity> import <Entity>Config"` — import works
2. `zima <entity> --help` — CLI registered correctly
3. `pytest tests/` — no existing tests broken
