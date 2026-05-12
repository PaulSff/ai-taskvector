"""
RagDetectOrigin unit: detect workflow ``content_kind`` via :func:`rag.content_types.registry.classify_content`
(package ``discriminant.py`` files under ``rag/content_types/<id>/``).

Input ``graph``: JSON root as dict/list, a **``.json`` file path** (str) to classify (loads here only
for origin detection), a JSON **string**, a ProcessGraph, or a small bundle ``{"parsed": …, "file_path": …}``
(``parsed`` is the graph root; ``file_path`` is used as the discriminant path hint).

Optional param ``virtual_path`` (str) is used as the discriminant path when the input does not
imply a file path (default ``"."``).

Output 0 (``origin``): ``content_kind`` string, except ``node_red_catalogue`` is mapped to ``generic``.
Output 1 (``graph``): normalized JSON root used for classification (dict/list), or ``None``.
Output 2 (``error``): error message if detection failed, else empty string.
Output 3 (``context``): ``{"file_path", "parsed", "origin"}`` for Router / JsonParser envelopes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rag.content_types.registry import classify_content
from units.registry import UnitSpec, register_unit

RAG_DETECT_ORIGIN_INPUT_PORTS = [("graph", "Any"), ("path", "Any")]
RAG_DETECT_ORIGIN_OUTPUT_PORTS = [
    ("origin", "str"),
    ("graph", "Any"),
    ("error", "str"),
    ("context", "Any"),
]


def _bundle_parts(graph: Any) -> tuple[Any | None, str, bool]:
    """Indexer-style ``{parsed, file_path}``: returns (parsed value, file_path, True) if key ``parsed`` exists."""
    if not isinstance(graph, dict):
        return None, "", False
    if "parsed" not in graph:
        return None, "", False
    fp = str(graph.get("file_path") or "").strip()
    return graph.get("parsed"), fp, True


def _graph_to_data(graph: Any) -> tuple[dict | list | None, Path]:
    """Return (JSON root for classify, path hint for discriminants)."""
    if graph is None:
        return None, Path(".")
    b_parsed, b_fp, is_bundle = _bundle_parts(graph)
    if is_bundle:
        hint = Path(b_fp) if b_fp else Path(".")
        if isinstance(b_parsed, (dict, list)):
            return b_parsed, hint
        if b_parsed is None and b_fp:
            pth = Path(b_fp)
            if pth.suffix.lower() == ".json" and pth.is_file():
                try:
                    return json.loads(
                        pth.read_text(encoding="utf-8", errors="replace")
                    ), pth
                except (OSError, json.JSONDecodeError):
                    return None, pth
        if isinstance(b_parsed, str):
            s = b_parsed.strip()
            if s[:1] in "[{":
                try:
                    return json.loads(s), hint
                except json.JSONDecodeError:
                    return None, hint
        return None, hint
    if isinstance(graph, (dict, list)):
        return graph, Path(".")
    if isinstance(graph, str):
        s = graph.strip()
        pth = Path(s)
        if pth.suffix.lower() == ".json" and pth.is_file():
            try:
                return json.loads(
                    pth.read_text(encoding="utf-8", errors="replace")
                ), pth
            except (OSError, json.JSONDecodeError):
                return None, pth
        if s[:1] in "[{":
            try:
                return json.loads(s), Path(".")
            except json.JSONDecodeError:
                return None, Path(".")
        return None, Path(s)
    if hasattr(graph, "model_dump"):
        return graph.model_dump(), Path(".")
    if hasattr(graph, "dict"):
        return getattr(graph, "dict")(), Path(".")
    return None, Path(".")


def _rag_detect_origin_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Output 0: origin (content_kind); output 1: normalized graph; output 2: error; output 3: routing context."""
    g_in = inputs.get("graph") if inputs else None
    p_in = inputs.get("path") if inputs else None
    graph_in: Any = None
    if g_in is not None and not (isinstance(g_in, str) and not str(g_in).strip()):
        graph_in = g_in
    elif p_in is not None and not (isinstance(p_in, str) and not str(p_in).strip()):
        graph_in = p_in
    err_msg = ""
    vp = str(params.get("virtual_path") or "").strip()
    disc_path = Path(vp) if vp else Path(".")
    fp_out = ""
    try:
        data, hint = _graph_to_data(graph_in)
        if hint != Path("."):
            disc_path = hint
        if isinstance(graph_in, str) and graph_in.strip():
            fp_out = graph_in.strip()
        elif isinstance(graph_in, dict) and graph_in.get("file_path"):
            fp_out = str(graph_in.get("file_path") or "").strip()
        raw = classify_content(disc_path, data)
        origin = "generic" if raw == "node_red_catalogue" else raw
    except Exception as e:
        origin = "generic"
        err_msg = str(e)
        data = None
    ctx = {"file_path": fp_out, "parsed": data, "origin": origin}
    return (
        {
            "origin": origin,
            "graph": data,
            "error": err_msg,
            "context": ctx,
        },
        state,
    )


def register_rag_detect_origin() -> None:
    """Register the RagDetectOrigin unit type."""
    register_unit(
        UnitSpec(
            type_name="RagDetectOrigin",
            input_ports=RAG_DETECT_ORIGIN_INPUT_PORTS,
            output_ports=RAG_DETECT_ORIGIN_OUTPUT_PORTS,
            step_fn=_rag_detect_origin_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description="Detect content_kind; supports path / JSON string / bundle {parsed,file_path}. Outputs origin, graph, error, context.",
        )
    )


__all__ = [
    "register_rag_detect_origin",
    "RAG_DETECT_ORIGIN_INPUT_PORTS",
    "RAG_DETECT_ORIGIN_OUTPUT_PORTS",
]
