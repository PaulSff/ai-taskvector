# Valve

Controllable valve: setpoint (0–1) maps to flow rate. Used as an action target for RL/control.

## Purpose

Converts a normalized setpoint (e.g. from an RL agent) into a flow value. Flow = setpoint × max_flow. Marked as **controllable** so the graph treats it as an action input.

## Interface

| Port / Param | Direction | Type   | Description                          |
|--------------|-----------|--------|--------------------------------------|
| **Inputs**   | in        | float  | `setpoint` — 0–1, controls flow      |
| **Outputs**  | out       | float  | `flow` — actual flow rate            |
| **Params**   | config    | —      | `max_flow` (default 1.0)             |

## Example

**Params:** `{"max_flow": 1.0}`

**Input:** `{"setpoint": 0.5}`  
**Output:** `{"flow": 0.5}`

**Input:** `{"setpoint": [0.8]}` (e.g. from agent)  
**Output:** `{"flow": 0.8}`
