"""Tank unit (simulator): energy/mass balance, cooling toward ambient.

Accepts optional start (trigger) input: on action=start, internal state is reset to initial.
"""

import numpy as np

from units.registry import UnitSpec, register_unit

# start port last so existing graphs (indices 0..4) stay valid
TANK_INPUT_PORTS = [
    ("hot_flow", "float"),
    ("cold_flow", "float"),
    ("dump_flow", "float"),
    ("hot_temp", "float"),
    ("cold_temp", "float"),
    ("start", "trigger"),
]


def _tank_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Tank: energy/mass balance, cooling toward ambient. Resets state on start trigger."""
    capacity = float(params.get("capacity", 1.0))
    cooling_rate = float(params.get("cooling_rate", 0.01))
    ambient = 20.0
    temp_min, temp_max = 0.0, 100.0

    # Reset state when start (action=start) is received
    start = inputs.get("start")
    if start is not None and isinstance(start, dict) and start.get("action") == "start":
        state = {}
    elif start is not None and start == "start":
        state = {}

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


def register_tank() -> None:
    register_unit(UnitSpec(
        type_name="Tank",
        input_ports=TANK_INPUT_PORTS,
        output_ports=[("temp", "float"), ("volume", "float"), ("volume_ratio", "float")],
        step_fn=_tank_step,
    ))
