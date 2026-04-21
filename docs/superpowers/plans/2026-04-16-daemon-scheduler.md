# Daemon Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Schedule` config entity and a global daemon mode that runs PJobs in 45-minute cycles with 3 fixed stages (work/rest/dream), killing previous stage PJobs on transition.

**Architecture:** A new `ScheduleConfig` model stores cycle types and 32-cycle mappings. `DaemonScheduler` runs in a background process, using `threading.Timer` for stage triggers within each cycle. Stage transitions kill lingering PJobs via `subprocess.Popen` and record timeout history. The CLI gains `zima schedule *` and `zima daemon *` commands.

**Tech Stack:** Python 3.12, Typer, Pytest, Rich (console output), subprocess, threading

---

## File Map

| File | Responsibility |
|------|----------------|
| `zima/models/schedule.py` | `ScheduleConfig`, `ScheduleStage`, `ScheduleCycleType` dataclasses with validation |
| `zima/commands/schedule.py` | `zima schedule create/list/show/update/delete/validate/set-type/set-mapping` CLI |
| `zima/core/daemon_scheduler.py` | `DaemonScheduler` — cycle alignment, stage timers, PJob spawn/kill, state/history persistence |
| `zima/daemon_runner.py` | Entry point for the detached daemon process |
| `zima/cli.py` | Register `schedule` subcommand and top-level `daemon` commands |
| `zima/models/__init__.py` | Export `ScheduleConfig` |
| `zima/core/__init__.py` | Export `DaemonScheduler` |
| `zima/config/manager.py` | Add `"schedule"` to `KINDS` |
| `tests/unit/test_models_schedule.py` | Unit tests for `ScheduleConfig` validation and serialization |
| `tests/unit/test_daemon_scheduler.py` | Unit tests for `DaemonScheduler` cycle math and stage transitions (mocked subprocess) |

---

## Task 1: ScheduleConfig Model

**Files:**
- Create: `zima/models/schedule.py`
- Modify: `zima/models/__init__.py`
- Modify: `zima/config/manager.py`
- Test: `tests/unit/test_models_schedule.py`

### Step 1.1: Add `"schedule"` to ConfigManager.KINDS

```python
# zima/config/manager.py
KINDS = {"agent", "workflow", "variable", "env", "pmg", "pjob", "schedule"}
```

Run: `pytest tests/unit/test_config_manager.py -v`
Expected: PASS (no regressions)

### Step 1.2: Write ScheduleConfig model

Create `zima/models/schedule.py`:

