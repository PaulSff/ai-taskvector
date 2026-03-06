# Random

Outputs random float(s) each step. Used for testing, exploration, or injecting random flow/noise.

## Purpose

Stateless unit that emits random values in a configurable range. Useful as a placeholder action source, noise, or for sanity-checking runtime execution. Optional **trigger** input (e.g. from Split) so it runs on the same tick as simulators; flow is Split → Random → Source (noise).

## Interface

| Port / Param | Direction | Type   | Description                    |
|--------------|-----------|--------|--------------------------------|
| **Inputs**   | trigger   | any    | Optional; when wired (e.g. from Split), Random runs when trigger is received |
| **Outputs**  | out       | float  | `value` — one float or first of list |
| **Params**   | config    | —      | `min` (default 0), `max` (default 1), `size` (default 1; if > 1 also outputs `values` list) |

## Example

**Params:** `{"min": 0, "max": 1}`  
**Outputs:** `{"value": 0.42}`

**Params:** `{"min": -1, "max": 1, "size": 3}`  
**Outputs:** `{"value": 0.1, "values": [0.1, -0.5, 0.8]}`
