"""Schedule configuration model for daemon-mode cycle scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field

from zima.models.base import BaseConfig, Metadata
from zima.models.serialization import YamlSerializable
from zima.utils import generate_timestamp, validate_code


@dataclass
class ScheduleStage(YamlSerializable):
    """A stage within a cycle (e.g., work, rest, dream)."""

    FIELD_ALIASES = {
        "offset_minutes": "offsetMinutes",
        "duration_minutes": "durationMinutes",
    }

    name: str = ""
    offset_minutes: int = 0
    duration_minutes: int = 0


@dataclass
class ScheduleCycleType(YamlSerializable):
    """Mapping of stage names to PJob codes for one cycle type."""

    FIELD_ALIASES = {"type_id": "typeId"}

    type_id: str = ""
    work: list[str] = field(default_factory=list)
    rest: list[str] = field(default_factory=list)
    dream: list[str] = field(default_factory=list)

    def get_stage_pjobs(self, stage_name: str) -> list[str]:
        return getattr(self, stage_name, [])


@dataclass
class ScheduleConfig(BaseConfig):
    """Schedule configuration for daemon-mode 32-cycle scheduling."""

    SPEC_FIELD_ALIASES = {
        "cycle_minutes": "cycleMinutes",
        "daily_cycles": "dailyCycles",
        "cycle_types": "cycleTypes",
        "cycle_mapping": "cycleMapping",
    }

    kind: str = "Schedule"
    metadata: Metadata = field(default_factory=Metadata)
    cycle_minutes: int = 45
    daily_cycles: int = 32
    stages: list[ScheduleStage] = field(default_factory=list)
    cycle_types: list[ScheduleCycleType] = field(default_factory=list)
    cycle_mapping: list[str] = field(default_factory=list)

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
            if stage.offset_minutes <= prev_offset:
                errors.append("stages must be sorted by offsetMinutes with no duplicates")
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
                errors.append(f"cycleMapping[{i}] references unknown typeId '{mapped_type}'")

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
