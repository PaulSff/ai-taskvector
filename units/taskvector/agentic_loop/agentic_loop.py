from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future
from typing import Any, Literal

from agents.chat.telegram_gateway.telegram_worker import (
    is_telegram_poller_running,
    start_telegram_poller,
    stop_telegram_poller_async,
)
from services.logging import setup_colored_logging
from units.registry import UnitSpec, register_unit

DEAFAULT_UPDATE_INTERVAL_S = 60

AGENTIC_LOOP_INPUT_PORTS = [
    ("start", "Any"),   # { "action": "taskvector_daemon_start", "update_interval_s": 60}
    ("stop", "Any"),    # { "action": "taskvector_daemon_stop"}
    ("switch", "Any"),  # { "action": "taskvector_daemon_switch", "update_interval_s": 60}
]

AGENTIC_LOOP_OUTPUT_PORTS = [
    ("data", "Any"),
    ("error", "Any"),
]

Status = Literal["running", "stopped"]

# In-process counters (per unit worker process).
_LOOP_STATE: dict[str, Any] = {
    "running": False,
    "started_at": None,     # ISO str
    "total_running": 0,
    "total_turns": 0,
    "total_erors": 0,
    "total_tokens": 0,
    "next_update_in_s": 0,
    "stop_requested": False,
}

logger = setup_colored_logging(logging.DEBUG)


def _get_background_loop(params: dict[str, Any]) -> asyncio.AbstractEventLoop:
    """
    Mirror the AgentOrchestrator pattern:
    - prefer params['_executor'] exposing '_loop'
    - otherwise use params['_executor_loop'] / params['_background_loop']
    """
    exec_obj = params.get("_executor")
    background_loop = getattr(exec_obj, "_loop", None) if exec_obj is not None else None

    if background_loop is None:
        background_loop = params.get("_executor_loop") or params.get("_background_loop")

    if not isinstance(background_loop, asyncio.AbstractEventLoop):
        raise TypeError(
            "AgenticLoop: background event loop not provided. Pass params['_executor'] (GraphExecutor) or params['_executor_loop']."
        )

    return background_loop


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _fire_and_forget(coro, background_loop, timeout_s: Any = None) -> None:
    fut: Future[Any] = asyncio.run_coroutine_threadsafe(coro, background_loop)

    def _done_callback(f: Future[Any]) -> None:
        try:
            _ = f.result(timeout=timeout_s) if timeout_s is not None else f.result()
        except Exception:
            logger.exception("Background coroutine failed")

    fut.add_done_callback(_done_callback)


