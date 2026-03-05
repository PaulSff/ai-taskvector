# HttpIn

Canonical HTTP entry for POST /step from the training client. One input (request), one output (passthrough). The next node (e.g. step_router) routes the message to StepDriver and Switch.

## Purpose

Represents the HTTP endpoint where the training client sends reset/step requests. At runtime the adapter injects the request into this unit; the unit passes it through. No code template in deploy — Node-RED export maps this type to the platform “http in” node (see `NODE_RED_TYPE_MAP`). Params (e.g. url, method) are exported as node config.

## Interface

| Port / Param | Direction | Type | Description                    |
|--------------|-----------|------|--------------------------------|
| **Inputs**   | in        | any  | `request` — injected by adapter |
| **Outputs**  | out       | any  | Same as request (passthrough)   |
| **Params**   | config    | —    | url, method, etc. (platform-specific) |

## Example

**Params:** `{"url": "/step", "method": "POST"}` (typical for Node-RED)

At runtime the adapter feeds the parsed request body into `request`; the unit outputs it on `out` for the step_router.
