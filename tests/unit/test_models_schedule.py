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
