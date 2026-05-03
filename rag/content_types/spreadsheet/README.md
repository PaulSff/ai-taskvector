# spreadsheet

**Detected by:** `.xlsx`, `.xls` suffixes  
**Index strategy:** `docling` (Docling text extraction)  
**Organises to:** `_organized/Spreadsheets`

> **Note:** `.csv` and `.tsv` files are organised here but indexed as `plain-text`
> (read directly as UTF-8 via `PlainTextExtract`), since they need no Docling processing.

---

## Extraction subflow — `spreadsheet_extract.json`

Triggered by `rag_upload_pipeline.json` when `content_type_id == "spreadsheet"`.

```
inject_path (file path)
    ├─► LoadDocument          — Docling parses sheets; body text may be sparse
    │       ├─ body_text ─────────────────► Aggregate.in_0  (key: body)
    │       └─ tables ──► TablesToText ──► Aggregate.in_1  (key: tables_text)
    └─────────────────────────────────────► Aggregate.in_2  (key: file_path)
                                                ↓
                                          Aggregate
                                     {body, tables_text, file_path}
                                                ↓
                                        PayloadTransform
                              builds {items: [{text, metadata}]}
                                                ↓
                                        RagChunkBuilder → chunks
```

### Text produced

```
<any prose body text extracted from the workbook>

Tables:
<CSV representation of all sheet data>
```

For Excel files the `Tables:` section is typically the primary content — Docling
converts each sheet into a CSV table. The `body` field is often empty or minimal.

### Metadata stored per chunk

| Key | Value |
| :--- | :--- |
| `file_path` | Absolute path to the source file |
| `content_type` | `"document"` |
| `origin` | `"spreadsheet"` |
| `chunk_index` | Position of this chunk within the document |
| `chunk_count` | Total number of chunks for this document |
