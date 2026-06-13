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

    * ``ALLOW`` – only for commands that are obviously low-risk (for example
      read-only inspection or simple workspace helpers).  This tier is an
      explicit allowlist, not a default fallback.
    * ``REQUIRE_APPROVAL`` – high-risk but contextually legitimate operations
      such as privilege escalation, service control or process termination.
      These are not executed until a human approves them.
    * ``DENY`` – destructive or irreversible operations such as recursive file
      removal, disk formatting or system shutdown.  These are blocked outright.

    In *conservative mode* (the default for the bash tool and the static
    registry) any command that does not match an explicit ``ALLOW`` rule and
    does not match a deny/approval rule is treated as ``REQUIRE_APPROVAL``.
    This closes the "unknown command defaults to ALLOW" bypass that a purely
    pattern-based policy would leave open.
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
    )

    # High-risk but sometimes legitimate commands require approval.
    _APPROVAL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
        # Privilege escalation.
        (re.compile(r"\bsudo\b", re.IGNORECASE), "privilege escalation"),
        # Service control.
        (re.compile(r"\bnginx\s+-s\b", re.IGNORECASE), "service control"),
        (re.compile(r"\bsystemctl\b", re.IGNORECASE), "service control"),
        # Process termination.
        (re.compile(r"\bkill\b", re.IGNORECASE), "process termination"),
        (
            re.compile(r"\bstop-process\b", re.IGNORECASE),
            "process termination",
        ),
    )

    # Commands that are obviously low-risk.  These are evaluated *after* the
    # deny and approval rules so dangerous subcommands still win.
    _ALLOW_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(
                r"^\s*(?:"
                r"echo|ls|ll|cat|pwd|which|where|"
                r"python|python3|node|"
                r"npm\s+(?:list|view)|"
                r"git\s+(?:status|log|diff|show|branch)|"
                r"find|grep|mkdir|touch|cp|mv"
                r")\b",
                re.IGNORECASE,
            ),
            "common workspace command",
        ),
    )

    def __init__(self, *, conservative: bool = True) -> None:
        """Create a policy.

        Args:
            conservative: When ``True`` (the default for production use) any
                command that does not match an explicit allow or deny/approval
                rule is treated as ``REQUIRE_APPROVAL``.
        """
        self._conservative = conservative

    def evaluate(self, command: str) -> SafetyDecision:
        """Return the safety decision for ``command``.

        Deny rules are checked first so that destructive subcommands cannot be
        hidden behind approval-only prefixes such as ``sudo``.  Approval rules
        come next, then the explicit allowlist.  In conservative mode unknown
        commands require approval; otherwise they are allowed.
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

        for pattern, reason in self._ALLOW_RULES:
            if pattern.search(command):
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

        This method preserves the old binary allow/blocked interface used by
        callers that only need to know whether execution is permitted.
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
