"""
Chameleon unit: run a sequence of registered units in one step.

Each list entry is a dict with ``type`` (registered ``UnitSpec.type_name``), optional ``params``,
and optional ``inputs`` (port name → value), passed to that type's ``step_fn``. Useful for batching
several ``RunWorkflow``-style actions without duplicating nodes in the parent graph.

Params: "_needs_executor": true - optional. When the executor injects a background event loop via
params["_executor"] or params["_executor_loop"] / params["_background_loop"], Chameleon will schedule
async-capable child step coroutines on that loop using asyncio.run_coroutine_threadsafe. Child units
that are synchronous will keep working. Streaming via params["_stream_callback"] is supported.
"""

from __future__ import annotations

import asyncio
from typing import Any

from units.registry import UnitSpec, get_unit_spec, register_unit

CHAMELEON_INPUT_PORTS = [("actions", "Any"), ("data", "Any")]
CHAMELEON_OUTPUT_PORTS = [
    ("data", "Any"),
    ("last", "Any"),
    ("error", "str"),
]


def _normalize_actions(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        inner = raw.get("actions")
        if isinstance(inner, list):
            return inner
    return []


def _running_error_summary(results: list[dict[str, Any]]) -> str | None:
    errs = [str(e) for e in (r.get("error") for r in results) if e]
    if not errs:
        return None
    return "; ".join(errs[:5]) + ("; …" if len(errs) > 5 else "")


def _emit_chameleon_stream(
    stream_outputs: bool,
    stream_cb: Any,
    *,
    step_index: int,
    total: int,
    results: list[dict[str, Any]],
    last_outputs: dict[str, Any],
) -> None:
    if not stream_outputs or not callable(stream_cb):
        return
    from runtime.stream_ui_signals import chameleon_stream_chunk

    payload: dict[str, Any] = {
        "chameleon_stream": True,
        "done": total <= 0 or step_index >= total - 1,
        "index": step_index,
        "total": total,
        "step": results[-1] if results else None,
        "data": list(results),
        "last": dict(last_outputs),
        "error": _running_error_summary(results),
    }
    try:
        stream_cb(chameleon_stream_chunk(payload))
    except Exception:
        pass


def _get_background_loop_from_params(
    params: dict[str, Any],
) -> asyncio.AbstractEventLoop | None:
    """Resolve a background event loop from common injected params:
    prefer params['_executor']._loop, else params['_executor_loop'] or params['_background_loop'].
    """
    exec_obj = params.get("_executor")
    if exec_obj is not None:
        bg = getattr(exec_obj, "_loop", None)
        if isinstance(bg, asyncio.AbstractEventLoop):
            return bg
    bg = params.get("_executor_loop") or params.get("_background_loop")
    if isinstance(bg, asyncio.AbstractEventLoop):
        return bg
    return None


def _schedule_on_background_loop(
    coro: Any, background_loop: asyncio.AbstractEventLoop
) -> Any:
    """Schedule coroutine on background_loop and block until done using run_coroutine_threadsafe."""
    fut = asyncio.run_coroutine_threadsafe(coro, background_loop)
    return fut.result()


async def _maybe_run_child_async_step(
    spec: UnitSpec, params: dict[str, Any], inputs: dict[str, Any], loop_dt: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call spec.step_fn (sync or async). Normalize return to (outputs_dict, state_dict).

    Raises whatever the underlying step_fn raises.
    """
    step_fn = getattr(spec, "step_fn", None)
    if not callable(step_fn):
        raise RuntimeError("spec.step_fn is not callable")

    # Each child gets its own empty state dict (same semantics as original)
    child_state: dict[str, Any] = {}

    try:
        res = step_fn(params, inputs, child_state, loop_dt)
        if asyncio.iscoroutine(res):
            res = await res
    except Exception:
        raise

    # Normalize results: accept dict or (dict, dict)
    if isinstance(res, dict):
        return res, child_state
    if isinstance(res, (list, tuple)) and len(res) >= 1 and isinstance(res[0], dict):
        out = res[0]
        st = res[1] if len(res) > 1 and isinstance(res[1], dict) else child_state
        return out, st

    # Fallback: return empty outputs and the child_state
    return {}, child_state


def _chameleon_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = inputs.get("actions")
    if raw is None:
        raw = inputs.get("data")
    actions = _normalize_actions(raw)
    stream_outputs = bool(params.get("stream_outputs"))
    sc = params.get("_stream_callback")

    if not actions and raw is not None and not isinstance(raw, (list, dict)):
        return (
            {
                "data": [],
                "last": {},
                "error": "Chameleon: actions must be a list or dict with key 'actions'",
            },
            state,
        )

    loop_dt = float(params.get("loop_dt", dt if dt else 0.1) or 0.1)
    results: list[dict[str, Any]] = []
    last_outputs: dict[str, Any] = {}
    n = len(actions)

    if n == 0:
        _emit_chameleon_stream(
            stream_outputs,
            sc,
            step_index=-1,
            total=0,
            results=results,
            last_outputs=last_outputs,
        )
        return {"data": [], "last": {}, "error": None}, state

    background_loop = _get_background_loop_from_params(params)

    for step_index, item in enumerate(actions):
        if not isinstance(item, dict):
            results.append(
                {"type": None, "outputs": {}, "error": "item must be a dict"}
            )
            _emit_chameleon_stream(
                stream_outputs,
                sc,
                step_index=step_index,
                total=n,
                results=results,
                last_outputs=last_outputs,
            )
            continue

        utype = str(item.get("type") or "").strip()
        if not utype:
            results.append({"type": "", "outputs": {}, "error": "missing type"})
            _emit_chameleon_stream(
                stream_outputs,
                sc,
                step_index=step_index,
                total=n,
                results=results,
                last_outputs=last_outputs,
            )
            continue

        if utype == "Chameleon":
            results.append(
                {
                    "type": utype,
                    "outputs": {},
                    "error": "nested Chameleon is not allowed",
                }
            )
            _emit_chameleon_stream(
                stream_outputs,
                sc,
                step_index=step_index,
                total=n,
                results=results,
                last_outputs=last_outputs,
            )
            continue

        spec = get_unit_spec(utype)
        if spec is None:
            results.append(
                {"type": utype, "outputs": {}, "error": "unknown type or no step_fn"}
            )
            _emit_chameleon_stream(
                stream_outputs,
                sc,
                step_index=step_index,
                total=n,
                results=results,
                last_outputs=last_outputs,
            )
            continue

        if getattr(spec, "code_block_driven", False):
            results.append(
                {
                    "type": utype,
                    "outputs": {},
                    "error": "code_block_driven types are not supported here",
                },
            )
            _emit_chameleon_stream(
                stream_outputs,
                sc,
                step_index=step_index,
                total=n,
                results=results,
                last_outputs=last_outputs,
            )
            continue

        child_params = dict(item.get("params") or {})
        child_inputs = dict(item.get("inputs") or {})
        if callable(sc):
            child_params["_stream_callback"] = sc

        try:
            step_fn = getattr(spec, "step_fn", None)
            if not callable(step_fn):
                results.append(
                    {
                        "type": utype,
                        "outputs": {},
                        "error": "unknown type or no step_fn",
                    }
                )
                _emit_chameleon_stream(
                    stream_outputs,
                    sc,
                    step_index=step_index,
                    total=n,
                    results=results,
                    last_outputs=last_outputs,
                )
                continue

            if isinstance(background_loop, asyncio.AbstractEventLoop):

                async def _call_step(fn, cparams, cinputs, cdt):
                    child_state: dict[str, Any] = {}
                    res = fn(cparams, cinputs, child_state, cdt)
                    if asyncio.iscoroutine(res):
                        res = await res
                    if isinstance(res, dict):
                        return res
                    if (
                        isinstance(res, (list, tuple))
                        and len(res) >= 1
                        and isinstance(res[0], dict)
                    ):
                        return res[0]
                    return {}

                try:
                    outputs = _schedule_on_background_loop(
                        _call_step(step_fn, child_params, child_inputs, loop_dt),
                        background_loop,
                    )
                except Exception as e:
                    results.append(
                        {
                            "type": utype,
                            "outputs": {},
                            "error": f"{type(e).__name__}: {e}",
                        }
                    )
                    _emit_chameleon_stream(
                        stream_outputs,
                        sc,
                        step_index=step_index,
                        total=n,
                        results=results,
                        last_outputs=last_outputs,
                    )
                    continue
            else:
                child_state: dict[str, Any] = {}
                res = step_fn(child_params, child_inputs, child_state, loop_dt)
                if asyncio.iscoroutine(res):
                    try:
                        try:
                            running_loop = asyncio.get_running_loop()
                        except RuntimeError:
                            running_loop = None
                        if running_loop and running_loop.is_running():
                            outputs = asyncio.run_coroutine_threadsafe(
                                res, running_loop
                            ).result()
                        else:
                            outputs = asyncio.get_event_loop().run_until_complete(res)
                    except Exception as e:
                        results.append(
                            {
                                "type": utype,
                                "outputs": {},
                                "error": f"{type(e).__name__}: {e}",
                            }
                        )
                        _emit_chameleon_stream(
                            stream_outputs,
                            sc,
                            step_index=step_index,
                            total=n,
                            results=results,
                            last_outputs=last_outputs,
                        )
                        continue
                else:
                    outputs = res

                if (
                    isinstance(outputs, (list, tuple))
                    and len(outputs) >= 1
                    and isinstance(outputs[0], dict)
                ):
                    outputs = outputs[0]
                outputs = outputs if isinstance(outputs, dict) else {}

            results.append({"type": utype, "outputs": outputs, "error": None})
            last_outputs = outputs
        except Exception as e:
            results.append(
                {"type": utype, "outputs": {}, "error": f"{type(e).__name__}: {e}"}
            )

        _emit_chameleon_stream(
            stream_outputs,
            sc,
            step_index=step_index,
            total=n,
            results=results,
            last_outputs=last_outputs,
        )

    summary = _running_error_summary(results)
    return {"data": results, "last": last_outputs, "error": summary}, state


def register_chameleon() -> None:
    register_unit(
        UnitSpec(
            type_name="Chameleon",
            input_ports=CHAMELEON_INPUT_PORTS,
            output_ports=CHAMELEON_OUTPUT_PORTS,
            step_fn=_chameleon_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Run a list of {type, params?, inputs?} dicts through registered unit step_fns in order; "
                "outputs per step on data (list), last step outputs on last, concatenated step errors on error. "
                "Supports executor-injected background loop via params['_executor'] or params['_executor_loop'] when _needs_executor is set."
            ),
        )
    )


__all__ = ["register_chameleon", "CHAMELEON_INPUT_PORTS", "CHAMELEON_OUTPUT_PORTS"]
