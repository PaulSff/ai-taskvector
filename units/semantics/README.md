# Semantics environment

Units for lightweight NLP-style processing (no external APIs by default).

## Units

| Type | Description |
|------|-------------|
| **LanguageDetector** | Detect language of text with [lingua-py](https://github.com/pemistahl/lingua-py). See `language_detector/README.md`. |
| **CleanText** | Clean markdown/code/JSON-like noise from text before language detection. See `clean_text/README.md`. |

## Setup

Install the optional dependency (also listed in the repo root `requirements.txt`):

```bash
pip install -r units/semantics/requirements.txt
```

## Graphs

1. Use **`add_environment`** with `env_id: semantics` so **LanguageDetector** appears in the Units Library.
2. Set **`environment_type`** to **`semantics`** when the workflow is semantics-focused (inference / `build_env`).

## Training

Semantics graphs typically use **LLMAgent** / **Inject**-style flows rather than RL training; `SemanticsEnvSpec` registers semantics units and uses the same **GraphEnv** step loop as `web`.
