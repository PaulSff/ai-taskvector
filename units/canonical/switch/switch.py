"""
Switch unit: demux one action vector to N scalar outputs (one per action target).

Used in canonical training flow: env injects action vector -> Switch -> action 1..n (valves).
"""
from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

# Default up to 8 outputs
DEFAULT_N = 8
SWITCH_INPUT_PORTS = [("action", "vector")]
SWITCH_OUTPUT_PORTS = [(f"out_{i}", "float") for i in range(DEFAULT_N)]


def _switch_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Demux action vector: output[i] = action[i]."""
    raw_action = inputs.get("action")
    action: list[float] = []

    if isinstance(raw_action, (list, tuple)):
        for item in raw_action:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                action.append(float(item))
            else:
                raise TypeError("action values must be numeric")

    elif isinstance(raw_action, (int, float)) and not isinstance(raw_action, bool):
        action.append(float(raw_action))

    elif raw_action is not None:
        raise ValueError("action must be a vector or number")

    raw_num_outputs = params.get("num_outputs", DEFAULT_N)

    if not isinstance(raw_num_outputs, int) or isinstance(raw_num_outputs, bool):
        raise TypeError("num_outputs must be an integer")

    n = min(max(raw_num_outputs, 1), DEFAULT_N)

    out: Data = {}

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


__all__ = ["SWITCH_INPUT_PORTS", "SWITCH_OUTPUT_PORTS", "register_switch"]
