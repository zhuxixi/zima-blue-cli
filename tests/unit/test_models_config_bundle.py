"""Unit tests for ConfigBundle.inject_dynamic_vars()."""

from __future__ import annotations

from zima.models.config_bundle import ConfigBundle
from zima.models.pjob import Overrides
from zima.models.variable import VariableConfig


class TestInjectDynamicVars:
    """Test the 3-tier variable priority merge logic in inject_dynamic_vars()."""

    def _make_bundle(
        self,
        variable: VariableConfig | None = None,
        overrides: Overrides | None = None,
    ) -> ConfigBundle:
        """Create a ConfigBundle with the given variable and overrides."""
        bundle = ConfigBundle()
        if variable is not None:
            bundle.variable = variable
        if overrides is not None:
            bundle.overrides = overrides
        return bundle

    # -- Scenario 1: Same key in runtime overrides AND preExec -> runtime wins --

    def test_runtime_override_wins_over_preexec(self):
        """When a key exists in both runtime overrides and preExec, runtime wins."""
        variable = VariableConfig.create(
            code="test-var",
            name="Test",
            values={"repo": "static-repo", "label": "static-label"},
        )
        overrides = Overrides(variable_values={"repo": "override-repo"})
        bundle = self._make_bundle(variable=variable, overrides=overrides)

        # Simulate the executor flow: apply_overrides is called before inject
        bundle.apply_overrides(overrides)

        dynamic_vars = {"repo": "preexec-repo", "extra": "preexec-extra"}
        bundle.inject_dynamic_vars(dynamic_vars)

        # "repo" should keep the override value, not the preExec value
        assert bundle.variable.values["repo"] == "override-repo"
        # "extra" from preExec should be injected
        assert bundle.variable.values["extra"] == "preexec-extra"
        # Static values untouched
        assert bundle.variable.values["label"] == "static-label"

    # -- Scenario 2: Same key in static config AND preExec -> preExec wins --

    def test_preexec_wins_over_static_config(self):
        """When a key exists in static config and preExec, preExec wins."""
        variable = VariableConfig.create(
            code="test-var",
            name="Test",
            values={"repo": "static-repo"},
        )
        bundle = self._make_bundle(variable=variable)

        dynamic_vars = {"repo": "preexec-repo"}
        bundle.inject_dynamic_vars(dynamic_vars)

        assert bundle.variable.values["repo"] == "preexec-repo"

    # -- Scenario 3: No conflicts -> additive merge --

    def test_additive_merge_no_conflicts(self):
        """When there are no key conflicts, both sources are merged."""
        variable = VariableConfig.create(
            code="test-var",
            name="Test",
            values={"static_key": "static_value"},
        )
        bundle = self._make_bundle(variable=variable)

        dynamic_vars = {"preexec_key": "preexec_value"}
        bundle.inject_dynamic_vars(dynamic_vars)

        assert bundle.variable.values["static_key"] == "static_value"
        assert bundle.variable.values["preexec_key"] == "preexec_value"

    # -- Edge case: bundle.variable is None --

    def test_none_variable_creates_new(self):
        """When bundle.variable is None, a new VariableConfig is created."""
        bundle = self._make_bundle(variable=None)

        dynamic_vars = {"pr_number": "42", "repo": "owner/repo"}
        bundle.inject_dynamic_vars(dynamic_vars)

        assert bundle.variable is not None
        assert bundle.variable.values == {"pr_number": "42", "repo": "owner/repo"}

    # -- Edge case: empty dynamic_vars --

    def test_empty_dynamic_vars_noop(self):
        """When dynamic_vars is empty, bundle is not modified."""
        variable = VariableConfig.create(
            code="test-var",
            name="Test",
            values={"existing": "value"},
        )
        bundle = self._make_bundle(variable=variable)
        original_values = bundle.variable.values.copy()

        bundle.inject_dynamic_vars({})

        assert bundle.variable.values == original_values

    def test_empty_dynamic_vars_no_variable_noop(self):
        """When dynamic_vars is empty and variable is None, nothing happens."""
        bundle = self._make_bundle(variable=None)

        bundle.inject_dynamic_vars({})

        assert bundle.variable is None

    # -- Edge case: overrides present but no variable --

    def test_none_variable_with_overrides(self):
        """When variable is None but overrides exist, new VariableConfig is created
        with preExec values (overrides only protect existing variable keys)."""
        overrides = Overrides(variable_values={"repo": "override-repo"})
        bundle = self._make_bundle(variable=None, overrides=overrides)

        dynamic_vars = {"repo": "preexec-repo", "extra": "value"}
        bundle.inject_dynamic_vars(dynamic_vars)

        assert bundle.variable is not None
        # With no existing variable, preExec values are all injected
        assert bundle.variable.values["repo"] == "preexec-repo"
        assert bundle.variable.values["extra"] == "value"
