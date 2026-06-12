"""
AgentOrchestrator unit: agent turn execution.

Receives a context dict on the ``data`` input port containing:
  user_message, messenger, role_id (or role_hint), history, session_language,
  last_apply_result, graph, recent_changes, use_current_graph,
  provider, cfg, rag_index_dir, mydata_dir, coding_is_allowed,
  contribution_is_allowed, training_config_path

Output ports:
  status   {"type":"status","status":"..."}
  token    {"type":"token","token":"<full reply text>"}
  message  {"type":"final","message":{id, ts, role, content, agent, graph,
             parsed_edits, last_apply_result, session_language, run_output,
             follow_up_contexts, apply, source, turn_id, llm_user_message,
             llm_system_prompt}}
  role     {"role_id":"...","name":"..."}
  error    {"type":"error","error":"..."} or None

Streaming: LLM token chunks stream through _stream_callback in params (same
mechanism as all other streaming units).
Params: "_needs_executor": true - MUST be set in params, so that the executor injects the async loop
"""

from __future__ import annotations

import asyncio
from typing import Any

from units.registry import UnitSpec, register_unit

from .turn_runner_async import run_orchestrator_turn_async

AGENT_ORCHESTRATOR_INPUT_PORTS = [
    ("data", "Any"),  # context dict (see module docstring)
    ("messenger", "str"),  # optional — also accepted inside data["messenger"]
]
AGENT_ORCHESTRATOR_OUTPUT_PORTS = [
    ("status", "Any"),
    ("token", "Any"),
    ("message", "Any"),
    ("role", "Any"),
    ("error", "Any"),
]


def _agent_orchestrator_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one agent turn using run_orchestrator_turn_async scheduled on the
    GraphExecutor background event loop (executor._loop). Blocks until done.
    """
    # Normalize data input
    data = inputs.get("data") or {}
    if isinstance(data, str):
        data = {"user_message": data}
    if not isinstance(data, dict):
        data = {}

    # messenger can come from the data dict or from the separate input port
    messenger_port = inputs.get("messenger")
    if messenger_port and "messenger" not in data:
        data = {**data, "messenger": str(messenger_port)}

    stream_cb = params.get("_stream_callback")

    try:
        # Resolve background loop: prefer executor instance, then loop object directly.
        background_loop = None
        exec_obj = params.get("_executor")
        if exec_obj is not None:
            # support either GraphExecutor or object exposing _loop
            background_loop = getattr(exec_obj, "_loop", None)
        if background_loop is None:
            background_loop = params.get("_executor_loop") or params.get(
                "_background_loop"
            )

        if not isinstance(background_loop, asyncio.AbstractEventLoop):
            raise RuntimeError(
                "Background event loop not provided. Pass params['_executor'] (GraphExecutor) or params['_executor_loop']."
            )

        # Build coroutine and schedule it on the executor loop; block until completion.
        coro = run_orchestrator_turn_async(data, stream_callback=stream_cb)
        fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
        result = fut.result()  # may raise exceptions from the coroutine

    except Exception as exc:
        error_payload: dict[str, Any] = {
            "type": "error",
            "error": str(exc) or type(exc).__name__,
        }
        return (
            {
                "status": None,
                "token": None,
                "message": None,
                "role": None,
                "error": error_payload,
            },
            state,
        )

    return (result, state)


def register_agent_orchestrator() -> None:
    """Register the AgentOrchestrator unit type."""
    register_unit(
        UnitSpec(
            type_name="AgentOrchestrator",
            input_ports=AGENT_ORCHESTRATOR_INPUT_PORTS,
            output_ports=AGENT_ORCHESTRATOR_OUTPUT_PORTS,
            step_fn=_agent_orchestrator_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Framework-agnostic agent turn orchestrator. Runs dispatcher → role workflow → "
                "follow-up chain → graph apply/validate → post-apply rounds. "
                "Emits token stream via _stream_callback; final outputs on all ports."
            ),
        )
    )


__all__ = [
    "register_agent_orchestrator",
    "AGENT_ORCHESTRATOR_INPUT_PORTS",
    "AGENT_ORCHESTRATOR_OUTPUT_PORTS",
]
