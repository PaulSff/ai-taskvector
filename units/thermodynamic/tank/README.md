# Tank

Mixing tank with energy/mass balance and cooling toward ambient. Consumes hot/cold/dump flows and outputs temperature, volume, and volume ratio.

## Purpose

Models a single tank: inflows (hot, cold), outflow (dump), mixed temperature, and cooling. State is carried across steps (volume, temp). Used as the main process unit in thermodynamic control (e.g. temperature + level control).

## Interface

| Port / Param   | Direction | Type  | Description                    |
|----------------|-----------|-------|--------------------------------|
| **Inputs**     | in        | float | `hot_flow` — hot water flow    |
|                | in        | float | `cold_flow` — cold water flow  |
|                | in        | float | `dump_flow` — drain flow       |
|                | in        | float | `hot_temp` — temp of hot in    |
|                | in        | float | `cold_temp` — temp of cold in  |
| **Outputs**    | out       | float | `temp` — current tank temp     |
|                | out       | float | `volume` — current volume     |
|                | out       | float | `volume_ratio` — volume/capacity (0–1) |
| **Params**     | config    | —     | `capacity` (default 1.0)       |
|                | config    | —     | `cooling_rate` (default 0.01)  |

## Example

**Params:** `{"capacity": 1.0, "cooling_rate": 0.01}`

**Inputs (one step):**  
`{"hot_flow": 0.1, "cold_flow": 0.05, "dump_flow": 0.0, "hot_temp": 60, "cold_temp": 10}`

**Outputs:**  
`{"temp": 35.2, "volume": 0.55, "volume_ratio": 0.55}`
