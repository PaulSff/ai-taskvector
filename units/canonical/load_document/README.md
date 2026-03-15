# LoadDocument

Loads a document (PDF, DOCX, XLSX, PPT, HTML, MD) via Docling and outputs body text and tables separately. Uses Docling API: `export_to_text(labels=...)` with all labels except `TABLE` for body; `document.tables` + `export_to_dataframe(doc=...)` for tables. Downstream TablesToText + Aggregate + Prompt produce one document string with compact table content.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs**   | path      | str  | Absolute or relative path to the file. |
| **Outputs**  | body_text | str  | Plain text from document (all elements except TABLE, via Docling labels). |
| **Outputs**  | tables    | Any  | List of tables; each table = list of dicts (for TablesToText). |
| **Outputs**  | error     | str  | Non-empty on failure (file not found, docling error). |

Requires `docling` (e.g. `pip install -r requirements-rag.txt`). Uses `docling_core.types.doc.labels.DocItemLabel` when available. Used in the doc_to_text workflow for RAG indexing.
