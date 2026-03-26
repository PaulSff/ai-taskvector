# IsAQuestion

Detects whether the input text has at least one sentence ending with `?`.

Designed for flows like:

`Inject(user_message/LLM output) -> CleanText -> IsAQuestion -> logic`

## Setup

```bash
pip install -r units/semantics/requirements.txt
```

## Ports

- **In:** `text` (str)
- **Out(0):** `is_question` (bool) - `true` if any sentence ends with `?`
- **Out(1):** `question_sentence` (str) - first sentence that ends with `?`, otherwise `""`
- **Out(2):** `non_question_text` (str) - original input text when `is_question=false`, otherwise `""`

## Behavior

1. Reads `text` from input (fallback to `params.text`).
2. Splits text into sentence-like chunks (`.`, `!`, `?`, newlines).
3. Finds the first chunk whose trimmed text ends with `?`.
4. Emits:
   - `is_question=true` and that sentence, or
   - `is_question=false`, empty `question_sentence`, and `non_question_text` passthrough.
