# spaCy NLP Processor

Processes text with spaCy to extract noun phrases, verbs, and structured entities / phrase matches. Registered as unit type **spacy_nlp_processor**. Use this unit to transform raw text (or multilingual text) into simple structured outputs suitable for downstream pipelines, LLM prompts, analytics, or lightweight IE tasks.

## Behavior

- **Primary modes:** Always processes the provided text input with spaCy using a resolved model (per-language mapping, explicit model override, or fallback). It returns:
  - noun phrases (from spaCy noun_chunks when available),
  - verbs (optionally lemmatized),
  - entities and matched phrases (spaCy NER + user-supplied Phrase/Token matchers).

- **Model resolution:** The unit selects a spaCy model using (in priority order):
  1. explicit `model` param,
  2. `model_map` / `model_map_override` lookup by ISO-639-1 language code,
  3. built-in `DEFAULT_MODEL_MAP` fallback (English small model).
  If loading the selected model fails, the unit falls back to the English default model; if that fails it uses a blank English pipeline.

- **Device handling (GPU/CPU):** Specify `device` (or `use_gpu` boolean). The unit attempts to enable GPU using spaCy's available APIs (prefer_gpu or require_gpu). If GPU cannot be enabled the processor runs on CPU and reports the effective device in verbose mode.

- **Pattern matching:** You may supply phrase or token patterns via:
  - `pattern_file` — path to a JSON file (must be a list of pattern objects),
  - `patterns_to_find` — list of in-memory pattern objects.
  Patterns are merged (file first, then supplied list). Each pattern object may contain:
  - `"label"` or `"id"` — label for matches,
  - `"pattern_type"` — `"phrase"` (default) or other (treated as token matcher),
  - `"pattern"` — string or list of strings for phrase patterns; list of token dicts for token patterns.
  Phrase patterns use PhraseMatcher (with optional LOWER matching); token patterns use the Matcher.

- **Noun chunk parser:** If noun_chunks are required and the loaded model lacks a parser, the unit tries to add a `"parser"` pipe (best-effort). If this fails, noun phrase output will be an empty list.

- **Validation and robustness:** Many operations are defensive — missing pattern files, malformed params, or unavailable components fall back to safe defaults rather than raising.

- **Verbose/meta:** If `verbose` is true, the unit appends a META entity with model name, pipeline components, and effective device.

## Interface

| Port / Param                | Direction | Type               | Description |
|-----------------------------|-----------|--------------------|-------------|
| **Inputs**                  |           |                    | |
| input_0                     | in        | str                | Text to process. If missing, treated as empty string. |
| input_1                     | in        | str                | ISO 639-1 language code (e.g., `"en"`, `"de"`). Defaults to `"en"`. |
| **Outputs**                 |           |                    | |
| output_0                    | out       | list[str]          | Noun phrases (from spaCy noun_chunks when available). |
| output_1                    | out       | list[str]          | Verbs (lemmatized by default; controlled by param). |
| output_2                    | out       | list[dict]         | Structured entities, phrase matches, token matches, and optional meta entry. Each dict: `{"text","label","start_char","end_char","type"}`. |
| **Params**                  |           |                    | |
| model                       | param     | str optional       | Explicit spaCy model name (e.g., `en_core_web_sm`). Overrides model_map. |
| model_map / model_map_override | param  | dict               | Mapping from ISO-639-1 to spaCy model names. Defaults to built-in small models. |
| device                      | param     | str               | `"gpu"` or `"cpu"`. If omitted, `use_gpu` is used to pick device. |
| use_gpu                     | param     | bool               | Legacy toggle to prefer GPU when `device` not set. |
| disable_components          | param     | list[str]          | spaCy pipeline components to disable when loading model (e.g., `["parser","ner"]`). |
| pattern_file                | param     | str (path)         | Path to JSON file containing a list of pattern objects. Missing/nonexistent files are ignored. |
| patterns_to_find            | param     | list[dict]         | In-memory list of pattern objects to merge with pattern_file. |
| lower_case_phrase_matching  | param     | bool               | If true (default), PhraseMatcher uses LOWER attribute for case-insensitive phrase matching. |
| pattern_type                | param     | string (per pattern)| Use `"phrase"` (default) for PhraseMatcher, other values use the token Matcher. |
| ensure_parser_for_noun_chunks | param   | bool               | Default true. Adds a `'parser'` pipe if noun_chunks are desired and not present. |
| use_lemma_for_verbs         | param     | bool               | Default true — verbs in output_1 are lemmatized. |
| include_spacy_ents          | param     | bool               | Default true — include spaCy NER entities in output_2. |
| max_length                  | param     | int                | If set (>0), assigned to `nlp.max_length` to allow long texts. |
| verbose                     | param     | bool               | If true, add a META entry to `output_2` with model/pipeline/device info. |