def _agenticloop_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    global _LOOP_STATE

    # ---- Make framework state the source of truth ----
    if state is None:
        state = {}

    # Ensure required keys exist
    state.setdefault("running", False)
    state.setdefault("started_at", None)  # ISO str
    state.setdefault("total_running", 0)
    state.setdefault("total_turns", 0)
    state.setdefault("total_erors", 0)
    state.setdefault("total_tokens", 0)
    state.setdefault("next_update_in_s", 0)
    state.setdefault("stop_requested", False)

    try:
        start_payload = inputs.get("start")
        stop_payload = inputs.get("stop")
        switch_payload = inputs.get("switch")

        # Enforce only one control input at a time.
        control_inputs = [p is not None for p in (start_payload, stop_payload, switch_payload)]
        if sum(control_inputs) > 1:
            return (
                {"data": None, "error": {"type": "error", "error": "Provide only one of start/stop/switch"}},
                state,
            )

        if start_payload is not None and not isinstance(start_payload, dict):
            return (
                {"data": None, "error": {"type": "error", "error": "start must be an object"}},
                state,
            )
        if stop_payload is not None and not isinstance(stop_payload, dict):
            return (
                {"data": None, "error": {"type": "error", "error": "stop must be an object"}},
                state,
            )
        if switch_payload is not None and not isinstance(switch_payload, dict):
            return (
                {"data": None, "error": {"type": "error", "error": "switch must be an object"}},
                state,
            )

        background_loop = _get_background_loop(params)

        params_update_interval_s = _safe_int(
            params.get("update_interval_s"), default=DEAFAULT_UPDATE_INTERVAL_S
        )

        # ---- STOP ----
        if stop_payload is not None:
            action = stop_payload.get("action")
            if action != "taskvector_daemon_stop":
                return (
                    {"data": None, "error": {"type": "error", "error": f"Invalid stop.action={action!r}"}},
                    state,
                )

            coro = stop_telegram_poller_async()
            timeout_s = params.get("timeout_s")
            _fire_and_forget(coro, background_loop, timeout_s=timeout_s)

            state["running"] = False
            state["stop_requested"] = False

            return (
                {
                    "data": {
                        "status": "stopped",
                        "stats": {
                            "started_at": state.get("started_at"),
                            "total_running": str(state.get("total_running", 0)),
                            "total_turns": str(state.get("total_turns", 0)),
                            "total_erors": str(state.get("total_erors", 0)),
                            "total_tokens": str(state.get("total_tokens", 0)),
                        },
                    },
                    "error": None,
                },
                state,
            )

        # ---- SWITCH ----
        if switch_payload is not None:
            action = switch_payload.get("action")
            if action != "taskvector_daemon_switch":
                return (
                    {"data": None, "error": {"type": "error", "error": f"Invalid switch.action={action!r}"}},
                    state,
                )

            # Decide based on the daemon's real state (not state dict)
            daemon_running = is_telegram_poller_running()
            # optional but recommended:
            logger.info("SWITCH: daemon_running=%s", daemon_running)

            # Update interval for next_update_in_s computation (must be int, not None)
            switch_update_interval_s = _safe_int(
                switch_payload.get("update_interval_s") if switch_payload is not None else None,
                default=params_update_interval_s,
            )

            if daemon_running:
                # currently running => stop
                coro = stop_telegram_poller_async()
                timeout_s = params.get("timeout_s")
                _fire_and_forget(coro, background_loop, timeout_s=timeout_s)

                state["running"] = False
                state["stop_requested"] = False

                return (
                    {
                        "data": {
                            "status": "stopped",
                            "stats": {
                                "started_at": state.get("started_at"),
                                "total_running": str(state.get("total_running", 0)),
                                "total_turns": str(state.get("total_turns", 0)),
                                "total_erors": str(state.get("total_erors", 0)),
                                "total_tokens": str(state.get("total_tokens", 0)),
                            },
                        },
                        "error": None,
                    },
                    state,
                )

            # currently stopped => start
            coro = start_telegram_poller()
            timeout_s = params.get("timeout_s")
            _fire_and_forget(coro, background_loop, timeout_s=timeout_s)

            # Optimistically update local state; the real service state is checked via is_telegram_poller_running() next time.
            state["running"] = True
            state["total_running"] = int(state.get("total_running", 0)) + 1
            if not state.get("started_at"):
                state["started_at"] = "..."
            return (
                {
                    "data": {
                        "status": "running",
                        "stats": {
                            "started_at": state.get("started_at"),
                            "total_running": str(state.get("total_running", 0)),
                            "total_turns": str(state.get("total_turns", 0)),
                            "total_erors": str(state.get("total_erors", 0)),
                            "total_tokens": str(state.get("total_tokens", 0)),
                            "next_update_in_s": int(state.get("next_update_in_s", switch_update_interval_s)),

                        },
                    },
                    "error": None,
                },
                state,
            )

        # ---- START ----
        if start_payload is not None:
            action = start_payload.get("action")
            if action != "taskvector_daemon_start":
                return (
                    {"data": None, "error": {"type": "error", "error": f"Invalid start.action={action!r}"}},
                    state,
                )

            payload_update_interval_s = start_payload.get("update_interval_s", None)
            update_interval_s = (
                _safe_int(payload_update_interval_s, default=params_update_interval_s)
                if payload_update_interval_s is not None
                else params_update_interval_s
            )
            state["next_update_in_s"] = update_interval_s

            coro = start_telegram_poller()
            timeout_s = params.get("timeout_s")
            _fire_and_forget(coro, background_loop, timeout_s=timeout_s)

            state["running"] = True
            state["total_running"] = int(state.get("total_running", 0)) + 1
            if not state.get("started_at"):
                state["started_at"] = "..."

            return (
                {
                    "data": {
                        "status": "running",
                        "stats": {
                            "started_at": state.get("started_at"),
                            "total_running": str(state.get("total_running", 0)),
                            "total_turns": str(state.get("total_turns", 0)),
                            "total_erors": str(state.get("total_erors", 0)),
                            "total_tokens": str(state.get("total_tokens", 0)),
                            "next_update_in_s": int(state.get("next_update_in_s", update_interval_s)),
                        },
                    },
                    "error": None,
                },
                state,
            )

        # <-- Missing return was here (no start/stop/switch provided)
        return (
            {
                "data": {
                    "status": "idle",
                    "stats": {
                        "started_at": state.get("started_at"),
                        "total_running": str(state.get("total_running", 0)),
                        "total_turns": str(state.get("total_turns", 0)),
                        "total_erors": str(state.get("total_erors", 0)),
                        "total_tokens": str(state.get("total_tokens", 0)),
                        "next_update_in_s": int(state.get("next_update_in_s", 0)),
                    },
                },
                "error": None,
            },
            state,
        )

    except (TypeError, ValueError, RuntimeError, TimeoutError) as e:
        state["total_erors"] = int(state.get("total_erors", 0)) + 1
        return (
            {"data": None, "error": {"type": "error", "error": f"{type(e).__name__}: {e}"}},
            state,
        )


def register_agentic_loop() -> None:
    register_unit(
        UnitSpec(
            type_name="AgenticLoop",
            input_ports=AGENTIC_LOOP_INPUT_PORTS,
            output_ports=AGENTIC_LOOP_OUTPUT_PORTS,
            step_fn=_agenticloop_step,
            environment_tags=["taskvector"],
            environment_tags_are_agnostic=False,
            description=(
                "Start/stop the worker daemon. "
                "Start input: {action: taskvector_daemon_start, update_interval_s: 60}. "
                "Stop input: {action: taskvector_daemon_stop}. "
                "Switch input: {action: taskvector_daemon_switch, update_interval_s?: 60}. "
                "Switch toggles based on current state; start/update_interval_s may come from either params['update_interval_s'] or payload."
                "Uses executor background loop awaiting pattern via run_coroutine_threadsafe."
            ),
        )
    )


__all__ = ["AGENTIC_LOOP_INPUT_PORTS", "AGENTIC_LOOP_OUTPUT_PORTS", "register_agentic_loop"]
