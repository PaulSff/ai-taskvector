"""
Run a content-type extraction workflow for JSON → RAG (text, metadata) pairs.

Workflow contract (``rag/workflows/json_kind_index_extract.json``):
  - ``inject_path`` (resolved file path) → ``rag_detect``
    (:class:`~units.rag.rag_detect_origin.RagDetectOrigin`) loads JSON from disk for ``.json`` paths
    when the graph input is unwired → ``JsonParser`` (RagDetectOrigin ``context``) →
    ``RagJsonIndexExtract`` with ``kind_in`` from ``origin``.
  - Read ``chunks`` from whichever branch unit produced ``chunks`` in executor outputs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _pairs_from_extract_output(raw: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(raw, list):
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        meta = item.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        if text is None:
            continue
        st = str(text).strip()
        if not st:
            continue
        out.append((st, meta))
    return out


def run_json_index_extraction_workflow(
    workflow_path: Path | str,
    *,
    path: Path,
    data: dict | list,
    source: str,
    json_kind: str,
    execution_timeout_s: float = 120.0,
) -> list[tuple[str, dict[str, Any]]] | None:
    """
    Execute the registry extraction workflow; return pairs or ``None`` on hard failure.

    The graph reads JSON from ``path`` on disk; ``data`` is unused by the workflow but kept for
    callers that already pass parsed content alongside ``path``.

    On success with an empty ``chunks`` list, returns ``[]``. The indexer does not apply any fallback.
    """
    from runtime.run import run_workflow

    wf = Path(workflow_path).resolve()
    if not wf.is_file():
        return None

    initial_inputs = {
        "inject_path": {"data": str(path.resolve())},
    }
    try:
        outputs = run_workflow(
            wf,
            initial_inputs=initial_inputs,
            unit_param_overrides=None,
            execution_timeout_s=execution_timeout_s,
        )
    except Exception:
        return None

    chunks = None
    for ports in (outputs or {}).values():
        if isinstance(ports, dict) and ports.get("chunks") is not None:
            chunks = ports.get("chunks")
            break
    return _pairs_from_extract_output(chunks)