```python
"""Schedule configuration model for daemon-mode cycle scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field

from zima.models.base import BaseConfig, Metadata
from zima.utils import generate_timestamp, validate_code


@dataclass
class ScheduleStage:
    """A stage within a cycle (e.g., work, rest, dream)."""

    name: str = ""
    offset_minutes: int = 0
    duration_minutes: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "offsetMinutes": self.offset_minutes,
            "durationMinutes": self.duration_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleStage:
        return cls(
            name=data.get("name", ""),
            offset_minutes=data.get("offsetMinutes", 0),
            duration_minutes=data.get("durationMinutes", 0),
        )


@dataclass
class ScheduleCycleType:
    """Mapping of stage names to PJob codes for one cycle type."""

    type_id: str = ""
    work: list[str] = field(default_factory=list)
    rest: list[str] = field(default_factory=list)
    dream: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        result: dict = {"typeId": self.type_id}
        if self.work:
            result["work"] = self.work
        if self.rest:
            result["rest"] = self.rest
        if self.dream:
            result["dream"] = self.dream
        return result

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleCycleType:
        return cls(
            type_id=data.get("typeId", ""),
            work=data.get("work", []),
            rest=data.get("rest", []),
            dream=data.get("dream", []),
        )

    def get_stage_pjobs(self, stage_name: str) -> list[str]:
        return getattr(self, stage_name, [])


@dataclass
class ScheduleConfig(BaseConfig):
    """Schedule configuration for daemon-mode 32-cycle scheduling."""

    kind: str = "Schedule"
    metadata: Metadata = field(default_factory=Metadata)
    cycle_minutes: int = 45
    daily_cycles: int = 32
    stages: list[ScheduleStage] = field(default_factory=list)
    cycle_types: list[ScheduleCycleType] = field(default_factory=list)
    cycle_mapping: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata.to_dict(),
            "spec": {
                "cycleMinutes": self.cycle_minutes,
                "dailyCycles": self.daily_cycles,
                "stages": [s.to_dict() for s in self.stages],
                "cycleTypes": [ct.to_dict() for ct in self.cycle_types],
                "cycleMapping": self.cycle_mapping,
            },
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleConfig:
        spec = data.get("spec", {})
        return cls(
            api_version=data.get("apiVersion", "zima.io/v1"),
            kind=data.get("kind", "Schedule"),
            metadata=Metadata.from_dict(data.get("metadata", {})),
            cycle_minutes=spec.get("cycleMinutes", 45),
            daily_cycles=spec.get("dailyCycles", 32),
            stages=[ScheduleStage.from_dict(s) for s in spec.get("stages", [])],
            cycle_types=[ScheduleCycleType.from_dict(ct) for ct in spec.get("cycleTypes", [])],
            cycle_mapping=spec.get("cycleMapping", []),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
        )

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        description: str = "",
    ) -> ScheduleConfig:
        now = generate_timestamp()
        return cls(
            metadata=Metadata(code=code, name=name, description=description),
            cycle_minutes=45,
            daily_cycles=32,
            stages=[
                ScheduleStage(name="work", offset_minutes=0, duration_minutes=20),
                ScheduleStage(name="rest", offset_minutes=20, duration_minutes=15),
                ScheduleStage(name="dream", offset_minutes=35, duration_minutes=10),
            ],
            cycle_types=[],
            cycle_mapping=["idle"] * 32,
            created_at=now,
            updated_at=now,
        )

    def validate(self, resolve_refs: bool = False) -> list[str]:
        errors = []

        if not self.metadata.code:
            errors.append("metadata.code is required")
        elif not validate_code(self.metadata.code):
            errors.append(f"metadata.code '{self.metadata.code}' has invalid format")

        if not self.metadata.name:
            errors.append("metadata.name is required")

        if self.cycle_minutes <= 0:
            errors.append("spec.cycleMinutes must be > 0")

        if self.daily_cycles != 32:
            errors.append("spec.dailyCycles must be 32")

        # Validate stages
        prev_offset = -1
        for stage in self.stages:
            end = stage.offset_minutes + stage.duration_minutes
            if end > self.cycle_minutes:
                errors.append(
                    f"stage '{stage.name}' ends at {end}m, exceeding cycle {self.cycle_minutes}m"
                )
            if stage.offset_minutes < prev_offset:
                errors.append(f"stages must be sorted by offsetMinutes")
            prev_offset = stage.offset_minutes

        # Validate cycleMapping length
        if len(self.cycle_mapping) != self.daily_cycles:
            errors.append(
                f"cycleMapping length ({len(self.cycle_mapping)}) must equal dailyCycles ({self.daily_cycles})"
            )

        # Validate typeIds
        valid_type_ids = {ct.type_id for ct in self.cycle_types}
        valid_type_ids.add("idle")
        for i, mapped_type in enumerate(self.cycle_mapping):
            if mapped_type not in valid_type_ids:
                errors.append(
                    f"cycleMapping[{i}] references unknown typeId '{mapped_type}'"
                )

        # Optional: validate PJob refs exist
        if resolve_refs:
            from zima.config.manager import ConfigManager

            manager = ConfigManager()
            all_pjobs = set()
            for ct in self.cycle_types:
                all_pjobs.update(ct.work)
                all_pjobs.update(ct.rest)
                all_pjobs.update(ct.dream)

            for pjob in all_pjobs:
                if not manager.config_exists("pjob", pjob):
                    errors.append(f"referenced pjob '{pjob}' not found")

        return errors

    def get_cycle_type(self, type_id: str) -> ScheduleCycleType | None:
        for ct in self.cycle_types:
            if ct.type_id == type_id:
                return ct
        return None
```

### Step 1.3: Export ScheduleConfig

Modify `zima/models/__init__.py`:

```python
from .schedule import ScheduleConfig

__all__ = [
    # ... existing entries ...
    "ScheduleConfig",
]
```

### Step 1.4: Write model tests

Create `tests/unit/test_models_schedule.py`:

