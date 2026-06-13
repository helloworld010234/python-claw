"""Tests for the bash tool adapter and dangerous command policy."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from python_claw.adapters.tools.policy import (
    CommandSafetyDecision,
    DangerousCommandError,
    DangerousCommandPolicy,
    SafetyDecision,
)
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
        "rm -fr /tmp/foo",
        "rm -Rf /tmp/foo",
        "rm -dR /tmp/foo",
        "rm --recursive /tmp/foo",
        "rm --dir --recursive /tmp/foo",
        "sudo apt update",
        "drop database users",
        "nginx -s reload",
        "systemctl restart nginx",
        "kill 1234",
        "KILL 1234",
        "RM -RF /tmp/foo",
        "Remove-Item -Recurse C:\\foo",
        "Remove-Item -Force -Recurse C:\\foo",
        "remove-item -r -path foo",
        "REMOVE-ITEM -RECURSE -PATH foo",
        "rm -Recurse C:\\foo",
        "del -Recurse C:\\foo",
        "erase -Recurse C:\\foo",
        "rd /s c:\\foo",
        "RD /S c:\\foo",
        "rmdir /s /q c:\\foo",
        "del /s c:\\foo",
        "DEL /S *.txt",
        "erase /s C:\\foo",
        "ERASE /S *.txt",
        "format C:",
        "FORMAT D:",
        "format",
        "shutdown /s",
        "SHUTDOWN /R",
        "Stop-Process -Name foo",
        "STOP-PROCESS -ID 1234",
    ],
)
def test_policy_check_raises_for_non_allowed_commands(command: str) -> None:
    """The legacy check() interface blocks DENY, APPROVAL and unknown commands."""
    policy = DangerousCommandPolicy()
    with pytest.raises(DangerousCommandError):
        policy.check(command)


@pytest.mark.parametrize(
    "command,expected",
    [
        ("echo hello", CommandSafetyDecision.ALLOW),
        ("python -c 'print(1)'", CommandSafetyDecision.ALLOW),
        ("ls -la", CommandSafetyDecision.ALLOW),
        ("cat file.txt", CommandSafetyDecision.ALLOW),
        ("git status", CommandSafetyDecision.ALLOW),
        ("mkdir foo", CommandSafetyDecision.ALLOW),
        ("cp a b", CommandSafetyDecision.ALLOW),
        ("sudo apt update", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("kill 1234", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("nginx -s reload", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("systemctl restart nginx", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("Stop-Process -Name foo", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("rm -r /tmp/foo", CommandSafetyDecision.DENY),
        ("rm -rf /tmp/foo", CommandSafetyDecision.DENY),
        ("rm -fr /tmp/foo", CommandSafetyDecision.DENY),
        ("rm -Rf /tmp/foo", CommandSafetyDecision.DENY),
        ("rm -dR /tmp/foo", CommandSafetyDecision.DENY),
        ("rm --recursive /tmp/foo", CommandSafetyDecision.DENY),
        ("rm --dir --recursive /tmp/foo", CommandSafetyDecision.DENY),
        ("drop database users", CommandSafetyDecision.DENY),
        ("Remove-Item -Recurse C:\\foo", CommandSafetyDecision.DENY),
        ("Remove-Item -r C:\\foo", CommandSafetyDecision.DENY),
        ("rm -Recurse C:\\foo", CommandSafetyDecision.DENY),
        ("del -Recurse C:\\foo", CommandSafetyDecision.DENY),
        ("erase -Recurse C:\\foo", CommandSafetyDecision.DENY),
        ("rd /s c:\\foo", CommandSafetyDecision.DENY),
        ("del /s c:\\foo", CommandSafetyDecision.DENY),
        ("erase /s C:\\foo", CommandSafetyDecision.DENY),
        ("format C:", CommandSafetyDecision.DENY),
        ("format", CommandSafetyDecision.DENY),
        ("shutdown /s", CommandSafetyDecision.DENY),
    ],
)
def test_policy_decisions(command: str, expected: CommandSafetyDecision) -> None:
    policy = DangerousCommandPolicy()
    decision = policy.evaluate(command)
    assert isinstance(decision, SafetyDecision)
    assert decision.decision is expected


@pytest.mark.parametrize(
    "command",
    [
        "echo hello",
        "python -c 'print(1)'",
        "ls -la",
        "cat file.txt",
        "git status",
        "mkdir foo",
        "cp a b",
    ],
)
def test_policy_allows_explicitly_safe_commands(command: str) -> None:
    policy = DangerousCommandPolicy()
    policy.check(command)


@pytest.mark.parametrize(
    "command",
    [
        "rm file.txt",
        "del file.txt",
        "Remove-Item -Path file.txt",
        "remove-item -force file.txt",
        "rd folder",
        "rmdir folder",
        "dropbox start",
        "skillful echo",
        "killall process",
        "format(x)",
        "myshutdown",
        "deliver package",
        "rdonly file",
        "unknown_command --flag",
    ],
)
def test_policy_conservative_mode_requires_approval_for_unknown(command: str) -> None:
    """In conservative mode unknown commands are not allowed to run directly."""
    policy = DangerousCommandPolicy()
    decision = policy.evaluate(command)
    assert decision.decision is CommandSafetyDecision.REQUIRE_APPROVAL
    with pytest.raises(DangerousCommandError):
        policy.check(command)


def test_policy_non_conservative_mode_allows_unknown() -> None:
    """Without conservative mode unknown commands fall back to ALLOW."""
    policy = DangerousCommandPolicy(conservative=False)
    decision = policy.evaluate("unknown_command --flag")
    assert decision.decision is CommandSafetyDecision.ALLOW


def test_policy_deny_rules_take_precedence_over_approval() -> None:
    """Destructive subcommands must be denied even when prefixed with sudo."""
    policy = DangerousCommandPolicy()
    assert policy.evaluate("sudo rm -rf /").decision is CommandSafetyDecision.DENY
    assert policy.evaluate("sudo rm --recursive /tmp/foo").decision is CommandSafetyDecision.DENY


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


def test_bash_timeout_kills_child_process(sandbox: WorkspaceSandbox) -> None:
    """Timeout must terminate the whole process tree, not just the shell."""
    tool = BashTool(
        sandbox=sandbox,
        policy=DangerousCommandPolicy(),
        timeout_seconds=1,
        max_output_chars=1000,
    )
    sentinel = sandbox.root / "sentinel.txt"
    script = sandbox.root / "spawn_child.py"
    delay_seconds = 5
    script.write_text(
        "import subprocess, sys, time\n"
        "sentinel = sys.argv[1]\n"
        f"subprocess.Popen([sys.executable, '-c', 'import time, sys; from pathlib import Path; "
        f'time.sleep({delay_seconds}); Path(sys.argv[1]).write_text("leak")\', sentinel])\n'
        "time.sleep(60)\n",
        encoding="utf-8",
    )

    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": f"python {script} {sentinel}"},
    )
    result = asyncio.run(tool.execute(call))
    assert result.is_error is True
    assert "timed out" in result.output

    # Wait longer than the child would need to write the sentinel if it survived.
    time.sleep(delay_seconds + 2)
    assert not sentinel.exists()


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
        "rm -fr /tmp/foo",
        "rm --recursive /tmp/foo",
        "rm --dir --recursive /tmp/foo",
        "drop database users",
        "Remove-Item -Recurse C:\\foo",
        "rm -Recurse C:\\foo",
        "del -Recurse C:\\foo",
        "erase -Recurse C:\\foo",
        "rd /s c:\\foo",
        "del /s c:\\foo",
        "erase /s C:\\foo",
        "format C:",
        "format",
        "shutdown /s",
    ],
)
def test_bash_denies_dangerous_commands(bash_tool: BashTool, command: str) -> None:
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "denied by safety policy" in result.output


@pytest.mark.parametrize(
    "command",
    [
        "sudo echo hi",
        "kill 1234",
        "systemctl restart nginx",
        "nginx -s reload",
        "Stop-Process -Name foo",
        "rm file.txt",
        "del file.txt",
        "unknown_command --flag",
    ],
)
def test_bash_requires_approval_for_risky_or_unknown_commands(
    bash_tool: BashTool, command: str
) -> None:
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "requires approval before execution" in result.output


def test_bash_require_approval_does_not_run_command(bash_tool: BashTool) -> None:
    """A command that requires approval must not be executed."""
    side_effect = bash_tool._sandbox.root / "should_not_exist.txt"
    command = (
        f"python -c \"from pathlib import Path; Path('{side_effect.name}').write_text('x')\" "
        "&& sudo echo hi"
    )
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "requires approval before execution" in result.output
    assert not side_effect.exists()


def test_bash_deny_does_not_run_command(bash_tool: BashTool) -> None:
    """A denied command must not be executed, even if a later part looks safe."""
    side_effect = bash_tool._sandbox.root / "should_not_exist_denied.txt"
    command = (
        "rm -rf /tmp/nonexistent_claw_test "
        f"&& python -c \"from pathlib import Path; Path('{side_effect.name}').write_text('x')\""
    )
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "denied by safety policy" in result.output
    assert not side_effect.exists()


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/foo",
        "Remove-Item -Recurse C:\\foo",
        "rm -Recurse C:\\foo",
        "rd /s c:\\foo",
        "del /s c:\\foo",
        "erase /s C:\\foo",
        "format C:",
        "shutdown /s",
    ],
)
def test_bash_windows_destructive_commands_still_blocked(bash_tool: BashTool, command: str) -> None:
    """Destructive Windows/Unix patterns remain blocked without approval."""
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert (
        "denied by safety policy" in result.output
        or "requires approval before execution" in result.output
    )


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
