"""Typer CLI shell for the skeleton milestone."""

from __future__ import annotations

from typing import Annotated

import typer

from python_claw.__about__ import __version__

app = typer.Typer(
    add_completion=False,
    help="Python AgentOps Harness command line.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"python-claw {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the python-claw version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Python AgentOps Harness command line."""
    _ = version


def main() -> None:
    app()