## Pattern object format

A pattern object is a dict with these fields (examples shown):

- label / id (string) — required for labeling matches.
- pattern_type (string) — `"phrase"` (default) or `"token"`.
- pattern — for phrase: string or list[str]; for token: list[dict] token pattern as spaCy expects.

Example phrase pattern:

```json
{
  "label": "PRODUCT",
  "pattern_type": "phrase",
  "pattern": ["iPhone 12", "Pixel 5"]
}
```

Example token pattern:

```json
{
  "label": "DATE_EXPR",
  "pattern_type": "token",
  "pattern": [
    {"LOWER": "on"}, {"IS_SPACE": False, "OP": "?"}, {"SHAPE": "dd/dd/dddd"}
  ]
}
```

Note: phrase patterns are converted into docs with nlp.make_doc before adding to PhraseMatcher.

## Outputs explained

- output_0 (noun phrases): list of `chunk.text` from `doc.noun_chunks` (may be empty if parser unavailable).
- output_1 (verbs): contiguous list of verbs (lemmas by default). Consider post-processing to deduplicate or preserve unique set.
- output_2 (entities/matches): combined list containing:
  - spaCy NER entities with "type": "spacy_ent",
  - PhraseMatcher matches with "type": "phrase_match",
  - Matcher token matches with "type": "token_match",
  - optional "meta" record when `verbose=true`.

Each dict contains text, label, start_char, end_char, and type.

## Example Usage

Params:

```json
{
  "model_map_override": {"en": "en_core_web_sm"},
  "patterns_to_find": [
    {"label":"PRODUCT","pattern_type":"phrase","pattern":["iPhone 12","Pixel 5"]},
    {"label":"FIX_PATTERN","pattern_type":"token","pattern":[{"LOWER":"fix"},{"LOWER":"valve"}]}
  ],
  "use_lemma_for_verbs": true,
  "lower_case_phrase_matching": true,
  "verbose": true
}
```

Inputs (example):
- input_0: "Please fix the valve on the iPhone 12 today."
- input_1: "en"

Outputs (example):
- output_0: 
```json
[
"the valve", 
"the iPhone 12"
]
```
- output_1 (lemmas for verbs found): 
- 
```json
[
"fix", 
"be", 
"do"
]
```
- output_2: 
```json
[
    {"text":"iPhone 12","label":"PRODUCT","start_char":24,"end_char":33,"type":"phrase_match"},
    {"text":"fix the valve","label":"FIX_PATTERN","start_char":7,"end_char":20,"type":"token_match"},
    {"text":"iPhone 12","label":"PRODUCT","start_char":24,"end_char":33,"type":"spacy_ent"},
    {"text":"{\"model\":\"en_core_web_sm\",\"nlp_pipe\":[...],\"effective_device\":\"cpu\"}",
     "label":"META","start_char":0,"end_char":0,"type":"meta"}
  ]
```

## Implementation notes & recommendations

- PhraseMatcher attr: the unit uses LOWER by default for case-insensitive matches. If you prefer exact orth matching set `lower_case_phrase_matching` to `false`. The implementation safely constructs PhraseMatcher to avoid passing a None attr.
- Noun chunk fallback: if you rely on noun_chunks, ensure the chosen model has a parser; otherwise set `ensure_parser_for_noun_chunks` to true (default) and ensure the environment can install required model components.
- Performance: for very long documents consider chunking input text before processing or set `max_length` appropriately.
- GPU: GPU enabling is best-effort; if `device: "gpu"` is set but unavailable, the unit will continue on CPU and — if `verbose` — report the effective device.
- Patterns: malformed pattern files are ignored; pass well-formed JSON lists of pattern objects to `pattern_file`.

## Entry point

Call the unit's step function with:
- params: dictionary containing the params described above,
- inputs: {"input_0": <text>, "input_1": <lang>},
- state: dict (preserved between runs),
- dt: float (timestep, ignored by this unit).

It returns (outputs, state) where outputs is:
{"output_0": [...], "output_1": [...], "output_2": [...]}

## License & Attribution

This unit uses spaCy. Ensure appropriate spaCy model packages are installed (e.g., `python -m spacy download en_core_web_sm`) and respect their licenses.

## Quick sanity tests

- Empty text: input_0 = "" → outputs empty lists.
- Missing model file: specify non-existent model → falls back to English default or blank pipeline.
- Patterns: provide both phrase and token patterns and verify output_2 includes both match types.
- GPU toggle: set device="gpu" on CPU-only machine → runs on CPU and (if verbose) reports effective_device.
