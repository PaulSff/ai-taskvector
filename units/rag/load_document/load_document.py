from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

from units.registry import UnitSpec, register_unit

LOAD_DOCUMENT_INPUT_PORTS = [("path", "str")]
LOAD_DOCUMENT_OUTPUT_PORTS = [
    # ─── Text exports ────────────────────────────────────────────────────────────
    ("body_text", "str"),  # plain prose text, tables excluded (backward compat)
    (
        "markdown",
        "str",
    ),  # structure-preserving Markdown (headings, lists, code, tables)
    ("html", "str"),  # HTML export
    ("doctags", "str"),  # DocTags format — structured annotation / AI training format
    # ─── Structured data ─────────────────────────────────────────────────────────
    ("json_doc", "Any"),  # full DoclingDocument as dict (lossless round-trip)
    ("tables", "Any"),  # list[{rows, schema}] — structured table data
    (
        "pictures",
        "Any",
    ),  # list[{index, image_base64?, caption, classification, description}]
    ("headings", "Any"),  # list[{level, text, page}]
    ("furniture", "Any"),  # list[{label, text, page}] — page headers / footers
    ("key_value_items", "Any"),  # list[{key, value}]
    # ─── Metadata ────────────────────────────────────────────────────────────────
    ("page_count", "float"),  # pages for documents; sheets for spreadsheets
    ("error", "str"),
]

# Suffixes handled by pandas rather than Docling.
# NOTE: Docling has no support for the legacy .xls binary format, so .xls
# must use the pandas path (requires xlrd). There is no Docling fallback.
_SPREADSHEET_SUFFIXES = frozenset({".xlsx", ".xls"})

_EMPTY_OUTPUT: dict[str, Any] = {
    "body_text": "",
    "markdown": "",
    "html": "",
    "doctags": "",
    "json_doc": {},
    "tables": [],
    "pictures": [],
    "headings": [],
    "furniture": [],
    "key_value_items": [],
    "page_count": 0.0,
    "error": "",
}


# ─────────────────────────────────────────────────────────────────────────────
# Spreadsheet helpers
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Docling helpers
# ─────────────────────────────────────────────────────────────────────────────


def _body_text_excluding_tables(document: Any) -> str:
    try:
        from docling_core.types.doc.labels import (  # type: ignore[import-not-found]
            DocItemLabel,
        )

        labels_include = set(DocItemLabel) - {DocItemLabel.TABLE}
        return (document.export_to_text(labels=labels_include) or "").strip()
    except Exception:
        return ""


def _export_markdown(document: Any) -> str:
    try:
        return (document.export_to_markdown() or "").strip()
    except Exception:
        return ""


def _export_html(document: Any) -> str:
    try:
        return (document.export_to_html() or "").strip()
    except Exception:
        return ""


def _export_doctags(document: Any) -> str:
    """Export to DocTags format. Returns the raw string representation."""
    try:
        dt = document.export_to_doctags()
        if isinstance(dt, str):
            return dt.strip()
        # Newer Docling versions return a DocTagsDocument object
        if hasattr(dt, "to_string"):
            return (dt.to_string() or "").strip()
        return str(dt).strip() if dt else ""
    except Exception:
        return ""


def _export_json_doc(document: Any) -> dict[str, Any]:
    """Lossless DoclingDocument serialisation."""
    try:
        result = document.export_to_dict()
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    try:
        return document.model_dump(mode="json")
    except Exception:
        return {}


def _get_page_count(document: Any) -> float:
    try:
        pages = getattr(document, "pages", None)
        if pages is not None:
            return float(len(pages))
    except Exception:
        pass
    return 0.0


def _extract_headings(document: Any) -> list[dict[str, Any]]:
    """Extract section headings and the document title as {level, text, page} dicts."""
    out: list[dict[str, Any]] = []
    try:
        from docling_core.types.doc.labels import (  # type: ignore[import-not-found]
            DocItemLabel,
        )

        heading_labels = frozenset({DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE})
        for item in document.texts or []:
            label = getattr(item, "label", None)
            if label not in heading_labels:
                continue
            text = str(getattr(item, "text", "") or "").strip()
            if not text:
                continue
            prov = getattr(item, "prov", []) or []
            page = prov[0].page_no if prov else None
            level = getattr(item, "level", 1)
            level = int(level) if isinstance(level, (int, float)) else 1
            out.append({"level": level, "text": text, "page": page})
    except Exception:
        pass
    return out


