from __future__ import annotations

from typer.testing import CliRunner

from python_claw.adapters.cli.main import app


def test_cli_help_loads_without_agent_implementation() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Python AgentOps Harness" in result.output
