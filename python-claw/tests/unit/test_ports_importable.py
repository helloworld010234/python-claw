from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "python_claw.ports.llm",
        "python_claw.ports.tools",
        "python_claw.ports.repositories",
        "python_claw.ports.reporters",
        "python_claw.ports.chatops",
        "python_claw.ports.clock",
        "python_claw.ports.tracing",
    ],
)
def test_port_modules_are_importable(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__doc__ is not None


def test_port_public_exports_are_importable() -> None:
    from python_claw.ports import (
        AgentTool,
        ApprovalRepository,
        ChatOpsPort,
        Clock,
        LlmGateway,
        MessageRepository,
        Reporter,
        RunRepository,
        SessionRepository,
        ToolRegistry,
        TraceRecorder,
    )

    assert AgentTool is not None
    assert ApprovalRepository is not None
    assert ChatOpsPort is not None
    assert Clock is not None
    assert LlmGateway is not None
    assert MessageRepository is not None
    assert Reporter is not None
    assert RunRepository is not None
    assert SessionRepository is not None
    assert ToolRegistry is not None
    assert TraceRecorder is not None
