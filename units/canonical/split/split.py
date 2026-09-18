"""
Split unit: fan-out one input to N outputs (same message to each target).

Used in canonical training flow: step_driver output 0 (action=start) → Split → simulator 1..n.
"""
from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

DEFAULT_N = 8
SPLIT_INPUT_PORTS = [("trigger", "any")]
SPLIT_OUTPUT_PORTS = [(f"out_{i}", "any") for i in range(DEFAULT_N)]


def _split_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Copy the trigger input to every output port."""
    value = inputs.get("trigger")
    num_outputs = params.get("num_outputs", DEFAULT_N)

    if not isinstance(num_outputs, int) or isinstance(num_outputs, bool):
        raise TypeError("num_outputs must be an integer")

    n = min(max(num_outputs, 1), DEFAULT_N)
    out = {f"out_{i}": value for i in range(n)}

    return out, state


def register_split() -> None:
    register_unit(UnitSpec(
        type_name="Split",
        input_ports=SPLIT_INPUT_PORTS,
        output_ports=SPLIT_OUTPUT_PORTS,
        step_fn=_split_step,
        role="split",
        description=(
            "Fans out one trigger input to N outputs "
            "(same message to each target); used to broadcast "
            "reset/step to simulators."
        ),
    ))


__all__ = ["SPLIT_INPUT_PORTS", "SPLIT_OUTPUT_PORTS", "register_split"]
