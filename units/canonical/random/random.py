"""
Random unit: outputs random float(s) each step (e.g. for flow, noise, or testing).

Optional input: trigger (from Split) — when present, Random runs on the same tick as simulators.
Params: min, max (default 0, 1); size (default 1 = one scalar). Output: "value" (single float) or "values" (list).
"""
import random

from units.registry import UnitSpec, register_unit

RANDOM_INPUT_PORTS = [("trigger", "any")]
RANDOM_OUTPUT_PORTS = [("value", "float")]


def _random_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Emit one or more random floats in [min, max]."""
    lo = float(params.get("min", 0.0))
    hi = float(params.get("max", 1.0))
    size = int(params.get("size", 1))
    size = max(1, min(size, 16))
    if size == 1:
        out = random.uniform(lo, hi)
        return {"value": out}, state
    values = [random.uniform(lo, hi) for _ in range(size)]
    return {"value": values[0], "values": values}, state


def register_random() -> None:
    register_unit(UnitSpec(
        type_name="Random",
        input_ports=RANDOM_INPUT_PORTS,
        output_ports=RANDOM_OUTPUT_PORTS,
        step_fn=_random_step,
        role="random",
    ))


__all__ = ["register_random", "RANDOM_INPUT_PORTS", "RANDOM_OUTPUT_PORTS"]
