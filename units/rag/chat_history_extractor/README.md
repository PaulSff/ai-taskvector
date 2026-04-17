# ChatHistoryExtract

Extracts structured metadata and text items from chat history JSON (list or dict with "messages"). Supports semantic grouping by turns and optional character-based chunking for index documents.

## Purpose

Normalize chat histories for downstream indexing or processing. Accepts either a raw list of message dicts or a dict containing `"messages"`. Produces items with extracted text and metadata including roles, assistants, timestamps, feedbacks, message counts, and grouping/chunking information. Behavior is configurable via params (grouping vs char-chunking, max messages, inclusion of aggregated text/feedbacks, role fallback).

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Inputs** | `data` | Any | Chat history: either a list of message dicts or a dict with a `"messages"` list. Each message may include `role`, `content`, `assistant`, `feedback`, `ts`. |
|  | `file_path` | Any | Optional path string to a file containing JSON chat history; overrides `data`'s file\_path and is used to set metadata file paths. |
| **Params** | `group_size` | int | Number of turns per group (default 4). Applied when `chunk_mode` != `"char"`. |
|  | `group_overlap` | int | Sliding-window overlap between groups (default 0). |
|  | `max_messages` | int | Maximum messages to process (default 8000). |
|  | `include_text` | bool | If true, include aggregated `text` (first 1000 message contents) in metadata (default true). |
|  | `include_feedbacks` | bool | If true, include aggregated `feedbacks` in metadata (default true). |
|  | `role_fallback` | str | Fallback string when `role` is missing; set to `""` to omit empty-role-only lines like extractors.py (default `"?"`). |
|  | `chunk_mode` | str | `"none"` (default) for grouping by turns, or `"char"` to produce character-chunked index documents matching extractors.py behavior. |
|  | `chunk_chars` | int | Max chars per chunk when `chunk_mode` == `"char"` (default 4000). |
| **Outputs** | `items` | Any | List of items: each item is `{"text": <str>, "metadata": <dict>}`. Metadata shape varies: grouping items include `group_index`, `group_size`, `total_groups`; char-chunked items include `chunk_index`, `chunk_count` and slim meta keys. |
|  | `error` | str | Empty string on success, or an error message. |

## Metadata fields (commonly present)

- **content\_type**: `"chat_history"`
- **format**: `"chat_history"`
- **name**: e.g., `"Chat history (42 messages)"`
- **source**: source string (from input or file name)
- **messages\_count**: number of messages processed
- **roles**: list of observed roles
- **assistants**: list of assistant identifiers
- **timestamps**: list of timestamps (strings)
- **text**: aggregated message contents (present if include\_text=true)
- **feedbacks**: list of feedback strings (present if include\_feedbacks=true)
- **file\_path**, **raw\_json\_path**, **origin**: file/path info and `"chat_history"`
- **group\_index**, **group\_size**, **total\_groups** (when grouping)
- **chunk\_index**, **chunk\_count** (when chunk\_mode == `"char"`)

## Example

- Default grouping (params omitted):
  - params: `{}` → groups of 4 turns, no char-chunking
  - output: items with grouped text and `group_index` metadata

- Index document mode (character chunking):
  - params: `{"chunk_mode": "char", "chunk_chars": 4000, "include_text": false}`
  - output: items whose texts are header + chunk (matching extractors.build\_chat\_history\_index\_documents), metadata is slim (includes chunk\_index/chunk\_count)

## Notes

- Messages may contain:
  - `role`: speaker role (string)
  - `content`: string or list (list values will be JSON-stringified)
  - `assistant`: assistant identifier/name
  - `feedback`: string or dict (dicts are flattened into `k:v` pairs)
  - `ts`: timestamp (any value converted to str)
- To mimic extractors.py line omission for messages with no role, set `role_fallback` to `""`.
- To produce slim metadata exactly like extractors.py index documents, use `chunk_mode: "char"` and set `include_text: false`.
