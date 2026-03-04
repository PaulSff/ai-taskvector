"""
Split unit: fan-out one input to N outputs (same message to each target).

Used in canonical training flow: step_driver output 0 (action=start) → Split → simulator 1..n.
"""
from units.registry import UnitSpec, register_unit

# Default up to 8 outputs; graph can have fewer connections
DEFAULT_N = 8
SPLIT_INPUT_PORTS = [("trigger", "any")]
SPLIT_OUTPUT_PORTS = [(f"out_{i}", "any") for i in range(DEFAULT_N)]


def _split_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Copy the trigger input to every output port."""
    value = inputs.get("trigger")
    n = int(params.get("num_outputs", DEFAULT_N))
    n = min(max(n, 1), DEFAULT_N)
    out = {f"out_{i}": value for i in range(n)}
    return out, state


def register_split() -> None:
    register_unit(UnitSpec(
        type_name="Split",
        input_ports=SPLIT_INPUT_PORTS,
        output_ports=SPLIT_OUTPUT_PORTS,
        step_fn=_split_step,
        role="split",
    ))


__all__ = ["register_split", "SPLIT_INPUT_PORTS", "SPLIT_OUTPUT_PORTS"]
