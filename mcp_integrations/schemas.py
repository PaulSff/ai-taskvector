
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from mcp.client import Transport
from mcp.server.lowlevel import Server

from core.schemas.primitives import Data


@dataclass(frozen=True)
class MCPServerConfig:
    server_id: str
    mode: str  # "in_memory" | "http" | "custom_transport"
    mcp_url: str | None = None
    mcp_server_object: Server[Any] | None = None
    custom_transport: Transport | None = None

    # Optional HTTP auth (only if you switch to custom_transport in your setup)
    mcp_http_headers: dict[str, str] | None = None
    mcp_bearer_token: str | None = None


class MCPHost(Protocol):
    async def call_tool(self, tool_name: str, arguments: Data) -> Data: ...
    async def read_resource(self, resource_uri: str) -> Data: ...


class MCPParams(TypedDict, total=False):
    mcp_host: MCPHost
    mcp_in_memory: bool
    mcp_server_object: Server[Any]
    mcp_custom_transport: Transport
    mcp_url: str
    mcp_http_headers: dict[str, str]
    mcp_bearer_token: str
