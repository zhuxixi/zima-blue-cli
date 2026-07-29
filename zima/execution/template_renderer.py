"""Workflow template rendering and syntax validation — framework adapter.

Moved out of ``zima.models`` so the domain layer stays free of ``jinja2``.
These functions operate on the pure data carried by
:class:`~zima.models.workflow.WorkflowConfig` (template string + format +
default values).

NOTE: :meth:`PJobExecutor._render_workflow` / :meth:`render_prompt`
(``zima/execution/executor.py``) are parallel, intentionally *lenient*
implementations for the agent run path (bare ``Template``, swallow errors into
an HTML comment). This module serves the *strict* CLI ``workflow render`` path
(raises on error). Kept separate on purpose.
"""

from __future__ import annotations

import string
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateError, UndefinedError


def _get_jinja_env() -> Environment:
    """Get a Jinja2 environment matching the CLI render settings."""
    return Environment(
        loader=BaseLoader(),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_workflow_template(
    template: str,
    fmt: str,
    variables: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> str:
    """Render a workflow template.

    Args:
        template: Template content string.
        fmt: Template format (``"jinja2"``, ``"mustache"``, ``"plain"``).
        variables: Variable values to interpolate.
        defaults: Default values merged under ``variables`` (e.g. from
            ``WorkflowConfig._get_default_values()``).

    Returns:
        Rendered template string.

    Raises:
        ValueError: If the format is unsupported or rendering fails.
    """
    if fmt == "plain":
        return template

    if fmt == "mustache":
        # Simple mustache support using string.Template as fallback
        t = string.Template(template)
        return t.safe_substitute(variables)

    if fmt == "jinja2":
        try:
            env = _get_jinja_env()
            jinja_template = env.from_string(template)

            # Merge defaults under the caller-supplied variables
            context = dict(defaults or {})
            context.update(variables)

            return jinja_template.render(**context)
        except UndefinedError as e:
            raise ValueError(f"Undefined variable in template: {e}")
        except TemplateError as e:
            raise ValueError(f"Template rendering error: {e}")

    raise ValueError(f"Unsupported template format: {fmt}")


def validate_template_syntax(template: str, fmt: str) -> list[str]:
    """Validate template syntax (Jinja2 parse).

    Returns:
        List of error messages (empty if valid or format is not Jinja2).
    """
    errors: list[str] = []
    if fmt == "jinja2" and template:
        try:
            _get_jinja_env().parse(template)
        except TemplateError as e:
            errors.append(f"Template syntax error: {e}")
    return errors
