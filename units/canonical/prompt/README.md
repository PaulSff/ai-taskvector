# Prompt

| **Inputs**     | data      | Any  | Merged context dict from Aggregate (keys defined by your pipeline/template) |
Assembles the system prompt string from a **template** and merged **data** (from ). Generic: no hardcoded data keys or prompt names; any LLM agent can use it. Pipeline: **Aggregate → Prompt → LLMAgent → Parser**.

## Purpose

Template contains placeholders `{key}`; each is replaced with `data[key]`. Data keys and template text come from your prompt templates (e.g. JSON or text files), not from this unit. Use for Workflow Designer, RL Coach, or any custom agent.

## Interface

| Port / Param   | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs**     | data      | Any  | Merged context dict from Aggregate (keys defined by your pipeline/template) |
| **Outputs**    | system_prompt | str | Assembled string after substituting {key} from data |
| **Params**     | template  | str  | Inline template string with placeholders `{key}` |
| **Params**     | template_path | str | Path to .txt (template body) or .json (see below) |
| **Params**     | format_keys | list | Keys whose values are json.dumps'd when substituting (e.g. graph_summary); also in JSON file |

If both `template` and `template_path` are set, `template` wins. Placeholders not present in data are replaced with empty string.

## Template format (JSON)

JSON files may use either:

- **Single string**: `{"template": "Full prompt with {placeholders}.", "format_keys": ["graph_summary"]}`
- **Structured sections**: `{"sections": [{"id": "intro", "content": "..."}, {"id": "dynamic", "content": "{graph_summary}"}], "format_keys": ["graph_summary"]}`

Sections are concatenated in order (with `\n\n` between them) to form the template, then placeholders are substituted. This keeps prompt files readable and editable as normal structured JSON.

- **Placeholders**: `{identifier}` — word characters only. Example: `{graph_summary}`, `{user_message}`, `{rag_context}`.
- **format_keys**: List of keys whose values are serialized as JSON (e.g. `graph_summary` → pretty-printed dict). Other values are stringified.

## Example

**Params:** `{"template_path": "config/prompts/workflow_designer.json"}`  
**Data (from Aggregate):** `{"graph_summary": {...}, "user_message": "Add a valve", "rag_context": "..."}`  
Template file defines the text and which keys exist; Prompt only substitutes. No hardcoded assistant names.
