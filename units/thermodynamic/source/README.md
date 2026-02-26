# Source

Constant temperature and max-flow source for thermodynamic flows (e.g. hot or cold water supply).

## Purpose

Provides fixed `temp` and `max_flow` values from parameters. Used as input to valves and mixing logic. No inputs; runs every step.

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | —         | —      | None (no input ports)          |
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