```python
import pytest

from zima.models.schedule import ScheduleConfig, ScheduleCycleType, ScheduleStage


class TestScheduleStage:
    def test_to_dict_and_from_dict(self):
        stage = ScheduleStage(name="work", offset_minutes=0, duration_minutes=20)
        data = stage.to_dict()
        assert data == {"name": "work", "offsetMinutes": 0, "durationMinutes": 20}
        restored = ScheduleStage.from_dict(data)
        assert restored == stage


class TestScheduleCycleType:
    def test_get_stage_pjobs(self):
        ct = ScheduleCycleType(type_id="A", work=["p1"], rest=["p2"], dream=["p3"])
        assert ct.get_stage_pjobs("work") == ["p1"]
        assert ct.get_stage_pjobs("rest") == ["p2"]
        assert ct.get_stage_pjobs("dream") == ["p3"]
        assert ct.get_stage_pjobs("unknown") == []


class TestScheduleConfig:
    def test_create_defaults(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        assert cfg.cycle_minutes == 45
        assert cfg.daily_cycles == 32
        assert len(cfg.stages) == 3
        assert len(cfg.cycle_mapping) == 32
        assert cfg.cycle_mapping[0] == "idle"

    def test_validate_valid(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        cfg.cycle_types = [ScheduleCycleType(type_id="A")]
        cfg.cycle_mapping = ["A"] * 32
        assert cfg.validate() == []

    def test_validate_missing_code(self):
        cfg = ScheduleConfig.create(code="", name="Daily")
        errors = cfg.validate()
        assert any("metadata.code is required" in e for e in errors)

    def test_validate_stage_overflow(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        cfg.stages = [ScheduleStage(name="work", offset_minutes=0, duration_minutes=50)]
        errors = cfg.validate()
        assert any("exceeding cycle" in e for e in errors)

    def test_validate_unsorted_stages(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        cfg.stages = [
            ScheduleStage(name="rest", offset_minutes=20, duration_minutes=15),
            ScheduleStage(name="work", offset_minutes=0, duration_minutes=20),
        ]
        errors = cfg.validate()
        assert any("sorted by offsetMinutes" in e for e in errors)

    def test_validate_mapping_length(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        cfg.cycle_mapping = ["A"] * 10
        errors = cfg.validate()
        assert any("must equal dailyCycles" in e for e in errors)

    def test_validate_unknown_type_id(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        cfg.cycle_mapping = ["Z"] * 32
        errors = cfg.validate()
        assert any("unknown typeId 'Z'" in e for e in errors)
```

Run: `pytest tests/unit/test_models_schedule.py -v`
Expected: 8 tests PASS

### Step 1.5: Commit

```bash
git add zima/models/schedule.py zima/models/__init__.py zima/config/manager.py tests/unit/test_models_schedule.py
git commit -m "feat(models): add ScheduleConfig with validation and tests"
```

---

## Task 2: Schedule CLI Commands

**Files:**
- Create: `zima/commands/schedule.py`
- Modify: `zima/cli.py`
- Modify: `zima/commands/__init__.py` (optional, no exports needed)

### Step 2.1: Write schedule commands

Create `zima/commands/schedule.py`:

