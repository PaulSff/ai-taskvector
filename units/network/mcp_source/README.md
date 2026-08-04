## MCPSource unit

Enables TaskVector to interact with Model Context Protocol (MCP) servers.

## Overview

The `MCPSource` unit serves as a bridge between the TaskVector framework and MCP-compliant servers. It consumes structured source requests and returns the  results, allowing the AI to extend its capabilities via external sources.


### Inputs
- `parser_output`: Dict containing `mcp_source` { `resource_uri`: str }

### Parameters
- `mcp_host`: Host object for dispatch.
- `mcp_in_memory`: Boolean.
- `mcp_server_object`: Server object for in-memory mode.
- `mcp_custom_transport`: Transport object (required for auth).
- `mcp_url`: HTTP URL for MCP server.
- `mcp_http_headers`: Dict (only with custom transport).
- `mcp_bearer_token`: String (only with custom transport).
.

### Outputs
- `data`: Content of the requested resource.
- `error`: Error message string.

## Example:

```json
{
  "mcp_source": {
    "resource_uri": "mcp://server-1/logs/today.txt"
  }
}
```

## Constraints & Critical Notes

Authentication via `mcp_http_headers` or `mcp_bearer_token` is **only** permitted when using the Custom Transport mode. Attempting to use these with the standard HTTP transport will result in a ValueError.

## Execution Flow

The unit handles asynchronous execution using `asyncio`. It is designed to be thread-safe, checking for an existing event loop before deciding whether to use `run_coroutine_threadsafe` or `asyncio.run`.

## Transport Mechanisms

The unit supports four distinct modes of operation based on the provided parameters:
1. **Host-dispatch:** Uses `mcp_host` for direct dispatch.
2. **In-memory:** Uses `mcp_in_memory` and `mcp_server_object` (primarily for testing).
3. **Custom Transport:** Uses `mcp_custom_transport` for advanced configurations.
4. **HTTP Transport:** Uses `mcp_url` as the default fallback.
