# LanguageDetector

Detects the natural language of input text using [lingua-py](https://github.com/pemistahl/lingua-py) (offline, no API).

## Setup

```bash
pip install -r units/semantics/requirements.txt
```

## Tests

From repo root:

```bash
pytest units/semantics/language_detector/tests/test_language_detector.py -v
```

Tests that call Lingua are skipped if `lingua-language-detector` is not installed.

## Ports

- **In:** `text` — string to classify (or set `params.text`).
- **Out:** `iso639_1` (e.g. `de`), `confidence` (0–1), `language` (Lingua name, e.g. `GERMAN`), `reliable` (bool), `error` (str if failure / missing dependency).

## Params

| Param | Meaning |
|--------|--------|
| `languages` | Comma-separated ISO 639-1 codes to *limit* candidates. Empty, `all`, or `all_spoken` → **all** spoken languages Lingua supports (~75). |
| `min_confidence` | If top probability is below this, `iso639_1` becomes `default_when_unknown`. |
| `default_when_unknown` | Fallback ISO code when uncertain or empty input (default `""`). |
| `low_accuracy` | Lingua low-accuracy mode: faster, weaker on very short text. |

## Graph

Add environment **`semantics`** to the graph (`add_environment`) so this unit appears in the Units Library, and set `environment_type` to `semantics` when the workflow is semantics-only.
