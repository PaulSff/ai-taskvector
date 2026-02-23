"""Source unit: outputs temp and max_flow from params."""

from units.registry import UnitSpec, register_unit


def _source_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Source: constant temp and max_flow from params."""
    temp = float(params.get("temp", 60.0))
    max_flow = float(params.get("max_flow", 1.0))
    return {"temp": temp, "max_flow": max_flow}, state


def register_source() -> None:
    register_unit(UnitSpec(
        type_name="Source",
        input_ports=[],
        output_ports=[("temp", "float"), ("max_flow", "float")],
        step_fn=_source_step,
    ))
