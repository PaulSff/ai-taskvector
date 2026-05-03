# html

**Detected by:** `.html` suffix  
**Index strategy:** `docling` (Docling text extraction)  
**Organises to:** `_organized/HTML`

---

## Extraction subflow — `html_extract.json`

Triggered by `rag_upload_pipeline.json` when `content_type_id == "html"`.

```
inject_path (file path)
    ├─► LoadDocument          — Docling parses HTML, strips tags, extracts text and tables
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
<visible page text with markup stripped>

Tables:
<CSV representation of any HTML tables>
```

Docling strips HTML tags and extracts readable text. `<table>` elements are
converted to CSV and appended in the `Tables:` section.

### Metadata stored per chunk

| Key | Value |
| :--- | :--- |
| `file_path` | Absolute path to the source file |
| `content_type` | `"document"` |
| `origin` | `"html"` |
| `chunk_index` | Position of this chunk within the document |
| `chunk_count` | Total number of chunks for this document |
