"""
Join unit (Collector): N inputs → one output vector (observation).

Used in canonical training flow: obs source 1..n → Join → observation vector to env.
"""
from units.registry import UnitSpec, register_unit

# Default up to 8 inputs; graph wires obs sources to in_0, in_1, ...
DEFAULT_N = 8
JOIN_INPUT_PORTS = [(f"in_{i}", "float") for i in range(DEFAULT_N)]
JOIN_OUTPUT_PORTS = [("observation", "vector")]


def _join_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Build observation vector from input ports in order (in_0, in_1, ...)."""
    n = int(params.get("num_inputs", DEFAULT_N))
    n = min(max(n, 1), DEFAULT_N)
    obs = []
    for i in range(n):
        key = f"in_{i}"
        v = inputs.get(key)
        if v is None:
            obs.append(0.0)
        elif isinstance(v, (list, tuple)):
            obs.append(float(v[0]) if v else 0.0)
        else:
            obs.append(float(v))
    return {"observation": obs}, state


def register_join() -> None:
    register_unit(UnitSpec(
        type_name="Join",
        input_ports=JOIN_INPUT_PORTS,
        output_ports=JOIN_OUTPUT_PORTS,
        step_fn=_join_step,
        role="join",
    ))


__all__ = ["register_join", "JOIN_INPUT_PORTS", "JOIN_OUTPUT_PORTS"]
