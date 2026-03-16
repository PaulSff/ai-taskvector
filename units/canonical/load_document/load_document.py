"""
LoadDocument unit: load a document via Docling and output body text, tables, and optional pictures.
Uses Docling API: export_to_text(labels=...) for body; document.tables + export_to_dataframe for tables;
when include_pictures=True, Docling pictures API (PdfPipelineOptions.generate_picture_images + iterate_items
+ PictureItem.get_image) for figures. Used in doc_to_text workflow for RAG indexing.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

LOAD_DOCUMENT_INPUT_PORTS = [("path", "str")]
LOAD_DOCUMENT_OUTPUT_PORTS = [("body_text", "str"), ("tables", "Any"), ("pictures", "Any"), ("error", "str")]


def _body_text_excluding_tables(document: Any) -> str:
    """Get body text via Docling API: export_to_text(labels=all except TABLE). Returns empty string if API unavailable."""
    try:
        from docling_core.types.doc.labels import DocItemLabel
        labels_include = set(DocItemLabel) - {DocItemLabel.TABLE}
        return (document.export_to_text(labels=labels_include) or "").strip()
    except Exception:
        return ""


def _make_converter(include_pictures: bool, path: Path):  # noqa: ANN201
    """Build DocumentConverter; for PDF + include_pictures use PdfPipelineOptions.generate_picture_images."""
    from docling.document_converter import DocumentConverter

    if not include_pictures or path.suffix.lower() != ".pdf":
        return DocumentConverter()
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True
        pipeline_options.images_scale = 1.5
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
    except Exception:
        return DocumentConverter()


def _extract_pictures(document: Any, conv_result: Any) -> list[dict[str, Any]]:
    """Extract pictures via Docling API: iterate_items + PictureItem.get_image, return list of {index, image_base64, caption}."""
    out: list[dict[str, Any]] = []
    try:
        from docling_core.types.doc import PictureItem
    except Exception:
        return out
    for idx, (element, _level) in enumerate(document.iterate_items() or [], start=1):
        if not isinstance(element, PictureItem):
            continue
        try:
            img = element.get_image(conv_result.document)
            if img is None:
                continue
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            caption = getattr(element, "caption", None) or getattr(element, "label", None)
            caption_str = str(caption).strip() if caption else None
            out.append({"index": idx, "image_base64": b64, "caption": caption_str})
        except Exception:
            continue
    return out


def _load_document_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run Docling on path; output body_text, tables, and optionally pictures (Docling pictures API)."""
    path_val = inputs.get("path") or params.get("path")
    include_pictures = bool(params.get("include_pictures") or inputs.get("include_pictures"))
    if not path_val or not isinstance(path_val, str):
        return ({"body_text": "", "tables": [], "pictures": [], "error": "LoadDocument: path missing"}, state)
    path = Path(path_val.strip()).expanduser().resolve()
    if not path.is_file():
        return ({"body_text": "", "tables": [], "pictures": [], "error": f"LoadDocument: file not found {path}"}, state)
    try:
        converter = _make_converter(include_pictures, path)
        result = converter.convert(str(path))
    except ImportError:
        return ({"body_text": "", "tables": [], "pictures": [], "error": "LoadDocument: docling not installed"}, state)
    except Exception as e:
        return ({"body_text": "", "tables": [], "pictures": [], "error": f"LoadDocument: {str(e)[:200]}"}, state)

    body_text = _body_text_excluding_tables(result.document)

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

    pictures: list[dict[str, Any]] = _extract_pictures(result.document, result) if include_pictures else []

    return ({"body_text": body_text, "tables": tables, "pictures": pictures, "error": ""}, state)


def register_load_document() -> None:
    register_unit(UnitSpec(
        type_name="LoadDocument",
        input_ports=LOAD_DOCUMENT_INPUT_PORTS,
        output_ports=LOAD_DOCUMENT_OUTPUT_PORTS,
        step_fn=_load_document_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Load a document (PDF, DOCX, XLSX, etc.) via Docling. Outputs body_text, tables, and optionally pictures (param include_pictures; Docling pictures API). For doc_to_text workflow.",
    ))


__all__ = ["register_load_document", "LOAD_DOCUMENT_INPUT_PORTS", "LOAD_DOCUMENT_OUTPUT_PORTS"]
