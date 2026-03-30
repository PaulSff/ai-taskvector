# Prompt

Assembles the **system_prompt** string from a template and the **data** dict, and passes through **user_message** from data for the LLM user role. Pipeline: **Aggregate → Prompt → LLMAgent**.

## Purpose

Template contains placeholders `{key}`; each is replaced with `data[key]`. Data keys and template text come from your pipeline (e.g. Aggregate keys).

## Data parameters the Prompt expects

The **data** input must be a dict. The Prompt uses:

| Key in data | Used for | Required |
|-------------|----------|----------|
| **user_message** | Content sent to the LLM as the user role (output port `user_message`). Must be a non-empty string for the model to receive the request. | Yes, for LLM flows |
| Any other keys | Substituted into the template as `{key}` for **system_prompt**. | As needed by your template |

Upstream (e.g. Aggregate or Inject) must supply **user_message** in the data dict so the LLM receives the user's request. If `user_message` is missing or empty, the Prompt outputs the placeholder `"(No message provided.)"` on the `user_message` port.

## Interface

| Port / Param   | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs**     | data      | Any  | Dict from Aggregate (or Inject). Must include **user_message** for LLM user role; other keys fill template placeholders. |
| **Outputs**    | system_prompt | str | Assembled string after substituting `{key}` from data |
| **Outputs**    | user_message  | str | `data["user_message"]` or placeholder if missing |
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
