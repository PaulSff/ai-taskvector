"""
list_unit: scaffold a new unit under units/<environment>/, register it in UNIT_REGISTRY.

Input ``data`` must be a dict:
  {action: list_unit, environment, new_unit_type, code_block_id, readme_md}
Implementation text is read from ``graph.code_blocks`` entry matching ``code_block_id`` (``source`` field).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.canonical._scaffold_env import repo_root_containing_units, run_list_unit
from units.registry import UnitSpec, register_unit

LIST_UNIT_INPUT_PORTS = [("data", "Any"), ("graph", "Any")]
LIST_UNIT_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _graph_to_dict(graph: Any) -> dict[str, Any]:
    if graph is None:
        return {}
    if isinstance(graph, dict):
        return graph
    md = getattr(graph, "model_dump", None)
    if callable(md):
        try:
            return md(by_alias=True)
        except TypeError:
            return md()
    return {}


def _lookup_code_block_source(graph_dict: dict[str, Any], code_block_id: str) -> str | None:
    bid = str(code_block_id).strip()
    if not bid:
        return None
    for b in graph_dict.get("code_blocks") or []:
        if isinstance(b, dict):
            if str(b.get("id", "")).strip() != bid:
                continue
            return str(b.get("source", "") if b.get("source") is not None else "")
        oid = getattr(b, "id", None)
        if oid is not None and str(oid).strip() == bid:
            src = getattr(b, "source", None)
            return str(src if src is not None else "")
    return None


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _ = params
    spec = inputs.get("data")
    if not isinstance(spec, dict):
        return (
            {"data": None, "error": "input data must be a dict: {action, environment, new_unit_type, code_block_id, readme_md}"},
            state,
        )
    if spec.get("action") != "list_unit":
        return ({"data": None, "error": 'input data["action"] must be "list_unit"'}, state)

    env = spec.get("environment")
    ntype = spec.get("new_unit_type")
    cb_id = spec.get("code_block_id")
    readme = spec.get("readme_md", "")
    if env is None:
        return ({"data": None, "error": 'input data["environment"] is required (env tag)'}, state)
    if not ntype:
        return ({"data": None, "error": 'input data["new_unit_type"] is required'}, state)
    if not cb_id:
        return ({"data": None, "error": 'input data["code_block_id"] is required'}, state)

    graph_dict = _graph_to_dict(inputs.get("graph"))
    if not graph_dict.get("code_blocks"):
        return ({"data": None, "error": "input graph has no code_blocks"}, state)

    module_src = _lookup_code_block_source(graph_dict, str(cb_id))
    if module_src is None:
        return (
            {"data": None, "error": f'no code_block with id {cb_id!r} on graph'},
            state,
        )

    root = repo_root_containing_units(Path(__file__))
    result = run_list_unit(
        root,
        str(env),
        str(ntype),
        str(readme) if readme is not None else "",
        module_source=module_src,
    )
    if not result.get("ok"):
        err_parts: list[str] = []
        if result.get("register_error"):
            err_parts.append(str(result["register_error"]))
        if result.get("error"):
            err_parts.append(str(result["error"]))
        if result.get("patch_error"):
            err_parts.append(f"patch: {result['patch_error']}")
        err = "; ".join(err_parts) if err_parts else "list_unit failed"
        return ({"data": result, "error": err}, state)
    return ({"data": result, "error": None}, state)


def register_list_unit() -> None:
    register_unit(UnitSpec(
        type_name="list_unit",
        input_ports=LIST_UNIT_INPUT_PORTS,
        output_ports=LIST_UNIT_OUTPUT_PORTS,
        step_fn=_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description=(
            "Scaffold units/<env>/<snake>/ from graph code_block.source. "
            "Inputs: data = {action: list_unit, environment, new_unit_type, code_block_id, readme_md}, graph = process graph."
        ),
    ))


__all__ = ["register_list_unit", "LIST_UNIT_INPUT_PORTS", "LIST_UNIT_OUTPUT_PORTS"]
