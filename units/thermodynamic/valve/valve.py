"""Valve unit: setpoint (0–1) -> flow."""

import numpy as np

from units.registry import UnitSpec, register_unit


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


def register_valve() -> None:
    register_unit(UnitSpec(
        type_name="Valve",
        input_ports=[("setpoint", "float")],
        output_ports=[("flow", "float")],
        step_fn=_valve_step,
        controllable=True,
        description="Control valve: setpoint (0–1) maps to flow (setpoint * max_flow); primary action target for RL.",
    ))
