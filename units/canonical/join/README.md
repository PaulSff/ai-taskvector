# Join

Collector: N scalar inputs → one observation vector. Used in canonical training flow so multiple observation sources feed a single vector to the env.

## Purpose

Wires observation source units (e.g. sensors) to a single ordered vector. The graph connects each source to `in_0`, `in_1`, …; Join outputs `observation` as a list of floats in that order. Used by RLGym, RLOracle, and RLAgent/LLMAgent as the observation input.

## Interface

| Port / Param   | Direction | Type   | Description                              |
|----------------|-----------|--------|------------------------------------------|
| **Inputs**     | in_0..in_N | float | Scalar values from observation sources   |
| **Outputs**    | out       | vector | `observation` — ordered list of floats  |
| **Params**     | config    | —      | `num_inputs` (default 8, max 8)         |

## Example

**Params:** `{"num_inputs": 2}`

**Inputs:** `{"in_0": 0.5, "in_1": 0.8}`  
**Output:** `{"observation": [0.5, 0.8]}`

**Inputs:** `{"in_0": [0.3], "in_1": 1.0}` (e.g. from agent)  
**Output:** `{"observation": [0.3, 1.0]}`
