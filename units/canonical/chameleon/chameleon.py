"""
Chameleon unit: run a sequence of registered units in one step.

Each list entry is a dict with ``type`` (registered ``UnitSpec.type_name``), optional ``params``,
and optional ``inputs`` (port name → value), passed to that type's ``step_fn``. Useful for batching
several ``RunWorkflow``-style actions without duplicating nodes in the parent graph.
"""
from __future__ import annotations

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
        _emit_chameleon_stream(stream_outputs, sc, step_index=-1, total=0, results=results, last_outputs=last_outputs)
        return {"data": [], "last": {}, "error": None}, state

    for step_index, item in enumerate(actions):
        if not isinstance(item, dict):
            results.append({"type": None, "outputs": {}, "error": "item must be a dict"})
            _emit_chameleon_stream(stream_outputs, sc, step_index=step_index, total=n, results=results, last_outputs=last_outputs)
            continue
        utype = str(item.get("type") or "").strip()
        if not utype:
            results.append({"type": "", "outputs": {}, "error": "missing type"})
            _emit_chameleon_stream(stream_outputs, sc, step_index=step_index, total=n, results=results, last_outputs=last_outputs)
            continue
        if utype == "Chameleon":
            results.append({"type": utype, "outputs": {}, "error": "nested Chameleon is not allowed"})
            _emit_chameleon_stream(stream_outputs, sc, step_index=step_index, total=n, results=results, last_outputs=last_outputs)
            continue
        spec = get_unit_spec(utype)
        if spec is None or spec.step_fn is None:
            results.append({"type": utype, "outputs": {}, "error": "unknown type or no step_fn"})
            _emit_chameleon_stream(stream_outputs, sc, step_index=step_index, total=n, results=results, last_outputs=last_outputs)
            continue
        if getattr(spec, "code_block_driven", False):
            results.append(
                {"type": utype, "outputs": {}, "error": "code_block_driven types are not supported here"},
            )
            _emit_chameleon_stream(stream_outputs, sc, step_index=step_index, total=n, results=results, last_outputs=last_outputs)
            continue

        child_params = dict(item.get("params") or {})
        child_inputs = dict(item.get("inputs") or {})
        # Same hook as GraphExecutor: optional streaming; units that do not use it ignore the key.
        if callable(sc):
            child_params["_stream_callback"] = sc
        child_state: dict[str, Any] = {}
        try:
            outputs, _new = spec.step_fn(child_params, child_inputs, child_state, loop_dt)
            out = outputs if isinstance(outputs, dict) else {}
            results.append({"type": utype, "outputs": out, "error": None})
            last_outputs = out
        except Exception as e:
            results.append({"type": utype, "outputs": {}, "error": f"{type(e).__name__}: {e}"})
        _emit_chameleon_stream(stream_outputs, sc, step_index=step_index, total=n, results=results, last_outputs=last_outputs)

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
                "outputs per step on data (list), last step outputs on last, concatenated step errors on error."
            ),
        )
    )


__all__ = ["register_chameleon", "CHAMELEON_INPUT_PORTS", "CHAMELEON_OUTPUT_PORTS"]
