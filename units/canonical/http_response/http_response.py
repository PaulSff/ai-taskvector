"""
HttpResponse: canonical exit that sends the /step response back to the client (e.g. runtime/train.py).

Input: payload (from step_driver output 1 on reset (action=idle), or from collector on step (obs/reward/done)).
At runtime the adapter reads this unit's input and sends the HTTP response.
"""
from units.registry import UnitSpec, register_unit

HTTP_RESPONSE_INPUT_PORTS = [("payload", "any")]
HTTP_RESPONSE_OUTPUT_PORTS = []  # side-effect only: response to client


def _http_response_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """No-op in-graph; adapter reads payload and sends HTTP response."""
    return ({}, state)


def register_http_response() -> None:
    register_unit(UnitSpec(
        type_name="HttpResponse",
        input_ports=HTTP_RESPONSE_INPUT_PORTS,
        output_ports=HTTP_RESPONSE_OUTPUT_PORTS,
        step_fn=_http_response_step,
        role="http_response",
        description="Canonical exit that sends the /step response (obs, reward, done) back to the client.",
    ))


__all__ = ["register_http_response", "HTTP_RESPONSE_INPUT_PORTS", "HTTP_RESPONSE_OUTPUT_PORTS"]
