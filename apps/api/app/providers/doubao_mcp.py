"""Lifecycle-managed client for the allowlisted Doubao SearchInfinity MCP tool."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ListToolsResult

DOUBAO_MCP_EXECUTABLE = "mcp-server-askecho-search-infinity"
DOUBAO_SEARCH_TOOL = "web_search"


class McpErrorCode(StrEnum):
    """Stable lifecycle and transport failure categories."""

    UNAVAILABLE = "search_mcp_unavailable"
    REQUIRED_TOOL_MISSING = "search_mcp_required_tool_missing"
    TIMEOUT = "search_mcp_timeout"
    CALL_FAILED = "search_mcp_call_failed"


class McpRuntimeError(RuntimeError):
    """Secret-safe MCP error."""

    def __init__(self, code: McpErrorCode) -> None:
        self.code = code
        super().__init__(f"Doubao MCP failed with {code.value}")


class McpSession(Protocol):
    async def initialize(self) -> Any: ...

    async def list_tools(self) -> ListToolsResult: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
    ) -> CallToolResult: ...


class McpConnector(Protocol):
    def connect(self) -> AbstractAsyncContextManager[McpSession]: ...


class StdioDoubaoConnector:
    """Launch the fixed installed official server with an allowlisted environment."""

    def __init__(self, child_env: dict[str, str]) -> None:
        executable = Path(sys.executable).with_name(DOUBAO_MCP_EXECUTABLE)
        if not executable.is_file():
            raise McpRuntimeError(McpErrorCode.UNAVAILABLE)
        safe_names = {
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
        }
        self._parameters = StdioServerParameters(
            command=str(executable),
            args=[],
            env={
                **{name: os.environ[name] for name in safe_names if name in os.environ},
                **child_env,
                "PYTHONUNBUFFERED": "1",
            },
        )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[McpSession]:
        with open(os.devnull, "w", encoding="utf-8") as errlog:  # noqa: ASYNC230
            async with stdio_client(self._parameters, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    yield session


@dataclass
class _CallCommand:
    arguments: dict[str, Any]
    future: Any
    cancelled: Any


class DoubaoMcpRuntime:
    """Supervise persistent stdio from one owner task and service queued calls."""

    def __init__(
        self,
        *,
        connector: McpConnector,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        import asyncio

        self._connector = connector
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._queue: asyncio.Queue[_CallCommand | None] = asyncio.Queue()
        self._owner_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()
        self._startup_error: McpRuntimeError | None = None
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def start(self) -> None:
        import asyncio

        if self._owner_task is None or self._owner_task.done():
            self._queue = asyncio.Queue()
            self._started = asyncio.Event()
            self._startup_error = None
            self._owner_task = asyncio.create_task(self._run(), name="doubao-mcp-supervisor")
        try:
            async with asyncio.timeout(self._timeout_seconds + 1):
                await self._started.wait()
        except TimeoutError as exc:
            raise McpRuntimeError(McpErrorCode.TIMEOUT) from exc
        if self._startup_error is not None:
            raise self._startup_error

    async def stop(self) -> None:
        task = self._owner_task
        if task is None:
            return
        await self._queue.put(None)
        with suppress(Exception):
            await task
        self._owner_task = None
        self._ready = False

    async def call_web_search(self, arguments: dict[str, Any]) -> CallToolResult:
        """Call only the approved tool; callers cannot provide a tool name."""
        import asyncio

        await self.start()
        future: asyncio.Future[CallToolResult] = asyncio.get_running_loop().create_future()
        cancelled = asyncio.Event()
        await self._queue.put(_CallCommand(arguments, future, cancelled))
        try:
            return await future
        except asyncio.CancelledError:
            cancelled.set()
            future.cancel()
            raise

    async def _run(self) -> None:
        connection: AbstractAsyncContextManager[McpSession] | None = None
        session: McpSession | None = None
        try:
            try:
                connection, session = await self._connect()
                self._ready = True
            except McpRuntimeError as exc:
                self._startup_error = exc
                return
            finally:
                self._started.set()

            while (command := await self._queue.get()) is not None:
                for attempt in range(self._max_retries + 1):
                    if command.cancelled.is_set():
                        break
                    try:
                        result = await self._execute(session, command)
                    except TimeoutError:
                        code = McpErrorCode.TIMEOUT
                    except Exception:
                        code = McpErrorCode.CALL_FAILED
                    else:
                        if not command.future.done():
                            command.future.set_result(result)
                        break

                    self._ready = False
                    if connection is not None:
                        await _safe_exit(connection)
                    connection = None
                    session = None
                    if attempt == self._max_retries:
                        if not command.future.done():
                            command.future.set_exception(McpRuntimeError(code))
                        break
                    try:
                        connection, session = await self._connect()
                        self._ready = True
                    except McpRuntimeError as reconnect_error:
                        if not command.future.done():
                            command.future.set_exception(reconnect_error)
                        break
        finally:
            self._ready = False
            if connection is not None:
                await _safe_exit(connection)

    async def _connect(
        self,
    ) -> tuple[AbstractAsyncContextManager[McpSession], McpSession]:
        import asyncio

        connection = self._connector.connect()
        entered = False
        try:
            session = await connection.__aenter__()
            entered = True
            async with asyncio.timeout(self._timeout_seconds):
                await session.initialize()
                tools = await session.list_tools()
            if DOUBAO_SEARCH_TOOL not in {tool.name for tool in tools.tools}:
                raise McpRuntimeError(McpErrorCode.REQUIRED_TOOL_MISSING)
            return connection, session
        except McpRuntimeError:
            if entered:
                await _safe_exit(connection)
            raise
        except TimeoutError as exc:
            if entered:
                await _safe_exit(connection)
            raise McpRuntimeError(McpErrorCode.TIMEOUT) from exc
        except Exception as exc:
            if entered:
                await _safe_exit(connection)
            raise McpRuntimeError(McpErrorCode.UNAVAILABLE) from exc

    async def _execute(self, session: McpSession | None, command: _CallCommand) -> CallToolResult:
        import asyncio

        if session is None:
            raise McpRuntimeError(McpErrorCode.UNAVAILABLE)
        call = asyncio.create_task(
            session.call_tool(
                DOUBAO_SEARCH_TOOL,
                command.arguments,
                read_timeout_seconds=timedelta(seconds=self._timeout_seconds),
            )
        )
        cancellation = asyncio.create_task(command.cancelled.wait())
        try:
            async with asyncio.timeout(self._timeout_seconds):
                done, _ = await asyncio.wait(
                    {call, cancellation}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancellation in done:
                    call.cancel()
                    with suppress(asyncio.CancelledError):
                        await call
                    raise asyncio.CancelledError
                return await call
        finally:
            if not call.done():
                call.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await call
            cancellation.cancel()
            with suppress(asyncio.CancelledError):
                await cancellation


async def _safe_exit(connection: AbstractAsyncContextManager[McpSession]) -> None:
    with suppress(Exception):
        await connection.__aexit__(None, None, None)
