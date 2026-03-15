"""
LoadDocument unit: load a document via Docling and output body text and tables.
Uses Docling API: export_to_text(labels=...) to get body without tables; document.tables + export_to_dataframe for tables.
Used in doc_to_text workflow for RAG indexing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

LOAD_DOCUMENT_INPUT_PORTS = [("path", "str")]
LOAD_DOCUMENT_OUTPUT_PORTS = [("body_text", "str"), ("tables", "Any"), ("error", "str")]


def _body_text_excluding_tables(document: Any) -> str:
    """Get body text via Docling API: export_to_text(labels=all except TABLE). Returns empty string if API unavailable."""
    try:
        from docling_core.types.doc.labels import DocItemLabel
        labels_include = set(DocItemLabel) - {DocItemLabel.TABLE}
        return (document.export_to_text(labels=labels_include) or "").strip()
    except Exception:
        return ""


def _load_document_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run Docling on path; output body_text (via export_to_text excluding TABLE) and tables (list of list-of-dicts)."""
    path_val = inputs.get("path") or params.get("path")
    if not path_val or not isinstance(path_val, str):
        return (
            {"body_text": "", "tables": [], "error": "LoadDocument: path missing"},
            state,
        )
    path = Path(path_val.strip()).expanduser().resolve()
    if not path.is_file():
        return (
            {"body_text": "", "tables": [], "error": f"LoadDocument: file not found {path}"},
            state,
        )
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        return (
            {"body_text": "", "tables": [], "error": "LoadDocument: docling not installed"},
            state,
        )
    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
    except Exception as e:
        return (
            {"body_text": "", "tables": [], "error": f"LoadDocument: {str(e)[:200]}"},
            state,
        )
    # Body: Docling API — export_to_text(labels=all except TABLE)
    body_text = _body_text_excluding_tables(result.document)

    # Tables: each as list of dicts for TablesToText
    from units.data_bi._common import df_to_table

    tables: list[list[dict[str, Any]]] = []
    for table_item in getattr(result.document, "tables", []) or []:
        try:
            df = table_item.export_to_dataframe(doc=result.document)
        except Exception:
            continue
        tbl = df_to_table(df)
        if tbl:
            tables.append(tbl)

    return ({"body_text": body_text, "tables": tables, "error": ""}, state)


def register_load_document() -> None:
    register_unit(UnitSpec(
        type_name="LoadDocument",
        input_ports=LOAD_DOCUMENT_INPUT_PORTS,
        output_ports=LOAD_DOCUMENT_OUTPUT_PORTS,
        step_fn=_load_document_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Load a document (PDF, DOCX, XLSX, etc.) via Docling. Outputs body_text (export_to_text excluding TABLE) and tables (list of tables for TablesToText). For doc_to_text workflow.",
    ))


__all__ = ["register_load_document", "LOAD_DOCUMENT_INPUT_PORTS", "LOAD_DOCUMENT_OUTPUT_PORTS"]
