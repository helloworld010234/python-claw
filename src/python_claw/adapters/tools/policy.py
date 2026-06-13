"""Dangerous shell command policy for the bash tool."""

from __future__ import annotations

import re


class DangerousCommandError(Exception):
    """Raised when a command matches a blocked dangerous pattern."""


class DangerousCommandPolicy:
    """Blocks commands that match known destructive or privileged patterns."""

    _PATTERNS: tuple[re.Pattern[str], ...] = (
        # Unix recursive remove (rm -r, rm -rf)
        re.compile(r"\brm\s+-r(?:f?|(?=\s))", re.IGNORECASE),
        # Privilege escalation
        re.compile(r"\bsudo\b", re.IGNORECASE),
        # SQL/data destructive statements
        re.compile(r"\bdrop\b", re.IGNORECASE),
        # Service control
        re.compile(r"\bnginx\s+-s\b", re.IGNORECASE),
        re.compile(r"\bsystemctl\b", re.IGNORECASE),
        # Process termination
        re.compile(r"\bkill\b", re.IGNORECASE),
        # PowerShell recursive remove (any order with -Recurse / -r)
        re.compile(r"\bremove-item\b[\s\S]*?-(?:recurse|r)\b", re.IGNORECASE),
        # Windows cmd recursive directory remove
        re.compile(r"\b(?:rd|rmdir)\b[\s\S]*?/s\b", re.IGNORECASE),
        # Windows cmd recursive file delete
        re.compile(r"\bdel\b[\s\S]*?/s\b", re.IGNORECASE),
        # Windows disk format (bare command or with drive letter)
        re.compile(r"(?:^\s*)format\s*$|(?:^\s*|\s)format\s+[a-zA-Z]:", re.IGNORECASE),
        # Windows shutdown
        re.compile(r"\bshutdown\b", re.IGNORECASE),
        # PowerShell process termination
        re.compile(r"\bstop-process\b", re.IGNORECASE),
    )

    def check(self, command: str) -> None:
        """Raise ``DangerousCommandError`` if the command is blocked."""
        for pattern in self._PATTERNS:
            if pattern.search(command):
                raise DangerousCommandError(f"command blocked by safety policy: {pattern.pattern}")
