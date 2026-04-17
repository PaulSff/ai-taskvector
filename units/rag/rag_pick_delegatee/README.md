# RagPickDelegatee

Reads nested **RunWorkflow** outputs and picks the first **TeamMember** row for auto-delegation.

## Purpose

Used after a nested graph that runs **RagSearch** → **Filter** (and similar). Inspects `nested.rag_filter.table` or, if missing, `nested.rag_search.table`, finds the first row whose text/metadata indicates a team member (`assistants_team_members.md` path or `## TeamMember:` heading), and outputs **`delegate_to`** as the role id.

## Interface

| Port / Param | Direction | Type | Description |
|----------------|-----------|------|-------------|
| **Inputs** | `nested` | Any | Dict shaped like RunWorkflow `data` (e.g. `{ "rag_search": {...}, "rag_filter": {...} }`) |
| | `user_message` | Any | String or dict with `user_message` — passed through to output |
| **Output** | `data` | Any | Dict: `user_message`, `has_delegatee` (bool), `delegate_to` (str) |

## Example

Downstream **PayloadTransform** or **delegate_request** can map `data.delegate_to` to the assistant role id when `has_delegatee` is true.
