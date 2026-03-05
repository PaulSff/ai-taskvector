# Switch

Demux: one action vector → N scalar outputs (one per action target). Used in canonical training flow so the env/agent can send one vector that is split to valves or other actuators.

## Purpose

Takes a single `action` list (e.g. from RL agent or training client) and outputs `out_0`, `out_1`, … as scalars. The graph wires these to action targets (e.g. valves). Enables a single action vector to drive multiple controllable units in a fixed order.

## Interface

| Port / Param   | Direction | Type   | Description                          |
|----------------|-----------|--------|--------------------------------------|
| **Inputs**     | in        | vector | `action` — list of floats            |
| **Outputs**   | out_0..out_N | float | Scalar per target (0.0 if index missing) |
| **Params**     | config    | —      | `num_outputs` (default 8, max 8)    |

## Example

**Params:** `{"num_outputs": 3}`

**Input:** `{"action": [0.5, 0.8, 0.0]}`  
**Outputs:** `{"out_0": 0.5, "out_1": 0.8, "out_2": 0.0}`

**Input:** `{"action": [1.0]}` (only one value)  
**Outputs:** `{"out_0": 1.0, "out_1": 0.0, "out_2": 0.0}`
