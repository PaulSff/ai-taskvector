# CleanText

Preprocesses user text before language detection by removing markdown code blocks and noisy code/JSON-like content.

Designed for flows like:

`Inject(user_message) -> CleanText -> LanguageDetector -> Aggregate`

## Setup

```bash
pip install -r units/semantics/requirements.txt
```

## Ports

- **In:** `text` (str)
- **Out:** `text` (cleaned str), `error` (str when cleanup fails; `text` falls back to raw input)

## Params

| Param | Default | Meaning |
|---|---:|---|
| `symbol_density_threshold` | `0.25` | Mark block as code/noise if code-like symbol ratio is above threshold. |
| `min_block_len` | `4` | Drop blocks shorter than this length. |
| `max_chars` | `600` | Truncate final cleaned output to this many chars (`0` disables truncation). |

## Behavior

1. Uses `markdown-it-py` to parse markdown and remove:
   - fenced code (` ```...``` `)
   - indented code blocks
   - inline code (`` `...` ``)
2. Splits text into paragraph-like blocks and drops blocks that look like:
   - code / console logs
   - JSON-ish punctuation-only fragments
   - URL-only lines
3. Normalizes whitespace and returns compact text for language detection.

When `markdown-it-py` is unavailable, the unit falls back to raw text and still applies block filtering.
