"""ZimaBlue CLI - v2 Simplified"""

from __future__ import annotations

from zima.utils import setup_windows_utf8

setup_windows_utf8()

import typer

from zima import get_version
from zima.commands import agent as agent_cmd
from zima.commands import daemon as daemon_cmd
from zima.commands import env as env_cmd
from zima.commands import pjob as pjob_cmd
from zima.commands import pmg as pmg_cmd
from zima.commands import schedule as schedule_cmd
from zima.commands import variable as variable_cmd
from zima.commands import workflow as workflow_cmd

app = typer.Typer(
    name="zima",
    help="ZimaBlue CLI - Agent Runner",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"zima {get_version()}")
        raise typer.Exit()


# Register subcommands
app.add_typer(agent_cmd.app, name="agent")
app.add_typer(workflow_cmd.app, name="workflow")
app.add_typer(variable_cmd.app, name="variable")
app.add_typer(env_cmd.app, name="env")
app.add_typer(pmg_cmd.app, name="pmg")
app.add_typer(pjob_cmd.app, name="pjob")
app.add_typer(schedule_cmd.app, name="schedule")
app.add_typer(daemon_cmd.app, name="daemon")


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        help="Show version and exit",
        callback=_version_callback,
        is_eager=True,
    ),
):
    """ZimaBlue CLI - Agent Runner"""


if __name__ == "__main__":
    app()
