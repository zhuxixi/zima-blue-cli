"""Structure validation for example configuration packs (issue #228, A6).

Installs each supported example pack (``examples/webhook``, ``examples/sdd``)
into an isolated ZIMA_HOME and validates every entity through the domain
models, so the packs cannot silently rot: an invalid example fails CI.

Task 14 extends this module with strict template rendering (A7).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from zima.config.manager import ConfigManager
from zima.models.agent import AgentConfig
from zima.models.env import EnvConfig
from zima.models.pjob import PJobConfig
from zima.models.variable import VariableConfig
from zima.models.workflow import WorkflowConfig

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_ROOT = REPO_ROOT / "examples"

MODEL_MAP = {
    "agent": AgentConfig,
    "workflow": WorkflowConfig,
    "variable": VariableConfig,
    "env": EnvConfig,
    "pjob": PJobConfig,
}

# Reviewed pack composition (spec §6 coverage matrix). Entity kinds absent from
# a pack are not validated for that pack — a missing kind is not a failure; a
# changed count is.
SCENES = {
    "webhook": {"agent": 2, "workflow": 2, "variable": 1, "env": 1, "pjob": 2},
    "sdd": {"agent": 4, "workflow": 6, "env": 1, "pjob": 12},
}

_KIND_DIRS = ("agents", "workflows", "variables", "envs", "pmgs", "pjobs", "schedules")


def _install_scene(scene: str, zima_home: Path) -> None:
    """Copy an example pack's YAML dirs into the isolated config root.

    Only copies kind dirs that exist in the pack; ``copytree`` creates the
    destination dir (e.g. ``pjobs/``, not pre-created by the fixture).
    """
    for kind_dir in _KIND_DIRS:
        src = EXAMPLES_ROOT / scene / kind_dir
        if src.is_dir():
            shutil.copytree(src, zima_home / "configs" / kind_dir, dirs_exist_ok=True)


def _validate_entity(kind: str, code: str, manager: ConfigManager) -> list[str]:
    """Validate one installed entity through its domain model."""
    data = manager.load_config(kind, code)
    errors = MODEL_MAP[kind].from_dict(data).validate()
    return [f"{kind}/{code}: {e}" for e in errors]


@pytest.mark.parametrize("scene", list(SCENES))
def test_scene_all_entities_validate(scene: str, isolated_zima_home):
    """Every YAML file in the pack must pass entity-level domain validation."""
    _install_scene(scene, isolated_zima_home)
    manager = ConfigManager()
    errors: list[str] = []
    for kind in SCENES[scene]:
        for code in manager.list_config_codes(kind):
            errors += _validate_entity(kind, code, manager)
    assert not errors, errors


@pytest.mark.parametrize("scene", list(SCENES))
def test_scene_pack_composition_matches_matrix(scene: str, isolated_zima_home):
    """Per-kind file counts must match the reviewed matrix.

    Guards against example files being silently added or removed: a new file
    must be reviewed into the matrix, not shipped unvalidated.
    """
    _install_scene(scene, isolated_zima_home)
    manager = ConfigManager()
    for kind, expected in SCENES[scene].items():
        codes = manager.list_config_codes(kind)
        assert len(codes) == expected, f"{scene}/{kind}: expected {expected}, got {codes}"
