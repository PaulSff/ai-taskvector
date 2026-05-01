# FetchSource

Unified source resolver — the single entry point for all RAG ingestion pipelines.

## Purpose

Normalises any external source (local file path or remote URL) into a **resolved local
file path** that every downstream unit can handle uniformly. `FileTypeDetector` and all
subsequent pipeline units are completely unaware of whether the content originally came
from disk or a remote server.

| Source type     | Behaviour |
|-----------------|-----------|
| Local file path | Verifies the file exists; outputs the resolved absolute path. |
| `http://` / `https://` | Downloads to `save_dir`; outputs the saved local path. |
| `ftp://` / `ftps://` | Downloads via `urllib` to `save_dir`; outputs the local path. |

Downloaded files are stored **persistently** — not in a temp directory — so:
- The same URL hit twice re-uses the cached file unless `overwrite` is `True`.
- Files can be inspected and audited after indexing.

## Interface

| Port / Param | Direction | Type | Description |
|---|---|---|---|
| **Input** | `source` | Any | Local file path **or** remote URL string |
| **Output** | `file_path` | str | Resolved local path — always present on success |
| | `source` | str | Original source string passed in |
| | `fetched` | Any | `True` if a network download was performed; `False` for local passthrough or cache hit |
| | `error` | str | Error message on failure; empty on success |
| **Params** | `save_dir` | str | Directory where downloaded files are saved (required for remote sources) |
| | `overwrite` | bool | Re-download even if the file already exists locally (default: `False`) |

## Pipeline position

```
inject_source ──► FetchSource ──► FileTypeDetector ──► PayloadTransform ──► RunWorkflow ──► …
                      │
              always outputs
              a local file_path
```

`FetchSource` is the **only unit** that knows about remote protocols.
Everything downstream treats content as a local file.

## Protocol support

| Scheme | Status | Implementation |
|---|---|---|
| `http://`, `https://` | ✓ | `requests` (lazy import) |
| `ftp://`, `ftps://` | ✓ | `urllib.request` (stdlib) |
| `s3://` | Planned | extend `_fetch_source_step` with `boto3` |
| Local path | ✓ | passthrough + existence check |

## Filename derivation

Downloaded files are saved as `{sha256_prefix_16}{original_extension}` — the hash
ensures two different URLs sharing the same filename never collide, while the extension
is preserved for downstream type detection.
