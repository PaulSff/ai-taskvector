"""
RLOracle pipeline: step-handler for external-runtime training (Node-RED, PyFlow, etc.).

Two roles: step_driver (outputs action to process) and collector (inputs observation, returns obs/reward/done).
"""
from units.registry import UnitSpec, register_unit

ORACLE_INPUT_PORTS = [("observation", "vector")]
ORACLE_OUTPUT_PORTS = [("action", "vector")]


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    return {}, state


def register_oracle_units() -> None:
    register_unit(UnitSpec(
        type_name="RLOracle",
        input_ports=ORACLE_INPUT_PORTS,
        output_ports=ORACLE_OUTPUT_PORTS,
        step_fn=_noop_step,
        environment_tags=["RL training"],
        environment_tags_are_agnostic=True,
        description="Step-handler node for external-runtime training (e.g. Node-RED/PyFlow): collector returns obs/reward/done; step_driver injects action.",
        pipeline=True,
        template_path="units/pipelines/rl_oracle/workflow.json",
        runtime_scope="external",
    ))


__all__ = ["register_oracle_units", "ORACLE_INPUT_PORTS", "ORACLE_OUTPUT_PORTS"]
