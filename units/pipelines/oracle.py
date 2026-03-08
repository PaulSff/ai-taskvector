"""
RLOracle unit type: step-handler node for external-runtime training.

Two roles (params.role): step_driver (outputs action to process) and collector
(inputs observation from sensors, returns obs/reward/done to client). One UnitSpec:
input observation (used by collector), output action (used by step_driver).
See docs/PROCESS_GRAPH_TOPOLOGY.md §5.2.
"""
from units.registry import UnitSpec, register_unit

# Collector: observation in (from sensors). Step_driver: action out (to process).
ORACLE_INPUT_PORTS = [("observation", "vector")]
ORACLE_OUTPUT_PORTS = [("action", "vector")]


def _noop_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """No-op; RLOracle runs via adapters, not executor."""
    return {}, state


def register_oracle_units() -> None:
    """Register RLOracle in the unit registry."""
    register_unit(UnitSpec(
        type_name="RLOracle",
        input_ports=ORACLE_INPUT_PORTS,
        output_ports=ORACLE_OUTPUT_PORTS,
        step_fn=_noop_step,
        environment_tags=["RL training"],
        description="Step-handler node for external-runtime training (e.g. Node-RED/PyFlow): collector returns obs/reward/done; step_driver injects action.",
        pipeline=True,
        runtime_scope="external",
    ))


__all__ = ["register_oracle_units", "ORACLE_INPUT_PORTS", "ORACLE_OUTPUT_PORTS"]
