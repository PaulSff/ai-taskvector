# RagChunkBuilder

Universal text chunking unit that turns input items (text + metadata) into smaller text chunks with per-chunk metadata for RAG pipelines.

## Purpose

Splits input items (each item: `{"text": str, "metadata": dict}`) into chunks using one of two strategies:
- `chars`: fixed-size character windows with optional overlap.
- `lines`: pack whole lines into chunks up to `chunk_size`.

Each output chunk includes the chunk text and merged metadata with `chunk_index` (zero-based) and `chunk_count` (total chunks for that item).

## Interface

| Port / Param | Direction | Type | Description |
|--------------:|:---------:|:----:|-------------|
| **Inputs** | `items` | Any | List of items OR dict `{"items": [...]}`; each item: `{"text": str, "metadata": dict}` |
| **Outputs** | `chunks` | Any | List of chunk objects: `{"text": str, "metadata": dict}` |
|  | `error` | str | Error message (empty on success) |
| **Params** | `strategy` | str | `"chars"` (default) or `"lines"`. Any value other than `"lines"` uses `chars`. |
|  | `chunk_size` | int | Default `1000`. Clamped to range `[100, 20000]`. |
|  | `overlap` | int | Default `100`. Clamped to `[0, chunk_size // 2]`. (Only used for `chars`.) |

## Behavior / Details

- Default strategy: **chars**.
- Character strategy: splits text into windows of up to `chunk_size` characters; the next window starts at `end - overlap` (if `overlap > 0`).
- Line strategy: splits text by lines and accumulates whole lines into a buffer until adding another line would exceed `chunk_size`, then flushes the buffer as a chunk.
- Skips items where `text` is not a string or is only whitespace.
- Per-chunk metadata is a shallow merge of the original `metadata` with:
  - `chunk_index` (int, zero-based)
  - `chunk_count` (int)
  If original metadata contains these keys they will be overwritten.
- `chunk_size` and `overlap` are converted via `int(...)`; invalid numeric conversions will produce an error returned in `error`.
- Safety clamps ensure reasonable sizes: `chunk_size` minimum 100, maximum 20000; `overlap` at most half of `chunk_size`.

## Example

Input item:
```python
{"text": "Line1\nLine2\nLine3", "metadata": {"source": "doc1"}}
```

With strategy="lines", chunk_size=10 → chunks with whole-line packing; each chunk metadata includes chunk_index and chunk_count.

With strategy="chars", chunk_size=5, overlap=2 → sliding character windows of size 5 with 2-char overlap.

## Errors and edge cases

If `inputs["items"]` is not a list (or dict wrapping a list), the unit returns `{"chunks": [], "error": "items must be a list"}`.
Exceptions inside the step are caught and returned as `{"chunks": [], "error": str(e)}`.
Empty or whitespace-only texts are omitted from output.