```python
"""Schedule management commands for daemon-mode cycle configuration."""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from zima.config.manager import ConfigManager
from zima.models.schedule import ScheduleConfig, ScheduleCycleType
from zima.utils import validate_code_with_error

app = typer.Typer(name="schedule", help="Schedule management - daemon cycle configuration")
console = Console(legacy_windows=False, force_terminal=True)


@app.command()
def create(
    example: bool = typer.Option(False, "--example", help="Print example YAML and exit"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name"),
    code: Optional[str] = typer.Option(None, "--code", "-c", help="Unique code"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if exists"),
):
    """Create a new Schedule"""
    if example:
        print(EXAMPLE_YAML)
        raise typer.Exit(0)

    if not name or not code:
        console.print("[red]✗[/red] --name and --code are required")
        raise typer.Exit(1)

    is_valid, error = validate_code_with_error(code)
    if not is_valid:
        console.print(f"[red]✗[/red] Invalid code: {error}")
        raise typer.Exit(1)

    manager = ConfigManager()
    if manager.config_exists("schedule", code):
        if force:
            manager.delete_config("schedule", code)
            console.print(f"[yellow]⚠[/yellow] Overwriting existing schedule '{code}'")
        else:
            console.print(f"[red]✗[/red] Schedule '{code}' already exists")
            raise typer.Exit(1)

    config = ScheduleConfig.create(code=code, name=name)
    manager.save_config("schedule", code, config.to_dict())
    console.print(f"[green]✓[/green] Schedule '{code}' created")
    console.print(f"   File: {manager.get_config_path('schedule', code)}")


@app.command("list")
def list_schedules():
    """List all Schedules"""
    manager = ConfigManager()
    configs = manager.list_configs("schedule")

    if not configs:
        console.print("[yellow]No schedules found.[/yellow]")
        return

    table = Table(title="Schedules")
    table.add_column("Code", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Cycles", style="yellow")
    table.add_column("Types", style="blue")

    for data in configs:
        cfg = ScheduleConfig.from_dict(data)
        type_count = len(cfg.cycle_types)
        table.add_row(cfg.metadata.code, cfg.metadata.name, str(cfg.daily_cycles), str(type_count))

    console.print(table)


@app.command()
def show(
    code: str = typer.Argument(..., help="Schedule code"),
):
    """Show Schedule details"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)

    tree = Tree(f"[bold cyan]Schedule: {code}[/bold cyan]")
    meta = tree.add("[bold]Metadata[/bold]")
    meta.add(f"Name: {cfg.metadata.name}")
    if cfg.metadata.description:
        meta.add(f"Description: {cfg.metadata.description}")

    spec = tree.add("[bold]Spec[/bold]")
    spec.add(f"Cycle: {cfg.cycle_minutes} minutes")
    spec.add(f"Daily cycles: {cfg.daily_cycles}")

    stages = tree.add("[bold]Stages[/bold]")
    for s in cfg.stages:
        stages.add(f"{s.name}: +{s.offset_minutes}m ({s.duration_minutes}m)")

    types = tree.add("[bold]Cycle Types[/bold]")
    for ct in cfg.cycle_types:
        types.add(f"{ct.type_id}: work={ct.work}, rest={ct.rest}, dream={ct.dream}")

    mapping = tree.add("[bold]Cycle Mapping (first 16)[/bold]")
    mapping.add(str(cfg.cycle_mapping[:16]))

    console.print(tree)


@app.command()
def update(
    code: str = typer.Argument(..., help="Schedule code"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
):
    """Update Schedule metadata"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)
    if name:
        cfg.metadata.name = name
    if description is not None:
        cfg.metadata.description = description

    manager.save_config("schedule", code, cfg.to_dict())
    console.print(f"[green]✓[/green] Schedule '{code}' updated")


@app.command()
def delete(
    code: str = typer.Argument(..., help="Schedule code"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a Schedule"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    if not force:
        if not typer.confirm(f"Delete schedule '{code}'?"):
            console.print("Cancelled")
            raise typer.Exit(0)

    manager.delete_config("schedule", code)
    console.print(f"[green]✓[/green] Schedule '{code}' deleted")


@app.command()
def validate(
    code: str = typer.Argument(..., help="Schedule code"),
    strict: bool = typer.Option(True, "--strict/--no-strict", help="Check PJob refs exist"),
):
    """Validate a Schedule"""
    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)
    errors = cfg.validate(resolve_refs=strict)

    if errors:
        console.print(f"[red]✗[/red] Validation failed:")
        for e in errors:
            console.print(f"   [red]•[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Schedule '{code}' is valid")


@app.command()
def set_type(
    code: str = typer.Argument(..., help="Schedule code"),
    type_id: str = typer.Option(..., "--typeId", help="Cycle type ID (e.g., A)"),
    stage: str = typer.Option(..., "--stage", help="Stage name: work/rest/dream"),
    pjobs: List[str] = typer.Option(..., "--pjobs", help="Comma-separated PJob codes"),
):
    """Set PJobs for a cycle type and stage"""
    valid_stages = {"work", "rest", "dream"}
    if stage not in valid_stages:
        console.print(f"[red]✗[/red] stage must be one of {valid_stages}")
        raise typer.Exit(1)

    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)

    # Find or create cycle type
    ct = cfg.get_cycle_type(type_id)
    if ct is None:
        ct = ScheduleCycleType(type_id=type_id)
        cfg.cycle_types.append(ct)

    setattr(ct, stage, list(pjobs))
    manager.save_config("schedule", code, cfg.to_dict())
    console.print(f"[green]✓[/green] Set {code}/{type_id}/{stage} = {list(pjobs)}")


@app.command()
def set_mapping(
    code: str = typer.Argument(..., help="Schedule code"),
    index: int = typer.Option(..., "--index", help="Cycle index 0-31"),
    type_id: str = typer.Option(..., "--type", help="Type ID or 'idle'"),
):
    """Set cycle mapping at a specific index"""
    if not (0 <= index <= 31):
        console.print("[red]✗[/red] index must be 0-31")
        raise typer.Exit(1)

    manager = ConfigManager()
    if not manager.config_exists("schedule", code):
        console.print(f"[red]✗[/red] Schedule '{code}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", code)
    cfg = ScheduleConfig.from_dict(data)
    cfg.cycle_mapping[index] = type_id
    manager.save_config("schedule", code, cfg.to_dict())
    console.print(f"[green]✓[/green] Set cycleMapping[{index}] = '{type_id}'")


EXAMPLE_YAML = """\
apiVersion: zima.io/v1
kind: Schedule
metadata:
  code: daily-32
  name: "每日32周期调度"
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
      work: [pjob-a1]
      rest: [pjob-a2]
      dream: [pjob-a3]
  cycleMapping:
    - A
    - idle
    - A
    # ... total 32 items
"""
```

### Step 2.2: Register schedule CLI

Modify `zima/cli.py`:

```python
from zima.commands import schedule as schedule_cmd

# Register subcommands
app.add_typer(schedule_cmd.app, name="schedule")
```

### Step 2.3: Quick CLI test

Run: `python -m zima.cli schedule create --code test-sched --name "Test"`
Expected: `✓ Schedule 'test-sched' created`

Run: `python -m zima.cli schedule list`
Expected: Table showing `test-sched`

Run: `python -m zima.cli schedule delete test-sched --force`
Expected: `✓ Schedule 'test-sched' deleted`

