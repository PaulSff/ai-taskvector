"""
RagBuildIndexDocument unit: one RAG row (searchable ``text`` + Chroma ``metadata``) from extracted fields.

Params:
  - ``text_template`` (str): ``str.format`` with ``extracted`` keys (missing → "").
  - ``metadata_keys`` (list[str]): copy keys from ``extracted`` into metadata.
  - ``static_metadata`` (dict): merged into metadata after extracted keys.
"""

from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit

RAG_BUILD_INDEX_DOCUMENT_INPUT_PORTS = [
    ("extracted", "Any"),
    ("file_path", "str"),
    ("chunk_texts", "Any"),
    ("chunk_metadatas", "Any"),
]
RAG_BUILD_INDEX_DOCUMENT_OUTPUT_PORTS = [
    ("text", "str"),
    ("metadata", "Any"),
    ("document", "Any"),
    ("error", "str"),
    ("chunk_texts", "Any"),
    ("chunk_metadatas", "Any"),
]


def _as_dict(val: Any) -> dict[str, Any]:
    return dict(val) if isinstance(val, dict) else {}


def _file_path_str(val: Any) -> str:
    """Accept a bare path string or a RagExtract-style ``{"file_path": "..."}`` dict."""
    if isinstance(val, dict):
        v = val.get("file_path")
        if v is None and len(val) == 1:
            v = next(iter(val.values()))
        return str(v or "").strip()
    return str(val or "").strip()


def _rag_build_index_document_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    extracted = _as_dict(inputs.get("extracted"))
    fp = _file_path_str(inputs.get("file_path"))
    if not fp:
        fp = _file_path_str(extracted)
    err = ""
    tpl = str(params.get("text_template") or "{text}").strip() or "{text}"

    class _Fmt(dict):
        def __missing__(self, key: str) -> str:  # type: ignore[override]
            return ""

    try:
        text = tpl.format_map(
            _Fmt(
                **{str(k): ("" if v is None else str(v)) for k, v in extracted.items()}
            ),
        )
    except (ValueError, KeyError, IndexError) as e:
        text = tpl
        err = str(e)

    meta: dict[str, Any] = {}
    mk = params.get("metadata_keys")
    if isinstance(mk, list):
        for k in mk:
            ks = str(k).strip()
            if ks and ks in extracted:
                meta[ks] = extracted[ks]
    sm = params.get("static_metadata")
    if isinstance(sm, dict):
        meta.update(sm)
    if fp:
        meta.setdefault("file_path", fp)

    doc = {"text": text, "metadata": meta}
    ct = inputs.get("chunk_texts")
    cm = inputs.get("chunk_metadatas")
    out_ct = ct if isinstance(ct, list) else []
    out_cm = cm if isinstance(cm, list) else []
    return (
        {
            "text": text,
            "metadata": meta,
            "document": doc,
            "error": err,
            "chunk_texts": out_ct,
            "chunk_metadatas": out_cm,
        },
        state,
    )


def register_rag_build_index_document() -> None:
    register_unit(
        UnitSpec(
            type_name="RagBuildIndexDocument",
            input_ports=RAG_BUILD_INDEX_DOCUMENT_INPUT_PORTS,
            output_ports=RAG_BUILD_INDEX_DOCUMENT_OUTPUT_PORTS,
            step_fn=_rag_build_index_document_step,
            environment_tags_are_agnostic=True,
            description=(
                "Build one RAG document from extracted + file_path; optional chunk_texts / chunk_metadatas "
                "are echoed for a linear flat→RBD→Embedder→Chroma chain."
            ),
        )
    )


__all__ = [
    "register_rag_build_index_document",
    "RAG_BUILD_INDEX_DOCUMENT_INPUT_PORTS",
    "RAG_BUILD_INDEX_DOCUMENT_OUTPUT_PORTS",
]
