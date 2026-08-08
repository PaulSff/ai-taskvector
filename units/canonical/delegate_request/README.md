# Unit: delegate_request

The `delegate_request` unit normalizes LLM delegation actions to facilitate chat handoffs between different AI roles in the TaskVector framework.


## Purpose

This unit acts as a translation and validation layer. When an agent decides to hand off a conversation to another specialized role, it emits a `delegate_request`. This unit ensures the target role is valid and formats the request into a standardized structure that the GUI and system can process for a seamless transition.


## Interface

### Input Ports
- `action` (Any): An action dictionary. Expected format: `{"action": "delegate_request", "delegate_to": "role_id", "message": "..."}`
- `parser_output` (Any): Output from a ProcessAgent. It looks for a `delegate_request` key within this object.

### Output Ports
- `data` (Any): The normalized handoff data.
- `error` (str): Error message if resolution fails.


## Data Schema

The `data` output port emits a dictionary with the following structure:

```json
{
  "ok": boolean,          // True if the role was successfully resolved
  "delegate_to": string, // The resolved snake_case role_id
  "message": string | null, // The optional message to pass to the next agent
  "error": string         // Error details if ok is False
}
```


## Role Resolution Logic

The unit resolves the `delegate_to` field using the following priority:
1. **Role ID**: Matches the string directly against configured chat agent IDs (snake_case).
2. **Role Name**: If no ID match is found, it iterates through available roles to match the provided string against the human-readable `role_name`.

If neither matches or no chat agents are configured, the unit returns `ok: False` with a descriptive error.


## Example Usage

**Input Payload:**
```json
{
  "action": "delegate_request",
  "delegate_to": "researcher",
  "message": "Please analyze the latest market trends."
}
```

**Output Result:**
```json
{
  "ok": true,
  "delegate_to": "researcher_agent",
  "message": "Please analyze the latest market trends.",
  "error": ""
}
```