def _extract_furniture(document: Any) -> list[dict[str, Any]]:
    """Extract page headers and footers as {label, text, page} dicts."""
    out: list[dict[str, Any]] = []
    try:
        from docling_core.types.doc.labels import (  # type: ignore[import-not-found]
            DocItemLabel,
        )

        furniture_labels = frozenset(
            {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
        )
        for item in document.texts or []:
            label = getattr(item, "label", None)
            if label not in furniture_labels:
                continue
            text = str(getattr(item, "text", "") or "").strip()
            if not text:
                continue
            prov = getattr(item, "prov", []) or []
            page = prov[0].page_no if prov else None
            label_str = (
                label.value
                if (label is not None and hasattr(label, "value"))
                else str(label)
            )
            out.append({"label": label_str, "text": text, "page": page})
    except Exception:
        pass
    return out


def _extract_key_value_items(document: Any) -> list[dict[str, Any]]:
    """Extract key-value pairs found by Docling's KV extraction pipeline."""
    out: list[dict[str, Any]] = []
    try:
        for kv in document.key_value_items or []:
            key_text = str(getattr(kv, "key", "") or "").strip()
            val_text = str(getattr(kv, "value", "") or "").strip()
            if key_text or val_text:
                out.append({"key": key_text, "value": val_text})
    except Exception:
        pass
    return out


def _extract_pictures_enhanced(
    document: Any,
    conv_result: Any,
    include_images: bool,
) -> list[dict[str, Any]]:
    """Extract picture metadata. image_base64 is only populated when include_images=True.

    Classification and description come from VLM enrichment pipelines when enabled;
    they are None for standard (non-VLM) conversions.
    """
    out: list[dict[str, Any]] = []
    try:
        from docling_core.types.doc import PictureItem  # type: ignore[import-not-found]
    except Exception:
        return out

    for idx, (element, _level) in enumerate(document.iterate_items() or [], start=1):
        if not isinstance(element, PictureItem):
            continue
        try:
            pic: dict[str, Any] = {
                "index": idx,
                "image_base64": None,  # populated only when include_images=True
                "caption": None,
                "classification": None,  # populated by VLM classification enrichment
                "description": None,  # populated by VLM description enrichment
            }

            # ── Image data (large — gated by include_images param) ──────────
            if include_images:
                try:
                    img = element.get_image(conv_result.document)
                    if img is not None:
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        pic["image_base64"] = base64.b64encode(buf.getvalue()).decode(
                            "ascii"
                        )
                except Exception:
                    pass

            # ── Caption ─────────────────────────────────────────────────────
            caption = getattr(element, "caption", None) or getattr(
                element, "label", None
            )
            pic["caption"] = str(caption).strip() if caption else None

            # ── VLM annotations (only present when enrichment pipeline ran) ─
            for ann in getattr(element, "annotations", []) or []:
                ann_type = type(ann).__name__
                if "Classification" in ann_type:
                    predicted = getattr(ann, "predicted_classes", []) or []
                    if predicted:
                        best = max(
                            predicted,
                            key=lambda x: getattr(x, "confidence", 0),
                        )
                        pic["classification"] = {
                            "class_name": str(getattr(best, "class_name", best)),
                            "confidence": getattr(best, "confidence", None),
                        }
                elif "Semantic" in ann_type or "Description" in ann_type:
                    desc = getattr(ann, "description", None) or getattr(
                        ann, "text", None
                    )
                    pic["description"] = str(desc).strip() if desc else None

            out.append(pic)
        except Exception:
            continue

    return out


def _make_converter(params: dict[str, Any]) -> Any:
    """
    Build a ``DocumentConverter`` with optional enrichment pipeline options.

    Enrichment params (all default to False / disabled):
      do_picture_classification  bool   - classify pictures (chart, diagram, logo …)
      do_picture_description     bool   - caption pictures with a VLM
      picture_description_model  str    - local model: "smolvlm" (default) | "granite"
                                          or any HuggingFace repo_id
      picture_description_api_url str  - if set, use a remote API endpoint instead
                                          of a local model (requires network access)
      images_scale               float - render resolution for picture extraction
                                          (default 2.0; also used by include_pictures)
      do_code_enrichment         bool   - advanced code block parsing + language detection
      do_formula_enrichment      bool   - extract LaTeX from equations

    Note: enrichment pipeline options are applied to the PDF format only.
    Other formats (DOCX, HTML, MD …) use the default Docling pipeline.
    """
    from docling.document_converter import (  # type: ignore[import-not-found]
        DocumentConverter,
    )

    do_classify = bool(params.get("do_picture_classification", False))
    do_describe = bool(params.get("do_picture_description", False))
    do_code = bool(params.get("do_code_enrichment", False))
    do_formula = bool(params.get("do_formula_enrichment", False))
    include_pics = bool(params.get("include_pictures", False))
    images_scale = float(params.get("images_scale", 2.0))
    desc_model = str(
        params.get("picture_description_model", "smolvlm") or "smolvlm"
    ).strip()
    desc_api_url = str(params.get("picture_description_api_url", "") or "").strip()

    needs_enrichment = do_classify or do_describe or do_code or do_formula
    needs_images = do_classify or do_describe or include_pics

    # Honour rag_offline — prevents HF Hub from downloading enrichment models;
    # uses only what is already in the local cache (same flag as the embedding model).
    try:
        from rag.ragconf_loader import rag_offline_raw

        if rag_offline_raw():
            import os

            os.environ["HF_HUB_OFFLINE"] = "1"
    except Exception:
        pass

    if not needs_enrichment and not needs_images:
        return DocumentConverter()

    try:
        from docling.datamodel.base_models import (  # type: ignore[import-not-found]
            InputFormat,
        )
        from docling.datamodel.pipeline_options import (  # type: ignore[import-not-found]
            PdfPipelineOptions,
        )
        from docling.document_converter import (  # type: ignore[import-not-found]
            PdfFormatOption,
        )

        opts = PdfPipelineOptions()

        if needs_images:
            opts.generate_picture_images = True
            opts.images_scale = images_scale

        if do_classify:
            opts.do_picture_classification = True

        if do_describe:
            opts.do_picture_description = True
            if desc_api_url:
                # Remote API endpoint (VLLM, Ollama, watsonx, …)
                try:
                    from docling.datamodel.pipeline_options import (  # type: ignore[import-not-found]
                        PictureDescriptionApiOptions,
                    )

                    opts.enable_remote_services = True
                    opts.picture_description_options = PictureDescriptionApiOptions(
                        url=desc_api_url,
                        params={"max_completion_tokens": 200},
                        prompt="Describe the image in three sentences. Be concise and accurate.",
                    )
                except Exception:
                    pass
            elif desc_model == "granite":
                try:
                    from docling.datamodel.pipeline_options import (  # type: ignore[import-not-found]
                        granite_picture_description,
                    )

                    opts.picture_description_options = granite_picture_description
                except Exception:
                    pass
            elif desc_model == "smolvlm":
                try:
                    from docling.datamodel.pipeline_options import (  # type: ignore[import-not-found]
                        smolvlm_picture_description,
                    )

                    opts.picture_description_options = smolvlm_picture_description
                except Exception:
                    pass
            else:
                # Treat desc_model as a HuggingFace repo_id
                try:
                    from docling.datamodel.pipeline_options import (  # type: ignore[import-not-found]
                        PictureDescriptionVlmOptions,
                    )

                    opts.picture_description_options = PictureDescriptionVlmOptions(
                        repo_id=desc_model,
                        prompt="Describe the image in three sentences. Be concise and accurate.",
                    )
                except Exception:
                    pass

        if do_code:
            opts.do_code_enrichment = True

        if do_formula:
            opts.do_formula_enrichment = True

        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )

    except Exception:
        # Pipeline options unavailable in this Docling version — fall back to defaults
        return DocumentConverter()


