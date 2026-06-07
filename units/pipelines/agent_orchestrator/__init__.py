"""
ChatOrchestrator pipeline: dispatcher → role resolver → AgentOrchestrator.

Registers the ``ChatOrchestrator`` pipeline type so it can be added to graphs
via ``add_pipeline``.  The workflow template (``workflow.json``) is the same
orchestration graph that chat.py runs directly via ``orchestration_workflow_path()``.

Topology:
  inject_context
      → build_dispatch_payload (PayloadTransform)   # build run_workflow action when auto-delegation on
      → run_dispatcher (RunWorkflow)                 # run dispatcher_workflow.json or no-op
      → merge_dispatch (Aggregate)                   # {dispatcher_out, context}
      → resolve_role (PayloadTransform)              # full context with role_id resolved
      → orchestrator (AgentOrchestrator)             # full agent turn
"""

from __future__ import annotations

from pathlib import Path

from units.registry import UnitSpec, register_unit

_WORKFLOW_PATH = Path(__file__).resolve().parent / "workflow.json"

CHAT_ORCHESTRATOR_INPUT_PORTS: list[tuple[str, str]] = [
    ("data", "Any"),  # context dict (user_message, role_id, history, …)
    ("messenger", "str"),  # messenger source identifier
]
CHAT_ORCHESTRATOR_OUTPUT_PORTS: list[tuple[str, str]] = [
    ("status", "Any"),
    ("token", "Any"),
    ("message", "Any"),
    ("role", "Any"),
    ("error", "Any"),
]


def _noop_step(params: dict, inputs: dict, state: dict, dt: float) -> tuple[dict, dict]:
    return {}, state


def register_chat_orchestrator() -> None:
    """Register the ChatOrchestrator pipeline type."""
    register_unit(
        UnitSpec(
            type_name="ChatOrchestrator",
            input_ports=CHAT_ORCHESTRATOR_INPUT_PORTS,
            output_ports=CHAT_ORCHESTRATOR_OUTPUT_PORTS,
            step_fn=_noop_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Messenger-agnostic chat orchestration pipeline: runs the dispatcher, "
                "resolves the role, then drives a full agent turn via AgentOrchestrator. "
                "Inputs: data (context dict), messenger. "
                "Outputs: status, token, message, role, error."
            ),
            pipeline=True,
            template_path=str(_WORKFLOW_PATH),
        )
    )


def orchestration_workflow_path() -> Path:
    """Absolute path to the orchestration workflow JSON (used by the messenger to run the pipeline)."""
    return _WORKFLOW_PATH


__all__ = [
    "register_chat_orchestrator",
    "orchestration_workflow_path",
    "CHAT_ORCHESTRATOR_INPUT_PORTS",
    "CHAT_ORCHESTRATOR_OUTPUT_PORTS",
]
