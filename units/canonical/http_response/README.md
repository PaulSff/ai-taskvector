# HttpResponse

Canonical exit that sends the /step response back to the training client. Input is the payload (observation, reward, done); the adapter reads it and sends the HTTP response.

## Purpose

Sink for the step response: on reset, payload may be from StepDriver (e.g. action=idle); on step, payload comes from StepRewards (observation, reward, done). The graph does not execute logic here — the adapter reads this unit’s input and sends it as the HTTP body. No code template; Node-RED export maps this type to the platform “http response” node.

## Interface

| Port / Param | Direction | Type | Description                          |
|--------------|-----------|------|--------------------------------------|
| **Inputs**   | in        | any  | `payload` — body to send to client   |
| **Outputs**  | —         | —    | None (side-effect only)              |
| **Params**   | config    | —    | Platform-specific response options   |

## Example

**Input:** `{"payload": {"observation": [0.5, 0.8], "reward": 0.1, "done": false}}`

The adapter reads `payload` and returns it as the HTTP response body to the training client.