def _build_table_rows(
    table_item: Any,
    conv_result: Any,
) -> dict[str, Any] | None:
    """Convert a Docling TableItem to {rows, schema} dict. Returns None on failure."""
    try:
        df = table_item.export_to_dataframe(doc=conv_result.document)
        if df is None:
            return None
        schema = _build_schema_from_columns(list(df.columns))
        norm_cols = [s["name"] for s in schema]
        df.columns = norm_cols
        wrapped = [
            {col: {"value": row.get(col), "formula": None} for col in norm_cols}
            for row in df.to_dict(orient="records")
        ]
        return {"rows": wrapped, "schema": schema}
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Unit step
# ─────────────────────────────────────────────────────────────────────────────


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
        return {**_EMPTY_OUTPUT, "error": "path missing"}, state

    path = Path(path_val.strip()).expanduser().resolve()
    if not path.is_file():
        return {**_EMPTY_OUTPUT, "error": f"file not found: {path}"}, state

    tables_out: list[dict[str, Any]] = []
    # Pre-declare so the type checker sees them as always-bound
    body_text: str = ""
    markdown: str = ""
    html: str = ""
    doctags: str = ""
    json_doc: dict[str, Any] = {}
    pictures: list[dict[str, Any]] = []
    headings: list[dict[str, Any]] = []
    furniture: list[dict[str, Any]] = []
    key_value_items: list[dict[str, Any]] = []
    page_count: float = 0.0

    if path.suffix.lower() in _SPREADSHEET_SUFFIXES:
        # ─────────────────────────────────────────────────────────────────────
        # Spreadsheet path: pandas for values, openpyxl for formula strings
        # (.xlsx only — .xls has no formula API).
        # Most Docling-specific outputs are not applicable and remain empty.
        # ─────────────────────────────────────────────────────────────────────
        try:
            import pandas as pd  # type: ignore[import-untyped]

            dfs = pd.read_excel(path, sheet_name=None)  # all sheets → OrderedDict
            page_count = float(len(dfs))

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
                df.columns = norm_cols
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

        except Exception as e:
            return {
                **_EMPTY_OUTPUT,
                "error": f"spreadsheet parsing error: {e}",
            }, state

    else:
        # ─────────────────────────────────────────────────────────────────────
        # Docling path: PDF, DOCX, HTML, Markdown, etc.
        # ─────────────────────────────────────────────────────────────────────
        try:
            converter = _make_converter(params)
            result = converter.convert(str(path))
            doc = result.document

            # ── Text exports ─────────────────────────────────────────────────
            body_text = _body_text_excluding_tables(doc)
            markdown = _export_markdown(doc)
            html = _export_html(doc)
            doctags = _export_doctags(doc)

            # ── Lossless JSON ────────────────────────────────────────────────
            json_doc = _export_json_doc(doc)

            # ── Metadata ─────────────────────────────────────────────────────
            page_count = _get_page_count(doc)

            # ── Structured items ─────────────────────────────────────────────
            pictures = _extract_pictures_enhanced(doc, result, include_pictures)
            headings = _extract_headings(doc)
            furniture = _extract_furniture(doc)
            key_value_items = _extract_key_value_items(doc)

            for table_item in getattr(doc, "tables", []) or []:
                tbl = _build_table_rows(table_item, result)
                if tbl is not None:
                    tables_out.append(tbl)

        except Exception as e:
            return {**_EMPTY_OUTPUT, "error": f"docling error: {e}"}, state

    return {
        "body_text": body_text,
        "markdown": markdown,
        "html": html,
        "doctags": doctags,
        "json_doc": json_doc,
        "tables": tables_out,
        "pictures": pictures,
        "headings": headings,
        "furniture": furniture,
        "key_value_items": key_value_items,
        "page_count": page_count,
        "error": "",
    }, state


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────


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
                "Load a document and expose its full Docling representation. "
                "XLSX/XLS: pandas + openpyxl (formula strings for .xlsx). "
                "PDF/DOCX/HTML/MD/etc.: Docling — outputs body_text, markdown, html, "
                "doctags, json_doc, tables, pictures, headings, furniture (headers/footers), "
                "key_value_items, and page_count. "
                "Params: "
                "include_pictures (bool, false) gate base64 image extraction; "
                "images_scale (float, 2.0) picture render resolution; "
                "do_picture_classification (bool, false) classify picture types via DocumentFigureClassifier; "
                "do_picture_description (bool, false) caption pictures with a VLM; "
                "picture_description_model (str, 'smolvlm') local model: 'smolvlm' | 'granite' | HF repo_id; "
                "picture_description_api_url (str, '') remote API endpoint (VLLM/Ollama/watsonx) — overrides model; "
                "do_code_enrichment (bool, false) parse code blocks + detect language; "
                "do_formula_enrichment (bool, false) extract LaTeX from equations. "
                "Enrichments apply to PDF only; other formats use default Docling pipeline."
            ),
        )
    )


__all__ = [
    "register_load_document",
    "LOAD_DOCUMENT_INPUT_PORTS",
    "LOAD_DOCUMENT_OUTPUT_PORTS",
]
