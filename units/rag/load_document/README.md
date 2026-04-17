# LoadDocument

Loads a document (PDF, DOCX, XLSX, PPT, HTML, MD) via Docling and outputs body text, tables, and optionally pictures. Uses Docling API: `export_to_text(labels=...)` for body; `document.tables` + `export_to_dataframe(doc=...)` for tables; when `include_pictures=True`, the Docling pictures API (`PdfPipelineOptions.generate_picture_images` for PDF, `document.iterate_items()` + `PictureItem.get_image()`) to extract figures as base64 PNGs. Downstream TablesToText + Aggregate + Prompt produce one document string; the `pictures` output can be used for multimodal RAG or export.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | path      | str  | Absolute or relative path to the file. |
| **Params**   | include_pictures | bool | If true, enable picture extraction (PDF: pipeline option; then iterate_items + PictureItem.get_image → base64). Default false. |
| **Params**   | data_only | bool | When extracting XLSX formulas, controls whether openpyxl loads cell values only (True) or preserves formulas (False). Set to False to extract formula strings; set to True to return evaluated values only. Default: False. |
| **Outputs**  | body_text | str  | Plain text from document (all elements except TABLE, via Docling labels). |
| **Outputs**  | tables    | Any  | List of tables; each table is a dict: `{"rows": [...], "schema": [...]}`. "rows" is a list of row dicts; each cell is a dict `{"value": , "formula": }`. "schema" is a list of column descriptors: `[{"index": i, "letter": "A", "name": column_name}, ...]`. |
| **Outputs**  | pictures  | Any  | When include_pictures: list of `{index, image_base64, caption}`; else `[]`. |
| **Outputs**  | error     | str  | Non-empty on failure (file not found, docling error). |

## Notes

- For XLSX files, the LoadDocument will use `pandas` + `openpyxl` to open the workbook(`data_only=False`) and extract cell formulas, so each cell becomes `{"value", "formula"}` when applicable;

- Requires `docling` (e.g. `pip install -r requirements-rag.txt`). For pictures, PDF uses `PdfPipelineOptions(generate_picture_images=True, images_scale=1.5)`. Used in the doc_to_text workflow for RAG indexing; RAG indexer uses only body_text + tables unless the workflow is extended to consume `pictures`.