### Step 2.4: Commit

```bash
git add zima/commands/schedule.py zima/cli.py
git commit -m "feat(cli): add zima schedule * commands"
```

---

## Task 3: DaemonScheduler Core

**Files:**
- Create: `zima/core/daemon_scheduler.py`
- Modify: `zima/core/__init__.py`
- Test: `tests/unit/test_daemon_scheduler.py`

### Step 3.1: Write DaemonScheduler

Create `zima/core/daemon_scheduler.py`:

```python
"""Daemon scheduler for 32-cycle PJob execution."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from zima.models.schedule import ScheduleConfig


class DaemonScheduler:
    """Runs PJobs on a fixed 45-minute cycle schedule with 3 stages."""

    def __init__(self, schedule: ScheduleConfig, daemon_dir: Path):
        self.schedule = schedule
        self.daemon_dir = daemon_dir
        self.running = False
        self.current_cycle = -1
        self.current_stage: str | None = None
        self.active_pjobs: dict[str, subprocess.Popen] = {}
        self._timers: list[threading.Timer] = []
        self._lock = threading.Lock()

        # Ensure runtime directories
        self.daemon_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = daemon_dir / "history"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> None:
        """Main scheduling loop."""
        self.running = True
        self._log("DaemonScheduler started")
        self._save_state()

        while self.running:
            now = datetime.now()
            cycle_num = self._current_cycle_num(now)
            cycle_start = self._cycle_start_time(now)
            next_cycle_start = cycle_start + timedelta(minutes=self.schedule.cycle_minutes)

            if cycle_num != self.current_cycle:
                self.current_cycle = cycle_num
                self._log(f"Entering cycle {cycle_num}")
                self._start_cycle(cycle_num, cycle_start)

            # Sleep until next cycle boundary
            sleep_seconds = (next_cycle_start - datetime.now()).total_seconds()
            if sleep_seconds > 0:
                self._sleep(sleep_seconds)

        self._log("DaemonScheduler stopped")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self.running = False
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()
        with self._lock:
            self._kill_all_pjobs(stage_name="shutdown")
        self._log("Received stop signal")

    def _start_cycle(self, cycle_num: int, cycle_start: datetime) -> None:
        """Schedule stage timers for this cycle."""
        self._cancel_timers()
        mapped_type = self.schedule.cycle_mapping[cycle_num]

        if mapped_type == "idle":
            self._log(f"Cycle {cycle_num} is idle, sleeping")
            return

        cycle_type = self.schedule.get_cycle_type(mapped_type)
        if cycle_type is None:
            self._log(f"Cycle {cycle_num}: unknown typeId '{mapped_type}', skipping")
            return

        now = datetime.now()
        for stage in self.schedule.stages:
            stage_start = cycle_start + timedelta(minutes=stage.offset_minutes)
            delay = (stage_start - now).total_seconds()
            if delay < 0:
                delay = 0  # Already passed, trigger immediately

            timer = threading.Timer(delay, self._trigger_stage, args=[stage.name, cycle_type])
            timer.daemon = True
            timer.start()
            self._timers.append(timer)

    def _trigger_stage(self, stage_name: str, cycle_type) -> None:
        """Trigger a stage: kill previous, start new PJobs."""
        if not self.running:
            return

        self.current_stage = stage_name
        self._log(f"Stage '{stage_name}' triggered in cycle {self.current_cycle}")

        # Kill previous stage PJobs
        with self._lock:
            self._kill_all_pjobs(stage_name=f"pre-{stage_name}")

        pjob_codes = cycle_type.get_stage_pjobs(stage_name)
        for code in pjob_codes:
            self._start_pjob(code)

        self._save_state()

    def _start_pjob(self, code: str) -> None:
        """Start a PJob asynchronously."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"{code}_{timestamp}_{self.current_cycle}.log"

        cmd = [sys.executable, "-m", "zima.cli", "pjob", "run", code]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=open(log_file, "w", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                if sys.platform == "win32"
                else 0,
                start_new_session=True if sys.platform != "win32" else False,
            )
            with self._lock:
                self.active_pjobs[code] = proc
            self._log(f"Started PJob {code} (PID {proc.pid}), log: {log_file}")
        except Exception as e:
            self._log(f"Failed to start PJob {code}: {e}")
            self._record_history(code, "launch_failed", str(e))

    def _kill_all_pjobs(self, stage_name: str) -> None:
        """Kill all active PJobs and record timeouts."""
        for code, proc in list(self.active_pjobs.items()):
            self._kill_pjob(code, proc, stage_name)
        self.active_pjobs.clear()

    def _kill_pjob(self, code: str, proc: subprocess.Popen, stage_name: str) -> None:
        """Kill a single PJob process."""
        if proc.poll() is not None:
            return  # Already finished

        self._log(f"Killing PJob {code} (PID {proc.pid}) at stage transition '{stage_name}'")
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception as e:
            self._log(f"Error killing PJob {code}: {e}")

        self._record_history(code, "killed_timeout", stage_name)

    def _record_history(self, code: str, status: str, detail: str) -> None:
        """Append a history record."""
        today = datetime.now().strftime("%Y-%m-%d")
        history_file = self.log_dir / f"{today}.jsonl"
        record = {
            "pjobCode": code,
            "scheduleCode": self.schedule.metadata.code,
            "cycleNum": self.current_cycle,
            "stage": self.current_stage or "",
            "status": status,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        }
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _save_state(self) -> None:
        """Persist lightweight runtime state."""
        state_file = self.daemon_dir / "state.json"
        state = {
            "running": self.running,
            "currentCycle": self.current_cycle,
            "currentStage": self.current_stage,
            "activePjobs": list(self.active_pjobs.keys()),
            "updatedAt": datetime.now().isoformat(),
        }
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _log(self, message: str) -> None:
        """Write to daemon log."""
        log_file = self.daemon_dir / "daemon.log"
        line = f"[{datetime.now().isoformat()}] {message}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)

    def _cancel_timers(self) -> None:
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()

    def _sleep(self, seconds: float) -> None:
        """Sleep in small chunks so stop() is responsive."""
        end = time.time() + seconds
        while time.time() < end and self.running:
            time.sleep(min(1.0, end - time.time()))

    def _current_cycle_num(self, dt: datetime) -> int:
        """Compute which 45-minute cycle we're in (0-31) based on midnight."""
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes_since_midnight = (dt - midnight).total_seconds() / 60
        cycle_num = int(minutes_since_midnight // self.schedule.cycle_minutes)
        return cycle_num % self.schedule.daily_cycles

    def _cycle_start_time(self, dt: datetime) -> datetime:
        """Compute the start time of the current cycle."""
        midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        minutes_since_midnight = (dt - midnight).total_seconds() / 60
        cycle_num = int(minutes_since_midnight // self.schedule.cycle_minutes)
        return midnight + timedelta(minutes=cycle_num * self.schedule.cycle_minutes)
```

