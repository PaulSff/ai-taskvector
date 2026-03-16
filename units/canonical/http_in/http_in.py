"""
HttpIn: canonical entry for HTTP POST /step from the training client (e.g. runtime/train.py).

Plain HTTP In: one input (request from client), one output (same message passthrough).
Bypasses nothing; the next unit (request_router) routes the message to step_driver and action Switch.
"""
from units.registry import UnitSpec, register_unit

HTTP_IN_INPUT_PORTS = [("request", "any")]
HTTP_IN_OUTPUT_PORTS = [("out", "any")]


def _http_in_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Passthrough; adapter injects request at runtime."""
    return ({"out": inputs.get("request")}, state)


def register_http_in() -> None:
    register_unit(UnitSpec(
        type_name="HttpIn",
        input_ports=HTTP_IN_INPUT_PORTS,
        output_ports=HTTP_IN_OUTPUT_PORTS,
        step_fn=_http_in_step,
        role="http_in",
        description="Canonical entry for HTTP POST /step from the training client; passthrough for request to router.",
    ))


__all__ = ["register_http_in", "HTTP_IN_INPUT_PORTS", "HTTP_IN_OUTPUT_PORTS"]
