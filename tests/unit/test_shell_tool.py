"""Tests for the bash tool adapter and dangerous command policy."""

from __future__ import annotations

import asyncio
import sys
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


class PermissivePolicy(DangerousCommandPolicy):
    """Policy that allows any command, used to test BashTool mechanics."""

    def evaluate(self, command: str) -> SafetyDecision:  # noqa: ARG002
        return SafetyDecision(
            decision=CommandSafetyDecision.ALLOW,
            reason="test permit",
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
        ":(){ :|:& };:",
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
        ("ls -la", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("cat file.txt", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("dir", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("type file.txt", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("which python", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("where python", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("grep pattern file.txt", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("findstr pattern file.txt", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("git status", CommandSafetyDecision.ALLOW),
        ("git log --oneline", CommandSafetyDecision.ALLOW),
        ("git diff HEAD~1", CommandSafetyDecision.ALLOW),
        ("git show HEAD", CommandSafetyDecision.ALLOW),
        ("git branch", CommandSafetyDecision.ALLOW),
        ("python -c 'print(1)'", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("python3 script.py", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("node -e 'console.log(1)'", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("npm install", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("npx eslint", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("pip install requests", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("uv run pytest", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("cp a b", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("copy a b", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("mv a b", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("move a b", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("mkdir foo", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("touch file.txt", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("curl https://example.com", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("wget https://example.com", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("bash -c 'echo hi'", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("sh script.sh", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("powershell -Command 'Get-Date'", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("pwsh -c 'Get-Date'", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("cmd /c dir", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("chmod +x script.sh", CommandSafetyDecision.REQUIRE_APPROVAL),
        ("chown user:group file.txt", CommandSafetyDecision.REQUIRE_APPROVAL),
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
        ("mkfs.ext4 /dev/sda1", CommandSafetyDecision.DENY),
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
        "pwd",
        "git status",
        "git log",
        "git log --oneline",
        "git diff",
        "git diff HEAD~1",
        "git show",
        "git show HEAD",
        "git branch",
    ],
)
def test_policy_allows_explicitly_safe_commands(command: str) -> None:
    policy = DangerousCommandPolicy()
    policy.check(command)


def test_git_allow_rules_reject_path_arguments() -> None:
    """Git inspection commands with path-like arguments require approval."""
    policy = DangerousCommandPolicy()
    assert (
        policy.evaluate("git status ../outside").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate("git diff C:\\Windows\\win.ini").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate("git show HEAD:../secret").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )


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


@pytest.mark.parametrize(
    "command",
    [
        "echo hello > file.txt",
        "echo hello | cat",
        "echo hello && echo world",
        "echo hello; echo world",
        "echo hello || echo world",
        "echo $(hostname)",
        "echo `hostname`",
        "echo hello\necho world",
    ],
)
def test_policy_shell_composition_requires_approval(command: str) -> None:
    """Redirection, pipes, chains and substitution require approval."""
    policy = DangerousCommandPolicy()
    decision = policy.evaluate(command)
    assert decision.decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert "shell composition" in decision.reason


def test_policy_deny_rules_take_precedence_over_approval() -> None:
    """Destructive subcommands must be denied even when prefixed with sudo."""
    policy = DangerousCommandPolicy()
    assert policy.evaluate("sudo rm -rf /").decision is CommandSafetyDecision.DENY
    assert policy.evaluate("sudo rm --recursive /tmp/foo").decision is CommandSafetyDecision.DENY


def test_policy_deny_rules_take_precedence_over_approval_interpreters() -> None:
    """Destructive subcommands nested in interpreters must still be denied."""
    policy = DangerousCommandPolicy()
    assert (
        policy.evaluate("python -c \"import os; os.system('rm -rf /')\"").decision
        is CommandSafetyDecision.DENY
    )
    assert policy.evaluate('bash -c "rm -rf /tmp/foo"').decision is CommandSafetyDecision.DENY


def test_bash_success(bash_tool: BashTool) -> None:
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": "echo hello"},
    )
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is False
    assert "exit code: 0" in result.output
    assert "hello" in result.output


def test_bash_non_zero_exit_code(sandbox: WorkspaceSandbox) -> None:
    """The bash tool reports non-zero exit codes, independent of policy."""
    tool = BashTool(
        sandbox=sandbox,
        policy=PermissivePolicy(),
        timeout_seconds=5,
        max_output_chars=1000,
    )
    command = "where nonexistent_file.exe" if sys.platform == "win32" else "which nonexistent_cmd"
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": command},
    )
    result = asyncio.run(tool.execute(call))
    assert result.is_error is True
    assert "exit code: " in result.output
    code_line = result.output.split("exit code: ")[1].splitlines()[0].strip()
    assert code_line != "0"


def test_bash_captures_stderr(sandbox: WorkspaceSandbox) -> None:
    """The bash tool captures stderr even when policy blocks path-reading commands."""
    tool = BashTool(
        sandbox=sandbox,
        policy=PermissivePolicy(),
        timeout_seconds=5,
        max_output_chars=1000,
    )
    call = ToolCall(
        id="c1",
        name="bash",
        arguments={"command": "python -c \"import sys; sys.stderr.write('boom\\n'); sys.exit(1)\""},
    )
    result = asyncio.run(tool.execute(call))
    assert result.is_error is True
    assert "stderr:" in result.output
    assert "boom" in result.output


def test_bash_timeout(sandbox: WorkspaceSandbox) -> None:
    """Timeout terminates a long-running allowed command."""
    tool = BashTool(
        sandbox=sandbox,
        policy=PermissivePolicy(),
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
        policy=PermissivePolicy(),
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
        arguments={
            "command": "echo xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        },
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
        ":(){ :|:& };:",
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
        "python -c 'print(1)'",
        "node -e 'console.log(1)'",
        "cp a b",
        "mv a b",
        "mkdir foo",
        "touch file.txt",
        "curl https://example.com",
        "bash -c 'echo hi'",
        "powershell -Command 'Get-Date'",
        "cmd /c dir",
        "chmod +x script.sh",
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


@pytest.mark.parametrize(
    "command",
    [
        "python -c \"from pathlib import Path; Path('should_not_exist.txt').write_text('x')\"",
        "mkdir should_not_exist_dir",
        "touch should_not_exist.txt",
        "cp should_not_exist.txt should_not_exist2.txt",
    ],
)
def test_bash_require_approval_does_not_run_command(bash_tool: BashTool, command: str) -> None:
    """A command that requires approval must not be executed."""
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "requires approval before execution" in result.output


def test_bash_deny_does_not_run_command(bash_tool: BashTool) -> None:
    """A denied command must not be executed, even if a later part looks safe."""
    side_effect = bash_tool._sandbox.root / "should_not_exist_denied.txt"
    command = f"rm -rf /tmp/nonexistent_claw_test && echo created > {side_effect.name}"
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "denied by safety policy" in result.output
    assert not side_effect.exists()


@pytest.mark.parametrize(
    "command",
    [
        "ls ..",
        "dir ..",
        "cat ../AGENTS.md",
        "type C:\\Windows\\win.ini",
        "grep pattern ../secret.txt",
        "findstr pattern C:\\Windows\\win.ini",
    ],
)
def test_bash_path_reading_commands_require_approval(bash_tool: BashTool, command: str) -> None:
    """Path-reading shell commands are blocked before any filesystem access."""
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "requires approval before execution" in result.output


def test_policy_path_reading_probe() -> None:
    """Manual acceptance probe for the shell safety policy boundary."""
    policy = DangerousCommandPolicy()
    assert policy.evaluate("ls ..").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert policy.evaluate("cat ../AGENTS.md").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert (
        policy.evaluate("type C:\\Windows\\win.ini").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate("grep pattern ../secret.txt").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate("findstr pattern C:\\Windows\\win.ini").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert policy.evaluate("echo hello").decision is CommandSafetyDecision.ALLOW
    assert policy.evaluate("git status").decision is CommandSafetyDecision.ALLOW
    assert (
        policy.evaluate('python -c "print(1)"').decision is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert policy.evaluate("rm -rf .").decision is CommandSafetyDecision.DENY


@pytest.mark.parametrize(
    "command",
    [
        "echo %PATH%",
        "echo %DEEPSEEK_API_KEY%",
        "echo %USERNAME%",
        "echo !PATH!",
        "echo !DEEPSEEK_API_KEY!",
        "echo %PATH:~0,3%",
        "echo %DEEPSEEK_API_KEY:~0,8%",
        "echo %PATH:Windows=REDACTED%",
        "echo %ProgramFiles(x86)%",
        "echo !PATH:~0,3!",
        "echo !DEEPSEEK_API_KEY:~0,8!",
        "echo %SECRET.KEY%",
        "echo %SECRET-KEY%",
        "echo %API KEY%",
        "echo % LEADING%",
        "echo !SECRET.KEY!",
        "echo !SECRET-KEY!",
        "echo !API KEY!",
        "echo ! LEADING!",
    ],
)
def test_policy_windows_variable_expansion_requires_approval(command: str) -> None:
    """Windows %VAR% and !VAR! expansion must require approval even in echo."""
    policy = DangerousCommandPolicy()
    decision = policy.evaluate(command)
    assert decision.decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert "shell variable expansion" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "echo %PATH%",
        "echo %DEEPSEEK_API_KEY%",
        "echo %USERNAME%",
        "echo !PATH!",
        "echo !DEEPSEEK_API_KEY!",
        "echo %PATH:~0,3%",
        "echo %DEEPSEEK_API_KEY:~0,8%",
        "echo %PATH:Windows=REDACTED%",
        "echo %ProgramFiles(x86)%",
        "echo !PATH:~0,3!",
        "echo !DEEPSEEK_API_KEY:~0,8!",
        "echo %SECRET.KEY%",
        "echo %SECRET-KEY%",
        "echo %API KEY%",
        "echo !SECRET.KEY!",
        "echo !SECRET-KEY!",
        "echo !API KEY!",
    ],
)
def test_bash_windows_variable_expansion_requires_approval(
    bash_tool: BashTool, command: str
) -> None:
    """BashTool must block Windows-style variable expansion before execution."""
    call = ToolCall(id="c1", name="bash", arguments={"command": command})
    result = asyncio.run(bash_tool.execute(call))
    assert result.is_error is True
    assert "requires approval before execution" in result.output


def test_policy_plain_delimiter_text_not_mistaken_for_variable() -> None:
    """Plain delimiter text without a closing delimiter is not treated as expansion.

    This is a deliberate safety-precision trade-off: we only flag well-formed
    ``%...%`` / ``!...!`` pairs that Windows shells actually expand.
    """
    policy = DangerousCommandPolicy()
    assert policy.evaluate("echo 100% done").decision is CommandSafetyDecision.ALLOW
    assert policy.evaluate("echo progress 50%").decision is CommandSafetyDecision.ALLOW
    assert policy.evaluate("echo % incomplete").decision is CommandSafetyDecision.ALLOW
    assert policy.evaluate("echo ! incomplete").decision is CommandSafetyDecision.ALLOW


def test_policy_windows_variable_expansion_probe() -> None:
    """Manual acceptance probe for Windows variable expansion blocking."""
    policy = DangerousCommandPolicy()
    assert policy.evaluate("echo %PATH%").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert (
        policy.evaluate("echo %DEEPSEEK_API_KEY%").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert policy.evaluate("echo !PATH!").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert policy.evaluate("echo hello").decision is CommandSafetyDecision.ALLOW
    assert (
        policy.evaluate("echo %PATH:~0,3%").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate("echo %DEEPSEEK_API_KEY:~0,8%").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate("echo %ProgramFiles(x86)%").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert (
        policy.evaluate("echo !DEEPSEEK_API_KEY:~0,8!").decision
        is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert policy.evaluate("echo %SECRET.KEY%").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert (
        policy.evaluate("echo %SECRET-KEY%").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert policy.evaluate("echo %API KEY%").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert policy.evaluate("echo % LEADING%").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert policy.evaluate("echo !SECRET.KEY!").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert (
        policy.evaluate("echo !SECRET-KEY!").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    )
    assert policy.evaluate("echo !API KEY!").decision is CommandSafetyDecision.REQUIRE_APPROVAL
    assert policy.evaluate("echo ! LEADING!").decision is CommandSafetyDecision.REQUIRE_APPROVAL


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
    assert "denied by safety policy" in result.output


def test_bash_non_conservative_mode_runs_unknown_commands(sandbox: WorkspaceSandbox) -> None:
    """In non-conservative mode unknown commands are executed by the bash tool."""
    tool = BashTool(
        sandbox=sandbox,
        policy=DangerousCommandPolicy(conservative=False),
        timeout_seconds=5,
        max_output_chars=1000,
    )
    call = ToolCall(id="c1", name="bash", arguments={"command": "whoami"})
    result = asyncio.run(tool.execute(call))
    assert result.is_error is False
    assert "exit code: 0" in result.output


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