### Step 3.2: Export DaemonScheduler

Modify `zima/core/__init__.py`:

```python
from .daemon_scheduler import DaemonScheduler

__all__ = ["AgentRunner", "ClaudeRunner", "DaemonScheduler"]
```

### Step 3.3: Write daemon scheduler tests

Create `tests/unit/test_daemon_scheduler.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zima.core.daemon_scheduler import DaemonScheduler
from zima.models.schedule import ScheduleConfig, ScheduleCycleType


class TestCycleMath:
    def test_current_cycle_num_at_midnight(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        dt = datetime(2026, 4, 16, 0, 0, 0)
        assert sched._current_cycle_num(dt) == 0

    def test_current_cycle_num_at_45_min(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        dt = datetime(2026, 4, 16, 0, 45, 0)
        assert sched._current_cycle_num(dt) == 1

    def test_current_cycle_num_at_22_30(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        dt = datetime(2026, 4, 16, 22, 30, 0)
        assert sched._current_cycle_num(dt) == 30

    def test_cycle_start_time(self):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, Path("/tmp/daemon"))
        dt = datetime(2026, 4, 16, 10, 15, 0)
        start = sched._cycle_start_time(dt)
        assert start == datetime(2026, 4, 16, 10, 0, 0)


class TestStageTransitions:
    def test_kill_all_pjobs_records_timeout(self, tmp_path):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, tmp_path)
        sched.current_cycle = 5
        sched.current_stage = "work"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        sched.active_pjobs["p1"] = mock_proc

        sched._kill_all_pjobs("rest")

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5)

        # Check history file
        history_file = tmp_path / "history"
        jsonl_files = list(history_file.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        lines = jsonl_files[0].read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        import json
        record = json.loads(lines[0])
        assert record["pjobCode"] == "p1"
        assert record["status"] == "killed_timeout"

    def test_start_pjob_launch_failed(self, tmp_path):
        cfg = ScheduleConfig.create(code="daily", name="Daily")
        sched = DaemonScheduler(cfg, tmp_path)
        sched.current_cycle = 1
        sched.current_stage = "work"

        with patch("zima.core.daemon_scheduler.subprocess.Popen", side_effect=OSError("boom")):
            sched._start_pjob("bad-pjob")

        history_file = tmp_path / "history"
        jsonl_files = list(history_file.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        import json
        record = json.loads(jsonl_files[0].read_text(encoding="utf-8").strip().split("\n")[0])
        assert record["pjobCode"] == "bad-pjob"
        assert record["status"] == "launch_failed"
```

Run: `pytest tests/unit/test_daemon_scheduler.py -v`
Expected: 6 tests PASS

