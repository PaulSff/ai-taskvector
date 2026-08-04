"""
MCPSource unit: fetch an MCP “resource” (source) via the python mcp SDK.

Dependencies: pip install "mcp[cli]"

Accepts inputs:
- parser_output (object/dict)
  - optional mcp_source payload, which must include:
    - resource_uri: non-empty string (the URI to read via read_resource)
  - Any additional fields in mcp_source (e.g., server, mode) are ignored by this component.

Transport/mode and credentials are taken from unit params (NOT from the payload):
- If params["mcp_host"] is provided, it uses host.read_resource(resource_uri) (cached discovery + dispatch).
- If params["mcp_in_memory"] is true, it uses params["mcp_server_object"] with Client(server_object).
- If params["mcp_custom_transport"] is provided, it uses Client(custom_transport).
- Otherwise it uses params["mcp_url"] as the HTTP transport URL for Client(mcp_url).
- Optional params["mcp_http_headers"] (dict) and/or params["mcp_bearer_token"] (str):
  - supported only when using params["mcp_custom_transport"] in this component; otherwise an error is raised.

Outputs:
- data: the best-effort parsed content returned from the MCP resource read
  (res.content or res.structured_content, or the raw object if those are missing)
- error: empty string on success, otherwise error message.

Streaming:
- Streaming is not required for the metadata/resource fetch itself.
- _stream_callback is used only to emit inline status tokens at start/end of execution (if provided and callable).
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

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


def _maybe_status(cb: Any | None, token: Any) -> None:
    if cb is None:
        return
    try:
        cb(token)
    except (TypeError, RuntimeError, BrokenPipeError, OSError):
        pass


async def _call_mcp_source_async(
    *,
    resource_uri: str,
    stream_cb: Any | None,
    params: dict[str, Any],
) -> Any:
    try:
        from runtime.run import INLINE_STATUS_FOR_STREAMING
        from runtime.stream_ui_signals import inline_status_stream_chunk
    except (ImportError, ModuleNotFoundError):
        inline_status_stream_chunk = lambda s: s  # type: ignore[assignment]
        INLINE_STATUS_FOR_STREAMING = None  # type: ignore[assignment]

    _maybe_status(stream_cb, inline_status_stream_chunk(INLINE_STATUS_FOR_STREAMING))

    try:
        host = params.get("mcp_host")
        if host is not None:
            return await host.read_resource(resource_uri)

        # Fallback: direct client (same style as MCPTool, but without auth support yet)
        from mcp import Client

        if params.get("mcp_in_memory") is True:
            server_object = params.get("mcp_server_object")
            if server_object is None:
                raise ValueError("params['mcp_server_object'] required when params['mcp_in_memory'] is true")

            async with Client(server_object) as client:
                if hasattr(client, "read_resource"):
                    res = await client.read_resource(resource_uri)
                else:
                    raise RuntimeError("SDK client has no read_resource()")

                return getattr(res, "content", None) or getattr(res, "structured_content", res)

        # Custom transport
        custom_transport = params.get("mcp_custom_transport")
        if custom_transport is not None:
            async with Client(custom_transport) as client:
                if hasattr(client, "read_resource"):
                    res = await client.read_resource(resource_uri)
                else:
                    raise RuntimeError("SDK client has no read_resource()")

                return getattr(res, "content", None) or getattr(res, "structured_content", res)

        # HTTP transport
        mcp_url = params.get("mcp_url")
        if not isinstance(mcp_url, str) or not mcp_url.strip():
            raise ValueError("params['mcp_url'] (HTTP) required when not using in_memory/custom_transport")

        if (isinstance(params.get("mcp_http_headers"), dict) and params.get("mcp_http_headers")) or (
            isinstance(params.get("mcp_bearer_token"), str) and params.get("mcp_bearer_token", "").strip()
        ):
            raise ValueError("mcp_http_headers / mcp_bearer_token require mcp_custom_transport in this component.")

        async with Client(mcp_url.strip()) as client:
            if hasattr(client, "read_resource"):
                res = await client.read_resource(resource_uri)
            else:
                raise RuntimeError("SDK client has no read_resource()")
            return getattr(res, "content", None) or getattr(res, "structured_content", res)

    finally:
        _maybe_status(stream_cb, inline_status_stream_chunk(None))


def _mcp_source_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parser_output = inputs.get("parser_output")
    parser_dict = _as_dict(parser_output) if parser_output is not None else None
    stream_cb = _get_stream_cb(params)

    if parser_dict is None:
        return ({"data": {}, "error": "mcp_source: parser_output must be an object/dict"}, state)

    payload = parser_dict.get("mcp_source")
    if not isinstance(payload, dict):
        return ({"data": {}, "error": "mcp_source: missing/invalid mcp_source payload"}, state)

    resource_uri = payload.get("resource_uri")
    if not isinstance(resource_uri, str) or not resource_uri.strip():
        return ({"data": {}, "error": "mcp_source: resource_uri must be a non-empty string"}, state)

    async def _go() -> dict[str, Any]:
        res = await _call_mcp_source_async(
            resource_uri=resource_uri.strip(),
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
        return ({"data": {}, "error": f"mcp_source execute failed: {e}"}, state)
    except TimeoutError as e:
        return ({"data": {}, "error": f"mcp_source execute failed (timeout): {e}"}, state)
    except asyncio.CancelledError:
        raise  # don’t convert cancellation into a “data error”


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
                "Reads an MCP resource (source) via the python mcp SDK. "
                "Consumes parser_output.mcp_source.resource_uri and returns the resource content. "
                "Transport/mode/credentials are sourced from unit params (not from payload). "
                "If params['mcp_host'] is provided, it uses cached discovery + dispatch."
            ),
        )
    )


__all__ = [
    "RUN_MCP_SOURCE_INPUT_PORTS",
    "RUN_MCP_SOURCE_OUTPUT_PORTS",
    "register_mcp_source",
]
