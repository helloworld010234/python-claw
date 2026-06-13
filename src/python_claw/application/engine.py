"""Agent engine: deterministic, testable agent loop orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from python_claw.application.commands import RunAgentCommand
from python_claw.application.config import AgentEngineConfig
from python_claw.application.exceptions import AgentEngineError
from python_claw.domain.common import PythonClawDomainError
from python_claw.domain.message import Message, Role, ToolResult, Usage
from python_claw.domain.run import AgentRun
from python_claw.domain.session import Session, SessionStatus

if TYPE_CHECKING:
    from python_claw.ports.llm import LlmGateway
    from python_claw.ports.reporters import Reporter
    from python_claw.ports.repositories import (
        MessageRepository,
        RunRepository,
        SessionRepository,
    )
    from python_claw.ports.tools import ToolRegistry
    from python_claw.ports.tracing import TraceRecorder


class AgentEngine:
    """Orchestrates a single agent run using injected ports only.

    The engine depends exclusively on ``domain`` and ``ports``; no concrete
    adapter (SQLAlchemy, FastAPI, Typer, LLM SDK, etc.) is imported.
    """

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        run_repository: RunRepository,
        message_repository: MessageRepository,
        llm_gateway: LlmGateway,
        tool_registry: ToolRegistry,
        reporter: Reporter,
        trace_recorder: TraceRecorder,
        config: AgentEngineConfig | None = None,
    ) -> None:
        self._session_repository = session_repository
        self._run_repository = run_repository
        self._message_repository = message_repository
        self._llm_gateway = llm_gateway
        self._tool_registry = tool_registry
        self._reporter = reporter
        self._trace_recorder = trace_recorder
        self._config = config or AgentEngineConfig()

    async def run(self, command: RunAgentCommand) -> AgentRun:
        """Execute a single agent run and return the terminal aggregate."""
        session = self._get_or_create_session(command.session_id)
        if session.status is SessionStatus.ARCHIVED:
            raise AgentEngineError(
                f"Cannot start run in archived session {command.session_id}"
            )

        user_message = Message(role=Role.USER, content=command.prompt)
        session.append(user_message)
        self._message_repository.save(user_message, session.id)

        run = AgentRun(
            id=command.run_id,
            session_id=session.id,
            prompt=command.prompt,
        )
        run.start()
        run.append_message(user_message)
        self._run_repository.save(run)

        self._notify_run_started(run)
        self._record_trace(
            run.id,
            "run_started",
            {
                "session_id": session.id,
                "prompt": command.prompt,
                "status": run.status.value,
            },
        )

        try:
            return await self._loop(session, run, command)
        except AgentEngineError:
            raise
        except Exception as exc:
            self._fail_run(run, exc)
            raise AgentEngineError(
                f"Unexpected error during run {run.id}: {exc}"
            ) from exc

    def _get_or_create_session(self, session_id: str) -> Session:
        session = self._session_repository.get_by_id(session_id)
        if session is None:
            session = Session(id=session_id)
            self._session_repository.save(session)
        return session

    async def _loop(
        self,
        session: Session,
        run: AgentRun,
        command: RunAgentCommand,
    ) -> AgentRun:
        working_memory_limit = (
            command.working_memory_limit or self._config.working_memory_limit
        )
        tools = self._tool_registry.list_definitions()

        for _turn in range(self._config.max_turns):
            context = list(session.get_working_memory(working_memory_limit))
            assistant_message, usage = await self._llm_gateway.chat(
                context, tools=tools
            )
            assistant_message = self._attach_usage(assistant_message, usage)

            session.append(assistant_message)
            self._message_repository.save(assistant_message, session.id)
            run.append_message(assistant_message)
            self._run_repository.save(run)

            self._notify_message(run, assistant_message)
            self._record_trace(
                run.id,
                "llm_response",
                self._message_payload(assistant_message),
            )

            if not assistant_message.tool_calls:
                run.complete()
                self._run_repository.save(run)
                self._record_trace(
                    run.id,
                    "run_finished",
                    {"status": run.status.value},
                )
                self._notify_run_finished(run)
                return run

            for call in assistant_message.tool_calls:
                result = await self._execute_tool(call)
                observation = Message(
                    role=Role.USER,
                    content=result.output,
                    tool_call_id=result.tool_call_id,
                )
                session.append(observation)
                self._message_repository.save(observation, session.id)
                run.append_message(observation)
                self._run_repository.save(run)

                self._notify_message(run, observation)
                self._record_trace(
                    run.id,
                    "tool_result",
                    {
                        "tool_call_id": result.tool_call_id,
                        "output": result.output,
                        "is_error": result.is_error,
                    },
                )

        run.timeout()
        self._run_repository.save(run)
        self._record_trace(
            run.id,
            "run_finished",
            {"status": run.status.value},
        )
        self._notify_run_finished(run)
        return run

    async def _execute_tool(self, call: Any) -> ToolResult:
        tool = self._tool_registry.get(call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                output=f"Tool '{call.name}' not found",
                is_error=True,
            )
        return await tool.execute(call)

    def _attach_usage(self, message: Message, usage: Usage) -> Message:
        if message.usage is not None:
            return message
        if usage.total_tokens == 0 and usage.cost == 0.0:
            return message
        return Message(
            role=message.role,
            content=message.content,
            tool_calls=message.tool_calls,
            tool_call_id=message.tool_call_id,
            usage=usage,
        )

    def _message_payload(self, message: Message) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": message.role.value,
            "content": message.content,
        }
        if message.tool_call_id is not None:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": dict(call.arguments),
                }
                for call in message.tool_calls
            ]
        if message.usage is not None:
            payload["usage"] = {
                "prompt_tokens": message.usage.prompt_tokens,
                "completion_tokens": message.usage.completion_tokens,
                "cost": message.usage.cost,
            }
        return payload

    def _fail_run(self, run: AgentRun, exc: Exception) -> None:
        """Best-effort attempt to persist a failed terminal status."""
        try:
            run.fail()
        except PythonClawDomainError:
            # Run may already be terminal; ignore and try to save current state.
            pass
        try:
            self._run_repository.save(run)
        except Exception:
            # Saving failed; we still want to notify/trace what we can.
            pass
        self._record_trace(
            run.id,
            "run_finished",
            {"status": run.status.value, "error": str(exc)},
        )
        self._notify_run_finished(run)

    def _notify_run_started(self, run: AgentRun) -> None:
        try:
            self._reporter.on_run_started(run)
        except Exception:
            pass

    def _notify_message(self, run: AgentRun, message: Message) -> None:
        try:
            self._reporter.on_message(run, message)
        except Exception:
            pass

    def _notify_run_finished(self, run: AgentRun) -> None:
        try:
            self._reporter.on_run_finished(run)
        except Exception:
            pass

    def _record_trace(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            self._trace_recorder.record(run_id, event_type, payload)
        except Exception:
            pass
