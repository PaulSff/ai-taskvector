"""
MCPTool unit: call an MCP tool using the python-sdk and return structured results.

Dependencies: pip install "mcp[cli]"

Accepts parser_output with optional mcp_tool payload:
{
  "tool_name": "add",
  "arguments": { "a": 1, "b": 2 },
  "stream": true
}.

Transport/mode and credentials are taken from unit params (NOT from the payload):
- HTTP transport:
  - params["mcp_url"] (e.g. "http://localhost:8000/mcp")
  - optional params["mcp_http_headers"] (dict) and/or params["mcp_bearer_token"] (str)
- In-memory (tests):
  - params["mcp_in_memory"] must be true
  - params["mcp_server_object"] provides the in-memory MCP server object
- Custom transport (if your runtime provides it):
  - params["mcp_custom_transport"] provides the transport object for the MCP SDK

If payload is missing/invalid, returns empty outputs with an error string.
Streaming: forwards status chunks via params["_stream_callback"] using inline_status_stream_chunk.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from units.registry import UnitSpec, register_unit

RUN_MCP_TOOL_INPUT_PORTS = [
    ("parser_output", "Any"),
]
RUN_MCP_TOOL_OUTPUT_PORTS = [
    ("data", "Any"),
    ("error", "str"),
]


def _as_dict(x: Any) -> dict[str, Any] | None:
    return x if isinstance(x, dict) else None


def _get_stream_cb(params: dict[str, Any]) -> Any | None:
    cb = params.get("_stream_callback")
    return cb if callable(cb) else None


def _maybe_status(cb: Any | None, token: Any) -> None:
    if cb is None:
        return
    try:
        cb(token)
    except (TypeError, RuntimeError, BrokenPipeError, OSError):
        pass


async def _call_mcp_tool_async(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    stream_cb: Any | None,
    params: dict[str, Any],
) -> Any:
    from mcp import Client

    try:
        from runtime.run import INLINE_STATUS_FOR_STREAMING
        from runtime.stream_ui_signals import inline_status_stream_chunk

    except Exception:
        inline_status_stream_chunk = lambda s: s  # type: ignore
        INLINE_STATUS_FOR_STREAMING = None  # type: ignore

    _maybe_status(stream_cb, inline_status_stream_chunk(INLINE_STATUS_FOR_STREAMING))

    try:
        # In-memory mode (tests)
        if params.get("mcp_in_memory") is True:
            server_object = params.get("mcp_server_object")
            if server_object is None:
                raise ValueError("params['mcp_server_object'] required when params['mcp_in_memory'] is true")

            async with Client(server_object) as client:
                result = await client.call_tool(tool_name, arguments)
                return getattr(result, "structured_content", result)

        # Custom transport (if provided by your runtime)
        custom_transport = params.get("mcp_custom_transport")
        if custom_transport is not None:
            async with Client(custom_transport) as client:
                result = await client.call_tool(tool_name, arguments)
                return getattr(result, "structured_content", result)

        # HTTP transport
        mcp_url = params.get("mcp_url")
        if not isinstance(mcp_url, str) or not mcp_url.strip():
            raise ValueError("params['mcp_url'] (HTTP) required when not using in_memory/custom_transport")

        # Your SDK expects `Client(server=...)` / accepts a `server` argument.
        # Given only the URL here, we use the URL as the `server` value.
        # If you need HTTP auth, you should pass it via `mcp_custom_transport`
        # (since the exact HTTP Transport+headers API varies by SDK version).
        if (isinstance(params.get("mcp_http_headers"), dict) and params.get("mcp_http_headers")) or (
            isinstance(params.get("mcp_bearer_token"), str) and params.get("mcp_bearer_token", "").strip()
        ):
            raise ValueError(
                "mcp_http_headers / mcp_bearer_token require mcp_custom_transport in this component."
            )

        async with Client(mcp_url.strip()) as client:
            result = await client.call_tool(tool_name, arguments)
            return getattr(result, "structured_content", result)

    finally:
        _maybe_status(stream_cb, inline_status_stream_chunk(None))


def _mcp_tool_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parser_output = inputs.get("parser_output")
    parser_dict = _as_dict(parser_output) if parser_output is not None else None
    stream_cb = _get_stream_cb(params)

    if parser_dict is None:
        return ({"data": {}, "error": "mcp_tool: parser_output must be an object/dict"}, state)

    payload = parser_dict.get("mcp_tool")
    if not isinstance(payload, dict):
        return ({"data": {}, "error": "mcp_tool: missing/invalid mcp_tool payload"}, state)

    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return ({"data": {}, "error": "mcp_tool: tool_name must be a non-empty string"}, state)

    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        return ({"data": {}, "error": "mcp_tool: arguments must be an object/dict"}, state)

    async def _go() -> dict[str, Any]:
        res = await _call_mcp_tool_async(
            tool_name=tool_name.strip(),
            arguments=cast(dict[str, Any], arguments),
            stream_cb=stream_cb,
            params=params,
        )
        return {"data": res, "error": ""}

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(_go(), loop)
            outputs = fut.result()
        else:
            outputs = asyncio.run(_go())

        return (cast(dict[str, Any], outputs), state)

    except (TypeError, ValueError, NotImplementedError) as e:
        return ({"data": {}, "error": f"mcp_tool execute failed: {e}"}, state)
    except Exception as e:
        return ({"data": {}, "error": f"mcp_tool execute failed: {e}"}, state)


def register_mcp_tool() -> None:
    register_unit(
        UnitSpec(
            type_name="MCPTool",
            input_ports=RUN_MCP_TOOL_INPUT_PORTS,
            output_ports=RUN_MCP_TOOL_OUTPUT_PORTS,
            step_fn=_mcp_tool_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Calls an MCP tool via the python mcp SDK. "
                "Consumes parser_output.mcp_tool and returns structured tool results. "
                "Transport/mode/credentials are sourced from unit params (not from payload). "
                "Streaming: uses params['_stream_callback'] for start/clear status only."
            ),
        )
    )

__all__ = [
    "RUN_MCP_TOOL_INPUT_PORTS",
    "RUN_MCP_TOOL_OUTPUT_PORTS",
    "register_mcp_tool",
]
