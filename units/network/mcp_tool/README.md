# MCPTool Unit

MCPTool unit, which enables TaskVector to interact with Model Context Protocol (MCP) servers.


## Overview

The `MCPTool` unit serves as a bridge between the TaskVector framework and MCP-compliant servers. It consumes structured tool requests and returns the execution results, allowing the AI to extend its capabilities via external tools.


## Technical Specifications

- **Input Port:** `parser_output` (expects a dictionary containing an `mcp_tool` payload).
- **Output Ports:** `data` (structured tool result) and `error` (error message string).
- **Dependencies:** Requires `mcp[cli]` Python package.


## Transport Mechanisms

The unit supports four distinct modes of operation based on the provided parameters:
1. **Host-dispatch:** Uses `mcp_host` for direct dispatch.
2. **In-memory:** Uses `mcp_in_memory` and `mcp_server_object` (primarily for testing).
3. **Custom Transport:** Uses `mcp_custom_transport` for advanced configurations.
4. **HTTP Transport:** Uses `mcp_url` as the default fallback.


## Constraints & Critical Notes

Authentication via `mcp_http_headers` or `mcp_bearer_token` is **only** permitted when using the Custom Transport mode. Attempting to use these with the standard HTTP transport will result in a ValueError.


## Execution Flow

The unit handles asynchronous execution using `asyncio`. It is designed to be thread-safe, checking for an existing event loop before deciding whether to use `run_coroutine_threadsafe` or `asyncio.run`.


## Examples

```json
    {
      "mcp_tool": {
        "tool_name": "calculate_sum",
        "arguments": {
          "a": 10,
          "b": 20
        }
      }
    }
```
