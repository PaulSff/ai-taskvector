"""
AgentOrchestrator unit: agent turn execution.

Receives a context dict (RoleChatTurnContext) on the ``data`` input port containing:
  user_message, messenger, role_id (or role_hint), history, session_language,
  last_apply_result, graph, recent_changes, state,
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
from typing import cast

from core.schemas.primitives import Data, Output
from runtime.executor import GraphStreamCallback
from units.registry import UnitSpec, register_unit

from .turn_runner import run_orchestrator_turn

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
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    """Run one agent turn using run_orchestrator_turn scheduled on the
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

    stream_cb = cast(
        GraphStreamCallback | None,
        params.get("_stream_callback"),
    )

    try:
        # Resolve background loop: prefer executor instance, then loop object directly.
        background_loop = None
        exec_obj = params.get("_executor")

        if exec_obj is not None:
            # Support either GraphExecutor or an object exposing _loop.
            background_loop = getattr(exec_obj, "_loop", None)

        if background_loop is None:
            background_loop = params.get("_executor_loop") or params.get(
                "_background_loop"
            )

        if not isinstance(background_loop, asyncio.AbstractEventLoop):
            raise TypeError(
                "Background event loop not provided. Pass "
                "params['_executor'] (GraphExecutor) or params['_executor_loop']."
            )

        run_id_value = params.get("run_id")
        run_id: str | None = (
            run_id_value if isinstance(run_id_value, str) else None
        )

        pub_endpoint_value = params.get("update_pub_endpoint")
        pub_endpoint: str | None = (
            pub_endpoint_value
            if isinstance(pub_endpoint_value, str)
            else None
        )

        batch_update_publisher = None
        if pub_endpoint is not None:
            from .utils.batch_update_publisher import BatchUpdatePublisher

            batch_update_publisher = BatchUpdatePublisher(
                pub_endpoint=pub_endpoint,
                run_id=run_id,
            )

        context: Data = {str(key): value for key, value in data.items()}

        coro = run_orchestrator_turn(
            context,
            stream_callback=stream_cb,
            batch_update_publisher=batch_update_publisher,
            run_id=run_id,
        )

        fut = asyncio.run_coroutine_threadsafe(coro, background_loop)

        timeout_value = params.get("timeout_s")
        timeout_s: float | None = (
            float(timeout_value)
            if isinstance(timeout_value, (int, float))
            else None
        )

        result = fut.result(timeout=timeout_s)


    except TimeoutError as exc:
        error_payload: Data = {
            "type": "error",
            "error": f"{type(exc).__name__}: {exc}",
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

    if result is None:
        return (
            {
                "status": None,
                "token": None,
                "message": None,
                "role": None,
                "error": {
                    "type": "error",
                    "error": "run_orchestrator_turn returned None",
                },
            },
            state,
        )

    if not isinstance(result, dict):
        return (
            {
                "status": None,
                "token": None,
                "message": None,
                "role": None,
                "error": {
                    "type": "error",
                    "error": f"run_orchestrator_turn returned non-dict result: {type(result).__name__}",
                },
            },
            state,
        )

    ports = {
        "status": result.get("status"),
        "token": result.get("token"),
        "message": result.get("message"),
        "role": result.get("role"),
        "error": result.get("error"),
    }

    if ports["message"] is None:
        return (
            {
                "status": ports["status"],
                "token": ports["token"],
                "message": None,
                "role": ports["role"],
                "error": {
                    "type": "error",
                    "error": f"Orchestrator returned message=None. Result keys={sorted(result.keys())}",
                },
            },
            state,
        )

    return (ports, state)


def register_agent_orchestrator() -> None:
    """Register the AgentOrchestrator unit type."""
    register_unit(
        UnitSpec(
            type_name="AgentOrchestrator",
            input_ports=AGENT_ORCHESTRATOR_INPUT_PORTS,
            output_ports=AGENT_ORCHESTRATOR_OUTPUT_PORTS,
            step_fn=_agent_orchestrator_step,
            environment_tags=["taskvector"],
            environment_tags_are_agnostic=False,
            description=(
                "Framework-agnostic agent turn orchestrator. Runs dispatcher → role workflow → "
                "follow-up chain → graph apply/validate → post-apply rounds. "
                "Emits token stream via _stream_callback; final outputs on all ports."
            ),
        )
    )


__all__ = [
    "AGENT_ORCHESTRATOR_INPUT_PORTS",
    "AGENT_ORCHESTRATOR_OUTPUT_PORTS",
    "register_agent_orchestrator",
]
