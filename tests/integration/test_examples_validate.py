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
from jinja2 import BaseLoader, Environment, StrictUndefined
from jinja2.meta import find_undeclared_variables

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


def _strict_render_check(pjob_code: str, manager: ConfigManager) -> None:
    """Strictly render a PJob's workflow template with sentinel values (A7).

    The executor render path (``PJobExecutor._render_workflow``) is
    deliberately lenient — undefined variables silently render empty — so it
    cannot prove a template is wired correctly. This check instead:

    1. extracts every template variable via ``jinja2.meta`` (which sees
       runtime-injected variables too, e.g. webhook ``--set-var`` names that
       have no static Variable config);
    2. renders under ``StrictUndefined`` with sentinel values — any undefined
       name or syntax error raises;
    3. asserts every sentinel survives into the output, proving real
       interpolation instead of silent emptying.

    Env settings mirror ``zima.execution.template_renderer._get_jinja_env``
    (the strict CLI render path) plus ``undefined=StrictUndefined``.
    """
    pjob = PJobConfig.from_dict(manager.load_config("pjob", pjob_code))
    workflow_code = pjob.spec.workflow
    assert workflow_code, f"{pjob_code}: PJob has no workflow reference"

    workflow = WorkflowConfig.from_dict(manager.load_config("workflow", workflow_code))
    if workflow.format != "jinja2":
        return  # plain/mustache templates have no strict jinja2 contract

    env = Environment(
        loader=BaseLoader(),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    variable_names = find_undeclared_variables(env.parse(workflow.template))
    sentinels = {name: f"XTEST_{name}" for name in variable_names}

    try:
        output = env.from_string(workflow.template).render(**sentinels)
    except Exception as exc:  # UndefinedError / TemplateError
        raise AssertionError(
            f"{pjob_code}: strict render of workflow '{workflow_code}' failed: {exc}"
        ) from exc

    for name, sentinel in sentinels.items():
        assert sentinel in output, (
            f"{pjob_code}: sentinel {sentinel} for variable '{name}' missing from "
            f"rendered workflow '{workflow_code}' (variable never interpolated)"
        )


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


@pytest.mark.parametrize("scene", list(SCENES))
def test_scene_pjobs_strict_render(scene: str, isolated_zima_home):
    """Every example PJob's template must render strictly (A7).

    The executor's render path is deliberately lenient (undefined variables
    render empty), so it cannot prove a template is correct. Here every
    template variable gets a sentinel value and the render runs under
    ``StrictUndefined``: an undefined variable raises, and every sentinel must
    survive into the output (proves real interpolation, not silent emptying).
    """
    _install_scene(scene, isolated_zima_home)
    manager = ConfigManager()
    for code in manager.list_config_codes("pjob"):
        _strict_render_check(code, manager)
