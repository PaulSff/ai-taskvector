# word

**Detected by:** `.doc`, `.docx` suffixes  
**Index strategy:** `docling` (Docling text extraction)  
**Organises to:** `_organized/Word`

---

## Extraction subflow — `word_extract.json`

Triggered by `rag_upload_pipeline.json` when `content_type_id == "word"`.

```
inject_path (file path)
    ├─► LoadDocument          — Docling extracts body text and table objects
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
<full document body text>

Tables:
<CSV representation of all tables found in the document>
```

Word documents with embedded tables will have both the prose text and the table
content indexed, making table data searchable alongside the surrounding context.

### Metadata stored per chunk

| Key | Value |
| :--- | :--- |
| `file_path` | Absolute path to the source file |
| `content_type` | `"document"` |
| `origin` | `"word"` |
| `chunk_index` | Position of this chunk within the document |
| `chunk_count` | Total number of chunks for this document |
