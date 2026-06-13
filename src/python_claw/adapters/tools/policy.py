"""Dangerous shell command policy for the bash tool."""

from __future__ import annotations

import re


class DangerousCommandError(Exception):
    """Raised when a command matches a blocked dangerous pattern."""


class DangerousCommandPolicy:
    """Blocks commands that match known destructive or privileged patterns."""

    _PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"\brm\s+-r(?:f?|(?=\s))", re.IGNORECASE),
        re.compile(r"\bsudo\b", re.IGNORECASE),
        re.compile(r"\bdrop\b", re.IGNORECASE),
        re.compile(r"\bnginx\s+-s\b", re.IGNORECASE),
        re.compile(r"\bsystemctl\b", re.IGNORECASE),
        re.compile(r"\bkill\b", re.IGNORECASE),
    )

    def check(self, command: str) -> None:
        """Raise ``DangerousCommandError`` if the command is blocked."""
        for pattern in self._PATTERNS:
            if pattern.search(command):
                raise DangerousCommandError(f"command blocked by safety policy: {pattern.pattern}")
