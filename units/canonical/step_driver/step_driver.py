"""
StepDriver unit: canonical trigger for reset/step.

Input: trigger ("reset" | "step") from env.
Output 0: start message → Split → simulators (action=start on reset, step tick on step).
Output 1: response (action=idle on reset) for env return.
Output 2: trigger pass-through → StepRewards (same reset/step value).
"""
from units.registry import UnitSpec, register_unit

STEP_DRIVER_INPUT_PORTS = [("trigger", "any")]
STEP_DRIVER_OUTPUT_PORTS = [("start", "message"), ("response", "message"), ("trigger", "any")]

# Sentinel values for trigger (env injects these)
TRIGGER_RESET = "reset"
TRIGGER_STEP = "step"


def _step_driver_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Emit start, response, and trigger pass-through (for StepRewards)."""
    trigger = inputs.get("trigger")
    if trigger == TRIGGER_RESET:
        return (
            {"start": {"action": "start"}, "response": {"action": "idle"}, "trigger": trigger},
            state,
        )
    # step or any other
    return (
        {"start": {"action": "step"}, "response": {}, "trigger": trigger if trigger is not None else TRIGGER_STEP},
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
