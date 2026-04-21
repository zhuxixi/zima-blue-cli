"""Integration tests for zima --version flag."""

from typer.testing import CliRunner

from zima.cli import app

runner = CliRunner()


class TestCLIVersion:
    def test_version_long_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "zima" in result.output

    def test_version_short_flag(self):
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "zima" in result.output

    def test_version_output_format(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        # Should be "zima X.Y.Z" or "zima unknown"
        output = result.output.strip()
        assert output.startswith("zima "), f"Unexpected output: {output}"

    def test_version_in_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "--version" in result.output