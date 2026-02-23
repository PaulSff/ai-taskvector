"""
Thermodynamic simulation units (NumPy mode).

Source: outputs temp, max_flow (from params)
Valve: input setpoint (0–1), outputs flow
Tank: inputs hot_flow, cold_flow, dump_flow, hot_temp, cold_temp; outputs temp, volume
Sensor: input value, outputs normalized measurement
"""
from __future__ import annotations

import numpy as np

from units.registry import UnitSpec, register_unit


def _source_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Source: constant temp and max_flow from params."""
    temp = float(params.get("temp", 60.0))
    max_flow = float(params.get("max_flow", 1.0))
    return {"temp": temp, "max_flow": max_flow}, state


def _valve_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Valve: setpoint (0–1) -> flow = setpoint * max_flow."""
    setpoint = inputs.get("setpoint", 0.0)
    if isinstance(setpoint, (list, np.ndarray)):
        setpoint = float(setpoint[0]) if len(setpoint) else 0.0
    setpoint = float(np.clip(setpoint, 0.0, 1.0))
    max_flow = float(params.get("max_flow", 1.0))
    flow = setpoint * max_flow
    return {"flow": flow}, state


def _tank_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Tank: energy/mass balance, cooling toward ambient."""
    capacity = float(params.get("capacity", 1.0))
    cooling_rate = float(params.get("cooling_rate", 0.01))
    ambient = 20.0
    temp_min, temp_max = 0.0, 100.0

    hot_flow = float(inputs.get("hot_flow", 0.0) or 0.0)
    cold_flow = float(inputs.get("cold_flow", 0.0) or 0.0)
    dump_flow = float(inputs.get("dump_flow", 0.0) or 0.0)
    hot_temp = float(inputs.get("hot_temp", state.get("hot_temp", 60.0)))
    cold_temp = float(inputs.get("cold_temp", state.get("cold_temp", 10.0)))

    volume = state.get("volume", capacity * 0.5)
    temp = state.get("temp", 20.0)

    total_inflow = hot_flow + cold_flow
    inflow_vol = total_inflow * dt
    dump_vol = dump_flow * dt
    prev_vol = max(volume, 1e-6)

    if total_inflow > 1e-6:
        mixed_temp = (
            hot_flow * hot_temp + cold_flow * cold_temp
        ) / total_inflow
    else:
        mixed_temp = temp

    retained = temp * max(prev_vol - dump_vol, 0.0)
    added = mixed_temp * inflow_vol
    volume = np.clip(prev_vol - dump_vol + inflow_vol, 0.01, capacity)
    temp = (retained + added) / volume
    temp = temp - cooling_rate * (temp - ambient)
    temp = float(np.clip(temp, temp_min, temp_max))

    new_state = {
        "volume": float(volume),
        "temp": temp,
        "hot_temp": hot_temp,
        "cold_temp": cold_temp,
    }
    return {"temp": temp, "volume": volume, "volume_ratio": volume / capacity}, new_state


def _sensor_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Sensor: pass-through with optional normalization (0–1 by default for obs)."""
    value = inputs.get("value", 0.0)
    if isinstance(value, (list, np.ndarray)):
        value = float(value[0]) if len(value) else 0.0
    value = float(value)
    measure = params.get("measure", "temperature")
    # Normalize for RL obs: temp/100, volume_ratio already 0–1
    if measure == "temperature":
        normalized = np.clip(value / 100.0, 0.0, 1.0)
    elif measure in ("volume", "volume_ratio"):
        normalized = np.clip(value, 0.0, 1.0)
    else:
        normalized = np.clip(value, 0.0, 1.0)
    return {"measurement": normalized, "raw": value}, state


def register_thermodynamic_units() -> None:
    """Register Source, Valve, Tank, Sensor in the unit registry."""
    register_unit(UnitSpec(
        type_name="Source",
        input_ports=[],
        output_ports=[("temp", "float"), ("max_flow", "float")],
        step_fn=_source_step,
    ))
    register_unit(UnitSpec(
        type_name="Valve",
        input_ports=[("setpoint", "float")],
        output_ports=[("flow", "float")],
        step_fn=_valve_step,
    ))
    register_unit(UnitSpec(
        type_name="Tank",
        input_ports=[
            ("hot_flow", "float"),
            ("cold_flow", "float"),
            ("dump_flow", "float"),
            ("hot_temp", "float"),
            ("cold_temp", "float"),
        ],
        output_ports=[("temp", "float"), ("volume", "float"), ("volume_ratio", "float")],
        step_fn=_tank_step,
    ))
    register_unit(UnitSpec(
        type_name="Sensor",
        input_ports=[("value", "float")],
        output_ports=[("measurement", "float"), ("raw", "float")],
        step_fn=_sensor_step,
    ))