### Step 3.4: Commit

```bash
git add zima/core/daemon_scheduler.py zima/core/__init__.py tests/unit/test_daemon_scheduler.py
git commit -m "feat(core): add DaemonScheduler with cycle math, stage timers, and kill logic"
```

---

## Task 4: Daemon Runner Entry Point

**Files:**
- Modify: `zima/daemon_runner.py`

### Step 4.1: Rewrite daemon_runner.py

```python
"""
Daemon runner - executed as a separate process for background scheduling.

Usage: python -m zima.daemon_runner --schedule <schedule_code>
"""

import argparse
import sys
from pathlib import Path

from zima.config.manager import ConfigManager
from zima.core.daemon_scheduler import DaemonScheduler
from zima.models.schedule import ScheduleConfig
from zima.utils import setup_windows_utf8

setup_windows_utf8()


def parse_args():
    parser = argparse.ArgumentParser(description="Zima Daemon Runner")
    parser.add_argument("--schedule", required=True, help="Schedule code to run")
    return parser.parse_args()


def main():
    args = parse_args()
    schedule_code = args.schedule

    manager = ConfigManager()
    if not manager.config_exists("schedule", schedule_code):
        print(f"Error: Schedule '{schedule_code}' not found")
        sys.exit(1)

    data = manager.load_config("schedule", schedule_code)
    schedule = ScheduleConfig.from_dict(data)

    errors = schedule.validate(resolve_refs=True)
    if errors:
        print(f"Error: Schedule validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    daemon_dir = Path.home() / ".zima" / "daemon"
    scheduler = DaemonScheduler(schedule, daemon_dir)

    # Write PID file
    pid_file = daemon_dir / "daemon.pid"
    pid_file.write_text(str(sys.pid if hasattr(sys, "pid") else 0), encoding="utf-8")

    try:
        scheduler.run()
    except KeyboardInterrupt:
        scheduler.stop()
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
```

### Step 4.2: Verify module runs with --help

Run: `python -m zima.daemon_runner --help`
Expected: Usage text showing `--schedule`

### Step 4.3: Commit

```bash
git add zima/daemon_runner.py
git commit -m "feat(daemon): rewrite daemon_runner.py as v3 entry point"
```

---

## Task 5: Daemon CLI Commands

**Files:**
- Modify: `zima/cli.py`

### Step 5.1: Add daemon commands to main CLI

Modify `zima/cli.py`. After the existing imports, add:

```python
from zima.core import start_daemon, stop_daemon, is_daemon_running
from zima.core.daemon_scheduler import DaemonScheduler
from zima.models.schedule import ScheduleConfig
```

Wait — `start_daemon`, `stop_daemon`, `is_daemon_running` are in `zima.core.daemon`. Import them:

```python
from zima.core.daemon import start_daemon, stop_daemon, is_daemon_running
```

Actually, check `zima/core/daemon.py` — those functions take `agent_dir: Path`, not schedule code. We will add new daemon-specific functions in `zima/cli.py` directly using `subprocess.Popen`, or better, add new functions in `zima/core/daemon.py`.

**Simpler approach:** implement daemon start/stop/status/logs directly in `zima/cli.py` as top-level commands.

Add this to `zima/cli.py` after the existing `logs` command:

