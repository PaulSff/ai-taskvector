# Split

Fan-out: one trigger input → N outputs (same message to each target). Used in canonical training flow to broadcast step/reset from StepDriver to all simulators.

## Purpose

Receives the “start” message from StepDriver (reset or step tick) and forwards it to multiple downstream units (e.g. simulators). Each output port gets the same value. Enables one driver to control many process units in lockstep.

## Interface

| Port / Param   | Direction | Type | Description                          |
|----------------|-----------|------|--------------------------------------|
| **Inputs**     | in        | any  | `trigger` — message from StepDriver  |
| **Outputs**   | out_0..out_N | any | Same message to each target        |
| **Params**     | config    | —    | `num_outputs` (default 8, max 8)    |

## Example

**Params:** `{"num_outputs": 2}`

**Input:** `{"trigger": {"action": "step"}}`  
**Outputs:** `{"out_0": {"action": "step"}, "out_1": {"action": "step"}}`

**Input:** `{"trigger": {"action": "start"}}` (reset)  
**Outputs:** `{"out_0": {"action": "start"}, "out_1": {"action": "start"}}`
