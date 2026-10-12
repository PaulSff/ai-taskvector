# Usage:
#
# 1. Somewhere during your app startup:
# ```python
# Build MCPHost([...server configs...])
# await host.start()
# ```
# 2. Pass `params["mcp_host"] = host` into MCPTool/MCPSource unit calls.
#
# Example shape:
#
# ```python
# host = MCPHost([
#     MCPServerConfig(server_id="bookshop", mode="http", mcp_url="http://localhost:8000/mcp"),
# ])
#
# await host.start()
# ```

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from mcp import Client


@dataclass(frozen=True)
class MCPServerConfig:
    server_id: str
    mode: str  # "in_memory" | "http" | "custom_transport"
    mcp_url: str | None = None
    mcp_server_object: Any | None = None
    custom_transport: Any | None = None

    # Optional HTTP auth (only if you switch to custom_transport in your setup)
    mcp_http_headers: dict[str, str] | None = None
    mcp_bearer_token: str | None = None


class MCPHost:
    """
    Host-side cache/discovery + dispatch:
    - start(): discover tools/resources per server and build indexes
    - call_tool(): execute a tool by name (routes to the right server)
    - read_resource(): read resource content by URI (routes to the right server)

    Designed to integrate with your MCPTool and MCPSource units.
    """

    def __init__(self, server_configs: list[MCPServerConfig]) -> None:
        self._server_configs = {c.server_id: c for c in server_configs}

        # name -> server_id
        self._tool_index: dict[str, str] = {}
        self._resource_index: dict[str, str] = {}

        # optional meta
        self._tool_meta: dict[str, Any] = {}
        self._resource_meta: dict[str, Any] = {}

        # server_id -> Client
        self._clients: dict[str, Client] = {}

        self._started = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return

            for server_id, cfg in self._server_configs.items():
                client = self._create_client(cfg)
                self._clients[server_id] = client
                await self._discover_for_server(server_id, client)

            self._started = True

    def _create_client(self, cfg: MCPServerConfig) -> Client:
        if cfg.mode == "in_memory":
            if cfg.mcp_server_object is None:
                raise ValueError("in_memory requires mcp_server_object")
            return Client(cfg.mcp_server_object)

        if cfg.mode == "custom_transport":
            if cfg.custom_transport is None:
                raise ValueError("custom_transport requires custom_transport")
            return Client(cfg.custom_transport)

        if cfg.mode == "http":
            if not cfg.mcp_url:
                raise ValueError("http requires mcp_url")
            if cfg.mcp_http_headers or cfg.mcp_bearer_token:
                raise ValueError("HTTP auth requires custom_transport for this host implementation")
            return Client(cfg.mcp_url.strip())

        raise ValueError(f"Unknown mode: {cfg.mode}")

    async def _discover_for_server(self, server_id: str, client: Client) -> None:
        # Discovery requires a connected client context in this SDK style.
        async with client as connected_client:
            await self._discover_tools(server_id, connected_client)
            await self._discover_resources(server_id, connected_client)

    async def _discover_tools(self, server_id: str, connected_client: Any) -> None:
        """
        Adapter: method name and response shape may vary.
        We try a few common ones and then normalize.
        """
        resp = None
        if hasattr(connected_client, "list_tools"):
            resp = await connected_client.list_tools()
            items = getattr(resp, "tools", None) or getattr(resp, "items", None) or resp
        elif hasattr(connected_client, "tools"):
            # some SDKs expose a method named tools()
            items = await connected_client.tools()  # type: ignore[attr-defined]
        else:
            # Nothing we can do; leave tools undiscovered.
            return

        if items is None:
            return

        for t in items:
            # normalize name from either objects or dicts
            name = None
            if isinstance(t, dict):
                name = t.get("name")
            else:
                name = getattr(t, "name", None)
            if not name:
                continue

            # first server wins (deterministic)
            self._tool_index.setdefault(str(name), server_id)
            self._tool_meta.setdefault(str(name), t)

    async def _discover_resources(self, server_id: str, connected_client: Any) -> None:
        """
        Adapter for resource discovery.
        If the SDK doesn't support listing resources in your configuration,
        this will simply be a no-op (reads can still work if your server allows direct reads).
        """
        if not (hasattr(connected_client, "list_resources") or hasattr(connected_client, "list_resource_templates")):
            return

        if hasattr(connected_client, "list_resources"):
            resp = await connected_client.list_resources()
            items = getattr(resp, "resources", None) or getattr(resp, "items", None) or resp
        else:
            resp = await connected_client.list_resource_templates()  # type: ignore[attr-defined]
            items = getattr(resp, "resources", None) or getattr(resp, "items", None) or resp

        if items is None:
            return

        for r in items:
            rid = None
            if isinstance(r, dict):
                rid = r.get("uri") or r.get("resource_uri")
            else:
                rid = getattr(r, "uri", None) or getattr(r, "resource_uri", None)
            if not rid:
                continue

            rid = str(rid)
            self._resource_index.setdefault(rid, server_id)
            self._resource_meta.setdefault(rid, r)

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_index

    def has_resource(self, resource_uri: str) -> bool:
        return resource_uri in self._resource_index

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._started:
            await self.start()

        server_id = self._tool_index.get(tool_name)
        if not server_id:
            raise ValueError(f"Tool '{tool_name}' not found in discovered MCP servers")

        client = self._clients[server_id]
        async with client as connected_client:
            result = await connected_client.call_tool(tool_name, arguments)
            return getattr(result, "structured_content", result)

    async def read_resource(self, resource_uri: str) -> Any:
        if not self._started:
            await self.start()

        server_id = self._resource_index.get(resource_uri)
        if not server_id:
            raise ValueError(f"Resource '{resource_uri}' not found in discovered MCP servers")

        client = self._clients[server_id]
        async with client as connected_client:
            if hasattr(connected_client, "read_resource"):
                result = await connected_client.read_resource(resource_uri)
            else:
                raise RuntimeError("SDK client has no read_resource()")

            # normalize content
            return (
                getattr(result, "content", None)
                or getattr(result, "structured_content", None)
                or result
            )
