from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

LOAD_DOCUMENT_INPUT_PORTS = [("path", "str")]
LOAD_DOCUMENT_OUTPUT_PORTS = [
    ("body_text", "str"),
    ("tables", "Any"),
    ("pictures", "Any"),
    ("error", "str"),
]


def _col_letter(i: int) -> str:
    result = []
    n = i + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result.append(chr(ord("A") + rem))
    return "".join(reversed(result))


def _build_schema_from_columns(cols: list[Any]) -> list[dict[str, Any]]:
    norm_cols = [
        c if (isinstance(c, str) and not c.startswith("Unnamed:")) and c is not None else _col_letter(i)
        for i, c in enumerate(cols)
    ]
    schema = [
        {"index": i, "letter": _col_letter(i), "name": col}
        for i, col in enumerate(norm_cols)
    ]
    return schema


def _extract_pictures(document: Any, conv_result: Any) -> list[dict[str, Any]]:
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


def _body_text_excluding_tables(document: Any) -> str:
    try:
        from docling_core.types.doc.labels import DocItemLabel
        labels_include = set(DocItemLabel) - {DocItemLabel.TABLE}
        return (document.export_to_text(labels=labels_include) or "").strip()
    except Exception:
        return ""


def _load_document_step(params: dict[str, Any], inputs: dict[str, Any], state: dict[str, Any], dt: float):
    path_val = inputs.get("path") or params.get("path")
    include_pictures = bool(params.get("include_pictures") or inputs.get("include_pictures"))

    if not path_val or not isinstance(path_val, str):
        return {"body_text": "", "tables": [], "pictures": [], "error": "path missing"}, state

    path = Path(path_val.strip()).expanduser().resolve()
    if not path.is_file():
        return {"body_text": "", "tables": [], "pictures": [], "error": f"file not found {path}"}, state

    tables_out: list[dict[str, Any]] = []

    # XLSX handling with pandas + openpyxl
    if path.suffix.lower() == ".xlsx":
        try:
            import pandas as pd
            import openpyxl

            dfs = pd.read_excel(path, sheet_name=None)  # all sheets
            wb = openpyxl.load_workbook(path, data_only=False)

            for sheet_name, df in dfs.items():
                sheet = wb[sheet_name]
                cols = list(df.columns)

                norm_cols = [
                    c if (isinstance(c, str) and not c.startswith("Unnamed:")) and c is not None
                    else _col_letter(i)
                    for i, c in enumerate(cols)
                ]

                df.columns = norm_cols  # normalize columns

                schema = [
                    {"index": i, "letter": _col_letter(i), "name": col}
                    for i, col in enumerate(norm_cols)
                ]

                out_rows = []
                for i in range(len(df)):
                    row_obj = {}
                    for j, col in enumerate(norm_cols):
                        val = df.iat[i, j]
                        cell = sheet.cell(row=i + 2, column=j + 1)
                        formula = None
                        if isinstance(cell.value, str) and cell.value.startswith("="):
                            formula = cell.value
                        elif hasattr(cell, "_value") and isinstance(cell._value, str) and cell._value.startswith("="):
                            formula = cell._value

                        row_obj[col] = {
                            "value": None if pd.isna(val) else val,
                            "formula": formula
                        }

                    if any(v["value"] is not None for v in row_obj.values()):
                        out_rows.append(row_obj)

                # Append the sheet's table to tables_out
                if out_rows:
                    tables_out.append({"rows": out_rows, "schema": schema})

            body_text = ""  # XLSX has no body text
            pictures = []  # optional: Excel pictures extraction can be added if needed

        except Exception as e:
            return {"body_text": "", "tables": [], "pictures": [], "error": f"xlsx parsing error: {e}"}, state

    else:
        # fallback to Docling for PDF, DOCX, etc.
        try:
            from docling.document_converter import DocumentConverter
            converter = DocumentConverter()
            result = converter.convert(str(path))
            body_text = _body_text_excluding_tables(result.document)
            pictures = _extract_pictures(result.document, result) if include_pictures else []
            for table_item in getattr(result.document, "tables", []) or []:
                try:
                    df = table_item.export_to_dataframe(doc=result.document)
                    if df is None:
                        continue
                    cols = list(df.columns)
                    schema = _build_schema_from_columns(cols)
                    wrapped = [{k: {"value": v, "formula": None} for k, v in r.items()} for r in df.to_dict(orient="records")]
                    tables_out.append({"rows": wrapped, "schema": schema})
                except Exception:
                    continue
        except Exception as e:
            return {"body_text": "", "tables": [], "pictures": [], "error": f"docling error: {e}"}, state

    return {"body_text": body_text, "tables": tables_out, "pictures": pictures, "error": ""}, state


def register_load_document() -> None:
    register_unit(UnitSpec(
        type_name="LoadDocument",
        input_ports=LOAD_DOCUMENT_INPUT_PORTS,
        output_ports=LOAD_DOCUMENT_OUTPUT_PORTS,
        step_fn=_load_document_step,
        environment_tags=None,
        environment_tags_are_agnostic=True,
        description="Load a document (XLSX, PDF, DOCX, etc.) preserving Excel formulas, tables, and optionally pictures.",
    ))


__all__ = ["register_load_document", "LOAD_DOCUMENT_INPUT_PORTS", "LOAD_DOCUMENT_OUTPUT_PORTS"]