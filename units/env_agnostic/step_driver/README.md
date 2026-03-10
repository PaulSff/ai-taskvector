# StepDriver

Canonical trigger for reset/step. Receives a trigger from the env (or HTTP/router) and emits a “start” message to simulators and a “response” message for the client.

## Purpose

Bridges the training loop (or HTTP `/step`) to the graph: on **reset**, sends `action: "start"` to Split → simulators and `action: "idle"` on the response port; on **step**, sends `action: "step"` to simulators and an empty response. The executor (or external adapter) injects the trigger and reads the response; in the HTTP path, the step_router feeds StepDriver from HttpIn.

## Interface

| Port / Param | Direction | Type    | Description                                    |
|--------------|-----------|---------|------------------------------------------------|
| **Inputs**   | in        | any     | `trigger` — `"reset"` or `"step"`             |
| **Outputs**  | start     | message | To Split → simulators (`action`: start/step)  |
|              | response  | message | To env/HTTP (`action`: idle on reset)        |
| **Params**   | —         | —       | None                                           |

## Example

**Input:** `{"trigger": "reset"}`  
**Outputs:** `{"start": {"action": "start"}, "response": {"action": "idle"}}`

**Input:** `{"trigger": "step"}`  
**Outputs:** `{"start": {"action": "step"}, "response": {}}`
