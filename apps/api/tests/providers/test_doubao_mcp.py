import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from mcp.types import CallToolResult, ListToolsResult, Tool

from app.providers.doubao_mcp import (
    DOUBAO_SEARCH_TOOL,
    DoubaoMcpRuntime,
    McpErrorCode,
    McpRuntimeError,
)


def tools(*names: str) -> ListToolsResult:
    return ListToolsResult(
        tools=[
            Tool(name=name, description="test", inputSchema={"type": "object"}) for name in names
        ]
    )


class FakeSession:
    def __init__(
        self,
        *,
        tool_names: tuple[str, ...] = (DOUBAO_SEARCH_TOOL,),
        outcomes: list[Any] | None = None,
    ) -> None:
        self.tool_names = tool_names
        self.outcomes = outcomes or [CallToolResult(content=[], structuredContent={"results": []})]
        self.initialize_calls = 0
        self.call_names: list[str] = []
        self.call_count = 0

    async def initialize(self) -> None:
        self.initialize_calls += 1

    async def list_tools(self) -> ListToolsResult:
        return tools(*self.tool_names)

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None, read_timeout_seconds: Any = None
    ) -> CallToolResult:
        del arguments, read_timeout_seconds
        self.call_names.append(name)
        outcome = self.outcomes[min(self.call_count, len(self.outcomes) - 1)]
        self.call_count += 1
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, asyncio.Event):
            await outcome.wait()
            raise AssertionError("event should not be set")
        return cast(CallToolResult, outcome)


class FakeConnector:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self.sessions = sessions
        self.connections = 0
        self.exits = 0

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[FakeSession]:
        session = self.sessions[min(self.connections, len(self.sessions) - 1)]
        self.connections += 1
        try:
            yield session
        finally:
            self.exits += 1


@pytest.mark.asyncio
async def test_lifecycle_initializes_allowlisted_tool_and_stops_cleanly() -> None:
    session = FakeSession(tool_names=(DOUBAO_SEARCH_TOOL, "unexpected_tool"))
    connector = FakeConnector([session])
    runtime = DoubaoMcpRuntime(connector=connector, timeout_seconds=1, max_retries=0)

    await runtime.start()
    result = await runtime.call_web_search({"Query": "测试"})
    await runtime.stop()

    assert result.structuredContent == {"results": []}
    assert runtime.is_ready is False
    assert session.call_names == [DOUBAO_SEARCH_TOOL]
    assert connector.exits == 1


@pytest.mark.asyncio
async def test_lifecycle_rejects_missing_required_tool() -> None:
    runtime = DoubaoMcpRuntime(
        connector=FakeConnector([FakeSession(tool_names=("unexpected_tool",))]),
        timeout_seconds=1,
        max_retries=0,
    )

    with pytest.raises(McpRuntimeError) as raised:
        await runtime.start()

    assert raised.value.code is McpErrorCode.REQUIRED_TOOL_MISSING


@pytest.mark.asyncio
async def test_call_reconnects_once_after_transport_failure() -> None:
    success = CallToolResult(content=[], structuredContent={"results": []})
    first = FakeSession(outcomes=[RuntimeError("private transport detail")])
    second = FakeSession(outcomes=[success])
    connector = FakeConnector([first, second])
    runtime = DoubaoMcpRuntime(connector=connector, timeout_seconds=1, max_retries=1)

    result = await runtime.call_web_search({"Query": "测试"})
    await runtime.stop()

    assert result is success
    assert connector.connections == 2
    assert "private transport detail" not in repr(result)


@pytest.mark.asyncio
async def test_call_returns_typed_timeout() -> None:
    runtime = DoubaoMcpRuntime(
        connector=FakeConnector([FakeSession(outcomes=[asyncio.Event()])]),
        timeout_seconds=0.01,
        max_retries=0,
    )

    with pytest.raises(McpRuntimeError) as raised:
        await runtime.call_web_search({"Query": "测试"})

    assert raised.value.code is McpErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_call_propagates_cancellation() -> None:
    runtime = DoubaoMcpRuntime(
        connector=FakeConnector([FakeSession(outcomes=[asyncio.Event()])]),
        timeout_seconds=10,
        max_retries=0,
    )
    task = asyncio.create_task(runtime.call_web_search({"Query": "测试"}))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    await runtime.stop()
