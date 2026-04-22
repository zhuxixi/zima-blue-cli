"""Tests for example YAML templates."""

from __future__ import annotations

import pytest
import yaml

from zima.models.agent import AgentConfig
from zima.models.env import EnvConfig
from zima.models.pjob import PJobConfig
from zima.models.pmg import PMGConfig
from zima.models.variable import VariableConfig
from zima.models.workflow import WorkflowConfig
from zima.templates.examples import (
    AGENT_EXAMPLE,
    ENV_EXAMPLE,
    EXAMPLES,
    PJOB_EXAMPLE,
    PMG_EXAMPLE,
    REVIEWER_WORKFLOW,
    VALID_KINDS,
    VARIABLE_EXAMPLE,
    WORKFLOW_EXAMPLE,
)

# Mapping from kind string to model class and example constant
KIND_MODEL_MAP = {
    "agent": (AgentConfig, AGENT_EXAMPLE),
    "workflow": (WorkflowConfig, WORKFLOW_EXAMPLE),
    "variable": (VariableConfig, VARIABLE_EXAMPLE),
    "env": (EnvConfig, ENV_EXAMPLE),
    "pmg": (PMGConfig, PMG_EXAMPLE),
    "pjob": (PJobConfig, PJOB_EXAMPLE),
}


def _get_first_example(kind: str) -> str:
    """Get the first (default) example for a given kind."""
    return list(EXAMPLES[kind].values())[0]


class TestExamplesStructure:
    """Parametrized tests for YAML structure correctness."""

    @pytest.mark.parametrize("kind", list(EXAMPLES.keys()))
    def test_example_is_valid_yaml(self, kind: str):
        """Each example must parse as valid YAML."""
        for example_yaml in EXAMPLES[kind].values():
            data = yaml.safe_load(example_yaml)
            assert isinstance(data, dict)

    @pytest.mark.parametrize("kind", list(EXAMPLES.keys()))
    def test_example_has_required_top_level_fields(self, kind: str):
        """Each example must have apiVersion, kind, metadata, spec."""
        for example_yaml in EXAMPLES[kind].values():
            data = yaml.safe_load(example_yaml)
            assert "apiVersion" in data, f"{kind}: missing apiVersion"
            assert "kind" in data, f"{kind}: missing kind"
            assert "metadata" in data, f"{kind}: missing metadata"
            assert "spec" in data, f"{kind}: missing spec"

    @pytest.mark.parametrize("kind", list(EXAMPLES.keys()))
    def test_example_metadata_has_code_and_name(self, kind: str):
        """Each example metadata must have code and name."""
        for example_yaml in EXAMPLES[kind].values():
            data = yaml.safe_load(example_yaml)
            metadata = data["metadata"]
            assert "code" in metadata, f"{kind}: metadata missing code"
            assert "name" in metadata, f"{kind}: metadata missing name"
            assert metadata["code"], f"{kind}: metadata.code is empty"
            assert metadata["name"], f"{kind}: metadata.name is empty"

    @pytest.mark.parametrize("kind", list(EXAMPLES.keys()))
    def test_example_kind_matches_entity(self, kind: str):
        """Each example kind field must match its entity type (capitalized)."""
        kind_map = {
            "agent": "Agent",
            "workflow": "Workflow",
            "variable": "Variable",
            "env": "Env",
            "pmg": "PMG",
            "pjob": "PJob",
            "schedule": "Schedule",
        }
        for example_yaml in EXAMPLES[kind].values():
            data = yaml.safe_load(example_yaml)
            assert (
                data["kind"] == kind_map[kind]
            ), f"{kind}: kind={data['kind']}, expected={kind_map[kind]}"


class TestExamplesCoverage:
    """Tests for EXAMPLES dict coverage."""

    def test_examples_covers_all_six_kinds(self):
        """EXAMPLES dict must contain all entity kinds."""
        expected = {"agent", "workflow", "variable", "env", "pmg", "pjob", "schedule"}
        assert set(EXAMPLES.keys()) == expected

    def test_valid_kinds_constant(self):
        """VALID_KINDS must be the correct set of kind strings."""
        expected = {"Agent", "Workflow", "Variable", "Env", "PMG", "PJob", "Schedule"}
        assert VALID_KINDS == expected

    def test_valid_kinds_size(self):
        """VALID_KINDS must have the correct number of entries."""
        assert len(VALID_KINDS) == 7


class TestAgentRoundTrip:
    """Round-trip test for Agent example."""

    def test_agent_from_dict(self):
        data = yaml.safe_load(AGENT_EXAMPLE)
        config = AgentConfig.from_dict(data)
        assert config.kind == "Agent"
        assert config.metadata.code == "my-agent"
        assert config.metadata.name == "My Agent"
        assert config.type == "kimi"
        assert config.parameters["model"] == "moonshot-v1-8k"
        assert config.defaults["workflow"] == "my-workflow"
        assert config.defaults["env"] == "my-env"
        assert config.is_valid()


