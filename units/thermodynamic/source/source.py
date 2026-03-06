"""Source unit (water source simulator): outputs temp and max_flow from params.

Accepts optional start (trigger) input for canonical flow: on action=start, state is reset (no-op for stateless Source).
"""

from units.registry import UnitSpec, register_unit

# start port: receive action=start from Split to align with canonical reset flow
# random port (optional): additive noise to temp (e.g. from Random unit)
SOURCE_INPUT_PORTS = [("start", "trigger"), ("random", "float")]
SOURCE_OUTPUT_PORTS = [("temp", "float"), ("max_flow", "float")]


def _source_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Source: temp and max_flow from params; optional random adds noise to temp. Ignores start trigger (stateless)."""
    temp = float(params.get("temp", 60.0))
    max_flow = float(params.get("max_flow", 1.0))
    r = inputs.get("random")
    if r is not None:
        try:
            r = float(r) if not isinstance(r, (list, tuple)) else float(r[0]) if r else 0.0
        except (TypeError, ValueError):
            r = 0.0
        temp = temp + r
    return {"temp": temp, "max_flow": max_flow}, state


def register_source() -> None:
    register_unit(UnitSpec(
        type_name="Source",
        input_ports=SOURCE_INPUT_PORTS,
        output_ports=SOURCE_OUTPUT_PORTS,
        step_fn=_source_step,
    ))
