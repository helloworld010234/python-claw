"""Tests for the bash tool adapter and dangerous command policy."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from python_claw.adapters.tools.policy import DangerousCommandError, DangerousCommandPolicy
from python_claw.adapters.tools.sandbox import WorkspaceSandbox
from python_claw.adapters.tools.shell import BashTool
from python_claw.domain.message import ToolCall


@pytest.fixture
def sandbox(tmp_path: Path) -> WorkspaceSandbox:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return WorkspaceSandbox(workspace)


@pytest.fixture
def bash_tool(sandbox: WorkspaceSandbox) -> BashTool:
    return BashTool(
        sandbox=sandbox,
        policy=DangerousCommandPolicy(),
        timeout_seconds=5,
        max_output_chars=1000,
    )


@pytest.mark.parametrize(
    "command",
    [
        "rm -r /tmp/foo",
        "rm -rf /tmp/foo",
        "sudo apt update",
        "drop database users",
        "nginx -s reload",
        "systemctl restart nginx",
        "kill 1234",
        "KILL 1234",
        "RM -RF /tmp/foo",
    ],
)
def test_policy_blocks_dangerous_commands(command: str) -> None:
    policy = DangerousCommandPolicy()
    with pytest.raises(DangerousCommandError):
        policy.check(command)


@pytest.mark.parametrize(
    "command",
    [
        "echo hello",
        "python -c 'print(1)'",
        "ls -la",
        "cat file.txt",
        "rm file.txt",
        "dropbox start",
        "skillful echo",
        "killall process",
    ],
)
def test_policy_allows_safe_commands(command: str) -> None:
    policy = DangerousCommandPolicy()
    policy.check(command)


def test_bash_success(bash_tool: BashTool) -> None:
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": "python -c \"print('hello')\""},
    )
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is False
    assert "exit code: 0" in result.output
    assert "hello" in result.output


def test_bash_non_zero_exit_code(bash_tool: BashTool) -> None:
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": 'python -c "import sys; sys.exit(42)"'},
    )
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "exit code: 42" in result.output


def test_bash_captures_stderr(bash_tool: BashTool) -> None:
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": "python -c \"import sys; sys.stderr.write('oops')\""},
    )
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is False
    assert "oops" in result.output
    assert "stderr:" in result.output


def test_bash_timeout(sandbox: WorkspaceSandbox) -> None:
    tool = BashTool(
        sandbox=sandbox,
        policy=DangerousCommandPolicy(),
        timeout_seconds=1,
        max_output_chars=1000,
    )
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": 'python -c "import time; time.sleep(60)"'},
    )
    result = asyncio.run(tool.execute(call))
    assert result.is_error is True
    assert "timed out" in result.output


def test_bash_truncates_long_output(sandbox: WorkspaceSandbox) -> None:
    tool = BashTool(
        sandbox=sandbox,
        policy=DangerousCommandPolicy(),
        timeout_seconds=5,
        max_output_chars=40,
    )
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": "python -c \"print('x'*100)\""},
    )
    result = asyncio.run(tool.execute(call))
    assert result.is_error is False
    assert "...[truncated]" in result.output
    assert len(result.output) == 40


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/foo",
        "sudo echo hi",
        "kill 1234",
    ],
)
def test_bash_blocks_dangerous_commands(bash_tool: BashTool, command: str) -> None:
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "blocked by safety policy" in result.output


def test_bash_empty_command(bash_tool: BashTool) -> None:
    call = ToolCall(id="c1", name="bash", arguments={"command": ""})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "empty" in result.output


def test_bash_missing_argument(bash_tool: BashTool) -> None:
    call = ToolCall(id="c1", name="bash", arguments={})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "command" in result.output
