"""Dangerous shell command policy for the bash tool."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class CommandSafetyDecision(StrEnum):
    """Safety decision for a shell command."""

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    """The outcome of evaluating a command against the safety policy."""

    decision: CommandSafetyDecision
    reason: str


class DangerousCommandError(Exception):
    """Raised when a command is not allowed to run directly."""

    def __init__(self, message: str, decision: CommandSafetyDecision | None = None) -> None:
        super().__init__(message)
        self.decision = decision


class DangerousCommandPolicy:
    """Decides whether a shell command may run, needs approval, or is denied.

    The policy uses three semantic tiers:

    * ``DENY`` – destructive or irreversible operations such as recursive file
      removal, disk formatting or system shutdown. These are blocked outright.
    * ``REQUIRE_APPROVAL`` – high-capability operations such as running an
      interpreter, copying/moving files, creating directories, invoking
      another shell, or reading files outside the workspace. These are not
      executed until a human approves them.
    * ``ALLOW`` – only for commands that are obviously read-only, low-risk and
      do not take path arguments (echo, pwd, git status/log/diff/show/branch).
      This tier is an explicit allowlist, not a default fallback.

    In *conservative mode* (the default for the bash tool and the static
    registry) any command that does not match an explicit ``ALLOW`` rule and
    does not match a deny/approval rule is treated as ``REQUIRE_APPROVAL``.
    This closes the "unknown command defaults to ALLOW" bypass that a purely
    pattern-based policy would leave open.

    Evaluation order is fixed so that the most restrictive decision wins:

    1. Deny rules catch destructive subcommands even when they are nested
       inside an approval-only wrapper such as ``sudo`` or ``bash -c``.
    2. Approval rules catch high-capability commands.
    3. Shell-composition checks catch redirections, pipes, command chains and
       command substitution that would let an otherwise safe command perform
       writes or execute other programs.
    4. Explicit allow rules finally permit simple read-only commands.
    5. In conservative mode unknown commands require approval; otherwise they
       are allowed.
    """

    # Destructive or irreversible commands are denied outright.
    _DENY_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
        # Unix recursive removal in all common flag orders and spellings.
        (
            re.compile(
                r"\brm(?:\s+-\S*[rR]\S*|\s+--recursive)(?=\s|$)",
                re.IGNORECASE,
            ),
            "recursive file removal",
        ),
        # PowerShell recursive remove (any order with -Recurse / -r).
        (
            re.compile(
                r"\bremove-item\b[\s\S]*?-(?:recurse|r)\b",
                re.IGNORECASE,
            ),
            "recursive file removal",
        ),
        # PowerShell rm/del/erase aliases used with -Recurse / -r.
        (
            re.compile(
                r"\b(?:rm|del|erase)\b[\s\S]*?-(?:recurse|r)\b",
                re.IGNORECASE,
            ),
            "recursive file removal",
        ),
        # Windows cmd recursive directory remove.
        (
            re.compile(r"\b(?:rd|rmdir)\b[\s\S]*?/s\b", re.IGNORECASE),
            "recursive directory removal",
        ),
        # Windows cmd recursive file delete (del /s and erase /s).
        (
            re.compile(r"\b(?:del|erase)\b[\s\S]*?/s\b", re.IGNORECASE),
            "recursive file deletion",
        ),
        # Windows disk format (bare command or with a drive letter).
        (
            re.compile(
                r"(?:^\s*)format\s*$|(?:^\s*|\s)format\s+[a-zA-Z]:",
                re.IGNORECASE,
            ),
            "disk formatting",
        ),
        # Filesystem creation (mkfs) is equivalent to formatting.
        (
            re.compile(r"\bmkfs(?:\.\w+)?\b", re.IGNORECASE),
            "disk formatting",
        ),
        # Windows shutdown / restart.
        (
            re.compile(r"\bshutdown\b", re.IGNORECASE),
            "system shutdown/reboot",
        ),
        # SQL/data destructive statements.
        (
            re.compile(r"\bdrop\b", re.IGNORECASE),
            "destructive data statement",
        ),
        # Classic bash fork bomb and common whitespace variants.
        (
            re.compile(
                r":\s*\(\s*\)\s*\{\s*:\s*\|?\s*:\s*&?\s*\}\s*;?\s*:",
                re.IGNORECASE,
            ),
            "resource exhaustion (fork bomb)",
        ),
    )

    # High-risk but sometimes legitimate commands require approval. Rules match
    # only at the start of the command line so that read-only inspection tools
    # are not incorrectly flagged just because a high-capability executable name
    # appears later.
    _APPROVAL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
        # Language interpreters and package/runtime managers.
        (re.compile(r"^\s*python[23]?\b", re.IGNORECASE), "python interpreter"),
        (re.compile(r"^\s*node\b", re.IGNORECASE), "node interpreter"),
        (re.compile(r"^\s*npm\b", re.IGNORECASE), "npm package manager"),
        (re.compile(r"^\s*npx\b", re.IGNORECASE), "npx package runner"),
        (re.compile(r"^\s*pip[23]?\b", re.IGNORECASE), "pip package manager"),
        (re.compile(r"^\s*uv\b", re.IGNORECASE), "uv package manager"),
        # File mutations.
        (re.compile(r"^\s*cp\b", re.IGNORECASE), "file copy"),
        (re.compile(r"^\s*copy\b", re.IGNORECASE), "file copy"),
        (re.compile(r"^\s*mv\b", re.IGNORECASE), "file move"),
        (re.compile(r"^\s*move\b", re.IGNORECASE), "file move"),
        (re.compile(r"^\s*mkdir\b", re.IGNORECASE), "directory creation"),
        (re.compile(r"^\s*touch\b", re.IGNORECASE), "file creation/update"),
        # Network downloaders.
        (re.compile(r"^\s*curl\b", re.IGNORECASE), "network download"),
        (re.compile(r"^\s*wget\b", re.IGNORECASE), "network download"),
        # Nested shells and command processors.
        (re.compile(r"^\s*bash\b", re.IGNORECASE), "nested shell"),
        (re.compile(r"^\s*sh\b", re.IGNORECASE), "nested shell"),
        (re.compile(r"^\s*powershell\b", re.IGNORECASE), "powershell interpreter"),
        (re.compile(r"^\s*pwsh\b", re.IGNORECASE), "powershell interpreter"),
        (re.compile(r"^\s*cmd\b", re.IGNORECASE), "windows command processor"),
        # Permission changes.
        (re.compile(r"^\s*chmod\b", re.IGNORECASE), "permission change"),
        (re.compile(r"^\s*chown\b", re.IGNORECASE), "permission change"),
        # Privilege escalation.
        (re.compile(r"^\s*sudo\b", re.IGNORECASE), "privilege escalation"),
        # Path-reading commands can access arbitrary paths, so they require
        # approval until a robust argument-level workspace sandbox is in place.
        # Use the dedicated read_file tool for controlled file reads.
        (re.compile(r"^\s*(?:ls|ll|dir)\b", re.IGNORECASE), "path-reading command"),
        (re.compile(r"^\s*(?:cat|type)\b", re.IGNORECASE), "path-reading command"),
        (re.compile(r"^\s*(?:grep|findstr)\b", re.IGNORECASE), "path-reading command"),
        (re.compile(r"^\s*(?:which|where)\b", re.IGNORECASE), "path-reading command"),
        # Service control.
        (re.compile(r"^\s*nginx\s+-s\b", re.IGNORECASE), "service control"),
        (re.compile(r"^\s*systemctl\b", re.IGNORECASE), "service control"),
        # Process termination.
        (re.compile(r"^\s*kill\b", re.IGNORECASE), "process termination"),
        (
            re.compile(r"^\s*stop-process\b", re.IGNORECASE),
            "process termination",
        ),
    )

    # Characters and sequences that turn an otherwise simple command into a
    # shell composition (redirection, pipe, command chain, substitution,
    # background job, multi-line script). Any command containing these is
    # treated as requiring approval in conservative mode, even if the base
    # command is on the allowlist.
    _SHELL_COMPOSITION_SEQUENCES: tuple[str, ...] = (
        ";",
        "&&",
        "||",
        "|",
        "&>",
        "2>",
        "1>",
        ">>",
        "<<",
        ">",
        "<",
        "`",
        "$(",
        "$",
        "\n",
        "\r",
    )

    # Commands that are obviously read-only / low-risk and do not accept path
    # arguments. Each rule matches only the simple form at the start of the
    # command line. Shell-composition checks run before these rules, so
    # redirections, pipes and command chains still require approval.
    _ALLOW_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"^\s*echo\b", re.IGNORECASE), "echo output"),
        (re.compile(r"^\s*pwd\b", re.IGNORECASE), "print working directory"),
        (
            re.compile(
                r"^\s*git\s+(?:status|log|diff|show|branch)\b",
                re.IGNORECASE,
            ),
            "read-only git inspection",
        ),
    )

    # Characters and sequences that indicate a path argument in an otherwise
    # allowlisted git command. These are used as a conservative guard because
    # ``git diff`` / ``git show`` can also take file paths.
    _PATH_ARGUMENT_SEQUENCES: tuple[str, ...] = (
        "/",
        "\\",
        "..",
    )

    def __init__(self, *, conservative: bool = True) -> None:
        """Create a policy.

        Args:
            conservative: When ``True`` (the default for production use) any
                command that does not match an explicit allow or deny/approval
                rule is treated as ``REQUIRE_APPROVAL``.
        """
        self._conservative = conservative

    @staticmethod
    def _has_shell_composition(command: str) -> bool:
        """Return True if ``command`` contains shell-composition characters."""
        return any(seq in command for seq in DangerousCommandPolicy._SHELL_COMPOSITION_SEQUENCES)

    @staticmethod
    def _has_path_argument(command: str) -> bool:
        """Return True if ``command`` likely contains a path argument."""
        return any(seq in command for seq in DangerousCommandPolicy._PATH_ARGUMENT_SEQUENCES)

    def evaluate(self, command: str) -> SafetyDecision:
        """Return the safety decision for ``command``.

        Deny rules are checked first so that destructive subcommands cannot be
        hidden behind approval-only prefixes such as ``sudo``. Approval rules
        come next, then shell-composition checks, then the explicit allowlist.
        In conservative mode unknown commands require approval; otherwise they
        are allowed.
        """
        for pattern, reason in self._DENY_RULES:
            if pattern.search(command):
                return SafetyDecision(
                    decision=CommandSafetyDecision.DENY,
                    reason=reason,
                )

        for pattern, reason in self._APPROVAL_RULES:
            if pattern.search(command):
                return SafetyDecision(
                    decision=CommandSafetyDecision.REQUIRE_APPROVAL,
                    reason=reason,
                )

        # A command that uses shell composition (redirection, pipe, chain,
        # substitution) is treated as requiring approval even if the leading
        # command is on the allowlist. This must run after deny/approval rules
        # but before allow rules.
        if self._has_shell_composition(command):
            return SafetyDecision(
                decision=CommandSafetyDecision.REQUIRE_APPROVAL,
                reason="shell composition requires review",
            )

        for pattern, reason in self._ALLOW_RULES:
            if pattern.search(command):
                if reason == "read-only git inspection" and self._has_path_argument(command):
                    break
                return SafetyDecision(
                    decision=CommandSafetyDecision.ALLOW,
                    reason=reason,
                )

        if self._conservative:
            return SafetyDecision(
                decision=CommandSafetyDecision.REQUIRE_APPROVAL,
                reason="unknown command requires review in conservative mode",
            )

        return SafetyDecision(
            decision=CommandSafetyDecision.ALLOW,
            reason="no safety rule matched",
        )

    def check(self, command: str) -> None:
        """Raise ``DangerousCommandError`` unless the command is ``ALLOW``.

        This method preserves the binary allow/blocked interface used by
        callers that only need to know whether direct execution is permitted.
        """
        decision = self.evaluate(command)
        if decision.decision is CommandSafetyDecision.ALLOW:
            return

        if decision.decision is CommandSafetyDecision.REQUIRE_APPROVAL:
            raise DangerousCommandError(
                f"command requires approval before execution: {decision.reason}",
                decision=decision.decision,
            )

        raise DangerousCommandError(
            f"command denied by safety policy: {decision.reason}",
            decision=decision.decision,
        )
