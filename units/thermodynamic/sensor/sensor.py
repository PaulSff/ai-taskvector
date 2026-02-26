"""Sensor unit: pass-through with optional normalization (0–1 for obs)."""

import numpy as np

from units.registry import UnitSpec, register_unit


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


def register_sensor() -> None:
    register_unit(UnitSpec(
        type_name="Sensor",
        input_ports=[("value", "float")],
        output_ports=[("measurement", "float"), ("raw", "float")],
        step_fn=_sensor_step,
    ))
