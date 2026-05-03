# LoadDocument

Loads a document and exposes its full structured representation. Two processing paths:

- **Spreadsheet path** (`.xlsx`, `.xls`) — pandas for cell values + openpyxl for formula strings
- **Docling path** (PDF, DOCX, PPTX, HTML, Markdown, and more) — full Docling conversion with optional enrichments

---

## Input ports

| Port | Type | Description |
| :--- | :--- | :--- |
| `path` | str | Absolute or relative path to the file |

---

## Output ports

### Text exports

| Port | Type | Description |
| :--- | :--- | :--- |
| `body_text` | str | Plain prose text with tables excluded — backward-compatible flat string |
| `markdown` | str | Structure-preserving Markdown: headings, lists, code blocks, inline tables |
| `html` | str | HTML export |
| `doctags` | str | DocTags format — Docling's structured annotation format for AI training data |

### Structured data

| Port | Type | Description |
| :--- | :--- | :--- |
| `tables` | Any | `list[{rows, schema}]` — see Tables section below |
| `pictures` | Any | `list[{index, image_base64, caption, classification, description}]` — see Pictures section below |
| `headings` | Any | `list[{level, text, page}]` extracted from `SECTION_HEADER` and `TITLE` items |
| `furniture` | Any | `list[{label, text, page}]` — page headers and footers (`PAGE_HEADER` / `PAGE_FOOTER`) |
| `key_value_items` | Any | `list[{key, value}]` from Docling's KV extraction pipeline |
| `json_doc` | Any | Full `DoclingDocument` serialised as a dict — lossless round-trip for downstream custom processing |

### Metadata

| Port | Type | Description |
| :--- | :--- | :--- |
| `page_count` | float | Number of pages (documents) or sheets (spreadsheets) |
| `error` | str | Non-empty on failure; all other ports are empty/default |

---

## Params

### Core

| Param | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `include_pictures` | bool | `false` | Gate base64 image data in `pictures` output. Metadata (caption, classification, description) is always extracted regardless. |
| `images_scale` | float | `2.0` | Picture render resolution. Automatically enabled when `include_pictures`, `do_picture_classification`, or `do_picture_description` is true. |

### Picture enrichments (PDF only)

All enrichments are **disabled by default**. They download models on first use and increase processing time.

| Param | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `do_picture_classification` | bool | `false` | Run `DocumentFigureClassifier` on every picture. Fills `pictures[].classification = {class_name, confidence}`. Classes include chart types, diagrams, logos, signatures, etc. |
| `do_picture_description` | bool | `false` | Run a VLM to caption every picture. Fills `pictures[].description`. |
| `picture_description_model` | str | `"smolvlm"` | Which local model to use for description. See model options below. |
| `picture_description_api_url` | str | `""` | Remote API endpoint (VLLM, Ollama, watsonx, etc.). When set, **overrides** `picture_description_model`. Requires network access. |

#### Model options for `picture_description_model`

| Value | Model | Size | Notes |
| :--- | :--- | :--- | :--- |
| `"smolvlm"` | HuggingFaceTB/SmolVLM-256M-Instruct | ~500 MB | Fast, lower quality. Good default for bulk processing. |
| `"granite"` | ibm-granite/granite-vision-3.1-2b-preview | ~4 GB | Higher quality. Runs locally. |
| any other string | Treated as a HuggingFace `repo_id` | varies | Passed to `PictureDescriptionVlmOptions(repo_id=...)` |

### Text enrichments (PDF only)

| Param | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `do_code_enrichment` | bool | `false` | Advanced code block parsing + language detection (`CodeFormula` model). Sets `code_language` on `CodeItem`. |
| `do_formula_enrichment` | bool | `false` | Extract LaTeX from equations (`CodeFormula` model). HTML export renders them via MathML. |

> **Note:** All enrichment params apply to **PDF only** via `PdfFormatOption + PdfPipelineOptions`. For DOCX, HTML, Markdown, and other formats, the default Docling pipeline is used regardless of these settings.

---

## Output formats in detail

### Tables

Each entry in `tables` follows this structure:

```json
{
  "schema": [
    {"index": 0, "letter": "A", "name": "Product"},
    {"index": 1, "letter": "B", "name": "Revenue"}
  ],
  "rows": [
    {
      "Product": {"value": "Widget A", "formula": null},
      "Revenue": {"value": 12500.0,   "formula": "=SUM(C2:C10)"}
    }
  ]
}
```

- `formula` is populated for `.xlsx` cells only (openpyxl with `data_only=False`)
- `formula` is always `null` for Docling-extracted tables (PDF, DOCX, etc.)

### Pictures

Each entry in `pictures`:

```json
{
  "index": 1,
  "image_base64": "iVBORw0KGgo...",
  "caption": "Figure 3: Revenue by quarter",
  "classification": {
    "class_name": "bar_chart",
    "confidence": 0.94
  },
  "description": "A bar chart showing quarterly revenue from Q1 2023 to Q4 2024..."
}
```

- `image_base64` is `null` unless `include_pictures: true`
- `classification` is `null` unless `do_picture_classification: true`
- `description` is `null` unless `do_picture_description: true`

---

## Spreadsheet path (`.xlsx`, `.xls`)

- Only `tables`, `page_count` (= sheet count), and `error` are populated
- All Docling-specific ports (`markdown`, `html`, `doctags`, `json_doc`, `headings`, `furniture`, `key_value_items`, `pictures`) are empty
- Formula strings are extracted for `.xlsx` via openpyxl (`data_only=False`); `.xls` returns values only (xlrd has no formula API)
- Docling has **no support** for `.xls` — this path must use pandas/xlrd

---

## Dependencies

| Feature | Required package |
| :--- | :--- |
| Docling path (PDF, DOCX, …) | `docling` |
| Spreadsheet `.xlsx` | `pandas`, `openpyxl` |
| Spreadsheet `.xls` | `pandas`, `xlrd` |
| Picture classification | auto-downloaded by Docling on first use |
| Picture description (local) | auto-downloaded by Docling on first use |
| Picture description (remote API) | network access + running endpoint |

---

## Example: workflow params for full PDF enrichment

```json
{
  "id": "load_doc",
  "type": "LoadDocument",
  "params": {
    "include_pictures": true,
    "images_scale": 2.0,
    "do_picture_classification": true,
    "do_picture_description": true,
    "picture_description_model": "smolvlm",
    "do_code_enrichment": true,
    "do_formula_enrichment": true
  }
}
```

## Example: remote description API (Ollama)

```json
{
  "params": {
    "do_picture_description": true,
    "picture_description_api_url": "http://localhost:11434/v1/chat/completions"
  }
}
```
