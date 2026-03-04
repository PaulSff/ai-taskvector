"""
StepDriver unit: canonical trigger for reset/step.

Input: trigger ("reset" | "step") from env.
Output 0: start message → Split → simulators (action=start on reset, step tick on step).
Output 1: response (action=idle on reset) for env return.
"""
from units.registry import UnitSpec, register_unit

STEP_DRIVER_INPUT_PORTS = [("trigger", "any")]
STEP_DRIVER_OUTPUT_PORTS = [("start", "message"), ("response", "message")]

# Sentinel values for trigger (env injects these)
TRIGGER_RESET = "reset"
TRIGGER_STEP = "step"


def _step_driver_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Emit start and response based on trigger (reset | step)."""
    trigger = inputs.get("trigger")
    if trigger == TRIGGER_RESET:
        return (
            {"start": {"action": "start"}, "response": {"action": "idle"}},
            state,
        )
    # step or any other
    return (
        {"start": {"action": "step"}, "response": {}},
        state,
    )


def register_step_driver() -> None:
    register_unit(UnitSpec(
        type_name="StepDriver",
        input_ports=STEP_DRIVER_INPUT_PORTS,
        output_ports=STEP_DRIVER_OUTPUT_PORTS,
        step_fn=_step_driver_step,
        role="step_driver",
    ))


__all__ = [
    "register_step_driver",
    "STEP_DRIVER_INPUT_PORTS",
    "STEP_DRIVER_OUTPUT_PORTS",
    "TRIGGER_RESET",
    "TRIGGER_STEP",
]
