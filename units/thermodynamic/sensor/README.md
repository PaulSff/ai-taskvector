# Sensor

Pass-through sensor with optional normalization for observations (0–1). Typical use: wire tank temp or volume_ratio into the sensor, then wire sensor output into an RL agent as observation.

## Purpose

Takes a scalar `value` (e.g. temperature or volume ratio) and outputs both a normalized value (`measurement`, 0–1 for RL) and the raw value (`raw`). Normalization depends on `params.measure`: temperature divides by 100; volume/volume_ratio is clipped to 0–1.

## Interface

| Port / Param | Direction | Type  | Description                          |
|--------------|-----------|-------|--------------------------------------|
| **Inputs**   | in        | float | `value` — raw reading                 |
| **Outputs**  | out       | float | `measurement` — normalized (0–1)      |
|              | out       | float | `raw` — same as input                 |
| **Params**   | config    | —     | `measure`: "temperature", "volume", "volume_ratio" (default "temperature") |

## Example

**Params:** `{"measure": "temperature"}`

**Input:** `{"value": 37.5}`  
**Output:** `{"measurement": 0.375, "raw": 37.5}`

**Params:** `{"measure": "volume_ratio"}`  
**Input:** `{"value": 0.82}`  
**Output:** `{"measurement": 0.82, "raw": 0.82}`