class TestWorkflowRoundTrip:
    """Round-trip test for Workflow example."""

    def test_workflow_from_dict(self):
        data = yaml.safe_load(WORKFLOW_EXAMPLE)
        config = WorkflowConfig.from_dict(data)
        assert config.kind == "Workflow"
        assert config.metadata.code == "my-workflow"
        assert config.metadata.name == "My Workflow"
        assert config.format == "jinja2"
        assert "{{ role }}" in config.template
        assert "{{ task }}" in config.template
        assert len(config.variables) == 2
        assert config.variables[0].name == "role"
        assert config.variables[0].required is True
        assert config.variables[1].name == "task"
        assert "example" in config.tags
        assert config.version == "1.0.0"
        assert config.is_valid()


class TestVariableRoundTrip:
    """Round-trip test for Variable example."""

    def test_variable_from_dict(self):
        data = yaml.safe_load(VARIABLE_EXAMPLE)
        config = VariableConfig.from_dict(data)
        assert config.kind == "Variable"
        assert config.metadata.code == "my-variables"
        assert config.metadata.name == "My Variables"
        assert config.for_workflow == "my-workflow"
        assert config.values["role"] == "senior developer"
        assert config.values["task"] == "code review"
        assert config.is_valid()


class TestEnvRoundTrip:
    """Round-trip test for Env example."""

    def test_env_from_dict(self):
        data = yaml.safe_load(ENV_EXAMPLE)
        config = EnvConfig.from_dict(data)
        assert config.kind == "Env"
        assert config.metadata.code == "my-env"
        assert config.metadata.name == "My Environment"
        assert config.for_type == "kimi"
        assert config.variables["DEBUG"] == "false"
        assert len(config.secrets) == 1
        assert config.secrets[0].name == "API_KEY"
        assert config.secrets[0].source == "env"
        assert config.secrets[0].key == "MY_API_KEY"
        assert config.override_existing is False
        assert config.is_valid()


class TestPMGRoundTrip:
    """Round-trip test for PMG example."""

    def test_pmg_from_dict(self):
        data = yaml.safe_load(PMG_EXAMPLE)
        config = PMGConfig.from_dict(data)
        assert config.kind == "PMG"
        assert config.metadata.code == "my-pmg"
        assert config.metadata.name == "My Parameter Group"
        assert "kimi" in config.for_types
        assert "claude" in config.for_types
        assert len(config.parameters) == 2
        # verbose flag
        assert config.parameters[0].name == "verbose"
        assert config.parameters[0].type == "flag"
        assert config.parameters[0].enabled is True
        # model long param
        assert config.parameters[1].name == "model"
        assert config.parameters[1].type == "long"
        assert config.parameters[1].value == "moonshot-v1-8k"
        assert config.is_valid()


class TestPJobRoundTrip:
    """Round-trip test for PJob example."""

    def test_pjob_from_dict(self):
        data = yaml.safe_load(PJOB_EXAMPLE)
        config = PJobConfig.from_dict(data)
        assert config.kind == "PJob"
        assert config.metadata.code == "my-job"
        assert config.metadata.name == "My Job"
        assert "example" in config.metadata.labels
        assert config.spec.agent == "my-agent"
        assert config.spec.workflow == "my-workflow"
        assert config.spec.variable == "my-variables"
        assert config.spec.env == "my-env"
        assert config.spec.pmg == "my-pmg"
        assert config.spec.execution.work_dir == "."
        assert config.spec.execution.timeout == 600
        assert config.spec.execution.keep_temp is False
        assert config.spec.output.save_to == "./output.md"
        assert config.spec.output.format == "raw"
        assert config.spec.output.append is False
        assert config.is_valid()


class TestReviewerWorkflow:
    """Tests for the reviewer-cr workflow template."""

    def test_reviewer_workflow_exists(self):
        assert "reviewer-cr" in EXAMPLES["workflow"]

    def test_reviewer_workflow_renders(self):
        wf_yaml = EXAMPLES["workflow"]["reviewer-cr"]
        data = yaml.safe_load(wf_yaml)
        wf = WorkflowConfig.from_dict(data)

        rendered = wf.render(
            {
                "repo": "owner/repo",
                "pr_number": "42",
                "pr_title": "Fix bug",
                "pr_diff": "+some code",
            }
        )
        assert "owner/repo" in rendered
        assert "zima-review" in rendered
        assert "<verdict>" in rendered

    def test_reviewer_workflow_has_required_variables(self):
        wf_yaml = EXAMPLES["workflow"]["reviewer-cr"]
        data = yaml.safe_load(wf_yaml)
        wf = WorkflowConfig.from_dict(data)

        var_names = {v.name for v in wf.variables}
        assert var_names == {"repo", "pr_number", "pr_title", "pr_diff"}

        for v in wf.variables:
            assert v.required is True

    def test_reviewer_workflow_is_valid(self):
        wf_yaml = EXAMPLES["workflow"]["reviewer-cr"]
        data = yaml.safe_load(wf_yaml)
        wf = WorkflowConfig.from_dict(data)
        assert wf.is_valid()

    def test_reviewer_workflow_constant_matches_dict(self):
        assert REVIEWER_WORKFLOW == EXAMPLES["workflow"]["reviewer-cr"]
