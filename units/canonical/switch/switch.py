"""
Switch unit: demux one action vector to N scalar outputs (one per action target).

Used in canonical training flow: env injects action vector -> Switch -> action 1..n (valves).
"""
from units.registry import UnitSpec, register_unit

# Default up to 8 outputs
DEFAULT_N = 8
SWITCH_INPUT_PORTS = [("action", "vector")]
SWITCH_OUTPUT_PORTS = [(f"out_{i}", "float") for i in range(DEFAULT_N)]


def _switch_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Demux action vector: output[i] = action[i]."""
    action = inputs.get("action")
    if action is None:
        action = []
    if not isinstance(action, (list, tuple)):
        action = [float(action)] if action is not None else []
    action = [float(x) for x in action]
    n = int(params.get("num_outputs", DEFAULT_N))
    n = min(max(n, 1), DEFAULT_N)
    out = {}
    for i in range(n):
        out[f"out_{i}"] = action[i] if i < len(action) else 0.0
    return out, state


def register_switch() -> None:
    register_unit(UnitSpec(
        type_name="Switch",
        input_ports=SWITCH_INPUT_PORTS,
        output_ports=SWITCH_OUTPUT_PORTS,
        step_fn=_switch_step,
        role="switch",
        description="Demuxes one action vector to N scalar outputs (one per action target, e.g. valves).",
    ))


__all__ = ["register_switch", "SWITCH_INPUT_PORTS", "SWITCH_OUTPUT_PORTS"]
