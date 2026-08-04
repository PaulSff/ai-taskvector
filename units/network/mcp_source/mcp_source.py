"""
MCPSource unit: fetch MCP tool metadata (or a capability listing) using the python-sdk.

Dependencies: pip install "mcp[cli]"

Accepts parser_output with optional mcp_source payload:
{
  "server": "optional/ignored",
  "mode": "list_tools" | "get_capabilities" | "auto"
}

Transport/mode and credentials are taken from unit params (NOT from the payload):
- params["mcp_url"] (e.g. "http://localhost:8000/mcp") for HTTP transport
- params["mcp_in_memory"] (bool) + params["mcp_server_object"] for in-memory tests
- params["mcp_custom_transport"] for custom transport (if your runtime provides it)
- optional params["mcp_http_headers"] (dict) and/or params["mcp_bearer_token"] (str) for auth

Outputs:
- data: a dict with tool list / capabilities (best-effort depending on SDK/server support)
- error: empty string on success, otherwise error message

Streaming is not required for metadata fetch; _stream_callback is used only if the unit emits status.
"""

from __future__ import annotations

import asyncio
from typing import Any

from units.registry import UnitSpec, register_unit

RUN_MCP_SOURCE_INPUT_PORTS = [
    ("parser_output", "Any"),
]
RUN_MCP_SOURCE_OUTPUT_PORTS = [
    ("data", "Any"),
    ("error", "str"),
]


def _as_dict(x: Any) -> dict[str, Any] | None:
    return x if isinstance(x, dict) else None


def _get_stream_cb(params: dict[str, Any]) -> Any | None:
    cb = params.get("_stream_callback")
    return cb if callable(cb) else None


def _maybe_status(cb: Any | None, token: str) -> None:
    if cb is None:
        return
    try:
        cb(token)
    except (TypeError, RuntimeError):
        pass


