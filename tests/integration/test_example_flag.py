"""CLI integration tests for --example flag on create commands."""

from __future__ import annotations

from typer.testing import CliRunner

from zima.commands.agent import app as agent_app
from zima.commands.env import app as env_app
from zima.commands.pjob import app as pjob_app
from zima.commands.pmg import app as pmg_app
from zima.commands.variable import app as variable_app
from zima.commands.workflow import app as workflow_app

runner = CliRunner()


class TestAgentExample:
    def test_create_example_exits_zero(self):
        result = runner.invoke(agent_app, ["create", "--example"])
        assert result.exit_code == 0

    def test_create_example_outputs_yaml(self):
        result = runner.invoke(agent_app, ["create", "--example"])
        assert "apiVersion: zima.io/v1" in result.output
        assert "kind: Agent" in result.output
        assert "my-agent" in result.output

    def test_create_example_ignores_other_params(self):
        result = runner.invoke(agent_app, ["create", "--example", "--name", "test"])
        assert result.exit_code == 0
        assert "my-agent" in result.output

    def test_create_without_example_still_requires_params(self):
        result = runner.invoke(agent_app, ["create"])
        assert result.exit_code == 1


class TestWorkflowExample:
    def test_create_example(self):
        result = runner.invoke(workflow_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: Workflow" in result.output


class TestVariableExample:
    def test_create_example(self):
        result = runner.invoke(variable_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: Variable" in result.output


class TestEnvExample:
    def test_create_example(self):
        result = runner.invoke(env_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: Env" in result.output


class TestPmgExample:
    def test_create_example(self):
        result = runner.invoke(pmg_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: PMG" in result.output


class TestPjobExample:
    def test_create_example(self):
        result = runner.invoke(pjob_app, ["create", "--example"])
        assert result.exit_code == 0
        assert "kind: PJob" in result.output
