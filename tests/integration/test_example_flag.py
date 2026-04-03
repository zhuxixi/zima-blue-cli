"""CLI integration tests for --example flag on create commands."""

from __future__ import annotations

from typer.testing import CliRunner

from zima.commands.agent import app as agent_app

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