async def _get_mcp_source_async(
    *,
    stream_cb: Any | None,
    params: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    from mcp import Client

    try:
        from runtime.stream_ui_signals import inline_status_stream_chunk
    except Exception:
        inline_status_stream_chunk = lambda s: s  # type: ignore

    if stream_cb:
        _maybe_status(stream_cb, inline_status_stream_chunk("Connecting to MCP source…"))

    # In-memory mode (tests)
    if params.get("mcp_in_memory") is True:
        server_object = params.get("mcp_server_object")
        if server_object is None:
            raise ValueError("params['mcp_server_object'] required when params['mcp_in_memory'] is true")

        async with Client(server_object) as client:
            # Best-effort: different SDK/server variants expose different APIs.
            # We'll try a few common patterns.
            if mode in ("list_tools", "auto"):
                if hasattr(client, "list_tools"):
                    res = await client.list_tools()
                    return {"tools": getattr(res, "tools", res)}
                if hasattr(client, "get_tools"):
                    res = await client.get_tools()
                    return {"tools": getattr(res, "tools", res)}
            if mode in ("get_capabilities", "auto"):
                if hasattr(client, "capabilities"):
                    return {"capabilities": client.capabilities}
            return {"result": "source fetched, but server/SDK does not expose list_tools/capabilities in this runtime"}

    # Custom transport
    custom_transport = params.get("mcp_custom_transport")
    if custom_transport is not None:
        async with Client(custom_transport) as client:
            if mode in ("list_tools", "auto"):
                if hasattr(client, "list_tools"):
                    res = await client.list_tools()
                    return {"tools": getattr(res, "tools", res)}
                if hasattr(client, "get_tools"):
                    res = await client.get_tools()
                    return {"tools": getattr(res, "tools", res)}
            if mode in ("get_capabilities", "auto"):
                if hasattr(client, "capabilities"):
                    return {"capabilities": client.capabilities}
            return {"result": "source fetched, but server/SDK does not expose list_tools/capabilities in this runtime"}

    # HTTP transport
    mcp_url = params.get("mcp_url")
    if not isinstance(mcp_url, str) or not mcp_url.strip():
        raise ValueError("params['mcp_url'] required when not using in_memory/custom_transport")

    transport = mcp_url.strip()
    headers = params.get("mcp_http_headers")
    bearer = params.get("mcp_bearer_token")

    if isinstance(headers, dict) and headers:
        async with Client({"url": transport, "headers": headers}) as client:  # scaffold; adjust if SDK differs
            if mode in ("list_tools", "auto"):
                if hasattr(client, "list_tools"):
                    res = await client.list_tools()
                    return {"tools": getattr(res, "tools", res)}
                if hasattr(client, "get_tools"):
                    res = await client.get_tools()
                    return {"tools": getattr(res, "tools", res)}
            if mode in ("get_capabilities", "auto"):
                if hasattr(client, "capabilities"):
                    return {"capabilities": client.capabilities}
            return {"result": "source fetched, but server/SDK does not expose list_tools/capabilities in this runtime"}

    if isinstance(bearer, str) and bearer.strip():
        token_headers = {"Authorization": f"Bearer {bearer.strip()}"}
        async with Client({"url": transport, "headers": token_headers}) as client:  # scaffold; adjust if SDK differs
            if mode in ("list_tools", "auto"):
                if hasattr(client, "list_tools"):
                    res = await client.list_tools()
                    return {"tools": getattr(res, "tools", res)}
                if hasattr(client, "get_tools"):
                    res = await client.get_tools()
                    return {"tools": getattr(res, "tools", res)}
            if mode in ("get_capabilities", "auto"):
                if hasattr(client, "capabilities"):
                    return {"capabilities": client.capabilities}
            return {"result": "source fetched, but server/SDK does not expose list_tools/capabilities in this runtime"}

    async with Client(transport) as client:
        if mode in ("list_tools", "auto"):
            if hasattr(client, "list_tools"):
                res = await client.list_tools()
                return {"tools": getattr(res, "tools", res)}
            if hasattr(client, "get_tools"):
                res = await client.get_tools()
                return {"tools": getattr(res, "tools", res)}
        if mode in ("get_capabilities", "auto"):
            if hasattr(client, "capabilities"):
                return {"capabilities": client.capabilities}
        return {"result": "source fetched, but server/SDK does not expose list_tools/capabilities in this runtime"}


def _mcp_source_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parser_output = inputs.get("parser_output")
    parser_dict = _as_dict(parser_output) if parser_output is not None else None
    stream_cb = _get_stream_cb(params)

    mode = "auto"
    if parser_dict is not None:
        payload = parser_dict.get("mcp_source")
        if isinstance(payload, dict):
            mv = payload.get("mode")
            if isinstance(mv, str) and mv.strip():
                mode = mv.strip()

    async def _go() -> dict[str, Any]:
        return await _get_mcp_source_async(
            stream_cb=stream_cb,
            params=params,
            mode=mode,
        )

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

        return ({"data": outputs, "error": ""}, state)
    except (TypeError, ValueError, NotImplementedError) as e:
        return ({"data": {}, "error": f"mcp_source execute failed: {e}"}, state)
    except Exception as e:
        return ({"data": {}, "error": f"mcp_source execute failed: {e}"}, state)


def register_mcp_source() -> None:
    register_unit(
        UnitSpec(
            type_name="MCPSource",
            input_ports=RUN_MCP_SOURCE_INPUT_PORTS,
            output_ports=RUN_MCP_SOURCE_OUTPUT_PORTS,
            step_fn=_mcp_source_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Uses the python mcp SDK to retrieve MCP source information (e.g., tool list/capabilities). "
                "Transport/mode and credentials are sourced from unit params (not from payload)."
            ),
        )
    )


__all__ = [
    "RUN_MCP_SOURCE_INPUT_PORTS",
    "RUN_MCP_SOURCE_OUTPUT_PORTS",
    "register_mcp_source",
]
