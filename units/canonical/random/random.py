"""
Random unit: outputs random float(s) each step (e.g. for flow, noise, or testing).

Optional input: trigger (from Split) — when present, Random runs on the same tick as simulators.
Params: min, max (default 0, 1); size (default 1 = one scalar). Output: "value" (single float) or "values" (list).
"""
import random

from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

RANDOM_INPUT_PORTS = [("trigger", "any")]
RANDOM_OUTPUT_PORTS = [
    ("value", "float"),
    ("values", "list[float]"),
]


def _number_param(params: Data, name: str, default: float) -> float:
    value = params.get(name, default)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    raise ValueError(f"{name} must be a number")


def _int_param(params: Data, name: str, default: int) -> int:
    value = params.get(name, default)

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    raise ValueError(f"{name} must be an integer")


def _random_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Emit one or more random floats in [min, max]."""
    lo = _number_param(params, "min", 0.0)
    hi = _number_param(params, "max", 1.0)

    size = _int_param(params, "size", 1)
    size = max(1, min(size, 16))

    if size == 1:
        return {"value": random.uniform(lo, hi)}, state

    values = [random.uniform(lo, hi) for _ in range(size)]

    return {
        "value": values[0],
        "values": values,
    }, state


def register_random() -> None:
    register_unit(UnitSpec(
        type_name="Random",
        input_ports=RANDOM_INPUT_PORTS,
        output_ports=RANDOM_OUTPUT_PORTS,
        step_fn=_random_step,
        role="random",
        description="Outputs random float(s) each step (min/max/size params); useful for noise or testing.",
    ))


__all__ = ["RANDOM_INPUT_PORTS", "RANDOM_OUTPUT_PORTS", "register_random"]
