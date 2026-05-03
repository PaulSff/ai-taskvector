# presentation

**Detected by:** `.pptx`, `.ppt` suffixes  
**Index strategy:** `docling` (Docling text extraction)  
**Organises to:** `_organized/Presentations`

---

## Extraction subflow — `presentation_extract.json`

Triggered by `rag_upload_pipeline.json` when `content_type_id == "presentation"`.

```
inject_path (file path)
    ├─► LoadDocument          — Docling extracts slide text and any table objects
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
<slide text concatenated across all slides>

Tables:
<CSV representation of any data tables in the presentation>
```

Docling extracts text from all slides in order. Speaker notes and hidden slides
may not be included depending on the Docling version.

### Metadata stored per chunk

| Key | Value |
| :--- | :--- |
| `file_path` | Absolute path to the source file |
| `content_type` | `"document"` |
| `origin` | `"presentation"` |
| `chunk_index` | Position of this chunk within the document |
| `chunk_count` | Total number of chunks for this document |
