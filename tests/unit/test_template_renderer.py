"""Unit tests for workflow template rendering/validation (zima.execution.template_renderer).

Covers the Jinja2 IO that was moved out of the domain layer (zima.models.workflow)
so that models stays jinja-free.
"""

import pytest

from tests.base import TestIsolator
from zima.execution.template_renderer import render_workflow_template, validate_template_syntax
from zima.models.workflow import WorkflowConfig


def _render(wf: WorkflowConfig, variables: dict) -> str:
    """Render a WorkflowConfig's template via the renderer (defaults pre-computed)."""
    return render_workflow_template(wf.template, wf.format, variables, wf._get_default_values())


class TestRenderWorkflowTemplate(TestIsolator):
    """Test template rendering."""

    def test_render_simple(self):
        """Test simple variable substitution."""
        workflow = WorkflowConfig.create(code="simple", name="Simple", template="Hello {{ name }}!")

        result = _render(workflow, {"name": "World"})
        assert result == "Hello World!"

    def test_render_with_defaults(self):
        """Test rendering with default values."""
        workflow = WorkflowConfig.create(
            code="defaults",
            name="Defaults",
            template="Hello {{ name }}!",
            variables=[{"name": "name", "type": "string", "default": "Anonymous"}],
        )

        # Without providing value, should use default
        result = _render(workflow, {})
        assert result == "Hello Anonymous!"

        # Providing value should override default
        result = _render(workflow, {"name": "Custom"})
        assert result == "Hello Custom!"

    def test_render_nested_variables(self):
        """Test rendering with nested variable access."""
        workflow = WorkflowConfig.create(
            code="nested", name="Nested", template="{{ task.name }}: {{ task.objective }}"
        )

        result = _render(workflow, {"task": {"name": "Review", "objective": "Check code"}})
        assert result == "Review: Check code"

    def test_render_with_condition(self):
        """Test rendering with conditionals."""
        workflow = WorkflowConfig.create(
            code="condition",
            name="Condition",
            template="{% if debug %}DEBUG{% else %}PROD{% endif %}",
        )

        assert _render(workflow, {"debug": True}) == "DEBUG"
        assert _render(workflow, {"debug": False}) == "PROD"

    def test_render_with_loop(self):
        """Test rendering with loops."""
        workflow = WorkflowConfig.create(
            code="loop", name="Loop", template="{% for item in items %}{{ item }} {% endfor %}"
        )

        result = _render(workflow, {"items": ["a", "b", "c"]})
        assert result == "a b c "

    def test_render_plain_format(self):
        """Test plain format returns template as-is."""
        workflow = WorkflowConfig.create(
            code="plain", name="Plain", template="No {{ substitution }}", format="plain"
        )

        result = _render(workflow, {})
        assert result == "No {{ substitution }}"

    def test_render_undefined_variable_error(self):
        """Test undefined variable renders as empty (Jinja2 default)."""
        workflow = WorkflowConfig.create(
            code="strict", name="Strict", template="{{ undefined_var }}"
        )

        # Jinja2 by default treats undefined as empty string
        # But we might want strict mode in the future
        result = _render(workflow, {})
        assert result == ""

    def test_render_invalid_template(self):
        """Test rendering invalid template raises error."""
        workflow = WorkflowConfig.create(
            code="invalid", name="Invalid", template="{% invalid_tag %}", format="jinja2"
        )

        with pytest.raises(ValueError) as exc_info:
            _render(workflow, {})

        assert "Template rendering error" in str(exc_info.value)


class TestValidateTemplateSyntax(TestIsolator):
    """Test template syntax validation (Jinja2 parse)."""

    def test_validate_template_syntax_error(self):
        """Test invalid Jinja2 template syntax is reported."""
        errors = validate_template_syntax("{% if true %}unclosed", "jinja2")
        assert any("Template syntax error" in e for e in errors)

    def test_validate_template_syntax_valid(self):
        """Test valid Jinja2 template passes."""
        errors = validate_template_syntax("Hello {{ name }}", "jinja2")
        assert errors == []

    def test_validate_template_syntax_non_jinja_skipped(self):
        """Test non-jinja format is skipped (no errors)."""
        assert validate_template_syntax("anything", "plain") == []
        assert validate_template_syntax("anything", "mustache") == []
