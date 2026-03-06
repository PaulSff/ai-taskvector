# Source

Constant temperature and max-flow source for thermodynamic flows (e.g. hot or cold water supply).

## Purpose

Provides `temp` and `max_flow` from parameters. Optional inputs: `start` (trigger from Split for canonical reset), `random` (additive noise to temp, e.g. from a Random unit). Used as input to valves and mixing logic.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | start     | trigger | Optional; action=start from Split |
|              | random    | float   | Optional; additive noise to temp |
| **Outputs**  | out       | float  | `temp` — supply temperature    |
|              | out       | float  | `max_flow` — maximum flow rate |
| **Params**   | config    | —      | `temp` (default 60.0)          |
|              | config    | —      | `max_flow` (default 1.0)      |

## Example

**Params:** `{"temp": 60, "max_flow": 1.0}`

**Outputs (each step):**
```json
{"temp": 60.0, "max_flow": 1.0}
```
