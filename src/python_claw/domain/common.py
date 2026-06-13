"""Shared domain primitives and exceptions."""

from __future__ import annotations


class PythonClawDomainError(Exception):
    """Base exception for all domain-level invariant violations."""
