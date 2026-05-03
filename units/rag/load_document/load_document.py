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

# Suffixes handled by pandas rather than Docling.
# NOTE: Docling has no support for the legacy .xls binary format, so .xls
# must use the pandas path (requires xlrd). There is no Docling fallback.
_SPREADSHEET_SUFFIXES = frozenset({".xlsx", ".xls"})


# -----------------------------
# Helpers
# -----------------------------


def _col_letter(i: int) -> str:
    """Convert 0-based column index to Excel column letter (0→A, 25→Z, 26→AA …)."""
    result = []
    n = i + 1
    while n:
        n, rem = divmod(n - 1, 26)
        result.append(chr(ord("A") + rem))
    return "".join(reversed(result))


def _build_schema_from_columns(cols: list[Any]) -> list[dict[str, Any]]:
    """Return a normalised schema list from raw DataFrame column names.

    Pandas ``Unnamed: N`` headers and non-string / empty-string values are
    replaced by their Excel column letter (A, B, …).
    """
    norm_cols = [
        c
        if (isinstance(c, str) and c and not c.startswith("Unnamed:"))
        else _col_letter(i)
        for i, c in enumerate(cols)
    ]
    return [
        {"index": i, "letter": _col_letter(i), "name": col}
        for i, col in enumerate(norm_cols)
    ]


def _extract_pictures(document: Any, conv_result: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from docling_core.types.doc import PictureItem  # type: ignore[import-untyped]
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
            caption = getattr(element, "caption", None) or getattr(
                element, "label", None
            )
            caption_str = str(caption).strip() if caption else None
            out.append({"index": idx, "image_base64": b64, "caption": caption_str})
        except Exception:
            continue
    return out


def _body_text_excluding_tables(document: Any) -> str:
    try:
        from docling_core.types.doc.labels import (  # type: ignore[import-not-found]
            DocItemLabel,
        )

        labels_include = set(DocItemLabel) - {DocItemLabel.TABLE}
        return (document.export_to_text(labels=labels_include) or "").strip()
    except Exception:
        return ""


# -----------------------------
# Unit step
# -----------------------------


def _load_document_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
):
    path_val = inputs.get("path") or params.get("path")
    include_pictures = bool(
        params.get("include_pictures") or inputs.get("include_pictures")
    )

    if not path_val or not isinstance(path_val, str):
        return {
            "body_text": "",
            "tables": [],
            "pictures": [],
            "error": "path missing",
        }, state

    path = Path(path_val.strip()).expanduser().resolve()
    if not path.is_file():
        return {
            "body_text": "",
            "tables": [],
            "pictures": [],
            "error": f"file not found {path}",
        }, state

    tables_out: list[dict[str, Any]] = []
    # Declare early so the type checker sees them as always-bound
    body_text: str = ""
    pictures: list[dict[str, Any]] = []

    if path.suffix.lower() in _SPREADSHEET_SUFFIXES:
        # -------------------------------------------------------
        # Spreadsheet path: pandas for values, openpyxl for
        # formula strings (.xlsx only — .xls has no formula API).
        # -------------------------------------------------------
        try:
            import pandas as pd  # type: ignore[import-untyped]

            dfs = pd.read_excel(path, sheet_name=None)  # all sheets → OrderedDict

            # openpyxl formula pass — .xlsx only
            wb = None
            if path.suffix.lower() == ".xlsx":
                try:
                    import openpyxl  # type: ignore[import-untyped]

                    wb = openpyxl.load_workbook(path, data_only=False)
                except Exception:
                    wb = None

            for sheet_name, df in dfs.items():
                schema = _build_schema_from_columns(list(df.columns))
                norm_cols = [s["name"] for s in schema]
                df.columns = norm_cols  # apply normalised names in-place

                sheet = wb[sheet_name] if wb is not None else None

                out_rows: list[dict[str, Any]] = []
                for i in range(len(df)):
                    row_obj: dict[str, Any] = {}
                    for j, col in enumerate(norm_cols):
                        val = df.iat[i, j]
                        formula: str | None = None
                        # When data_only=False, cell.value IS the formula string
                        # for formula cells — no need for the private _value attr.
                        if sheet is not None:
                            cell = sheet.cell(row=i + 2, column=j + 1)
                            cv = cell.value
                            if isinstance(cv, str) and cv.startswith("="):
                                formula = cv
                        try:
                            is_na = bool(pd.isna(val))
                        except Exception:
                            is_na = val is None
                        row_obj[col] = {
                            "value": None if is_na else val,
                            "formula": formula,
                        }

                    if any(v["value"] is not None for v in row_obj.values()):
                        out_rows.append(row_obj)

                if out_rows:
                    tables_out.append({"rows": out_rows, "schema": schema})

            # body_text and pictures already initialised to "" / [] above

        except Exception as e:
            return {
                "body_text": "",
                "tables": [],
                "pictures": [],
                "error": f"spreadsheet parsing error: {e}",
            }, state

    else:
        # -------------------------------------------------------
        # Docling path: PDF, DOCX, HTML, Markdown, etc.
        # -------------------------------------------------------
        try:
            from docling.document_converter import (  # type: ignore[import-not-found]
                DocumentConverter,
            )

            converter = DocumentConverter()
            result = converter.convert(str(path))
            body_text = _body_text_excluding_tables(result.document)
            pictures = (
                _extract_pictures(result.document, result) if include_pictures else []
            )

            for table_item in getattr(result.document, "tables", []) or []:
                try:
                    df = table_item.export_to_dataframe(doc=result.document)
                    if df is None:
                        continue
                    schema = _build_schema_from_columns(list(df.columns))
                    norm_cols = [s["name"] for s in schema]
                    df.columns = norm_cols
                    wrapped = [
                        {
                            col: {"value": row.get(col), "formula": None}
                            for col in norm_cols
                        }
                        for row in df.to_dict(orient="records")
                    ]
                    tables_out.append({"rows": wrapped, "schema": schema})
                except Exception:
                    continue

        except Exception as e:
            return {
                "body_text": "",
                "tables": [],
                "pictures": [],
                "error": f"docling error: {e}",
            }, state

    return {
        "body_text": body_text,
        "tables": tables_out,
        "pictures": pictures,
        "error": "",
    }, state


# -----------------------------
# Registration
# -----------------------------


def register_load_document() -> None:
    register_unit(
        UnitSpec(
            type_name="LoadDocument",
            input_ports=LOAD_DOCUMENT_INPUT_PORTS,
            output_ports=LOAD_DOCUMENT_OUTPUT_PORTS,
            step_fn=_load_document_step,
            environment_tags=None,
            environment_tags_are_agnostic=True,
            description=(
                "Load a document (XLSX/XLS via pandas+openpyxl, PDF/DOCX/HTML/MD via Docling). "
                "Outputs body text, structured tables (with formula strings for .xlsx), "
                "and optionally pictures."
            ),
        )
    )


__all__ = [
    "register_load_document",
    "LOAD_DOCUMENT_INPUT_PORTS",
    "LOAD_DOCUMENT_OUTPUT_PORTS",
]