```python
import subprocess

from zima.core.daemon_scheduler import DaemonScheduler


# ---------------------------------------------------------------------------
# Daemon commands
# ---------------------------------------------------------------------------

@app.command()
def daemon_start(
    schedule: str = typer.Option(..., "--schedule", "-s", help="Schedule code"),
):
    """Start the global daemon"""
    daemon_dir = Path.home() / ".zima" / "daemon"
    pid_file = daemon_dir / "daemon.pid"

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            # Check if process is alive
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                console.print(f"[yellow]⚠[/yellow] Daemon already running (PID {pid})")
                raise typer.Exit(1)
        except Exception:
            pass
        pid_file.unlink(missing_ok=True)

    manager = ConfigManager()
    if not manager.config_exists("schedule", schedule):
        console.print(f"[red]✗[/red] Schedule '{schedule}' not found")
        raise typer.Exit(1)

    data = manager.load_config("schedule", schedule)
    cfg = ScheduleConfig.from_dict(data)
    errors = cfg.validate(resolve_refs=True)
    if errors:
        console.print("[red]✗[/red] Schedule validation failed:")
        for e in errors:
            console.print(f"   [red]•[/red] {e}")
        raise typer.Exit(1)

    log_file = daemon_dir / "daemon.log"
    daemon_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "zima.daemon_runner",
        "--schedule",
        schedule,
    ]

    if sys.platform == "win32":
        proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=open(log_file, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    pid_file.write_text(str(proc.pid), encoding="utf-8")
    console.print(f"[green]✓[/green] Daemon started (PID {proc.pid})")
    console.print(f"   Schedule: {schedule}")
    console.print(f"   Log: {log_file}")


@app.command()
def daemon_stop():
    """Stop the global daemon"""
    daemon_dir = Path.home() / ".zima" / "daemon"
    pid_file = daemon_dir / "daemon.pid"

    if not pid_file.exists():
        console.print("[yellow]⚠[/yellow] Daemon is not running")
        raise typer.Exit(0)

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
        else:
            import os
            import signal
            os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        console.print(f"[green]✓[/green] Daemon stopped (PID {pid})")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to stop daemon: {e}")
        raise typer.Exit(1)


@app.command()
def daemon_status():
    """Show daemon status"""
    daemon_dir = Path.home() / ".zima" / "daemon"
    pid_file = daemon_dir / "daemon.pid"
    state_file = daemon_dir / "state.json"

    if not pid_file.exists():
        console.print("[yellow]Daemon is not running[/yellow]")
        raise typer.Exit(0)

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        console.print("[red]Invalid PID file[/red]")
        raise typer.Exit(1)

    # Check if alive
    alive = False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(1, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            alive = True
    else:
        import os
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            pass

    if not alive:
        console.print(f"[yellow]Daemon PID {pid} is not alive[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Daemon is running[/green] (PID {pid})")

    if state_file.exists():
        import json
        state = json.loads(state_file.read_text(encoding="utf-8"))
        console.print(f"   Current cycle: {state.get('currentCycle', 'unknown')}")
        console.print(f"   Current stage: {state.get('currentStage', 'unknown')}")
        console.print(f"   Active PJobs: {state.get('activePjobs', [])}")


@app.command()
def daemon_logs(
    tail: int = typer.Option(20, "--tail", "-n", help="Number of lines"),
):
    """Show daemon logs"""
    log_file = Path.home() / ".zima" / "daemon" / "daemon.log"
    if not log_file.exists():
        console.print("[yellow]No daemon logs found[/yellow]")
        raise typer.Exit(0)

    lines = log_file.read_text(encoding="utf-8").splitlines()
    for line in lines[-tail:]:
        console.print(line)
```

### Step 5.2: Ensure imports

Make sure `zima/cli.py` has these imports at the top:

```python
import subprocess
import sys
```

(They may already be there indirectly, but add them explicitly.)

### Step 5.3: Quick smoke test

Run: `python -m zima.cli daemon_status`
Expected: `Daemon is not running` (yellow)

Run: `python -m zima.cli daemon_logs`
Expected: `No daemon logs found` (yellow)

### Step 5.4: Commit

```bash
git add zima/cli.py
git commit -m "feat(cli): add daemon start/stop/status/logs commands"
```

---

## Task 6: End-to-End Smoke Test

**Files:** None (uses CLI only)

### Step 6.1: Create test schedule and verify CLI round-trip

```bash
python -m zima.cli schedule create --code e2e-test --name "E2E Test"
python -m zima.cli schedule set-type --code e2e-test --typeId A --stage work --pjobs nonexistent-pjob
python -m zima.cli schedule validate e2e-test --no-strict
python -m zima.cli schedule show e2e-test
python -m zima.cli schedule delete e2e-test --force
```

Expected: All commands succeed without traceback.

### Step 6.2: Run full test suite

```bash
pytest tests/unit -v --tb=short
```

Expected: All existing tests + new tests pass.

### Step 6.3: Final commit

```bash
git commit -m "test: verify daemon scheduler integration" --allow-empty
```

---

## Self-Review

### Spec coverage checklist

| Spec requirement | Implementing task |
|------------------|-------------------|
| `ScheduleConfig` model with schema | Task 1 |
| `zima schedule *` CLI | Task 2 |
| `DaemonScheduler` with cycle alignment | Task 3 |
| 3 stages (work/rest/dream) with timers | Task 3 |
| Kill previous stage PJobs on transition | Task 3 |
| Record `killed_timeout` history | Task 3 |
| `zima daemon start/stop/status/logs` | Tasks 4 & 5 |
| 32-cycle mapping + idle support | Task 1 (model), Task 3 (scheduler) |
| Validation (stages sorted, mapping length, typeIds, PJob refs) | Task 1 |
| Tests | Tasks 1, 3, 6 |

### Placeholder scan

- No "TBD", "TODO", or vague instructions found.
- All code snippets are concrete and copy-paste ready.
- All file paths are exact.

### Type consistency scan

- `ScheduleConfig.create()` signature matches model definition.
- `DaemonScheduler.__init__` takes `(ScheduleConfig, Path)` consistently.
- `cycle_mapping` is always `list[str]`.
- `killed_timeout` status string used consistently in `_kill_pjob` and tests.

No issues found.
