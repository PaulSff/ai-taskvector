# ProcessAgent

Parses LLM response text into **generic action blocks**: JSON objects with an `"action"` key (and optional payload). The unit does not depend on any specific action type (e.g. graph edits). Downstream units decide which actions they consume; the same syntax can be used for graph edits, config changes, or other domains.

**Unit type:** `ProcessAgent`

## Purpose

An LLM often returns free-form text plus structured JSON (e.g. in fenced ` ```json ` blocks or inline `{ ... }`). This unit extracts and normalizes those blocks into a single stream of action dicts. Each consumer (e.g. ApplyEdits for graph edits) filters by its own action set; actions it doesn’t recognize are ignored so other units can handle them.

**Where the content comes from:** In the assistant workflow the ProcessAgent’s **action** input is connected from the **LLMAgent** unit’s **action** output. So the content is the raw LLM response string (possibly markdown with embedded JSON blocks). The unit accepts that string and passes it to the parser; if the value is not a string (e.g. from another flow), it is stringified before parsing.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Input**  | action | Any | Raw LLM response (string or stringified); typically from an LLMAgent unit. |
| **Output** | edits  | Any | Parsed result: a **list** of action dicts, or a **dict** with `"edits"` (list) and optional side-channel keys. |

## Output shape

- **List:** `[ {"action": "add_unit", ...}, {"action": "connect", ...} ]` — all parsed action objects. Non-dict or non-`action` blocks are not included in this list; side-channel actions are extracted instead (see below).
- **Dict:** When any side-channel actions are present, the output is a dict, for example:
  - `edits` — list of the remaining action dicts (any `"action"` that isn’t a side-channel).
  - `request_unit_specs` — list of unit IDs (from `action: "request_unit_specs"`).
  - `request_file_content` — list of file paths (from `action: "request_file_content"`).
  - `rag_search` / `rag_search_max_results` — from `action: "search"`.
  - `read_code_block_ids` — from `action: "read_code_block"`.
- **Parse error:** If fenced JSON was present but every block failed to parse, the output is `{"parse_error": "..."}`.

Input that is `None` or missing yields output `[]` (empty list).

## Parsing rules

- Parsing is fully self-contained in **`action_blocks.py`** (no dependency on `assistants`). The unit step calls `parse_action_blocks()` from there.
- JSON block extraction is implemented in this module: fenced ` ```json ` and inline `{ ... }`; JSON is parsed leniently (e.g. `//` comments and trailing commas stripped).
- Objects with an `"action"` key are collected as action blocks; side-channel actions (`request_unit_specs`, `request_file_content`, `search`, `read_code_block`) are pulled out into the dict keys above. Nested `"edits"` arrays are flattened and processed the same way.

## Usage in a workflow

Typical flow: **LLMAgent → ProcessAgent → ApplyEdits** (or other consumers).

- **ApplyEdits (graph):** Reads `edits` and applies only actions in `GraphEditAction` (see `core.graph.graph_edits`). Other actions in the same stream are skipped.
- **Other units:** Can connect to the same `edits` output and handle their own action types (e.g. `send_email`, `update_config`) using the same `{"action": "...", ...}` format.

The ProcessAgent does not reference `GraphEditAction` or any domain-specific type; it only parses the generic structure so multiple consumers can share one syntax.
