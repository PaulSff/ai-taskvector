# plain-text

**Detected by:** `.txt`, `.yaml`, `.yml`, `.xml`, `.log`, `.ini`, `.cfg`, `.conf`, `.env`, `.rst`, `.csv`, `.tsv` suffixes  
**Index strategy:** `plain_text` (direct UTF-8 read — no Docling)  
**Organises to:** `_organized/Plain text`

---

## Extraction subflow — `plain_text_extract.json`

Triggered by `rag_upload_pipeline.json` when `content_type_id == "plain-text"`.

```
inject_path (file path)
    ↓
PlainTextExtract   — reads the file as UTF-8, wraps content in {text, metadata}
    ↓
RagChunkBuilder → chunks
```

This is the simplest extraction pipeline: no Docling, no table parsing, no
format conversion. The file is read directly as a UTF-8 string and passed
straight to the chunk builder.

### Why no Docling?

Plain text formats (YAML, CSV, logs, config files, etc.) are already in a
human-readable, embeddable form. Running Docling on them would add latency
with no quality benefit.

Note: `.csv` and `.tsv` files use this pipeline even though they are
**organised** into `_organized/Spreadsheets` — their content is plain text
and does not need Excel/table parsing.

### Text produced

The raw file content, stripped of leading/trailing whitespace, truncated to
`max_chars` (default 50 000 characters).

### Params (via `PlainTextExtract` unit)

| Param | Default | Description |
| :--- | :--- | :--- |
| `max_chars` | `50000` | Maximum characters to index per file |
| `encoding` | `"utf-8"` | File encoding |
| `origin` | `"plain_text"` | Stored in `metadata.origin` |

### Metadata stored per chunk

| Key | Value |
| :--- | :--- |
| `file_path` | Absolute path to the source file |
| `origin` | `"plain_text"` |
| `chunk_index` | Position of this chunk within the file |
| `chunk_count` | Total number of chunks for this file |
