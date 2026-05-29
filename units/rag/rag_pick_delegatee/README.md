# RagPickDelegatee

Reads nested **RunWorkflow** outputs and picks the first **TeamMember** row for auto-delegation.

## Purpose

Used after a nested graph that runs **RagSearch** → **Filter** (and similar). Inspects `nested.rag_filter.table` or, if missing, `nested.rag_search.table`, finds the first row whose text/metadata indicates a team member, and outputs **`delegate_to`** as the role id.

IDENTIFICATION: Only use metadata.file_path. Expect paths like: `/.../taskvector/<role_id>/ROLE.md` Returns the extracted `<role_id>` or `None`.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs** | `nested` | Any | Dict shaped like RunWorkflow `data` (e.g. `{ "rag_search": {...}, "rag_filter": {...} }`) |
| | `user_message` | Any | String or dict with `user_message` — passed through to output |
| **Output** | `data` | Any | Dict: `user_message`, `has_delegatee` (bool), `delegate_to` (str) |

**Params** 
To override the default pattern, pass the path pattern when running the unit.

```json
{
"role_path_regex": "<your_regex>"
}
```
The regex must include a capture group for **role_id**. If invalid, the unit falls back to the default.

```json
{
"role_path_regex": r"/taskvector/([^/]+)/ROLE\.md$"
}
```

## Example

Downstream **PayloadTransform** or **delegate_request** can map `data.delegate_to` to the agent role id when `has_delegatee` is true.
