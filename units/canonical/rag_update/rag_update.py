"""
RagUpdate unit: run RAG index incremental update (units_dir + mydata_dir) via rag.context_updater.

Params: rag_index_data_dir (str), units_dir (str), mydata_dir (str), embedding_model (str, optional).
No input ports. Output: data (dict) with keys ok, need_index, units_count, mydata_count, error, message, details.
Enables workflows (e.g. rag_update.json) to trigger index updates without direct context_updater calls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

RAG_UPDATE_INPUT_PORTS: list[tuple[str, str]] = []
RAG_UPDATE_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]


def _rag_update_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call rag.context_updater.run_update with params; return result dict on output 'data'."""
    from rag.context_updater import run_update

    rag_index_data_dir = params.get("rag_index_data_dir") or ""
    units_dir = params.get("units_dir") or ""
    mydata_dir = params.get("mydata_dir") or ""
    embedding_model = params.get("embedding_model")
    if not isinstance(rag_index_data_dir, str):
        rag_index_data_dir = str(rag_index_data_dir)
    if not isinstance(units_dir, str):
        units_dir = str(units_dir)
    if not isinstance(mydata_dir, str):
        mydata_dir = str(mydata_dir)
    rag_index_data_dir = Path(rag_index_data_dir.strip()).expanduser().resolve()
    units_dir = Path(units_dir.strip()).expanduser().resolve()
    mydata_dir = Path(mydata_dir.strip()).expanduser().resolve()
    if embedding_model is not None and not isinstance(embedding_model, str):
        embedding_model = str(embedding_model)
    elif embedding_model is not None:
        embedding_model = (embedding_model or "").strip() or None

    try:
        result = run_update(
            rag_index_data_dir,
            units_dir,
            mydata_dir,
            embedding_model=embedding_model,
        )
        # Index content changed (or may have changed): drop warm search handles.
        try:
            from units.canonical.rag_search.rag_search import clear_rag_index_cache

            clear_rag_index_cache()
        except Exception:
            pass
    except Exception as e:
        err_msg = str(e)[:200]
        result = {
            "ok": False,
            "need_index": True,
            "units_count": 0,
            "mydata_count": 0,
            "error": err_msg,
            "message": err_msg,
            "details": "",
        }
        return ({"data": result, "error": err_msg}, state)
    return ({"data": result, "error": None}, state)


def register_rag_update() -> None:
    """Register the RagUpdate unit type."""
    register_unit(UnitSpec(
        type_name="RagUpdate",
        input_ports=RAG_UPDATE_INPUT_PORTS,
        output_ports=RAG_UPDATE_OUTPUT_PORTS,
        step_fn=_rag_update_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="RAG index update: run incremental update from units_dir and mydata_dir. Params: rag_index_data_dir, units_dir, mydata_dir, embedding_model. Output: data (result dict).",
    ))


__all__ = ["register_rag_update", "RAG_UPDATE_INPUT_PORTS", "RAG_UPDATE_OUTPUT_PORTS"]
