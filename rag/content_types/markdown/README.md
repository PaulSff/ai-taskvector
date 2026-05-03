# markdown

**Detected by:** `.md` suffix  
**Index strategy:** `docling` (Docling text extraction)  
**Organises to:** `_organized/Markdown`

---

## Extraction subflow — `markdown_extract.json`

Triggered by `rag_upload_pipeline.json` when `content_type_id == "markdown"`.

```
inject_path (file path)
    ├─► LoadDocument          — Docling parses Markdown, extracts text and any tables
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
<Markdown rendered to plain text — headings, paragraphs, lists>

Tables:
<CSV representation of any GFM pipe tables>
```

Markdown files are processed via Docling rather than read as plain UTF-8, so
structured elements (headings, code blocks, tables) are properly parsed.
GitHub-Flavored Markdown pipe tables are converted to CSV in the `Tables:` section.

### Metadata stored per chunk

| Key | Value |
| :--- | :--- |
| `file_path` | Absolute path to the source file |
| `content_type` | `"document"` |
| `origin` | `"markdown"` |
| `chunk_index` | Position of this chunk within the document |
| `chunk_count` | Total number of chunks for this document |
